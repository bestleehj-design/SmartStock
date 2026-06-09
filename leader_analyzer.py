# -*- coding: utf-8 -*-
"""
龙头票分析器
在主线题材板块中识别龙头票
评分维度：连板高度、量能强度、流通市值、资金强度
"""
import mysql.connector
from datetime import datetime, date
import json
import sys
from newstocklib import initMySQL
from config import DB_CONFIG


class LeaderAnalyzer:
    """龙头票分析器，在指定题材板块中识别龙头"""

    def __init__(self, theme_analyzer=None, mydb=None):
        if theme_analyzer is not None:
            # 复用ThemeAnalyzer的基础数据
            self.ta = theme_analyzer
            self.mydb = theme_analyzer.mydb
            self.own_db = False
        else:
            if mydb is None:
                self.mydb = initMySQL()
                self.own_db = True
            else:
                self.mydb = mydb
                self.own_db = False
            self.ta = None
        self.dbcursor = self.mydb.cursor()

    def _zt_rate(self, code):
        """获取涨停幅度"""
        if self.ta:
            return self.ta._zt_rate(code)
        # fallback: 查询market
        self.dbcursor.execute(
            "SELECT market FROM stock_basic_info_tbl WHERE code = %s", (code,)
        )
        row = self.dbcursor.fetchone()
        market = row[0] if row else ''
        if market in ('主板', '中小板'):
            return 0.0988
        return 0.199

    def _get_concept_stocks(self, concept_code):
        """获取概念板块的成分股列表"""
        if self.ta and concept_code in self.ta.ths_concept_to_stocks:
            return self.ta.ths_concept_to_stocks[concept_code]

        self.dbcursor.execute(
            "SELECT code_list FROM stock_basic_info_tbl WHERE code = %s AND type=2",
            (concept_code,)
        )
        row = self.dbcursor.fetchone()
        if not row or not row[0]:
            return []
        return [c.strip() for c in row[0].split(';') if c.strip()]

    def _get_concept_name(self, concept_code):
        """获取概念名称"""
        if self.ta and concept_code in self.ta.concept_name_map:
            return self.ta.concept_name_map[concept_code]
        self.dbcursor.execute(
            "SELECT name FROM stock_basic_info_tbl WHERE code = %s", (concept_code,)
        )
        row = self.dbcursor.fetchone()
        return row[0] if row else concept_code

    def _get_stock_name(self, code):
        """获取股票名称"""
        if self.ta and code in self.ta.stock_to_name:
            return self.ta.stock_to_name[code]
        self.dbcursor.execute(
            "SELECT name FROM stock_basic_info_tbl WHERE code = %s AND type=0", (code,)
        )
        row = self.dbcursor.fetchone()
        return row[0] if row else code

    def _get_consecutive_zt_count(self, code, trade_date):
        """
        获取股票从trade_date往前数的连续涨停天数
        返回: 连续涨停天数(>=1), 0表示当天未涨停
        """
        if self.ta is None:
            return 0

        prev_dates = self.ta._get_prev_trade_dates(trade_date, 15)
        if not prev_dates:
            return 0

        prev_date = prev_dates[-1]
        today_data = self.ta._get_daily_data(trade_date)
        prev_data = self.ta._get_daily_data(prev_date)

        if not self.ta._is_limit_up(code, trade_date, prev_date, today_data, prev_data):
            return 0

        # 已确认当天涨停, 往回数连板
        consecutive = 1
        for i in range(len(prev_dates) - 1, 0, -1):
            check_date = prev_dates[i]
            check_prev = prev_dates[i - 1]
            d1 = self.ta._get_daily_data(check_date)
            d0 = self.ta._get_daily_data(check_prev)
            if self.ta._is_limit_up(code, check_date, check_prev, d1, d0):
                consecutive += 1
            else:
                break

        return consecutive

    def _get_stock_daily_basic(self, codes, trade_date):
        """批量获取股票的基本面数据(市值、换手率)"""
        trade_date_str = trade_date.strftime('%Y-%m-%d') if hasattr(trade_date, 'strftime') else str(trade_date)
        if not codes:
            return {}

        placeholders = ','.join(['%s'] * len(codes))
        self.dbcursor.execute(f"""
            SELECT code, turnover_rate_f, circ_mv, total_mv
            FROM daily_basic_tbl
            WHERE tradedate = %s AND code IN ({placeholders})
        """, [trade_date_str] + list(codes))
        result = {}
        for row in self.dbcursor.fetchall():
            result[row[0]] = {
                'turnover_rate': float(row[1]) if row[1] else 0,
                'circ_mv': float(row[2]) if row[2] else 0,
                'total_mv': float(row[3]) if row[3] else 0,
            }
        return result

    def _get_stock_daily_data(self, codes, trade_date):
        """批量获取日线数据(涨跌幅、成交额)"""
        trade_date_str = trade_date.strftime('%Y-%m-%d') if hasattr(trade_date, 'strftime') else str(trade_date)
        if not codes:
            return {}

        placeholders = ','.join(['%s'] * len(codes))
        self.dbcursor.execute(f"""
            SELECT code, close, amount, volume, adj_factor
            FROM daily_info_tbl
            WHERE tradedate = %s AND code IN ({placeholders})
        """, [trade_date_str] + list(codes))
        result = {}
        for row in self.dbcursor.fetchall():
            result[row[0]] = {
                'close': float(row[1]) if row[1] else 0,
                'amount': float(row[2]) if row[2] else 0,
                'volume': float(row[3]) if row[3] else 0,
                'adj_factor': float(row[4]) if row[4] else 1.0,
            }
        return result

    def _get_prev_trade_date(self, trade_date):
        """获取前一个交易日"""
        if self.ta:
            prev_dates = self.ta._get_prev_trade_dates(trade_date, 1)
            return prev_dates[-1] if prev_dates else None
        return None

    def find_leaders_in_theme(self, theme_code, trade_date, top_n=5):
        """
        在指定题材中找龙头票
        返回: [(code, name, consecutive_zt, total_score, detail_dict), ...]
        """
        if isinstance(trade_date, str):
            trade_date = datetime.strptime(trade_date, '%Y-%m-%d').date()

        stocks = self._get_concept_stocks(theme_code)
        if not stocks:
            print(f"  概念 {theme_code} 无成分股")
            return []

        concept_name = self._get_concept_name(theme_code)
        prev_date = self._get_prev_trade_date(trade_date)
        if prev_date is None:
            print(f"  无法获取前一个交易日")
            return []

        # 1. 找到当日涨停的股票
        zt_stocks = []
        if self.ta:
            today_data = self.ta._get_daily_data(trade_date)
            prev_data = self.ta._get_daily_data(prev_date)
            for code in stocks:
                if code not in today_data or code not in prev_data:
                    continue
                if self.ta._is_limit_up(code, trade_date, prev_date, today_data, prev_data):
                    zt_stocks.append(code)
        else:
            # 无theme_analyzer时的fallback: 直接从DB计算
            today_data = self._get_stock_daily_data(stocks, trade_date)
            prev_data_inner = self._get_stock_daily_data(stocks, prev_date)
            for code in stocks:
                if code not in today_data or code not in prev_data_inner:
                    continue
                t = today_data[code]
                p = prev_data_inner[code]
                prev_close = p['close'] * p['adj_factor']
                if prev_close <= 0:
                    continue
                rise = (t['close'] * t['adj_factor'] - prev_close) / prev_close
                if rise >= self._zt_rate(code):
                    zt_stocks.append(code)

        if not zt_stocks:
            return []

        # 2. 获取连板数
        consecutive_map = {}
        for code in zt_stocks:
            cnt = self._get_consecutive_zt_count(code, trade_date)
            if cnt > 0:
                consecutive_map[code] = cnt

        if not consecutive_map:
            return []

        # 3. 批量获取基本面数据
        basic_data = self._get_stock_daily_basic(zt_stocks, trade_date)

        # 4. 批量获取资金流向
        trade_date_str = trade_date.strftime('%Y-%m-%d') if hasattr(trade_date, 'strftime') else str(trade_date)
        moneyflow_data = {}
        placeholders = ','.join(['%s'] * len(zt_stocks))
        self.dbcursor.execute(f"""
            SELECT code, net_lg_amount, net_elg_amount
            FROM daily_moneyflow_tbl
            WHERE tradedate = %s AND code IN ({placeholders})
        """, [trade_date_str] + zt_stocks)
        for row in self.dbcursor.fetchall():
            moneyflow_data[row[0]] = {
                'net_lg_amount': float(row[1]) if row[1] else 0,
                'net_elg_amount': float(row[2]) if row[2] else 0,
            }

        # 5. 对每个涨停股评分
        scored_stocks = []
        for code, consecutive in consecutive_map.items():
            name = self._get_stock_name(code)
            basic = basic_data.get(code, {})
            mf = moneyflow_data.get(code, {})

            # 连板高度评分 (0-40分)
            score_consecutive = min(consecutive * 10, 40)

            # 量能强度评分 (0-30分)
            turnover = basic.get('turnover_rate', 0)
            score_volume = min(turnover / 2, 30)  # 换手率60%给满分

            # 流通市值评分 (0-15分): 50-200亿最佳
            circ_mv = basic.get('circ_mv', 0)  # 万元
            circ_mv_yi = circ_mv / 10000  # 转换为亿元
            if 50 <= circ_mv_yi <= 200:
                score_cap = 15
            elif 20 <= circ_mv_yi < 50:
                score_cap = 12
            elif 200 < circ_mv_yi <= 500:
                score_cap = 10
            elif circ_mv_yi < 20:
                score_cap = 5
            elif circ_mv_yi > 500:
                score_cap = 3
            else:
                score_cap = 8

            # 资金强度评分 (0-15分): 大单+超大单净买入占成交额比
            net_big = mf.get('net_lg_amount', 0) + mf.get('net_elg_amount', 0)
            today_d = today_data.get(code, {}) if today_data else {}
            amount = today_d.get('amount', 0) if today_d else 0
            if amount > 0:
                mf_ratio = net_big / amount
                score_mf = max(0, min(mf_ratio * 500, 15))  # 2%给10分, 3%给15分
            else:
                score_mf = 0

            total = score_consecutive + score_volume + score_cap + score_mf

            # 涨停是基础条件, 总分会偏高, 归一化或直接保留
            scored_stocks.append({
                'code': code,
                'name': name,
                'consecutive_zt': consecutive,
                'total_score': round(total, 2),
                'score_consecutive': score_consecutive,
                'score_volume': round(score_volume, 2),
                'score_market_cap': score_cap,
                'score_moneyflow': round(score_mf, 2),
                'turnover_rate': round(turnover, 2) if turnover else 0,
                'circ_mv_yi': round(circ_mv_yi, 2),
                'net_big_amount': round(net_big, 2),
            })

        # 6. 按总分排序
        scored_stocks.sort(key=lambda x: x['total_score'], reverse=True)

        # 7. 打印结果
        print(f"\n  📊 {concept_name}({theme_code}) 龙头票候选:")
        print(f"  {'排名':<5}{'代码':<14}{'名称':<12}{'连板':<6}{'总分':<8}{'换手%':<8}{'市值(亿)':<10}{'大单净额':<12}")
        print(f"  {'-'*75}")
        for i, s in enumerate(scored_stocks[:top_n], 1):
            print(f"  {i:<5}{s['code']:<14}{s['name']:<12}{s['consecutive_zt']:<6}"
                  f"{s['total_score']:<8}{s['turnover_rate']:<8}{s['circ_mv_yi']:<10}{s['net_big_amount']:<12}")

        return scored_stocks

    def get_all_leaders(self, main_themes, trade_date, top_n=5):
        """
        获取所有主线题材的龙头票
        main_themes: ThemeAnalyzer.get_main_themes() 返回的结果列表
        返回: {theme_code: [(code, name, consecutive_zt, total_score, ...), ...]}
        """
        all_leaders = {}
        for theme in main_themes:
            theme_code = theme['theme_code']
            print(f"\n正在识别 [{theme['theme_name']}] 的龙头票...")
            leaders = self.find_leaders_in_theme(theme_code, trade_date, top_n)
            if leaders:
                all_leaders[theme_code] = [
                    (l['code'], l['name']) for l in leaders[:top_n]
                ]
        return all_leaders

    def cleanup(self):
        """清理资源"""
        try:
            self.dbcursor.close()
        except:
            pass
        if self.own_db:
            try:
                self.mydb.close()
            except:
                pass


