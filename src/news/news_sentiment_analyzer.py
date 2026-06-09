# -*- coding: utf-8 -*-
"""
持仓新闻舆情分析器
使用 akshare 抓取东方财富个股新闻，通过关键词匹配进行情感分析（利好/利空）

数据源: akshare stock_individual_news_em (封装东方财富 EM 个股新闻接口)
情感分析: 关键词匹配法，权重累加制

用法:
  python news_sentiment_analyzer.py                  # 分析最新交易日的持仓新闻
"""
import sys
import os
import json
import datetime
import traceback

# Ensure src/ directory is in sys.path for package imports
import sys, os
_SRC_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _SRC_DIR not in sys.path:
    sys.path.insert(0, _SRC_DIR)

from data.newstocklib import initMySQL

# ============================================================
# 关键词库 - 带权重
# ============================================================

# 负面词库: 权重 -1 到 -3
NEGATIVE_KEYWORDS = {
    -3: ['跌停', '违规', '立案', '调查', '监管', '处罚', '问询函',
         '业绩变脸', '退市风险', '质押爆仓', '债务违约', '商誉减值', '停产', 'ST'],
    -2: ['利空', '减持', '亏损', '暴跌', '诉讼', '爆雷', '被处罚',
         '资金占用', '大股东占款', '信息披露违规', '财务造假', '终止重组',
         '资产减值', '被ST', '*ST', '审计非标', '担保风险'],
    -1: ['预亏', '下滑', '下降', '预降', '退市', '暴雷', '停牌', '限售解禁',
         '股东减持', '股权冻结'],
}

# 正面词库: 权重 +1 到 +2
POSITIVE_KEYWORDS = {
    +2: ['涨停', '利好', '增持', '回购', '业绩预增', '超预期', '中标', '重组成功', '签订合同'],
    +1: ['增长', '突破', '新产品', '获批', '分红', '政策支持', '产能释放', '订单增长',
         '业绩大增', '扭亏', '预盈'],
}


