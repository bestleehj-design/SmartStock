# -*- coding: utf-8 -*-
"""
持仓股票消息面监控系统
每天自动抓取用户持仓股票的消息/新闻,进行情感分析,当发现负面消息时给予提示。

数据源: 东方财富个股资讯 (免费, 无需API Key)
情感分析: 关键词匹配法 (轻量级, 无需额外NLP依赖)
"""

import datetime
import time
import json
import re
import traceback
import requests
from lxml import etree

from newstocklib import initMySQL

# ============================================================
# 关键词库
# ============================================================

NEGATIVE_KEYWORDS = [
    '利空', '跌停', '亏损', '减持', '违规', '处罚', '暴雷', '业绩下滑', '业绩预亏',
    '退市风险', '立案调查', '诉讼', '债务违约', '商誉减值', '质押爆仓',
    '监管问询', '风险提示', '停牌', '终止重组', '资产减值', '股东减持',
    '被ST', '*ST', '财务造假', '信披违规', '大股东占用', '担保风险',
    '审计非标', '股权冻结', '限售解禁', '大幅预降', 'ST',
]

POSITIVE_KEYWORDS = [
    '利好', '涨停', '预增', '中标', '获批', '签订合同', '业绩大增', '回购',
    '增持', '分红', '重组成功', '政策支持', '产能释放', '订单增长',
]

# ============================================================
# NewsMonitor 核心类
# ============================================================