def main():
    """独立运行: 分析指定题材或所有主线题材的龙头票"""
    from theme_analyzer import ThemeAnalyzer

    if len(sys.argv) > 1:
        # 指定日期和可选题材代码
        trade_date = sys.argv[1]
    else:
        db = initMySQL()
        cursor = db.cursor()
        cursor.execute('SELECT MAX(tradedate) FROM daily_info_tbl')
        trade_date = cursor.fetchone()[0]
        cursor.close()
        db.close()

    print(f"\n目标交易日: {trade_date}")

    # 先运行主线题材分析
    ta = ThemeAnalyzer()
    try:
        results = ta.analyze_daily_themes(trade_date)
        main_themes = ta.get_main_themes(results, top_n=3, min_score=20)

        if not main_themes:
            print("\n未识别到主线题材, 退出")
            return

        print(f"\n{'='*80}")
        print(f"主线题材龙头票分析")
        print(f"{'='*80}")

        # 对每个主线题材找龙头
        la = LeaderAnalyzer(theme_analyzer=ta)
        all_leaders = la.get_all_leaders(main_themes, trade_date)

        # 保存带龙头信息的结果
        ta.save_to_db(trade_date, results, all_leaders)

        print(f"\n{'='*80}")
        print(f"总结: 主线题材及龙头票")
        print(f"{'='*80}")
        for i, theme in enumerate(main_themes, 1):
            leaders = all_leaders.get(theme['theme_code'], [])
            leader_str = ', '.join([f"{name}({code})" for code, name in leaders[:3]]) if leaders else '未识别'
            print(f"\n  {i}. {theme['theme_name']} (总分: {theme['total_score']})")
            print(f"     涨停: {theme['zt_count']}/{theme['zt_total']} "
                  f"高标:{theme['high_board_count']} 首板:{theme['first_board_count']}")
            print(f"     龙头: {leader_str}")

        la.cleanup()
    finally:
        ta.cleanup()


if __name__ == '__main__':
    main()