class NewsSentimentAnalyzer:
    """持仓新闻舆情分析器"""

    def __init__(self):
        self.db = initMySQL()
        self.cursor = self.db.cursor()

    # ----------------------------------------------------------
    # 获取追踪中的持仓股票
    # ----------------------------------------------------------

    def get_tracking_stocks(self):
        """从 selected_stocks 表读取 status='tracking' 的持仓"""
        sql = """
            SELECT code, name FROM selected_stocks
            WHERE status = 'tracking'
            ORDER BY code
        """
        self.cursor.execute(sql)
        rows = self.cursor.fetchall()
        stocks = [(row[0], row[1]) for row in rows]
        print(f"持仓股票数: {len(stocks)}")
        for code, name in stocks:
            print(f"  {code} {name}")
        return stocks

    # ----------------------------------------------------------
    # 格式转换: 纯数字 -> 东方财富格式
    # ----------------------------------------------------------

    @staticmethod
    def _to_em_code(code):
        """将代码转换为东方财富EM格式 (如 600519 -> 1.600519)"""
        code = code.strip().replace('.SZ', '').replace('.SH', '').replace('.BJ', '')
        if code.startswith(('6', '9')):
            return f'1.{code}'
        else:
            return f'0.{code}'

    @staticmethod
    def _clean_code(code):
        """清理代码，去掉后缀"""
        return code.strip().replace('.SZ', '').replace('.SH', '').replace('.BJ', '')

    # ----------------------------------------------------------
    # 抓取新闻
    # ----------------------------------------------------------

    def fetch_news_for_stock(self, stock_code):
        """
        使用 akshare 抓取个股新闻
        返回: list[dict], 每条包含 title, date, source
        """
        try:
            import akshare as ak
        except ImportError:
            print("  [ERROR] akshare 未安装，请执行: pip install akshare")
            return []

        clean_code = self._clean_code(stock_code)
        try:
            df = ak.stock_news_em(symbol=clean_code)
        except Exception as e:
            print(f"  [ERROR] akshare 接口调用失败 (symbol={clean_code}): {e}")
            return []

        if df is None or len(df) == 0:
            return []

        news_list = []
        for _, row in df.iterrows():
            title = str(row.get('新闻标题', '') or row.get('新闻内容', '') or row.get('title', '') or '').strip()
            pub_date = str(row.get('发布时间', '') or row.get('datetime', '') or row.get('date', '') or '').strip()
            source = str(row.get('文章来源', '') or row.get('source', '') or '东方财富').strip()

            if not title:
                continue

            news_list.append({
                'title': title,
                'date': pub_date,
                'source': source,
            })

        # 取最近 20 条
        return news_list[:20]

    # ----------------------------------------------------------
    # 情感分析 - 关键词匹配
    # ----------------------------------------------------------

    def analyze_sentiment(self, title):
        """
        对新闻标题进行关键词匹配情感分析
        总分 = 所有匹配关键词权重之和
        标签: <0=negative, >0=positive, 0=neutral

        返回: (sentiment_score, sentiment_label, matched_keywords)
        """
        title_lower = title.lower() if title else ''
        total_score = 0
        matched = []

        # 匹配负面词
        for weight, keywords in NEGATIVE_KEYWORDS.items():
            for kw in keywords:
                if kw.lower() in title_lower:
                    total_score += weight
                    matched.append({'keyword': kw, 'weight': weight})

        # 匹配正面词
        for weight, keywords in POSITIVE_KEYWORDS.items():
            for kw in keywords:
                if kw.lower() in title_lower:
                    total_score += weight
                    matched.append({'keyword': kw, 'weight': weight})

        # 判定标签
        if total_score < 0:
            label = 'negative'
        elif total_score > 0:
            label = 'positive'
        else:
            label = 'neutral'

        return total_score, label, matched

    # ----------------------------------------------------------
    # 保存到数据库
    # ----------------------------------------------------------

    def save_news_to_db(self, stock_code, stock_name, news_date, news_list):
        """
        INSERT 新闻到 stock_news_daily_tbl
        去重逻辑: 同股票+同日期+同标题 跳过

        返回: 本次保存的数量
        """
        insert_sql = """
            INSERT INTO stock_news_daily_tbl
                (stock_code, stock_name, news_date, news_title, news_source,
                 sentiment_score, sentiment_label, matched_keywords)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """
        saved_count = 0

        for news in news_list:
            title = news.get('title', '')
            if not title:
                continue

            # 检查去重
            self.cursor.execute("""
                SELECT id FROM stock_news_daily_tbl
                WHERE stock_code = %s AND news_date = %s AND news_title = %s
                LIMIT 1
            """, (stock_code, news_date, title))
            if self.cursor.fetchone():
                continue

            source = news.get('source', '东方财富')
            sentiment_score, sentiment_label, matched = self.analyze_sentiment(title)
            matched_json = json.dumps(matched, ensure_ascii=False) if matched else None

            try:
                self.cursor.execute(insert_sql, (
                    stock_code, stock_name, news_date, title, source,
                    sentiment_score, sentiment_label, matched_json
                ))
                if self.cursor.rowcount > 0:
                    saved_count += 1
            except Exception as e:
                print(f"    保存新闻失败 [{title[:30]}]: {e}")

        self.db.commit()
        if saved_count > 0:
            print(f"  [{stock_code}] 保存 {saved_count} 条新闻")
            neg_count = sum(1 for n in news_list
                           if self.analyze_sentiment(n.get('title', ''))[1] == 'negative')
            if neg_count > 0:
                print(f"    其中负面 {neg_count} 条")
        return saved_count

    # ----------------------------------------------------------
    # 主流程: 针对某个日期运行
    # ----------------------------------------------------------

    def run_for_date(self, date_obj):
        """
        主流程: 遍历持仓 -> 抓取新闻 -> 分析情感 -> 存入数据库

        参数:
          date_obj: datetime.date 对象
        """
        date_str = date_obj.strftime('%Y-%m-%d')
        print(f"\n{'#'*60}")
        print(f"# 持仓新闻舆情分析")
        print(f"# 目标日期: {date_str}")
        print(f"# 分析时间: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"{'#'*60}\n")

        # 1. 获取持仓
        stocks = self.get_tracking_stocks()
        if not stocks:
            print("当前无追踪中的持仓股票")
            return

        total_news = 0
        total_negative = 0

        # 2. 逐只抓取分析
        for code, name in stocks:
            print(f"\n--- {code} {name} ---")
            try:
                news_list = self.fetch_news_for_stock(code)
                if not news_list:
                    print(f"  [{code}] 未获取到新闻")
                    continue

                saved = self.save_news_to_db(code, name, date_obj, news_list)
                total_news += saved

                # 统计负面
                for n in news_list:
                    _, label, _ = self.analyze_sentiment(n.get('title', ''))
                    if label == 'negative':
                        total_negative += 1

            except Exception as e:
                print(f"  [ERROR] {code}: {e}")
                traceback.print_exc()

        # 3. 输出统计
        print(f"\n{'='*60}")
        print(f"[{date_str}] 分析完成")
        print(f"  持仓数: {len(stocks)}")
        print(f"  新保存新闻: {total_news} 条")
        print(f"  负面新闻: {total_negative} 条")
        print(f"{'='*60}")

    # ----------------------------------------------------------
    # 查询功能 - 供 Web API 使用
    # ----------------------------------------------------------

    def get_news_for_stock(self, stock_code, days=7):
        """获取指定股票近N天新闻"""
        self.cursor.execute("""
            SELECT id, stock_name, news_date, news_title, news_source,
                   sentiment_score, sentiment_label, matched_keywords, created_at
            FROM stock_news_daily_tbl
            WHERE stock_code = %s
              AND news_date >= DATE_SUB(CURDATE(), INTERVAL %s DAY)
            ORDER BY news_date DESC, id DESC
        """, (stock_code, days))
        rows = self.cursor.fetchall()

        news_list = []
        for r in rows:
            matched = json.loads(r[7]) if r[7] else []
            news_list.append({
                'id': r[0],
                'stock_name': r[1],
                'news_date': str(r[2]),
                'news_title': r[3],
                'news_source': r[4],
                'sentiment_score': r[5],
                'sentiment_label': r[6],
                'matched_keywords': matched,
                'created_at': str(r[8]),
            })
        return news_list

    def get_holdings_news_summary(self):
        """获取所有持仓最新负面新闻摘要"""
        self.cursor.execute("""
            SELECT n.stock_code, n.stock_name, n.news_date, n.news_title,
                   n.sentiment_score, n.sentiment_label, n.matched_keywords
            FROM stock_news_daily_tbl n
            INNER JOIN (
                SELECT stock_code, MAX(id) as max_id
                FROM stock_news_daily_tbl
                WHERE news_date >= DATE_SUB(CURDATE(), INTERVAL 7 DAY)
                GROUP BY stock_code
            ) latest ON n.stock_code = latest.stock_code AND n.id = latest.max_id
            INNER JOIN selected_stocks s ON s.code = n.stock_code AND s.status = 'tracking'
            ORDER BY n.sentiment_score ASC
        """)
        rows = self.cursor.fetchall()

        summary = []
        for r in rows:
            summary.append({
                'stock_code': r[0],
                'stock_name': r[1],
                'news_date': str(r[2]),
                'news_title': r[3],
                'sentiment_score': r[4],
                'sentiment_label': r[5],
                'matched_keywords': json.loads(r[6]) if r[6] else [],
            })
        return summary

    # ----------------------------------------------------------
    # 清理
    # ----------------------------------------------------------

    def cleanup(self):
        try:
            self.cursor.close()
        except:
            pass
        try:
            self.db.close()
        except:
            pass


# ============================================================
# 新闻利好分类器
# ============================================================

# 利好类别定义: 关键词 + 权重
BENEFIT_CATEGORIES = {
    '政策驱动': {
        'keywords': ['国务院', '发改委', '工信部', '政策', '规划', '大基金',
                     '产业政策', '十四五', '国家级', '战略', '重点支持'],
        'weight': 5,
        'desc': '国家政策/战略层面支持',
    },
    '国产替代': {
        'keywords': ['国产化', '自主可控', '进口替代', '信创', '去美化',
                     '国产替代', '自主突破', '打破垄断', '填补空白'],
        'weight': 4,
        'desc': '国产替代/自主可控机会',
    },
    '订单业绩': {
        'keywords': ['中标', '订单', '合同', '产能释放', '业绩预增', '超预期',
                     '营收增长', '净利润增长', '扭亏为盈', '产销两旺'],
        'weight': 4,
        'desc': '订单/业绩增长确认',
    },
    '业界改善': {
        'keywords': ['行业回暖', '供需改善', '涨价', '景气度', '去库存',
                     '需求复苏', '供不应求', '价格上调', '景气周期'],
        'weight': 3,
        'desc': '行业基本面改善/景气度提升',
    },
    '技术突破': {
        'keywords': ['新品发布', '技术突破', '量产', '通过认证', '打破纪录',
                     '首发', '领先', '专利', '创新'],
        'weight': 4,
        'desc': '技术/产品突破',
    },
    '资本运作': {
        'keywords': ['回购', '增持', '分红', '股权激励', '员工持股',
                     '高分红', '高股息', '回购计划'],
        'weight': 2,
        'desc': '公司回购/分红/激励',
    },
    '并购重组': {
        'keywords': ['收购', '重组', '资产注入', '借壳', '合并',
                     '重大资产', '整合', '入股'],
        'weight': 3,
        'desc': '并购整合/重组',
    },
    '国企改革': {
        'keywords': ['混改', '央企改革', '国资', '国企改革', '双百行动',
                     '国资入主', '央企'],
        'weight': 2,
        'desc': '国企改革/国资重组',
    },
}


class NewsCategorizer:
    """
    新闻利好分类器
    对新闻内容进行利好类别匹配（在已有情感分析之上叠加分类维度）
    """

    @staticmethod
    def categorize(text):
        """
        对一条新闻文本进行分类
        返回: {category: (score, weight), ...}
        """
        if not text:
            return {}

        text_lower = text.lower()
        results = {}

        for cat, rules in BENEFIT_CATEGORIES.items():
            matched = [kw for kw in rules['keywords'] if kw.lower() in text_lower]
            if matched:
                # score = 匹配数 / 关键词总数 × weight
                hit_rate = len(matched) / len(rules['keywords'])
                cat_score = round(hit_rate * rules['weight'], 2)
                results[cat] = {
                    'score': cat_score,
                    'weight': rules['weight'],
                    'matched': matched,
                    'desc': rules['desc'],
                }

        if not results:
            return {'未分类': {'score': 0, 'weight': 0, 'matched': [], 'desc': '未匹配到利好类别'}}

        return results

    @staticmethod
    def summarize_news(news_list):
        """
        对多条新闻进行汇总分类
        返回: (
            top_category,           # 主要利好类别
            category_scores,        # 各类别累计得分
            summary_text,           # 汇总描述
        )
        """
        cat_totals = {}
        cat_examples = {}

        for news in news_list:
            title = news.get('title', '')
            cats = NewsCategorizer.categorize(title)

            for cat_name, info in cats.items():
                if info['weight'] > 0:
                    if cat_name not in cat_totals:
                        cat_totals[cat_name] = 0
                        cat_examples[cat_name] = []
                    cat_totals[cat_name] += info['score']
                    if len(cat_examples[cat_name]) < 3:
                        cat_examples[cat_name].append(title[:60])

        if not cat_totals:
            return 'general', {}, '未识别到明确的利好类别'

        # 排名最高类别
        top = max(cat_totals, key=cat_totals.get)
        top_desc = BENEFIT_CATEGORIES.get(top, {}).get('desc', '')

        return top, cat_totals, f"主要利好: {top}({top_desc})"

    @staticmethod
    def get_benefit_bonus(category, cat_scores):
        """
        根据利好类别和得分，计算策略2加权分 (0-15)
        """
        if category == 'general':
            return 0

        total = sum(cat_scores.values())
        # 累计得分映射到0-15分
        bonus = min(total * 2, 15)
        return round(bonus, 1)


# ============================================================
# 入口 - 直接运行时分析最新日期
# ============================================================

if __name__ == '__main__':
    analyzer = NewsSentimentAnalyzer()
    try:
        # 获取最新交易日
        cursor = analyzer.db.cursor()
        cursor.execute('SELECT MAX(tradedate) FROM daily_info_tbl')
        target_date = cursor.fetchone()[0]
        cursor.close()

        if isinstance(target_date, datetime.date):
            pass
        elif isinstance(target_date, datetime.datetime):
            target_date = target_date.date()
        else:
            target_date = datetime.date.today()

        analyzer.run_for_date(target_date)
    except Exception as e:
        print(f"\n!!! 分析出错: {e}")
        traceback.print_exc()
    finally:
        analyzer.cleanup()