class NewsMonitor:
    """持仓股票消息面监控"""

    def __init__(self):
        self.mydb = initMySQL()
        self.dbcursor = self.mydb.cursor()
        self.alert_news = []          # 需要预警的新闻列表
        self.neutral_stocks = []      # 无负面消息的股票名称
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
                          'AppleWebKit/537.36 (KHTML, like Gecko) '
                          'Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'application/json, text/plain, */*',
            'Accept-Language': 'zh-CN,zh;q=0.9',
            'Referer': 'https://www.eastmoney.com/',
        })

    # ----------------------------------------------------------
    # 1. 读取持仓
    # ----------------------------------------------------------

    def get_holdings(self):
        """从 selected_stocks 表读取 status='tracking' 的持仓股票"""
        sql = """
            SELECT code, name FROM selected_stocks
            WHERE status = 'tracking'
            ORDER BY code
        """
        self.dbcursor.execute(sql)
        rows = self.dbcursor.fetchall()
        holdings = [(row[0], row[1]) for row in rows]
        print(f"持仓股票数: {len(holdings)}")
        for code, name in holdings:
            print(f"  {code} {name}")
        return holdings

    # ----------------------------------------------------------
    # 2. 代码格式转换
    # ----------------------------------------------------------

    @staticmethod
    def _to_eastmoney_code(code):
        """将纯数字代码转换为东方财富格式 (market.code)"""
        code = code.strip().replace('.SZ', '').replace('.SH', '').replace('.BJ', '')
        if code.startswith(('6', '9')):
            return f'1.{code}'   # 上海
        else:
            return f'0.{code}'   # 深圳 / 北京

    @staticmethod
    def _to_market_code(code):
        """将纯数字代码转换为 market.code 后缀 (如 SZ/SH/BJ)"""
        code = code.strip().replace('.SZ', '').replace('.SH', '').replace('.BJ', '')
        if code.startswith(('6', '9')):
            return f'{code}.SH'
        elif code.startswith(('8', '4')):
            return f'{code}.BJ'
        else:
            return f'{code}.SZ'

    # ----------------------------------------------------------
    # 3. 抓取东方财富新闻
    # ----------------------------------------------------------

    def fetch_stock_news(self, code):
        """
        从东方财富抓取单只股票近3天新闻。
        优先使用 方案A (公告/新闻API), 失败则降级到 方案B (搜索API)。

        返回: list[dict], 每个 dict 包含:
            title, summary, url, date, source
        """
        name = None
        # 获取股票名称
        sql = "SELECT name FROM selected_stocks WHERE code = %s LIMIT 1"
        self.dbcursor.execute(sql, (code,))
        row = self.dbcursor.fetchone()
        if row:
            name = row[0]

        em_code = self._to_eastmoney_code(code)
        today = datetime.date.today()
        three_days_ago = today - datetime.timedelta(days=3)
        start_date = three_days_ago.strftime('%Y-%m-%d')
        end_date = today.strftime('%Y-%m-%d')

        # --- 方案A: 个股公告/新闻API ---
        news_list = self._fetch_via_api_a(em_code, start_date, end_date)
        if news_list:
            print(f"  [{code}] 方案A 成功, 获取 {len(news_list)} 条")
            return news_list

        # --- 方案B: 搜索API ---
        keyword = name if name else code
        news_list = self._fetch_via_api_b(keyword, start_date, end_date)
        if news_list:
            print(f"  [{code}] 方案B 成功, 获取 {len(news_list)} 条")
            return news_list

        print(f"  [{code}] 所有方案均未获取到新闻")
        return []

    def _fetch_via_api_a(self, em_code, start_date, end_date):
        """方案A: 东方财富个股公告/新闻API"""
        url = 'https://np-anotice-stock.eastmoney.com/api/security/ann'
        params = {
            'sr': -1,
            'page_size': 30,
            'page_index': 1,
            'ann_type': 'A',
            'client_source': 'web',
            'stock_list': em_code,
            'f_node': 0,
            's_node': 0,
        }
        try:
            resp = self.session.get(url, params=params, timeout=15)
            resp.encoding = 'utf-8'
            data = resp.json()
        except Exception as e:
            print(f"    方案A 请求失败: {e}")
            return []

        list_data = None
        if isinstance(data, dict):
            if 'data' in data and isinstance(data['data'], dict):
                list_data = data['data'].get('list', [])
            elif 'Data' in data:
                list_data = data['Data']

        if not list_data:
            return []

        results = []
        for item in list_data:
            title = item.get('title', '') or item.get('art_title', '')
            summary = item.get('summary', '') or ''
            art_code = item.get('art_code', '')
            art_url = ''
            news_date_str = ''

            # 从 columns 中提取链接和日期
            columns = item.get('columns', [])
            if columns:
                for col in columns:
                    col_code = col.get('column_code', '')
                    content = col.get('content', '')
                    if col_code in ('NOTICE_DATE', 'DISPLAY_DATE', 'DECLARE_DATE'):
                        news_date_str = content
                    elif col_code == 'ART_URL':
                        art_url = content

            # 如果没有从 columns 提取到, 尝试直接字段
            if not news_date_str:
                news_date_str = item.get('notice_date', '') or item.get('display_date', '')
            if not art_url and art_code:
                art_url = f'https://np-anotice-stock.eastmoney.com/api/security/ann/detail?art_code={art_code}'

            # 日期过滤
            if not self._date_in_range(news_date_str, start_date, end_date):
                continue

            results.append({
                'title': title.strip(),
                'summary': summary.strip(),
                'url': art_url.strip(),
                'date': self._parse_date(news_date_str),
                'source': '东方财富',
            })

        return results

    def _fetch_via_api_b(self, keyword, start_date, end_date):
        """方案B: 东方财富CMS搜索结果API"""
        url = 'https://searchapi.eastmoney.com/bussiness/Web/GetCMSSearchResult'
        params = {
            'type': '8196',
            'pageindex': 1,
            'pagesize': 20,
            'keyword': keyword,
            'bt': start_date,
            'et': end_date,
            'name': 'zixun',
        }
        try:
            resp = self.session.get(url, params=params, timeout=15)
            resp.encoding = 'utf-8'
            data = resp.json()
        except Exception as e:
            print(f"    方案B 请求失败: {e}")
            return []

        articles = None
        if isinstance(data, dict):
            articles = data.get('Data', []) or data.get('data', [])

        if not articles:
            return []

        results = []
        for art in articles:
            title = art.get('Title', '') or art.get('title', '')
            summary = art.get('Content', '') or art.get('Summary', '') or art.get('summary', '')
            art_url = art.get('Url', '') or art.get('url', '')
            art_date = art.get('Date', '') or art.get('ShowDate', '') or art.get('date', '')

            # 清理 HTML 标签
            summary = re.sub(r'<[^>]+>', '', summary) if summary else ''

            results.append({
                'title': title.strip(),
                'summary': summary.strip(),
                'url': art_url.strip(),
                'date': self._parse_date(art_date),
                'source': art.get('SourceName', '') or art.get('source', '') or '东方财富',
            })

        return results

    @staticmethod
    def _date_in_range(date_str, start_date, end_date):
        """检查日期字符串是否在给定范围内"""
        if not date_str:
            return True  # 无法判断日期时保留
        date_str = str(date_str).strip()[:10]
        try:
            dt = datetime.datetime.strptime(date_str, '%Y-%m-%d').date()
            return datetime.datetime.strptime(start_date, '%Y-%m-%d').date() <= dt <= datetime.datetime.strptime(end_date, '%Y-%m-%d').date()
        except ValueError:
            return True  # 解析失败时保留

    @staticmethod
    def _parse_date(date_str):
        """解析日期字符串为 datetime, 失败返回 None"""
        if not date_str:
            return None
        date_str = str(date_str).strip()[:19]
        for fmt in ('%Y-%m-%d %H:%M:%S', '%Y-%m-%dT%H:%M:%S', '%Y-%m-%d'):
            try:
                return datetime.datetime.strptime(date_str, fmt)
            except ValueError:
                continue
        return None

    # ----------------------------------------------------------
    # 4. 情感分析
    # ----------------------------------------------------------

    def analyze_sentiment(self, title, summary):
        """
        关键词匹配情感分析

        评分规则:
        - 标题匹配负面词: +30 分
        - 摘要/内容匹配负面词: 每个词 +10 分 (最多 +40)
        - 匹配正面词: 每个词 -10 分
        - 负面总分 >= 30 且 > 正面总分: 标记为 negative
        - 否则: neutral

        返回: (sentiment, negative_score, positive_score)
        """
        title_lower = title.lower() if title else ''
        summary_lower = summary.lower() if summary else ''
        combined = title_lower + ' ' + summary_lower

        negative_score = 0
        positive_score = 0

        for kw in NEGATIVE_KEYWORDS:
            kw_lower = kw.lower()
            if kw_lower in title_lower:
                negative_score += 30
                break  # 标题命中一次即可, 不再重复加分

        for kw in NEGATIVE_KEYWORDS:
            kw_lower = kw.lower()
            count = summary_lower.count(kw_lower)
            if count > 0:
                negative_score += min(count * 10, 20)  # 单个词在摘要最多加20

        # 限制摘要负面分上限
        if negative_score > 70:
            negative_score = 70

        for kw in POSITIVE_KEYWORDS:
            kw_lower = kw.lower()
            count = combined.count(kw_lower)
            if count > 0:
                positive_score += count * 10

        if negative_score >= 30 and negative_score > positive_score:
            sentiment = 'negative'
        else:
            sentiment = 'neutral'

        return sentiment, negative_score, positive_score

    # ----------------------------------------------------------
    # 5. 保存到数据库
    # ----------------------------------------------------------

    def save_news(self, code, name, records):
        """
        保存新闻到 news_monitor_tbl (INSERT IGNORE 去重)

        返回: 本次新保存的预警新闻列表
        """
        alert_list = []
        insert_sql = """
            INSERT IGNORE INTO news_monitor_tbl
                (code, name, news_title, news_summary, news_url, news_date,
                 source, negative_score, positive_score, sentiment, is_alert)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """
        saved_count = 0

        for rec in records:
            title = rec.get('title', '')
            summary = rec.get('summary', '')
            news_url = rec.get('url', '')
            news_date = rec.get('date')
            source = rec.get('source', '')
            if not news_date:
                news_date = datetime.datetime.now()

            sentiment, neg_score, pos_score = self.analyze_sentiment(title, summary)
            is_alert = 1 if sentiment == 'negative' else 0

            try:
                self.dbcursor.execute(insert_sql, (
                    code, name, title, summary, news_url, news_date,
                    source, neg_score, pos_score, sentiment, is_alert
                ))
                if self.dbcursor.rowcount > 0:
                    saved_count += 1
                    if is_alert:
                        alert_list.append({
                            'code': code,
                            'name': name,
                            'title': title,
                            'summary': summary,
                            'url': news_url,
                            'date': news_date,
                            'source': source,
                            'negative_score': neg_score,
                            'positive_score': pos_score,
                        })
            except Exception as e:
                print(f"    保存新闻失败: {e}")

        self.mydb.commit()
        if saved_count > 0:
            print(f"  [{code}] 新保存 {saved_count} 条新闻, 其中预警 {len(alert_list)} 条")
        return alert_list

    # ----------------------------------------------------------
    # 6. 生成预警摘要
    # ----------------------------------------------------------

    def generate_alert(self, run_time):
        """生成本次预警摘要并输出到控制台"""
        print()
        print("=" * 52)
        print(f"=== 持仓消息面监控报告 {run_time} ===")

        has_alert = len(self.alert_news) > 0

        if not has_alert:
            print("未发现负面消息，所有持仓正常。")
            print("=" * 52)
            return

        print(f"发现负面消息: {len(self.alert_news)}")
        print()

        for i, alert in enumerate(self.alert_news, 1):
            market_code = self._to_market_code(alert['code'])
            print(f"[预警] {alert['name']} ({market_code}) - 负面")
            print(f"  - 标题: {alert['title']}")
            print(f"  - 负面分: {alert['negative_score']}, 正面分: {alert['positive_score']}")
            print(f"  - 链接: {alert['url']}")
            print()

        if self.neutral_stocks:
            names = ', '.join(self.neutral_stocks)
            print(f"其他持仓无负面消息: {names}")

        print("=" * 52)

    # ----------------------------------------------------------
    # 7. 主流程
    # ----------------------------------------------------------

    def run(self):
        """主流程: 读取持仓 -> 逐只抓取新闻 -> 分析 -> 保存 -> 输出预警"""
        run_time = datetime.datetime.now().strftime('%Y-%m-%d %H:%M')
        print(f"\n{'#' * 52}")
        print(f"# 持仓消息面监控")
        print(f"# 运行时间: {run_time}")
        print(f"{'#' * 52}\n")

        # 1. 读取持仓
        holdings = self.get_holdings()
        if not holdings:
            print("当前无持仓股票 (selected_stocks 中 status='tracking' 为空)")
            return

        # 2. 逐只抓取新闻并分析
        for code, name in holdings:
            print(f"\n--- {code} {name} ---")
            try:
                news_records = self.fetch_stock_news(code)
                if news_records:
                    alerts = self.save_news(code, name, news_records)
                    self.alert_news.extend(alerts)
                    if not alerts:
                        self.neutral_stocks.append(name)
                else:
                    self.neutral_stocks.append(name)
            except Exception as e:
                print(f"  [{code}] 处理出错: {e}")
                traceback.print_exc()

            # 请求间隔, 避免被封
            time.sleep(1)

        # 3. 生成预警摘要
        self.generate_alert(run_time)

    # ----------------------------------------------------------
    # 8. 清理
    # ----------------------------------------------------------

    def close(self):
        """关闭数据库连接"""
        try:
            self.dbcursor.close()
            self.mydb.close()
        except Exception:
            pass


# ============================================================
# 入口
# ============================================================

if __name__ == '__main__':
    monitor = NewsMonitor()
    try:
        monitor.run()
    finally:
        monitor.close()
