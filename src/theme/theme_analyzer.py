# -*- coding: utf-8 -*-

# Ensure src/ directory is in sys.path for package imports
import sys, os
_SRC_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _SRC_DIR not in sys.path:
    sys.path.insert(0, _SRC_DIR)
"""
主线题材分析器
通过多维度评分识别当前市场的主线题材板块
评分维度：涨停占比、涨停梯队、持续性、资金流入、板块涨幅、成交额占比
"""
import mysql.connector
from datetime import datetime, date, timedelta
import json
import sys
from data.newstocklib import initMySQL
from data.config import DB_CONFIG


class ThemeAnalyzer:
    """主线题材分析器，对同花顺概念板块进行六维评分"""

    def __init__(self, mydb=None):
        if mydb is None:
            self.mydb = initMySQL()
            self.own_db = True
        else:
            self.mydb = mydb
            self.own_db = False
        self.dbcursor = self.mydb.cursor()

        self._load_exchange_days()
        self._load_concept_mappings()
        self._load_stock_markets()

        # 缓存每日数据，避免重复查询
        self._daily_data_cache = {}
        self._prev_daily_data_cache = {}

    def _load_exchange_days(self):
        """加载交易日历"""
        self.dbcursor.execute(
            'SELECT trade_date FROM trade_date_info_tbl ORDER BY trade_date ASC'
        )
        rows = self.dbcursor.fetchall()
        self.exchange_days = []
        for r in rows:
            d = r[0]
            if isinstance(d, date):
                self.exchange_days.append(d)
            elif isinstance(d, datetime):
                self.exchange_days.append(d.date())
            else:
                self.exchange_days.append(d)
        print(f"  加载交易日历: {len(self.exchange_days)} 个交易日")

    def _load_concept_mappings(self):
        """加载同花顺概念板块及其成分股映射"""
        self.ths_concept_to_stocks = {}   # concept_code -> [stock_codes]
        self.concept_name_map = {}         # concept_code -> name
        self.stock_to_name = {}            # stock_code -> name

        # 1. 加载概念板块基本信息 (type=2 是同花顺概念)
        self.dbcursor.execute(
            "SELECT code, name, code_list FROM stock_basic_info_tbl WHERE type=2"
        )
        for row in self.dbcursor.fetchall():
            concept_code, concept_name, code_list_str = row
            self.concept_name_map[concept_code] = concept_name

            if not code_list_str:
                continue
            codes = [c.strip() for c in code_list_str.split(';') if c.strip()]
            self.ths_concept_to_stocks[concept_code] = codes

        # 2. 加载股票名称 (type=0 是普通股票)
        self.dbcursor.execute(
            "SELECT code, name FROM stock_basic_info_tbl WHERE type=0"
        )
        for row in self.dbcursor.fetchall():
            self.stock_to_name[row[0]] = row[1]

        print(f"  加载概念板块: {len(self.ths_concept_to_stocks)} 个")

    def _load_stock_markets(self):
        """加载股票所属市场板块，用于判断涨停幅度"""
        self.stock_to_market = {}
        self.dbcursor.execute(
            "SELECT code, market FROM stock_basic_info_tbl WHERE type=0"
        )
        for row in self.dbcursor.fetchall():
            self.stock_to_market[row[0]] = row[1] or ''

    def _zt_rate(self, code):
        """获取股票的涨停幅度"""
        market = self.stock_to_market.get(code, '')
        if market in ('主板', '中小板'):
            return 0.0988
        return 0.199

    def _get_prev_trade_dates(self, trade_date, n_days):
        """获取指定日期之前的n个交易日日期"""
        if isinstance(trade_date, str):
            trade_date = datetime.strptime(trade_date, '%Y-%m-%d').date()
        if isinstance(trade_date, datetime):
            trade_date = trade_date.date()

        # 找到trade_date在exchange_days中的位置
        idx = None
        for i, d in enumerate(self.exchange_days):
            if d == trade_date:
                idx = i
                break
            elif d > trade_date:
                idx = i - 1 if i > 0 else None
                break

        if idx is None:
            return []

        start = max(0, idx - n_days)
        return [self.exchange_days[i] for i in range(start, idx)]

    def _get_daily_data(self, trade_date):
        """获取指定交易日的所有股票日线数据，返回 {code: {close, amount, volume, adj_factor}}"""
        if isinstance(trade_date, (datetime, date)):
            trade_date_str = trade_date.strftime('%Y-%m-%d') if hasattr(trade_date, 'strftime') else str(trade_date)
        else:
            trade_date_str = str(trade_date)

        if trade_date_str in self._daily_data_cache:
            return self._daily_data_cache[trade_date_str]

        self.dbcursor.execute("""
            SELECT code, close, amount, volume, adj_factor
            FROM daily_info_tbl
            WHERE tradedate = %s
        """, (trade_date_str,))
        rows = self.dbcursor.fetchall()

        result = {}
        for row in rows:
            code, close, amount, volume, adj_factor = row
            result[code] = {
                'close': float(close) if close else 0,
                'amount': float(amount) if amount else 0,
                'volume': float(volume) if volume else 0,
                'adj_factor': float(adj_factor) if adj_factor else 1.0,
            }

        self._daily_data_cache[trade_date_str] = result
        return result

    def _is_limit_up(self, code, trade_date, prev_date, today_data=None, prev_data=None):
        """判断股票在trade_date是否涨停"""
        if today_data is None:
            today_data = self._get_daily_data(trade_date)
        if prev_data is None:
            prev_data = self._get_daily_data(prev_date)

        if code not in today_data or code not in prev_data:
            return False

        today = today_data[code]
        prev = prev_data[code]

        prev_close_adj = prev['close'] * prev['adj_factor']
        if prev_close_adj <= 0:
            return False
        curr_close_adj = today['close'] * today['adj_factor']

        rise = (curr_close_adj - prev_close_adj) / prev_close_adj
        return rise >= self._zt_rate(code)

    def _get_concept_zt_list(self, concept_codes, trade_date):
        """
        获取概念板块内所有涨停股及其连板信息
        返回: {
            concept_code: {
                'zt_codes': [code, ...],
                'consecutive_zt': {code: int},  # 连板数
                'zt_count': int,
            }
        }
        """
        prev_dates = self._get_prev_trade_dates(trade_date, 10)
        if not prev_dates:
            return {}

        prev_date = prev_dates[-1]  # 最近的前一个交易日

        today_data = self._get_daily_data(trade_date)
        prev_data = self._get_daily_data(prev_date)

        # 预加载历史数据用于连板检测
        hist_data_map = {}
        for pd_idx, pd_val in enumerate(prev_dates):
            hist_data_map[pd_val] = self._get_daily_data(pd_val)

        result = {}
        for concept_code in concept_codes:
            stocks = self.ths_concept_to_stocks.get(concept_code, [])
            zt_codes = []
            consecutive_map = {}

            for code in stocks:
                if self._is_limit_up(code, trade_date, prev_date, today_data, prev_data):
                    zt_codes.append(code)

                    # 计算连板数
                    consecutive = 1
                    for i in range(len(prev_dates) - 1, -1, -1):
                        check_date = prev_dates[i]
                        # 需要检查d[i]相对于d[i-1]是否涨停
                        if i == 0:
                            # 没有更早的日期了
                            break
                        check_prev = prev_dates[i - 1]
                        d1 = hist_data_map.get(check_date, {})
                        d0 = hist_data_map.get(check_prev, {})
                        if self._is_limit_up(code, check_date, check_prev, d1, d0):
                            consecutive += 1
                        else:
                            break
                    consecutive_map[code] = consecutive

            result[concept_code] = {
                'zt_codes': zt_codes,
                'consecutive_zt': consecutive_map,
                'zt_count': len(zt_codes),
            }

        return result

    def _score_zt_ratio(self, zt_count, total_stocks):
        """涨停占比评分(0-10): 涨停股数/板块总股数"""
        if total_stocks == 0:
            return 0
        ratio = zt_count / total_stocks
        # 10%以上即满分
        return round(min(ratio * 100, 10), 2)

    def _score_echelon(self, consecutive_zt):
        """涨停梯队评分(0-10): 高标(3连板+) + 中位(2连板) + 首板"""
        high_board = 0   # >= 3 连板
        mid_board = 0    # 2 连板
        first_board = 0  # 1 连板(首板)

        for code, cnt in consecutive_zt.items():
            if cnt >= 3:
                high_board += 1
            elif cnt == 2:
                mid_board += 1
            elif cnt == 1:
                first_board += 1

        # 高标龙头: 每只最多3分, 上限5分
        high_score = min(high_board * 3, 5)
        # 中位板: 每只2分, 上限3分
        mid_score = min(mid_board * 2, 3)
        # 首板: 每只0.5分, 上限2分
        first_score = min(first_board * 0.5, 2)

        return round(high_score + mid_score + first_score, 2)

    def _score_sustainability(self, concept_codes, trade_date):
        """持续性评分(0-10): 近5个交易日的涨停活跃度变化趋势"""
        prev_dates = self._get_prev_trade_dates(trade_date, 6)
        if len(prev_dates) < 3:
            return 0

        # 对每个概念计算近几天的涨停数
        result = {}
        for concept_code in concept_codes:
            stocks = self.ths_concept_to_stocks.get(concept_code, [])
            if len(stocks) < 5:
                result[concept_code] = 0
                continue

            daily_zt_counts = []
            for i in range(len(prev_dates) - 1, max(len(prev_dates) - 6, -1), -1):
                d = prev_dates[i]
                if i == 0:
                    break
                d_prev = prev_dates[i - 1]
                today_data = self._get_daily_data(d)
                prev_data = self._get_daily_data(d_prev)

                zt_count = 0
                for code in stocks:
                    if self._is_limit_up(code, d, d_prev, today_data, prev_data):
                        zt_count += 1
                daily_zt_counts.append(zt_count)

            if len(daily_zt_counts) < 3:
                result[concept_code] = 0
                continue

            # 最近3天涨停数的趋势
            recent = daily_zt_counts[:3]  # 最近3天

            # 基础分: 近5天总涨停活跃度
            total_zt = sum(daily_zt_counts)
            base_score = min(total_zt * 0.5, 8)

            # 趋势加分: 连续增长
            trend_bonus = 0
            if len(recent) >= 3 and recent[0] >= recent[1] >= recent[2] and recent[0] > 0:
                trend_bonus = 2

            result[concept_code] = round(min(base_score + trend_bonus, 10), 2)

        return result

    def _score_capital_flow(self, concept_codes, trade_date):
        """资金流入评分(0-10): 板块大单净流入占比"""
        trade_date_str = trade_date.strftime('%Y-%m-%d') if hasattr(trade_date, 'strftime') else str(trade_date)

        result = {}
        for concept_code in concept_codes:
            stocks = self.ths_concept_to_stocks.get(concept_code, [])
            if len(stocks) < 5:
                result[concept_code] = 0
                continue

            # 批量查询大单净额
            placeholders = ','.join(['%s'] * len(stocks))
            self.dbcursor.execute(f"""
                SELECT code, net_lg_amount
                FROM daily_moneyflow_tbl
                WHERE tradedate = %s AND code IN ({placeholders})
            """, [trade_date_str] + stocks)
            mf_rows = {row[0]: row[1] for row in self.dbcursor.fetchall()}

            # 批量查询成交额
            self.dbcursor.execute(f"""
                SELECT code, amount
                FROM daily_info_tbl
                WHERE tradedate = %s AND code IN ({placeholders})
            """, [trade_date_str] + stocks)
            amt_rows = {row[0]: float(row[1] or 0) for row in self.dbcursor.fetchall()}

            total_net_big = 0
            total_amount = 0
            valid_count = 0

            for code in stocks:
                net_big = mf_rows.get(code) or 0
                amount = amt_rows.get(code, 0)
                if amount > 0:
                    total_net_big += float(net_big)
                    total_amount += amount
                    valid_count += 1

            if valid_count == 0 or total_amount == 0:
                result[concept_code] = 0
                continue

            # 大单净流入占成交额的比例, 正值为流入
            ratio = total_net_big / total_amount
            # 映射到0-10分: 2%净流入给10分, 负值给0分
            score = max(0, min(ratio * 500, 10))
            result[concept_code] = round(score, 2)

        return result

    def _score_index_rise(self, concept_codes, trade_date):
        """板块指数涨幅评分(0-10): 板块成分股近5日和10日平均涨幅"""
        prev_dates = self._get_prev_trade_dates(trade_date, 15)
        if len(prev_dates) < 10:
            return {c: 0 for c in concept_codes}

        result = {}
        prev_5d = prev_dates[-5] if len(prev_dates) >= 5 else prev_dates[0]
        prev_10d = prev_dates[-10] if len(prev_dates) >= 10 else prev_dates[0]
        prev_6d = prev_dates[-6] if len(prev_dates) >= 6 else prev_dates[0]
        prev_11d = prev_dates[-11] if len(prev_dates) >= 11 else prev_dates[0]

        today_data = self._get_daily_data(trade_date)
        data_5d = self._get_daily_data(prev_5d)
        data_6d = self._get_daily_data(prev_6d)
        data_10d = self._get_daily_data(prev_10d)
        data_11d = self._get_daily_data(prev_11d)

        for concept_code in concept_codes:
            stocks = self.ths_concept_to_stocks.get(concept_code, [])
            if len(stocks) < 5:
                result[concept_code] = 0
                continue

            rise_5d_list = []
            rise_10d_list = []

            for code in stocks:
                t = today_data.get(code, {})
                d5 = data_5d.get(code, {})
                d6 = data_6d.get(code, {})
                d10 = data_10d.get(code, {})
                d11 = data_11d.get(code, {})

                t_close = t.get('close', 0) * t.get('adj_factor', 1)
                d5_close = d5.get('close', 0) * d5.get('adj_factor', 1)
                d6_close = d6.get('close', 0) * d6.get('adj_factor', 1)
                d10_close = d10.get('close', 0) * d10.get('adj_factor', 1)
                d11_close = d11.get('close', 0) * d11.get('adj_factor', 1)

                if d5_close > 0 and d6_close > 0:
                    rise_5d = (t_close - d5_close) / d5_close * 100
                    rise_5d_list.append(rise_5d)
                if d10_close > 0 and d11_close > 0:
                    rise_10d = (t_close - d10_close) / d10_close * 100
                    rise_10d_list.append(rise_10d)

            if not rise_5d_list:
                result[concept_code] = 0
                continue

            avg_5d = sum(rise_5d_list) / len(rise_5d_list)
            avg_10d = sum(rise_10d_list) / len(rise_10d_list) if rise_10d_list else avg_5d

            # 5日权重0.6, 10日权重0.4
            combined = avg_5d * 0.6 + avg_10d * 0.4
            # 映射: 10%涨幅给10分
            score = max(0, min(combined, 10))
            result[concept_code] = round(score, 2)

        return result

    def _score_turnover_ratio(self, concept_codes, trade_date):
        """成交额占比评分(0-10): 板块成交额/全市场成交额"""
        trade_date_str = trade_date.strftime('%Y-%m-%d') if hasattr(trade_date, 'strftime') else str(trade_date)

        # 全市场总成交额
        self.dbcursor.execute("""
            SELECT SUM(amount) FROM daily_info_tbl WHERE tradedate = %s
        """, (trade_date_str,))
        total_market_amt = float(self.dbcursor.fetchone()[0] or 0)

        if total_market_amt <= 0:
            return {c: 0 for c in concept_codes}

        result = {}
        for concept_code in concept_codes:
            stocks = self.ths_concept_to_stocks.get(concept_code, [])
            if len(stocks) < 5:
                result[concept_code] = 0
                continue

            placeholders = ','.join(['%s'] * len(stocks))
            self.dbcursor.execute(f"""
                SELECT SUM(amount) FROM daily_info_tbl
                WHERE tradedate = %s AND code IN ({placeholders})
            """, [trade_date_str] + stocks)
            concept_amt = float(self.dbcursor.fetchone()[0] or 0)

            ratio = concept_amt / total_market_amt
            # 4%以上满分, 正常主线题材成交占比在2%-5%
            score = min(ratio * 250, 10)
            result[concept_code] = round(score, 2)

        return result

    def analyze_daily_themes(self, trade_date):
        """
        分析指定交易日的主线题材
        返回按total_score降序排列的题材列表
        """
        if isinstance(trade_date, str):
            trade_date = datetime.strptime(trade_date, '%Y-%m-%d').date()

        print(f"\n{'='*60}")
        print(f"开始分析主线题材: {trade_date}")
        print(f"{'='*60}")

        # 1. 只分析有一定规模的概念板块(成分股>=10)
        candidate_concepts = [
            c for c, stocks in self.ths_concept_to_stocks.items()
            if len(stocks) >= 10
        ]
        print(f"候选概念板块数: {len(candidate_concepts)}")

        # 2. 获取所有候选概念的涨停信息
        print("正在计算涨停数据...")
        zt_info = self._get_concept_zt_list(candidate_concepts, trade_date)

        # 3. 过滤有涨停活动的概念
        active_concepts = [
            c for c in candidate_concepts
            if zt_info.get(c, {}).get('zt_count', 0) > 0
        ]
        print(f"有涨停活动的概念板块: {len(active_concepts)}")

        if not active_concepts:
            print("当日无涨停活动, 无法识别主线题材")
            return []

        # 4. 批量计算其他维度分数
        print("计算持续性分数...")
        sustainability_scores = self._score_sustainability(active_concepts, trade_date)

        print("计算资金流入分数...")
        capital_scores = self._score_capital_flow(active_concepts, trade_date)

        print("计算板块涨幅分数...")
        rise_scores = self._score_index_rise(active_concepts, trade_date)

        print("计算成交额占比分数...")
        turnover_scores = self._score_turnover_ratio(active_concepts, trade_date)

        # 5. 汇总评分
        results = []
        for concept_code in active_concepts:
            info = zt_info[concept_code]
            total_stocks = len(self.ths_concept_to_stocks[concept_code])
            zt_count = info['zt_count']
            consecutive = info['consecutive_zt']

            score_zt = self._score_zt_ratio(zt_count, total_stocks)
            score_ech = self._score_echelon(consecutive)
            score_sus = sustainability_scores.get(concept_code, 0)
            score_cap = capital_scores.get(concept_code, 0)
            score_rise = rise_scores.get(concept_code, 0)
            score_turn = turnover_scores.get(concept_code, 0)
            total = score_zt + score_ech + score_sus + score_cap + score_rise + score_turn

            # 高标和首板计数
            high_board = sum(1 for cnt in consecutive.values() if cnt >= 3)
            first_board = sum(1 for cnt in consecutive.values() if cnt == 1)

            results.append({
                'theme_code': concept_code,
                'theme_name': self.concept_name_map.get(concept_code, concept_code),
                'theme_type': 'concept',
                'score_zt_ratio': score_zt,
                'score_echelon': score_ech,
                'score_sustainability': score_sus,
                'score_capital_flow': score_cap,
                'score_index_rise': score_rise,
                'score_turnover_ratio': score_turn,
                'total_score': round(total, 2),
                'zt_count': zt_count,
                'zt_total': total_stocks,
                'high_board_count': high_board,
                'first_board_count': first_board,
                'zt_codes': info['zt_codes'],
                'consecutive_zt': consecutive,
            })

        # 6. 按总分排序
        results.sort(key=lambda x: x['total_score'], reverse=True)

        # 7. 打印top结果
        print(f"\n{'='*80}")
        print(f"主线题材分析结果 Top 30 ({trade_date})")
        print(f"{'='*80}")
        print(f"{'排名':<5}{'题材名称':<16}{'总分':<8}{'涨停占比':<10}{'梯队':<8}{'持续性':<8}{'资金':<8}{'涨幅':<8}{'成交':<8}")
        print('-' * 80)
        for i, r in enumerate(results[:30], 1):
            print(f"{i:<5}{r['theme_name']:<16}{r['total_score']:<8}"
                  f"{r['score_zt_ratio']:<10}{r['score_echelon']:<8}"
                  f"{r['score_sustainability']:<8}{r['score_capital_flow']:<8}"
                  f"{r['score_index_rise']:<8}{r['score_turnover_ratio']:<8}")

        return results

    def get_main_themes(self, results, top_n=3, min_score=20):
        """从分析结果中筛选主线题材"""
        main_themes = []
        for r in results[:top_n]:
            if r['total_score'] >= min_score:
                r['is_main_theme'] = True
                main_themes.append(r)
            else:
                r['is_main_theme'] = False
        return main_themes

    def save_to_db(self, trade_date, results, leader_info=None):
        """
        将分析结果保存到theme_daily_score_tbl
        leader_info: {theme_code: [(code, name), ...]} 龙头票信息
        """
        if isinstance(trade_date, (datetime, date)):
            trade_date_str = trade_date.strftime('%Y-%m-%d') if hasattr(trade_date, 'strftime') else str(trade_date)
        else:
            trade_date_str = str(trade_date)

        if leader_info is None:
            leader_info = {}

        insert_sql = """
            INSERT INTO theme_daily_score_tbl
            (trade_date, theme_code, theme_name, theme_type,
             score_zt_ratio, score_echelon, score_sustainability,
             score_capital_flow, score_index_rise, score_turnover_ratio,
             total_score, is_main_theme,
             zt_count, zt_total, high_board_count, first_board_count,
             net_big_order_amount, concept_turnover, avg_rise_5d,
             leader_codes, leader_names, analysis_detail)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                score_zt_ratio = VALUES(score_zt_ratio),
                score_echelon = VALUES(score_echelon),
                score_sustainability = VALUES(score_sustainability),
                score_capital_flow = VALUES(score_capital_flow),
                score_index_rise = VALUES(score_index_rise),
                score_turnover_ratio = VALUES(score_turnover_ratio),
                total_score = VALUES(total_score),
                is_main_theme = VALUES(is_main_theme),
                zt_count = VALUES(zt_count),
                zt_total = VALUES(zt_total),
                high_board_count = VALUES(high_board_count),
                first_board_count = VALUES(first_board_count),
                net_big_order_amount = VALUES(net_big_order_amount),
                concept_turnover = VALUES(concept_turnover),
                avg_rise_5d = VALUES(avg_rise_5d),
                leader_codes = VALUES(leader_codes),
                leader_names = VALUES(leader_names),
                analysis_detail = VALUES(analysis_detail)
        """

        saved = 0
        for r in results:
            theme_code = r['theme_code']
            leaders = leader_info.get(theme_code, [])
            leader_codes_json = json.dumps([l[0] for l in leaders]) if leaders else None
            leader_names_json = json.dumps([l[1] for l in leaders]) if leaders else None

            analysis_detail = json.dumps({
                'consecutive_zt': {
                    c: v for c, v in r.get('consecutive_zt', {}).items()
                }
            }) if r.get('consecutive_zt') else None

            values = (
                trade_date_str, r['theme_code'], r['theme_name'], r.get('theme_type', 'concept'),
                r['score_zt_ratio'], r['score_echelon'], r['score_sustainability'],
                r['score_capital_flow'], r['score_index_rise'], r['score_turnover_ratio'],
                r['total_score'], 1 if r.get('is_main_theme') else 0,
                r['zt_count'], r['zt_total'], r.get('high_board_count', 0), r.get('first_board_count', 0),
                0, 0, 0,
                leader_codes_json, leader_names_json,
                analysis_detail
            )

            try:
                self.dbcursor.execute(insert_sql, values)
                saved += 1
            except Exception as e:
                print(f"  保存 {r['theme_name']} 失败: {e}")

        self.mydb.commit()
        print(f"  共保存 {saved} 条记录到 theme_daily_score_tbl")

    # ---------- 长期主线分析 ----------

    # 需要排除的宏观/大盘/风格/地域指数型概念（不是真正的题材板块）
    _MACRO_INDEX_KEYWORDS = [
        # 同花顺大盘指数
        u'同花顺全A', u'同花顺沪深', u'同花顺主板', u'同花顺大盘',
        u'同花顺陆股通', u'同花顺深股通', u'同花顺低估值',
        u'同花顺中证', u'同花顺高估值', u'同花顺小盘', u'同花顺小市值',
        u'同花顺大市值', u'同花顺低盈利', u'同花顺热股',
        u'同花顺情绪指数', u'同花顺',  # 太宽泛的兜底
        u'深市新主板', u'沪市',
        # 两融/资金类
        u'融资融券', u'深股通', u'沪股通',
        # 打板/昨日涨停类(追踪指标，不是题材)
        u'昨日打板', u'昨日涨停', u'昨日首板', u'昨日非ST',
        u'沪深主板昨日涨停', u'龙虎榜指数', u'近期新高',
        # 业绩/财务风格类
        u'业绩预亏', u'减持新规', u'增发预案指数', u'低市盈率',
        # 地域类(不是题材)
        u'广东(除深圳)', u'粤港澳大湾区', u'京津冀一体化',
        u'长三角', u'海南', u'雄安',
        # 宽基/风格指数
        u'国企改革',  # 太宽泛
    ]

    def _is_macro_index(self, theme_name):
        """判断是否为宏观大盘指数（需要排除）"""
        for kw in self._MACRO_INDEX_KEYWORDS:
            if kw in theme_name:
                return True
        return False

    def analyze_long_term_themes(self, trade_date, lookback_days=20, min_active_days=3):
        """
        长期主线题材分析
        从theme_daily_score_tbl读取多日数据，找到持续性强的主线

        评分维度:
        - 累计强度(0.35): lookback期间总分累计，越高说明炒作越持续
        - 日均强度(0.25): 有活动的天数平均分，高均值说明不是一日游
        - 登顶频率(0.20): 进入top5的天数占比，频次高说明持续领涨
        - 趋势方向(0.20): 评分是上升还是下降，上升趋势说明主线仍在强化

        返回排序后的长期主线列表
        """
        if isinstance(trade_date, str):
            trade_date = datetime.strptime(trade_date, '%Y-%m-%d').date()

        trade_date_str = trade_date.strftime('%Y-%m-%d')

        # 获取lookback期间的所有交易日
        prev_dates = self._get_prev_trade_dates(trade_date, lookback_days)
        all_dates = prev_dates + [trade_date]

        if len(all_dates) < min_active_days:
            print(f"  交易日不足({len(all_dates)}天), 无法进行长期分析")
            return []

        date_strs = [d.strftime('%Y-%m-%d') if hasattr(d, 'strftime') else str(d) for d in all_dates]

        # 查询期间所有记录
        placeholders = ','.join(['%s'] * len(date_strs))
        self.dbcursor.execute(f"""
            SELECT theme_code, theme_name, trade_date, total_score,
                   score_zt_ratio, score_echelon, score_sustainability,
                   score_capital_flow, score_index_rise, score_turnover_ratio,
                   zt_count, zt_total, high_board_count, first_board_count,
                   leader_codes, leader_names
            FROM theme_daily_score_tbl
            WHERE trade_date IN ({placeholders})
            ORDER BY theme_code, trade_date
        """, date_strs)

        rows = self.dbcursor.fetchall()
        if not rows:
            print("  theme_daily_score_tbl 中无历史数据, 请先运行每日分析积累数据")
            print("  或者使用 backfill_history() 回填历史数据")
            return []

        # 组织数据: theme_code -> {date_str: record}
        theme_daily_map = {}
        all_theme_names = {}
        for row in rows:
            (theme_code, theme_name, td, total_score,
             score_zt, score_ech, score_sus, score_cap, score_rise, score_turn,
             zt_count, zt_total, high_board, first_board,
             leader_codes, leader_names) = row

            td_str = td.strftime('%Y-%m-%d') if hasattr(td, 'strftime') else str(td)

            if theme_code not in theme_daily_map:
                theme_daily_map[theme_code] = {}
                all_theme_names[theme_code] = theme_name

            theme_daily_map[theme_code][td_str] = {
                'total_score': float(total_score) if total_score else 0,
                'zt_count': zt_count or 0,
                'high_board_count': high_board or 0,
                'first_board_count': first_board or 0,
                'leader_codes': leader_codes,
                'leader_names': leader_names,
            }

        # 按天计算每日排名（用于top-N频率统计）
        daily_rankings = {}
        for date_str in date_strs:
            daily_scores = []
            for theme_code, day_map in theme_daily_map.items():
                if date_str in day_map:
                    daily_scores.append((theme_code, day_map[date_str]['total_score']))
            daily_scores.sort(key=lambda x: x[1], reverse=True)
            daily_rankings[date_str] = {code: rank for rank, (code, _) in enumerate(daily_scores, 1)}

        # 对每个主题计算长期指标
        theme_stats = []
        for theme_code, day_map in theme_daily_map.items():
            theme_name = all_theme_names.get(theme_code, theme_code)

            # 过滤宏观大盘指数
            if self._is_macro_index(theme_name):
                continue

            scores = [day_map[d]['total_score'] for d in date_strs if d in day_map]
            active_days = len(scores)

            if active_days < min_active_days:
                continue

            total_days = len(date_strs)

            # --- 指标1: 累计强度 (0-100分) ---
            cumulative_score = sum(scores)
            # 归一化: 平均每天20分, 20天满分 = 400
            max_possible = total_days * 30  # 假设每天最高30分
            norm_cumulative = min(cumulative_score / max(max_possible, 1) * 100, 100)

            # --- 指标2: 日均强度 (0-100分) ---
            avg_daily_score = cumulative_score / active_days
            # 日均20分以上算强
            norm_avg = min(avg_daily_score / 30 * 100, 100) if avg_daily_score > 0 else 0

            # --- 指标3: 登顶频率 (0-100分) ---
            top5_count = 0
            for date_str in date_strs:
                if date_str in daily_rankings:
                    rank = daily_rankings[date_str].get(theme_code, 999)
                    if rank <= 5:
                        top5_count += 1
            top5_ratio = top5_count / active_days if active_days > 0 else 0
            norm_top5 = top5_ratio * 100

            # --- 指标4: 趋势方向 (0-100分) ---
            # 用有活动的日子的顺序索引做线性回归
            active_date_indices = []
            active_scores_list = []
            for i, date_str in enumerate(date_strs):
                if date_str in day_map:
                    active_date_indices.append(i)
                    active_scores_list.append(day_map[date_str]['total_score'])

            trend_score = 50  # 默认中性
            trend_label = 'neutral'
            if len(active_scores_list) >= 3:
                n = len(active_scores_list)
                # 简单线性回归斜率
                x_mean = sum(active_date_indices) / n
                y_mean = sum(active_scores_list) / n
                numerator = sum(
                    (active_date_indices[i] - x_mean) * (active_scores_list[i] - y_mean)
                    for i in range(n)
                )
                denominator = sum((x - x_mean) ** 2 for x in active_date_indices)
                if denominator > 0:
                    slope = numerator / denominator
                    # 斜率归一化: 每天变化1分算明显趋势
                    norm_trend = 50 + min(max(slope * 25, -50), 50)
                    trend_score = norm_trend
                    if slope > 0.3:
                        trend_label = 'rising'
                    elif slope < -0.3:
                        trend_label = 'declining'
                    else:
                        trend_label = 'stable'

            # --- 综合长期得分 ---
            long_term_score = (
                norm_cumulative * 0.35 +
                norm_avg * 0.25 +
                norm_top5 * 0.20 +
                trend_score * 0.20
            )

            # 记录最近一天的龙头
            latest_date = date_strs[-1]
            latest = day_map.get(latest_date, {})
            latest_leaders_raw = latest.get('leader_codes')
            latest_leaders_names = latest.get('leader_names')
            if latest_leaders_raw:
                try:
                    leaders = json.loads(latest_leaders_raw) if isinstance(latest_leaders_raw, str) else latest_leaders_raw
                except:
                    leaders = []
            else:
                leaders = []

            theme_stats.append({
                'theme_code': theme_code,
                'theme_name': theme_name,
                'long_term_score': round(long_term_score, 2),
                'cumulative_score': round(cumulative_score, 2),
                'avg_daily_score': round(avg_daily_score, 2),
                'active_days': active_days,
                'total_days': total_days,
                'top5_count': top5_count,
                'top5_ratio': round(top5_ratio, 4),
                'trend_label': trend_label,
                'trend_score': round(trend_score, 2),
                'norm_cumulative': round(norm_cumulative, 2),
                'norm_avg': round(norm_avg, 2),
                'norm_top5': round(norm_top5, 2),
                'latest_leaders': leaders,
                'latest_zt_count': latest.get('zt_count', 0),
                'latest_high_board': latest.get('high_board_count', 0),
            })

        # 排序
        theme_stats.sort(key=lambda x: x['long_term_score'], reverse=True)

        # 打印结果
        print(f"\n{'='*90}")
        print(f"长期主线题材分析 (近{total_days}个交易日: {date_strs[0]} ~ {date_strs[-1]})")
        print(f"{'='*90}")
        print(f"{'排名':<5}{'题材名称':<18}{'长期分':<8}{'累计分':<8}"
              f"{'日均':<7}{'活跃':<6}{'Top5':<6}{'趋势':<8}{'最新涨停':<10}")
        print('-' * 90)
        for i, s in enumerate(theme_stats[:40], 1):
            trend_mark = {'rising': u'↑上升', 'declining': u'↓下降', 'stable': u'→平稳'}.get(s['trend_label'], s['trend_label'])
            print(f"{i:<5}{s['theme_name']:<18}{s['long_term_score']:<8.1f}{s['cumulative_score']:<8.1f}"
                  f"{s['avg_daily_score']:<7.1f}{s['active_days']}/{s['total_days']:<5}"
                  f"{s['top5_count']:<6}{str(trend_mark):<8}"
                  f"{s['latest_zt_count']}(高{s['latest_high_board']})")

        return theme_stats

    def get_long_term_main_themes(self, long_term_results, top_n=5, min_active_days=5, min_avg_score=10):
        """
        从长期分析结果中筛选长期主线

        筛选条件:
        - 活跃天数 >= min_active_days (不是一日游)
        - 日均分 >= min_avg_score (炒作力度足够)
        - 趋势不是declining (不能是退潮中的题材)
        - 或者是rising趋势但活跃天数略少也纳入（新兴主线）
        """
        main_themes = []
        emerging_themes = []

        for r in long_term_results:
            # 常规长期主线: 活跃天数多 + 日均分高 + 趋势非下降
            if (r['active_days'] >= min_active_days and
                r['avg_daily_score'] >= min_avg_score and
                r['trend_label'] != 'declining'):
                r['theme_category'] = 'long_term_main'
                main_themes.append(r)

            # 新兴主线: 趋势上升 + 近几日才崛起
            elif (r['active_days'] >= 3 and
                  r['trend_label'] == 'rising' and
                  r['avg_daily_score'] >= min_avg_score):
                r['theme_category'] = 'emerging'
                emerging_themes.append(r)

            else:
                r['theme_category'] = 'short_term'

        # 长期主线按长期分排序
        main_themes.sort(key=lambda x: x['long_term_score'], reverse=True)
        emerging_themes.sort(key=lambda x: x['long_term_score'], reverse=True)

        return main_themes[:top_n], emerging_themes[:top_n]

    # ---------- 历史回填 ----------

    def backfill_history(self, end_date, days=10):
        """
        回填历史主线分析数据
        对end_date往前days个交易日，逐日运行分析并存入DB
        """
        if isinstance(end_date, str):
            end_date = datetime.strptime(end_date, '%Y-%m-%d').date()

        prev_dates = self._get_prev_trade_dates(end_date, days)
        all_dates = prev_dates + [end_date]

        print(f"\n{'='*60}")
        print(f"历史回填: {all_dates[0]} ~ {all_dates[-1]} ({len(all_dates)}天)")
        print(f"{'='*60}")

        for i, d in enumerate(all_dates, 1):
            print(f"\n[{i}/{len(all_dates)}] {d}")
            # 检查是否已有数据
            d_str = d.strftime('%Y-%m-%d') if hasattr(d, 'strftime') else str(d)
            self.dbcursor.execute(
                "SELECT COUNT(*) FROM theme_daily_score_tbl WHERE trade_date = %s",
                (d_str,)
            )
            existing = self.dbcursor.fetchone()[0]
            if existing > 0:
                print(f"  已有 {existing} 条记录, 跳过")
                continue

            results = self.analyze_daily_themes(d)
            if results:
                self.save_to_db(d, results)

        print(f"\n历史回填完成!")

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
    """独立运行: 分析最新交易日的主线题材"""
    if len(sys.argv) > 1:
        trade_date = sys.argv[1]
    else:
        # 默认分析最新交易日
        db = initMySQL()
        cursor = db.cursor()
        cursor.execute('SELECT MAX(tradedate) FROM daily_info_tbl')
        trade_date = cursor.fetchone()[0]
        cursor.close()
        db.close()

    print(f"\n目标交易日: {trade_date}")

    analyzer = ThemeAnalyzer()
    try:
        results = analyzer.analyze_daily_themes(trade_date)
        if results:
            main_themes = analyzer.get_main_themes(results, top_n=3, min_score=20)
            print(f"\n{'='*80}")
            print(f"主线题材 (Top {len(main_themes)})")
            print(f"{'='*80}")
            for i, t in enumerate(main_themes, 1):
                print(f"  {i}. {t['theme_name']} (总分: {t['total_score']})")
                print(f"     涨停: {t['zt_count']}/{t['zt_total']}, 高标: {t['high_board_count']}, 首板: {t['first_board_count']}")
                print(f"     评分: 占比={t['score_zt_ratio']} 梯队={t['score_echelon']} 持续={t['score_sustainability']}")
                print(f"           资金={t['score_capital_flow']} 涨幅={t['score_index_rise']} 成交={t['score_turnover_ratio']}")

            # 保存到数据库
            analyzer.save_to_db(trade_date, results)
            print(f"\n结果已保存到 theme_daily_score_tbl")
    finally:
        analyzer.cleanup()


if __name__ == '__main__':
    main()
