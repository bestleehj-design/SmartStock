#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
交易规则回测验证 — 对 trading_plan.md 中 9 条规则逐一做量化验证.

用法:
  python3 src/skills/rule_backtest.py                 # 运行全部 9 条规则
  python3 src/skills/rule_backtest.py --rule 1        # 只运行规则 1
  python3 src/skills/rule_backtest.py --rule 1,4,7    # 运行多条
  python3 src/skills/rule_backtest.py --summary       # 只输出 PASS/FAIL 汇总

设计原则:
  1. 复用 verify_analysis.py 的 DB_CONFIG / OFFSET 回填模式
  2. 每规则独立函数, 可单独运行
  3. 客观代理变量, 不依赖人工标签
  4. 对照组设计: 每条规则都有 "执行" vs "不执行" 对照
  5. 统一收益周期: 1d/5d/10d/20d

局限性:
  1. 规则 1 的"代理条件"不等于人工判断的分类 → 仅供参考
  2. 规则 5 的宏观日期需手动维护 → 低置信度
  3. 规则 9 的统计结论 ≠ 交易策略 → 仅供特征验证
  4. 回测用收盘价模拟, 实际交易有滑点和手续费
  5. 样本量 < 30 的结果标记 ⚠️
  6. 回测不代表未来表现
"""

import sys
import os
_SRC_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _SRC_DIR not in sys.path:
    sys.path.insert(0, _SRC_DIR)

import pymysql
import argparse
import statistics
from collections import defaultdict
from datetime import datetime

# ──────────────────────────────────────────────────────────────
# 配置
# ──────────────────────────────────────────────────────────────

DB_CONFIG = {
    'host': 'localhost', 'port': 3306,
    'user': 'root', 'password': '12345678',
    'database': 'gp2', 'charset': 'utf8mb4',
}

# 回测默认时间范围 (含 MA60 预热期)
BACKTEST_START = '2022-11-01'
DATA_START = '2022-08-01'   # MA60 需要提前 ~3 个月
DATA_END = '2026-06-01'

# 规则 5: 宏观事件日期 (手工维护)
MACRO_EVENTS = [
    # 2024 CPI (每月中旬公布上月数据)
    '2024-01-11', '2024-02-13', '2024-03-12', '2024-04-10',
    '2024-05-15', '2024-06-12', '2024-07-11', '2024-08-14',
    '2024-09-11', '2024-10-10', '2024-11-13', '2024-12-11',
    # 2025 CPI
    '2025-01-15', '2025-02-12', '2025-03-12', '2025-04-10',
    '2025-05-13', '2025-06-11', '2025-07-15', '2025-08-13',
    '2025-09-11', '2025-10-15', '2025-11-13', '2025-12-10',
    # 2024 FOMC (每年 8 次)
    '2024-01-31', '2024-03-20', '2024-05-01', '2024-06-12',
    '2024-07-31', '2024-09-18', '2024-11-07', '2024-12-18',
    # 2025 FOMC
    '2025-01-29', '2025-03-19', '2025-05-07', '2025-06-18',
    '2025-07-30', '2025-09-17', '2025-11-06', '2025-12-17',
    # 2026 FOMC
    '2026-01-28', '2026-03-18',
    # 2026 CPI
    '2026-01-14', '2026-02-11', '2026-03-11', '2026-04-10',
    '2026-05-13',
]

# 规则 9: 持仓股票特征 (来自 trading_plan.md)
STOCK_PERSONALITIES = {
    '600584': {'name': '长电科技', 'high_open_low_close': True,
               'expected_pct': 80, 'feature': '高开后8成收跌'},
    '002384': {'name': '东山精密', 'fake_breakdown_pct': 67,
               'feature': '假跌破之王, 恢复率67%'},
    '688981': {'name': '中芯国际', 'fake_breakdown_pct': 60,
               'feature': '假跌破惯性, 恢复率60%'},
    '002138': {'name': '顺络电子', 'max_consec_up': 6,
               'feature': '连涨6天不回调是常态'},
    '002463': {'name': '沪电股份', 'typical_drawdown': (8, 11),
               'feature': '回调浅(8-11%), 假跌破偏多'},
    '603986': {'name': '兆易创新', 'high_open_low_close': True,
               'expected_pct': None, 'feature': '高开低走概率最高(对比全组)'},
    '301591': {'name': '肯特股份', 'max_consec_down': 7,
               'feature': '最长连跌7天, 跌起来不停'},
}

# SOX 乘数基准值 (来自 trading_plan.md 规则 2)
SOX_MULTIPLIER_BASELINE = {
    (5, 7):   1.51,
    (3, 5):   1.09,
    (1, 3):   0.90,
    (-1, -3): None,   # -0.25
    (-3, -1): None,   # 不调整
    (-5, -3): -0.61,
}

# ──────────────────────────────────────────────────────────────
# 工具函数
# ──────────────────────────────────────────────────────────────

def get_code_suffix(code):
    """返回带后缀的代码: 600584 → 600584.SH, 002384 → 002384.SZ"""
    if code.startswith('6'):
        return code + '.SH'
    return code + '.SZ'


def stats_summary(values):
    """计算 mean, median, win_rate(>0%), std_dev"""
    if not values:
        return {'mean': None, 'median': None, 'win_rate': None, 'std': None, 'n': 0}
    v = [x for x in values if x is not None]
    if not v:
        return {'mean': None, 'median': None, 'win_rate': None, 'std': None, 'n': 0}
    mean = sum(v) / len(v)
    median = statistics.median(v)
    win_rate = sum(1 for x in v if x > 0) / len(v) * 100
    std = statistics.stdev(v) if len(v) > 1 else 0
    return {'mean': mean, 'median': median, 'win_rate': win_rate, 'std': std, 'n': len(v)}


def format_pct(v):
    """格式化百分比"""
    if v is None:
        return '   N/A'
    return f'{v:+.2f}%'


# ──────────────────────────────────────────────────────────────
# RuleBacktester 主类
# ──────────────────────────────────────────────────────────────

class RuleBacktester:
    def __init__(self, start_date=DATA_START, end_date=DATA_END):
        self.conn = pymysql.connect(**DB_CONFIG)
        self.start_date = start_date
        self.end_date = end_date
        self._daily = {}         # {code: {date: {open,high,low,close,volume}}}
        self._daily_loaded = False
        self._sox = {}           # {date: chg_pct}
        self._sox_loaded = False
        self._meta = {}          # {code_without_suffix: {name, sw1, sw2, sw3}}
        self._meta_loaded = False
        self._checked_results = []  # 汇总每条规则的 PASS/FAIL

    # ── 数据加载 ──────────────────────────────────────────────

    def _load_stock_meta(self):
        """加载所有 A 股的行业分类"""
        if self._meta_loaded:
            return
        c = self.conn.cursor()
        c.execute("SELECT code, name, sw1, sw2, sw3 FROM stock_basic_info_tbl WHERE status=1 AND type=0")
        for row in c.fetchall():
            full_code, name, sw1, sw2, sw3 = row
            code = full_code.replace('.SH', '').replace('.SZ', '')
            if len(code) == 6 and code.isdigit():
                self._meta[code] = {
                    'name': name, 'sw1': sw1 or '', 'sw2': sw2 or '', 'sw3': sw3 or ''
                }
        c.close()
        self._meta_loaded = True

    def _get_all_codes(self):
        """获取所有 A 股代码 (不含后缀)"""
        self._load_stock_meta()
        return list(self._meta.keys())

    def _get_semiconductor_codes(self):
        """获取半导体板块 A 股代码"""
        self._load_stock_meta()
        codes = []
        for code, info in self._meta.items():
            if '半导体' in (info.get('sw2', '') + info.get('sw3', '')):
                codes.append(code)
        return codes

    def _resolve_code(self, code):
        """将代码转为完整代码 (带后缀). 支持 .TI / .HK 等非股票后缀."""
        if '.' in code:
            return code  # 已有后缀, 直接使用
        return get_code_suffix(code)

    def _load_daily(self, codes, start=None, end=None):
        """批量加载日K线数据.
        codes: 不带后缀的代码列表, 或带后缀的完整代码 (如 '885472.TI')
        结果存入 self._daily: {code_with_suffix: {date_str: {open,high,low,close,volume}}}
        """
        if not codes:
            return
        if start is None:
            start = self.start_date
        if end is None:
            end = self.end_date

        # 只加载尚未缓存的代码
        to_load = [c for c in codes if self._resolve_code(c) not in self._daily]
        if not to_load:
            return

        c = self.conn.cursor()
        batch_size = 500
        for i in range(0, len(to_load), batch_size):
            batch = to_load[i:i + batch_size]
            full_codes = [self._resolve_code(x) for x in batch]
            placeholders = ','.join(['%s'] * len(full_codes))
            sql = f'''
                SELECT code, tradedate, open, high, low, close, volume
                FROM daily_info_tbl
                WHERE code IN ({placeholders})
                  AND tradedate >= %s AND tradedate <= %s
                ORDER BY code, tradedate ASC
            '''
            c.execute(sql, full_codes + [start, end])
            for row in c.fetchall():
                full_code, d, o, h, l, cl, v = row
                date_str = str(d)
                if full_code not in self._daily:
                    self._daily[full_code] = {}
                self._daily[full_code][date_str] = {
                    'open': float(o), 'high': float(h),
                    'low': float(l), 'close': float(cl),
                    'volume': float(v) if v else 0
                }
        c.close()

    def _get_sorted_dates(self, full_code):
        """返回某只股票的已排序交易日列表"""
        data = self._daily.get(full_code, {})
        return sorted(data.keys())

    def _forward_returns(self, full_code, from_date, periods=(1, 5, 10, 20)):
        """计算从 from_date 起 N 个交易日的 forward return (%)"""
        dates = self._get_sorted_dates(full_code)
        try:
            idx = dates.index(from_date)
        except ValueError:
            return None
        result = {}
        for p in periods:
            if idx + p >= len(dates):
                result[p] = None
            else:
                future_close = self._daily[full_code][dates[idx + p]]['close']
                current_close = self._daily[full_code][from_date]['close']
                if current_close > 0:
                    result[p] = (future_close / current_close - 1) * 100
                else:
                    result[p] = None
        return result

    def _calc_ma(self, full_code, date_str, window):
        """计算 date_str 处的 MA(window)"""
        data = self._daily.get(full_code, {})
        dates = self._get_sorted_dates(full_code)
        try:
            idx = dates.index(date_str)
        except ValueError:
            return None
        if idx < window - 1:
            return None
        closes = [data[d]['close'] for d in dates[idx - window + 1:idx + 1]]
        return sum(closes) / len(closes) if closes else None

    def _calc_ma5(self, full_code, date_str):
        return self._calc_ma(full_code, date_str, 5)

    def _calc_ma20(self, full_code, date_str):
        return self._calc_ma(full_code, date_str, 20)

    def _calc_ma60(self, full_code, date_str):
        return self._calc_ma(full_code, date_str, 60)

    def _calc_rolling_returns(self, full_code, date_str, window):
        """计算过去 window 个交易日的累计收益率 (%)"""
        dates = self._get_sorted_dates(full_code)
        try:
            idx = dates.index(date_str)
        except ValueError:
            return None
        if idx < window:
            return None
        start_close = self._daily[full_code][dates[idx - window]]['close']
        end_close = self._daily[full_code][date_str]['close']
        if start_close > 0:
            return (end_close / start_close - 1) * 100
        return None

    def _load_sox(self):
        """加载 SOX 指数数据"""
        if self._sox_loaded:
            return
        c = self.conn.cursor()
        c.execute('''
            SELECT tradedate, chg_pct FROM sox_index_tbl
            WHERE tradedate >= %s AND tradedate <= %s
            ORDER BY tradedate ASC
        ''', (self.start_date, self.end_date))
        for row in c.fetchall():
            d, chg = row
            self._sox[str(d)] = float(chg) if chg else 0
        c.close()
        self._sox_loaded = True

    # ── 分类辅助 ──────────────────────────────────────────────

    def _categorize_position(self, full_code, date_str):
        """规则 1 的代理分类: 必清/减仓可等/不动.
        返回: 'must_clear', 'reduce_wait', 'hold', 或 None (无法判断)
        """
        data = self._daily.get(full_code, {})
        if date_str not in data:
            return None

        ma20 = self._calc_ma20(full_code, date_str)
        ma60 = self._calc_ma60(full_code, date_str)
        ret_20d = self._calc_rolling_returns(full_code, date_str, 20)

        if ma20 is None or ma60 is None or ret_20d is None:
            return None

        close = data[date_str]['close']
        above_ma20 = close > ma20
        above_ma60 = close > ma60

        # 检查连续 5 日收盘价 < MA20
        dates = self._get_sorted_dates(full_code)
        idx = dates.index(date_str)
        consec_below = True
        for j in range(max(0, idx - 4), idx + 1):
            d = dates[j]
            m20 = self._calc_ma20(full_code, d)
            if m20 is None or self._daily[full_code][d]['close'] > m20:
                consec_below = False
                break

        # 必清: MA60 跌破 且 连续 5 日收盘价 < MA20 且 近 20 日跌幅 > 15%
        if not above_ma60 and consec_below and ret_20d < -15:
            return 'must_clear'

        # 减仓可等: MA20 跌破但 MA60 站上 且 20 日跌幅 < 10%
        if not above_ma20 and above_ma60 and ret_20d > -10:
            return 'reduce_wait'

        # 不动: MA20 和 MA60 都站上 且 近 10 日跌幅 < 5%
        ret_10d = self._calc_rolling_returns(full_code, date_str, 10)
        if above_ma20 and above_ma60 and (ret_10d is not None and ret_10d > -5):
            return 'hold'

        return None

    def _identify_ma_breakdown(self, full_code):
        """找到所有 MA20 跌破事件: 前一日 close > MA20 且 当日 close < MA20.
        返回: [date_str, ...]"""
        dates = self._get_sorted_dates(full_code)
        events = []
        for i in range(1, len(dates)):
            prev_date = dates[i - 1]
            curr_date = dates[i]
            data = self._daily[full_code]

            prev_ma20 = self._calc_ma20(full_code, prev_date)
            curr_ma20 = self._calc_ma20(full_code, curr_date)
            if prev_ma20 is None or curr_ma20 is None:
                continue

            prev_close = data[prev_date]['close']
            curr_close = data[curr_date]['close']

            if prev_close > prev_ma20 and curr_close < curr_ma20:
                events.append(curr_date)
        return events

    def _identify_rebound_days(self, full_code):
        """找到所有反弹日: 前 3 日累计跌幅 ≥ 3% 且 当日涨幅 ≥ 1.5%"""
        dates = self._get_sorted_dates(full_code)
        events = []
        data = self._daily[full_code]
        for i in range(3, len(dates)):
            ret_3d = (data[dates[i - 1]]['close'] / data[dates[i - 4]]['close'] - 1) * 100
            daily_ret = (data[dates[i]]['close'] / data[dates[i - 1]]['close'] - 1) * 100
            if ret_3d <= -3 and daily_ret >= 1.5:
                events.append(dates[i])
        return events

    def _score_four_dim(self, full_code, date_str):
        """规则 6 的四维打分: 突破 vs 见顶.
        返回: (breakthrough_score, topping_score)"""
        data = self._daily.get(full_code, {})
        if date_str not in data:
            return None

        dates = self._get_sorted_dates(full_code)
        idx = dates.index(date_str)
        if idx < 5:
            return None

        row = data[date_str]
        o, h, l, c = row['open'], row['high'], row['low'], row['close']
        breakthrough = 0
        topping = 0

        # 维度 1: 成交量
        vols = [data[d]['volume'] for d in dates[max(0, idx - 5):idx]]
        avg_vol = sum(vols) / len(vols) if vols else 0
        if avg_vol > 0:
            vol_ratio = row['volume'] / avg_vol
            if vol_ratio > 1.5:
                breakthrough += 1
            elif vol_ratio < 0.7:
                topping += 1

        # 维度 2: 收盘位置 (相对日内振幅的位置)
        range_hl = h - l
        if range_hl > 0:
            body_pos = (c - l) / range_hl
            if body_pos > 0.7:
                breakthrough += 1
            elif body_pos < 0.3:
                topping += 1

        # 维度 3: K 线形态 (上影线比例)
        if range_hl > 0:
            upper_shadow = (h - max(o, c)) / range_hl
            if upper_shadow < 0.2:
                breakthrough += 1
            elif upper_shadow > 0.4:
                topping += 1

        # 维度 4: MA5 趋势
        ma5_curr = self._calc_ma5(full_code, date_str)
        ma5_prev = self._calc_ma5(full_code, dates[idx - 1])
        if ma5_curr and ma5_prev and ma5_curr > ma5_prev:
            breakthrough += 1
        else:
            topping += 1

        return (breakthrough, topping)

    # ── 输出辅助 ──────────────────────────────────────────────

    def _print_rule_header(self, rule_num, title):
        print(f"\n{'=' * 70}")
        print(f"  规则 {rule_num}: {title}")
        print(f"{'=' * 70}")

    def _print_result_table(self, rows, headers=None):
        """打印结果表. rows: [(label, stats_dict), ...]"""
        if headers is None:
            headers = ['分组', '均值', '中位数', '胜率', '标准差', '样本']
        # 计算列宽
        col_widths = [len(h) for h in headers]
        for r in rows:
            label = r[0]
            s = r[1]
            vals = [
                label,
                format_pct(s.get('mean')),
                format_pct(s.get('median')),
                f"{s.get('win_rate', 0):.1f}%" if s.get('win_rate') is not None else 'N/A',
                format_pct(s.get('std')),
                str(s.get('n', 0))
            ]
            for i, v in enumerate(vals):
                col_widths[i] = max(col_widths[i], len(str(v)))

        # 打印表头
        sep = '-' * (sum(col_widths) + len(col_widths) * 3 + 1)
        header_line = ' | '.join(h.ljust(col_widths[i]) for i, h in enumerate(headers))
        print(header_line)
        print(sep)

        # 打印数据行
        for r in rows:
            label = r[0]
            s = r[1]
            vals = [
                label,
                format_pct(s.get('mean')),
                format_pct(s.get('median')),
                f"{s.get('win_rate', 0):.1f}%" if s.get('win_rate') is not None else 'N/A',
                format_pct(s.get('std')),
                str(s.get('n', 0))
            ]
            line = ' | '.join(str(v).ljust(col_widths[i]) for i, v in enumerate(vals))
            print(line)
        print()

    def _print_checks(self, checks):
        """打印检查项. checks: [(description, passed, detail), ...]"""
        for desc, passed, detail in checks:
            if isinstance(passed, bool):
                status = 'PASS' if passed else 'FAIL'
                icon = '✅' if passed else '❌'
            else:
                status = 'PASS' if passed else 'FAIL'
                icon = '✅' if passed else '❌'
            if detail:
                print(f"  {icon} {desc}: {status}  ({detail})")
            else:
                print(f"  {icon} {desc}: {status}")

    def _record_result(self, rule_num, title, all_pass):
        self._checked_results.append({
            'rule': rule_num, 'title': title, 'all_pass': all_pass
        })

    # ══════════════════════════════════════════════════════════
    # 规则 1: 持仓分级制
    # ══════════════════════════════════════════════════════════

    def test_rule1_position_tier(self):
        """验证持仓分级制: 必清 / 减仓可等 / 不动, 卖出后 forward return 是否符合预期"""
        self._print_rule_header(1, '持仓分级制 — 必清/减仓可等/不动')
        print('验证: 按分类做卖出决策, 必清卖出后继续跌, 不动卖出后会涨, 分级有意义')
        print(f'数据范围: {BACKTEST_START} ~ {DATA_END}')

        codes = self._get_all_codes()
        self._load_daily(codes)

        groups = defaultdict(list)  # {tier: [forward_returns_5d, ...]}

        checked = 0
        for code in codes:
            full = get_code_suffix(code)
            dates = self._get_sorted_dates(full)
            # 只取回测范围内的日期
            for d in dates:
                if d < BACKTEST_START or d > DATA_END:
                    continue
                tier = self._categorize_position(full, d)
                if tier is None:
                    continue
                fwd = self._forward_returns(full, d)
                if fwd is None or fwd.get(5) is None:
                    continue
                groups[tier].append(fwd[5])
                checked += 1

        print(f'样本: {checked} 条分类事件')

        rows = []
        for tier in ['must_clear', 'reduce_wait', 'hold']:
            label = {'must_clear': '必清', 'reduce_wait': '减仓可等', 'hold': '不动'}[tier]
            vals = groups.get(tier, [])
            if vals:
                rows.append((label, stats_summary(vals)))
            else:
                rows.append((label, {'mean': None, 'median': None, 'win_rate': None, 'std': None, 'n': 0}))

        self._print_result_table(rows)

        # 检查项
        must_clear_n = len(groups.get('must_clear', []))
        hold_n = len(groups.get('hold', []))
        reduce_n = len(groups.get('reduce_wait', []))

        mc = stats_summary(groups.get('must_clear', []))
        hd = stats_summary(groups.get('hold', []))
        rw = stats_summary(groups.get('reduce_wait', []))

        checks = []
        if mc['n'] >= 30 and hd['n'] >= 30:
            checks.append((
                '必清组 5d return < 不动组',
                (mc['mean'] or 0) < (hd['mean'] or 0),
                f'必清={format_pct(mc["mean"])} vs 不动={format_pct(hd["mean"])}'
            ))
        else:
            checks.append((
                '必清组 5d return < 不动组', None,
                f'⚠️ 样本不足: 必清={mc["n"]}, 不动={hd["n"]}'
            ))

        if mc['n'] >= 30 and rw['n'] >= 30 and hd['n'] >= 30:
            monotonic = (mc['mean'] or 0) < (rw['mean'] or 0) < (hd['mean'] or 0)
            checks.append((
                '三组单调递减 (必清 < 减仓 < 不动)',
                monotonic,
                f'必清={format_pct(mc["mean"])} 减仓={format_pct(rw["mean"])} 不动={format_pct(hd["mean"])}'
            ))
        elif rw['n'] >= 30:
            checks.append((
                '三组单调递减', None,
                f'⚠️ 部分样本不足'
            ))

        checks.append((
            f'必清组 5d return 为负 (样本={mc["n"]})',
            mc['n'] >= 30 and (mc['mean'] or 0) < 0,
            f'必清 avg={format_pct(mc["mean"])}'
        ))

        checks.append((
            f'不动组 5d return 为正 (样本={hd["n"]})',
            hd['n'] >= 30 and (hd['mean'] or 0) > 0,
            f'不动 avg={format_pct(hd["mean"])}'
        ))

        self._print_checks(checks)
        all_pass = all(c[1] is not False for c in checks)
        self._record_result(1, '持仓分级制', all_pass)
        print(f'结论: {"规则成立 ✅" if all_pass else "规则存疑 ⚠️"} (注: 代理条件 ≠ 人工判断)\n')

    # ══════════════════════════════════════════════════════════
    # 规则 2: SOX 乘数
    # ══════════════════════════════════════════════════════════

    def test_rule2_sox_multiplier(self):
        """验证 SOX 涨跌对 A 股半导体次日收益的映射关系"""
        self._print_rule_header(2, 'SOX 乘数 — 费城半导体对 A 股半导体的传导系数')
        print('验证: SOX 各区间次日 A 股半导体板块的平均收益是否匹配 trading_plan.md 中的乘数')
        print(f'数据范围: {BACKTEST_START} ~ {DATA_END}')

        self._load_sox()

        # 获取半导体板块指数 885472.TI (需传完整代码, 因为 .TI 不是股票后缀)
        self._load_daily(['885472.TI'], start=self.start_date, end=self.end_date)
        semi_idx_full = '885472.TI'
        dates = self._get_sorted_dates(semi_idx_full)

        # SOX 区间定义
        ranges = [
            (-10, -5), (-5, -3), (-3, -1), (-1, 1),
            (1, 3), (3, 5), (5, 7), (7, 10)
        ]
        range_labels = ['-10~-5%', '-5~-3%', '-3~-1%', '-1~1%', '1~3%', '3~5%', '5~7%', '7~10%']

        range_returns = {label: [] for label in range_labels}
        range_yearly = defaultdict(lambda: defaultdict(list))  # {year: {range_label: [returns]}}

        for sox_date, sox_chg in self._sox.items():
            if sox_date not in dates:
                continue
            # 找 A 股次日
            idx = dates.index(sox_date)
            if idx + 1 >= len(dates):
                continue
            next_a_date = dates[idx + 1]
            # 确保是次日 (间隔 ≤ 3 天)
            from datetime import date as dt_date
            sd = dt_date(*map(int, sox_date.split('-')))
            nd = dt_date(*map(int, next_a_date.split('-')))
            if (nd - sd).days > 3:
                continue

            next_ret = (self._daily[semi_idx_full][next_a_date]['close'] /
                        self._daily[semi_idx_full][sox_date]['close'] - 1) * 100

            year = sox_date[:4]
            for (lo, hi), label in zip(ranges, range_labels):
                if lo <= sox_chg < hi:
                    range_returns[label].append(next_ret)
                    range_yearly[year][label].append(next_ret)
                    break

        # 打印总体区间表
        rows = []
        baseline_map = {
            '5~7%': 1.51, '3~5%': 1.09, '1~3%': 0.90,
            '-3~-1%': -0.25, '-5~-3%': -0.61,
        }
        for label in range_labels:
            vals = range_returns[label]
            s = stats_summary(vals)
            bl = baseline_map.get(label)
            bl_str = format_pct(bl) if bl is not None else '  —'
            if s['n'] > 0:
                label_with_n = f"{label} (n={s['n']})"
            else:
                label_with_n = f"{label} (n=0)"
            rows.append((label_with_n, s))

        print('总体区间统计:')
        self._print_result_table(rows)

        # 打印按年份分段
        print('按年份分段验证:')
        years = sorted(range_yearly.keys())
        for label in range_labels:
            if sum(len(v) for v in [range_yearly[y].get(label, []) for y in years]) < 10:
                continue
            year_rows = []
            for y in years:
                vals = range_yearly[y].get(label, [])
                s = stats_summary(vals)
                if s['n'] > 0:
                    year_rows.append((y, s))
            if year_rows:
                print(f'\n  SOX {label}:')
                self._print_result_table(year_rows)

        # 检查项
        checks = []
        sox_all_pass = True
        for label in range_labels:
            vals = range_returns[label]
            s = stats_summary(vals)
            bl = baseline_map.get(label)
            if s['n'] < 30:
                checks.append((f'{label} (n={s["n"]})', None, '⚠️ 样本不足'))
                continue
            if bl is not None:
                diff = abs((s['mean'] or 0) - bl)
                check_pass = diff < 1.0  # 允许 1% 偏差
                sox_all_pass = sox_all_pass and check_pass
                checks.append((
                    f'{label} mean={format_pct(s["mean"])} vs baseline={format_pct(bl)}',
                    check_pass,
                    f'偏差={diff:.2f}% (n={s["n"]})'
                ))
            if s['win_rate'] is not None and s['win_rate'] > 55:
                checks.append((
                    f'{label} win_rate={s["win_rate"]:.1f}% > 55%',
                    True,
                    f'n={s["n"]}'
                ))

        self._print_checks(checks)
        self._record_result(2, 'SOX 乘数', sox_all_pass)
        print(f'结论: {"规则成立 ✅" if sox_all_pass else "需关注 ⚠️"}\n')

    # ══════════════════════════════════════════════════════════
    # 规则 3: 反弹减仓优先级
    # ══════════════════════════════════════════════════════════

    def test_rule3_rebound_priority(self):
        """验证反弹日按优先级卖出的合理性"""
        self._print_rule_header(3, '反弹减仓优先级 — 反弹日卖出的效益')
        print('验证: 反弹日按 必清 > 减仓可等 > 减仓 > 不动 的顺序卖出是否合理')
        print(f'数据范围: {BACKTEST_START} ~ {DATA_END}')

        codes = self._get_all_codes()
        self._load_daily(codes)

        # 收集反弹日的分类数据
        rebound_tier_returns = defaultdict(list)  # {tier: [5d_forward_return]}
        all_tier_returns = defaultdict(list)      # 任意日分类的 5d return

        for code in codes:
            full = get_code_suffix(code)
            dates = self._get_sorted_dates(full)
            for d in dates:
                if d < BACKTEST_START or d > DATA_END:
                    continue
                tier = self._categorize_position(full, d)
                if tier is None:
                    continue
                fwd = self._forward_returns(full, d)
                if fwd is None or fwd.get(5) is None:
                    continue
                all_tier_returns[tier].append(fwd[5])

        # 找反弹日
        for code in codes:
            full = get_code_suffix(code)
            rebound_dates = self._identify_rebound_days(full)
            for d in rebound_dates:
                if d < BACKTEST_START:
                    continue
                tier = self._categorize_position(full, d)
                if tier is None:
                    continue
                fwd = self._forward_returns(full, d)
                if fwd is None or fwd.get(5) is None:
                    continue
                rebound_tier_returns[tier].append(fwd[5])

        tiers = ['must_clear', 'reduce_wait', 'hold']
        tier_labels = ['必清', '减仓可等', '不动']

        print('反弹日卖出 5d forward return:')
        rows = []
        for tier, label in zip(tiers, tier_labels):
            s = stats_summary(rebound_tier_returns.get(tier, []))
            rows.append((f'{label} (反弹日)', s))
        self._print_result_table(rows)

        print('任意日卖出 5d forward return (对照):')
        rows2 = []
        for tier, label in zip(tiers, tier_labels):
            s = stats_summary(all_tier_returns.get(tier, []))
            rows2.append((f'{label} (任意日)', s))
        self._print_result_table(rows2)

        # 检查项
        checks = []
        mc_r = stats_summary(rebound_tier_returns.get('must_clear', []))
        rw_r = stats_summary(rebound_tier_returns.get('reduce_wait', []))
        hd_r = stats_summary(rebound_tier_returns.get('hold', []))

        if mc_r['n'] >= 30:
            checks.append((
                '反弹日卖出 必清 → avg 5d < -1% (卖了后继续跌)',
                (mc_r['mean'] or 0) < -1,
                f'必清 avg={format_pct(mc_r["mean"])} (n={mc_r["n"]})'
            ))
        else:
            checks.append(('反弹日卖出 必清 → avg 5d < -1%', None, f'⚠️ n={mc_r["n"]}'))

        if rw_r['n'] >= 30:
            checks.append((
                '反弹日卖出 减仓可等 → avg 5d ≥ 0% (卖了后不跌)',
                (rw_r['mean'] or 0) >= 0,
                f'减仓 avg={format_pct(rw_r["mean"])} (n={rw_r["n"]})'
            ))
        else:
            checks.append(('反弹日卖出 减仓可等 → avg 5d ≥ 0%', None, f'⚠️ n={rw_r["n"]}'))

        if mc_r['n'] >= 30 and rw_r['n'] >= 30:
            checks.append((
                '反弹日卖出 必清 return < 减仓 return (优先级正确)',
                (mc_r['mean'] or 0) < (rw_r['mean'] or 0),
                f'必清={format_pct(mc_r["mean"])} vs 减仓={format_pct(rw_r["mean"])}'
            ))

        self._print_checks(checks)
        all_pass = all(c[1] is not False for c in checks)
        self._record_result(3, '反弹减仓优先级', all_pass)
        print(f'结论: {"规则成立 ✅" if all_pass else "规则存疑 ⚠️"} (注: 依赖规则 1 的代理分类)\n')

    # ══════════════════════════════════════════════════════════
    # 规则 4: SOX 涨 = 减仓窗口
    # ══════════════════════════════════════════════════════════

    def test_rule4_sox_sell_window(self):
        """验证 SOX > 3% 次日, A 股半导体买入 vs 卖出的收益对比"""
        self._print_rule_header(4, 'SOX 涨 = 减仓窗口，不是加仓窗口')
        print('验证: SOX > 3% 次日，A 股半导体开盘买入 vs 开盘卖出 (持有)，哪个收益更好')
        print(f'数据范围: {BACKTEST_START} ~ {DATA_END}')

        self._load_sox()
        semi_codes = self._get_semiconductor_codes()
        if not semi_codes:
            print('⚠️ 未找到半导体板块股票, 使用全 A 股替代')
            semi_codes = self._get_all_codes()
        self._load_daily(semi_codes)

        # 按 SOX 强度分段
        segments = [(3, 5, '+3~5%'), (5, 7, '+5~7%'), (7, 15, '+7%+')]
        all_segments = [(3, 15, '+3%+ (合并)')] + segments

        for lo, hi, seg_label in all_segments:
            buy_returns = {1: [], 5: [], 10: [], 20: []}
            sell_returns = {1: [], 5: [], 10: [], 20: []}

            for sox_date, sox_chg in self._sox.items():
                if not (lo <= sox_chg < hi):
                    continue
                if sox_date < BACKTEST_START or sox_date > DATA_END:
                    continue

                # 对每只半导体股票, 计算买入/卖出后的收益
                for code in semi_codes:
                    full = get_code_suffix(code)
                    if sox_date not in self._daily.get(full, {}):
                        continue
                    dates = self._get_sorted_dates(full)
                    try:
                        idx = dates.index(sox_date)
                    except ValueError:
                        continue
                    if idx + 1 >= len(dates):
                        continue
                    next_date = dates[idx + 1]
                    # 确保是下一个交易日 (间隔 ≤ 2 天)
                    from datetime import date as dt_date
                    sd = dt_date(*map(int, sox_date.split('-')))
                    nd = dt_date(*map(int, next_date.split('-')))
                    if (nd - sd).days > 2:
                        continue

                    curr_close = self._daily[full][sox_date]['close']
                    if curr_close <= 0:
                        continue

                    # 计算 forward returns
                    for period in [1, 5, 10, 20]:
                        if idx + period >= len(dates):
                            continue
                        future_close = self._daily[full][dates[idx + period]]['close']
                        ret = (future_close / curr_close - 1) * 100
                        buy_returns[period].append(ret)
                        sell_returns[period].append(-ret)  # 卖出 = 相反的收益

            # 打印结果
            if sum(len(buy_returns[p]) for p in [1, 5, 10, 20]) == 0:
                continue

            print(f'\n--- SOX {seg_label}: {len(buy_returns[5])} 条股票-日记录 ---')
            buy_s = stats_summary(buy_returns[5])
            sell_s = stats_summary(sell_returns[5])
            self._print_result_table([
                ('次日买入(持有)', buy_s),
                ('次日卖出', sell_s),
            ])

            print(f'  详细周期:')
            period_rows = []
            for p in [1, 5, 10, 20]:
                bs = stats_summary(buy_returns[p])
                period_rows.append((f'买入 {p}d', bs))
            self._print_result_table(period_rows)

            # 检查项
            checks = []
            if buy_s['n'] >= 30:
                checks.append((
                    f'SOX {seg_label}: 买入 avg 5d < 0?',
                    (buy_s['mean'] or 0) < 0,
                    f'买入 avg={format_pct(buy_s["mean"])}'
                ))
                checks.append((
                    f'SOX {seg_label}: 买入 win_rate < 50%?',
                    (buy_s['win_rate'] or 100) < 50,
                    f'买入 win_rate={buy_s["win_rate"]:.1f}%'
                ))
                checks.append((
                    f'SOX {seg_label}: 卖出 avg 5d > 0?',
                    (sell_s['mean'] or 0) > 0,
                    f'卖出 avg={format_pct(sell_s["mean"])}'
                ))
            else:
                checks.append((f'SOX {seg_label}', None, f'⚠️ 样本不足 (n={buy_s["n"]})'))

            self._print_checks(checks)

        # 汇总: 重新计算全部分段的买入收益
        all_buy_5d = []
        all_seg_pass = True
        for lo, hi, seg_label in all_segments:
            seg_buy = []
            for sox_date, sox_chg in self._sox.items():
                if not (lo <= sox_chg < hi):
                    continue
                if sox_date < BACKTEST_START or sox_date > DATA_END:
                    continue
                for code in semi_codes:
                    full = get_code_suffix(code)
                    if sox_date not in self._daily.get(full, {}):
                        continue
                    dates = self._get_sorted_dates(full)
                    try:
                        idx = dates.index(sox_date)
                    except ValueError:
                        continue
                    if idx + 5 >= len(dates):
                        continue
                    curr_close = self._daily[full][sox_date]['close']
                    if curr_close <= 0:
                        continue
                    future_close = self._daily[full][dates[idx + 5]]['close']
                    ret = (future_close / curr_close - 1) * 100
                    all_buy_5d.append(ret)
                    seg_buy.append(ret)

            seg_s = stats_summary(seg_buy)
            if seg_s['n'] >= 30:
                if (seg_s['mean'] or 0) >= 0:
                    all_seg_pass = False

        total_check = all_seg_pass and len(all_buy_5d) > 0
        self._record_result(4, 'SOX = 减仓窗口', total_check)
        print(f'结论: {"规则成立 ✅" if total_check else "需关注 ⚠️"}\n')

    # ══════════════════════════════════════════════════════════
    # 规则 5: CPI/宏观事件前不加仓
    # ══════════════════════════════════════════════════════════

    def test_rule5_macro_events(self):
        """验证宏观事件前后买入的收益差异"""
        self._print_rule_header(5, 'CPI/宏观事件前不加仓')
        print('验证: 宏观事件前买入 vs 事件后买入, 5d/10d 收益对比')
        print('方法: 使用硬编码的 CPI+FOMC 日期表')
        print('⚠️ 低置信度: 样本量小, 无法控制其他变量, 日期需手动维护')
        print(f'数据范围: {BACKTEST_START} ~ {DATA_END}')

        codes = self._get_all_codes()
        self._load_daily(codes)

        before_returns = {5: [], 10: [], 20: []}
        after_returns = {5: [], 10: [], 20: []}

        matched_events = 0
        for event_date in MACRO_EVENTS:
            if event_date < BACKTEST_START or event_date > DATA_END:
                continue
            matched_events += 1

            for code in codes:
                full = get_code_suffix(code)
                dates = self._get_sorted_dates(full)
                if event_date not in dates:
                    continue
                idx = dates.index(event_date)
                # 事件前 3 天买入
                if idx - 3 >= 0:
                    before_date = dates[idx - 3]
                    fwd = self._forward_returns(full, before_date)
                    if fwd:
                        for p in [5, 10, 20]:
                            if fwd.get(p) is not None:
                                before_returns[p].append(fwd[p])
                # 事件后 3 天买入
                if idx + 3 < len(dates):
                    after_date = dates[idx + 3]
                    fwd = self._forward_returns(full, after_date)
                    if fwd:
                        for p in [5, 10, 20]:
                            if fwd.get(p) is not None:
                                after_returns[p].append(fwd[p])

        print(f'匹配宏观事件: {matched_events} 天')
        print(f'事件前买入样本: {len(before_returns[5])} 条')
        print(f'事件后买入样本: {len(after_returns[5])} 条')

        # 按周期对比
        rows = []
        for p in [5, 10, 20]:
            b = stats_summary(before_returns[p])
            a = stats_summary(after_returns[p])
            rows.append((f'事件前买入 {p}d', b))
            rows.append((f'事件后买入 {p}d', a))
        self._print_result_table(rows)

        checks = []
        for p in [5, 10, 20]:
            b = stats_summary(before_returns[p])
            a = stats_summary(after_returns[p])
            if b['n'] >= 30 and a['n'] >= 30:
                checks.append((
                    f'{p}d: 事件前买入 < 事件后买入?',
                    (b['mean'] or 0) < (a['mean'] or 0),
                    f'前={format_pct(b["mean"])} vs 后={format_pct(a["mean"])}'
                ))
                checks.append((
                    f'{p}d: 事件前波动 > 事件后?',
                    (b['std'] or 0) > (a['std'] or 0),
                    f'前 std={format_pct(b["std"])} vs 后 std={format_pct(a["std"])}'
                ))
            else:
                checks.append((f'{p}d 对比', None, f'⚠️ 样本不足 (前={b["n"]}, 后={a["n"]})'))

        self._print_checks(checks)
        all_pass = matched_events >= 10
        self._record_result(5, '宏观事件前不加仓', all_pass)
        print(f'结论: {"规则成立 ✅" if all_pass else "样本不足 ⚠️"} (低置信度, 手工日期表)\n')

    # ══════════════════════════════════════════════════════════
    # 规则 6: 突破 vs 见顶 四维确认
    # ══════════════════════════════════════════════════════════

    def test_rule6_four_dim(self):
        """验证四维评分能否区分突破和见顶"""
        self._print_rule_header(6, '突破 vs 见顶 — 四维确认体系')
        print('验证: 四维得分 ≥3 突破 vs ≥3 见顶 vs 平局的 forward return 是否有显著差异')
        print(f'数据范围: {BACKTEST_START} ~ {DATA_END}')

        codes = self._get_all_codes()
        self._load_daily(codes)

        groups = {
            'breakthrough': [],  # ≥3 breakthrough
            'neutral': [],       # 2:2
            'topping': [],       # ≥3 topping
        }

        processed = 0
        for code in codes:
            full = get_code_suffix(code)
            dates = self._get_sorted_dates(full)
            for d in dates:
                if d < BACKTEST_START or d > DATA_END:
                    continue
                score = self._score_four_dim(full, d)
                if score is None:
                    continue
                bt, tp = score
                if bt >= 3:
                    group = 'breakthrough'
                elif tp >= 3:
                    group = 'topping'
                else:
                    group = 'neutral'

                fwd = self._forward_returns(full, d)
                if fwd and fwd.get(5) is not None:
                    groups[group].append(fwd[5])
                    processed += 1

        print(f'样本: {processed} 条评分事件')

        rows = [
            ('≥3 突破', stats_summary(groups['breakthrough'])),
            ('2:2 平局', stats_summary(groups['neutral'])),
            ('≥3 见顶', stats_summary(groups['topping'])),
        ]
        self._print_result_table(rows)

        # 涨停炸板场景: 看四维得分能否预测次日方向
        zhuban_fwd = {'封板': [], '炸板': []}
        zhuban_4d = {'封板_突破': [], '封板_见顶': [], '炸板_突破': [], '炸板_见顶': []}
        for code in codes:
            full = get_code_suffix(code)
            dates = self._get_sorted_dates(full)
            data = self._daily[full]
            for d in dates:
                if d < BACKTEST_START or d > DATA_END:
                    continue
                row = data[d]
                dates_idx = dates.index(d)
                if dates_idx < 1:
                    continue
                prev_close = data[dates[dates_idx - 1]]['close']
                if prev_close <= 0:
                    continue
                daily_high_chg = (row['high'] / prev_close - 1) * 100
                if daily_high_chg < 9.8:
                    continue
                # 触及涨停
                close_from_top = (row['high'] - row['close']) / row['high'] * 100 if row['high'] > 0 else 0
                if close_from_top > 3:
                    key = '炸板'
                elif close_from_top < 1:
                    key = '封板'
                else:
                    continue

                fwd = self._forward_returns(full, d)
                if fwd and fwd.get(5) is not None:
                    zhuban_fwd[key].append(fwd[5])
                # 看四维得分预测
                score = self._score_four_dim(full, d)
                if score and fwd and fwd.get(1) is not None:
                    bt_s, tp_s = score
                    if bt_s >= 3:
                        zhuban_4d[f'{key}_突破'].append(fwd[1])
                    elif tp_s >= 3:
                        zhuban_4d[f'{key}_见顶'].append(fwd[1])

        print('涨停炸板场景 (5d forward return):')
        fb_fwd = stats_summary(zhuban_fwd['封板'])
        zb_fwd = stats_summary(zhuban_fwd['炸板'])
        if fb_fwd['n'] > 0 or zb_fwd['n'] > 0:
            self._print_result_table([
                ('封板 5d', fb_fwd),
                ('炸板 5d', zb_fwd),
            ])

        print('四维得分预测 炸板/封板 次日方向:')
        zhd_rows = []
        for k in ['封板_突破', '封板_见顶', '炸板_突破', '炸板_见顶']:
            s = stats_summary(zhuban_4d[k])
            if s['n'] > 0:
                zhd_rows.append((k, s))
        if zhd_rows:
            self._print_result_table(zhd_rows)

        # 检查项
        bt_s = stats_summary(groups['breakthrough'])
        nt_s = stats_summary(groups['neutral'])
        tp_s = stats_summary(groups['topping'])

        checks = []
        if bt_s['n'] >= 30:
            checks.append((
                '≥3 突破组 avg 5d > +0.5%',
                (bt_s['mean'] or 0) > 0.5,
                f'突破 avg={format_pct(bt_s["mean"])} (n={bt_s["n"]})'
            ))
        else:
            checks.append(('≥3 突破组 avg 5d > +0.5%', None, f'⚠️ n={bt_s["n"]}'))

        if tp_s['n'] >= 30:
            checks.append((
                '≥3 见顶组 avg 5d < -0.5%',
                (tp_s['mean'] or 0) < -0.5,
                f'见顶 avg={format_pct(tp_s["mean"])} (n={tp_s["n"]})'
            ))
        else:
            checks.append(('≥3 见顶组 avg 5d < -0.5%', None, f'⚠️ n={tp_s["n"]}'))

        if bt_s['n'] >= 30 and nt_s['n'] >= 30 and tp_s['n'] >= 30:
            monotonic = (bt_s['mean'] or 0) > (nt_s['mean'] or 0) > (tp_s['mean'] or 0)
            checks.append((
                '三组单调递减 (突破 > 平局 > 见顶)',
                monotonic,
                f'突破={format_pct(bt_s["mean"])} 平局={format_pct(nt_s["mean"])} 见顶={format_pct(tp_s["mean"])}'
            ))

        if bt_s['n'] >= 30 and tp_s['n'] >= 30:
            checks.append((
                '突破 win_rate - 见顶 win_rate > 10%',
                (bt_s['win_rate'] or 0) - (tp_s['win_rate'] or 0) > 10,
                f'突破={bt_s["win_rate"]:.1f}% vs 见顶={tp_s["win_rate"]:.1f}%'
            ))

        self._print_checks(checks)
        all_pass = all(c[1] is not False for c in checks)
        self._record_result(6, '四维确认', all_pass)
        print(f'结论: {"规则成立 ✅" if all_pass else "规则存疑 ⚠️"}\n')

    # ══════════════════════════════════════════════════════════
    # 规则 7: 收盘判断 ≠ 盘中判断 (假跌破等 3 天)
    # ══════════════════════════════════════════════════════════

    def test_rule7_fake_breakdown(self):
        """验证 MA20 跌破后等 3 天 vs 立刻卖出的优劣"""
        self._print_rule_header(7, '收盘判断 ≠ 盘中判断 — 假跌破等 3 天')
        print('验证: MA20 跌破后, 策略 A (立刻卖) vs 策略 B (等 3 天), 哪个收益更好')
        print(f'数据范围: {BACKTEST_START} ~ {DATA_END}')

        codes = self._get_all_codes()
        self._load_daily(codes)

        strategy_a = []  # 立刻卖
        strategy_b = []  # 等 3 天
        recovery_rates = {}  # {code: (breakdowns, recoveries)}

        for code in codes:
            full = get_code_suffix(code)
            events = self._identify_ma_breakdown(full)
            breakdowns = 0
            recoveries = 0
            for event_date in events:
                if event_date < BACKTEST_START or event_date > DATA_END:
                    continue
                breakdowns += 1
                dates = self._get_sorted_dates(full)
                idx = dates.index(event_date)

                # 策略 A: 跌破日收盘卖出
                fwd_a = self._forward_returns(full, event_date)
                if fwd_a and fwd_a.get(20) is not None:
                    strategy_a.append(fwd_a[20])

                # 策略 B: 等 3 天
                if idx + 3 < len(dates):
                    day3_date = dates[idx + 3]
                    day3_close = self._daily[full][day3_date]['close']
                    day3_ma20 = self._calc_ma20(full, day3_date)
                    if day3_ma20 and day3_close > day3_ma20:
                        recoveries += 1
                        # 站回 MA20 → 留 (不计算卖出收益)
                    else:
                        # 没站回 → 第 3 天收盘卖出
                        fwd_b = self._forward_returns(full, day3_date)
                        if fwd_b and fwd_b.get(20) is not None:
                            strategy_b.append(fwd_b[20])
                else:
                    # 等不到第 3 天, 按策略 A 处理
                    if fwd_a and fwd_a.get(20) is not None:
                        strategy_b.append(fwd_a[20])

            if breakdowns > 0:
                recovery_rates[code] = (breakdowns, recoveries)

        # 计算恢复率, 分层
        high_recovery = []  # > 60%
        low_recovery = []   # < 40%
        for code, (bd, rc) in recovery_rates.items():
            rate = rc / bd * 100 if bd > 0 else 0
            if rate > 60:
                high_recovery.append(code)
            elif rate < 40:
                low_recovery.append(code)

        print(f'总 MA20 跌破事件: {len(strategy_a)}')
        print(f'假跌破恢复率 > 60% 的股票: {len(high_recovery)} 只')
        print(f'假跌破恢复率 < 40% 的股票: {len(low_recovery)} 只')

        sa = stats_summary(strategy_a)
        sb = stats_summary(strategy_b)
        print('\n全局对比 (20d forward return):')
        self._print_result_table([
            ('策略 A: 立刻卖', sa),
            ('策略 B: 等 3 天', sb),
        ])

        checks = []
        if sa['n'] >= 30 and sb['n'] >= 30:
            checks.append((
                '全局: 策略 B 20d return > 策略 A (等 3 天更好)',
                (sb['mean'] or 0) > (sa['mean'] or 0),
                f'A={format_pct(sa["mean"])} vs B={format_pct(sb["mean"])}'
            ))
            checks.append((
                '全局: 策略 B win_rate > 策略 A',
                (sb['win_rate'] or 0) > (sa['win_rate'] or 0),
                f'A win={sa["win_rate"]:.1f}% vs B win={sb["win_rate"]:.1f}%'
            ))
        else:
            checks.append(('全局对比', None, f'⚠️ 样本不足 (A={sa["n"]}, B={sb["n"]})'))

        self._print_checks(checks)
        all_pass = all(c[1] is not False for c in checks)
        self._record_result(7, '假跌破等 3 天', all_pass)
        print(f'结论: {"规则成立 ✅" if all_pass else "规则存疑 ⚠️"}\n')

    # ══════════════════════════════════════════════════════════
    # 规则 8: 最弱票不一定会继续弱
    # ══════════════════════════════════════════════════════════

    def test_rule8_weakest_rebound(self):
        """验证反弹日最弱票是否补涨"""
        self._print_rule_header(8, '最弱票不一定会继续弱 — 反弹日补涨效应')
        print('验证: 反弹日, 同板块中最弱票的次日反弹幅度是否最大')
        print(f'数据范围: {BACKTEST_START} ~ {DATA_END}')

        self._load_stock_meta()
        codes = self._get_all_codes()
        self._load_daily(codes)

        # 按 sw1 分组
        sector_stocks = defaultdict(list)
        for code in codes:
            meta = self._meta.get(code, {})
            sw1 = meta.get('sw1', '')
            if sw1:
                sector_stocks[sw1].append(code)

        # 只分析有足够股票的板块
        large_sectors = {s: stks for s, stks in sector_stocks.items() if len(stks) >= 20}

        weakest_next_returns = []
        strongest_next_returns = []
        weakest_sell_5d = []    # 卖出最弱的 5d 收益
        strongest_sell_5d = []  # 卖出最强的 5d 收益
        sector_results = {}

        for sw1, sector_codes in large_sectors.items():
            sector_weakest = []
            sector_strongest = []
            sector_wsell = []
            sector_ssell = []

            for code in sector_codes:
                full = get_code_suffix(code)
                dates = self._get_sorted_dates(full)
                data = self._daily[full]
                for i in range(5, len(dates)):
                    d = dates[i]
                    if d < BACKTEST_START or d > DATA_END:
                        continue

                    # 计算近 5 日收益
                    ret_5d = (data[d]['close'] / data[dates[i - 5]]['close'] - 1) * 100
                    if ret_5d is None:
                        continue

                    # 判断是否是反弹日 (按板块)
                    # 简化: 用该股自身判断
                    if i < 3:
                        continue
                    ret_3d = (data[dates[i - 1]]['close'] / data[dates[i - 4]]['close'] - 1) * 100
                    daily_ret = (data[d]['close'] / data[dates[i - 1]]['close'] - 1) * 100
                    if not (ret_3d <= -3 and daily_ret >= 1.5):
                        continue

                    # 在该板块内找所有股票的近 5 日收益
                    sector_5d_rets = {}
                    for sc in sector_codes:
                        sfull = get_code_suffix(sc)
                        sdates = self._get_sorted_dates(sfull)
                        if d not in self._daily.get(sfull, {}):
                            continue
                        sidx = sdates.index(d) if d in sdates else -1
                        if sidx < 5:
                            continue
                        sdata = self._daily[sfull]
                        sret = (sdata[d]['close'] / sdata[sdates[sidx - 5]]['close'] - 1) * 100
                        sector_5d_rets[sc] = sret

                    if len(sector_5d_rets) < 10:
                        continue

                    sorted_stocks = sorted(sector_5d_rets.items(), key=lambda x: x[1])
                    n = len(sorted_stocks)
                    quintile = n // 5
                    weakest_cut = sorted_stocks[:max(1, quintile)]
                    strongest_cut = sorted_stocks[-max(1, quintile):]

                    # 次日收益
                    if i + 1 < len(dates):
                        for sc, _ in weakest_cut:
                            sfull = get_code_suffix(sc)
                            sdata = self._daily[sfull]
                            sdates = self._get_sorted_dates(sfull)
                            if d not in self._daily.get(sfull, {}):
                                continue
                            sidx = sdates.index(d) if d in sdates else -1
                            if sidx < 0 or sidx + 1 >= len(sdates):
                                continue
                            nr = (sdata[sdates[sidx + 1]]['close'] / sdata[d]['close'] - 1) * 100
                            sector_weakest.append(nr)
                            weakest_next_returns.append(nr)

                            # 卖出最弱: 跟踪 5d
                            fwd = self._forward_returns(sfull, d)
                            if fwd and fwd.get(5) is not None:
                                sector_wsell.append(fwd[5])
                                weakest_sell_5d.append(fwd[5])

                        for sc, _ in strongest_cut:
                            sfull = get_code_suffix(sc)
                            sdata = self._daily[sfull]
                            sdates = self._get_sorted_dates(sfull)
                            if d not in self._daily.get(sfull, {}):
                                continue
                            sidx = sdates.index(d) if d in sdates else -1
                            if sidx < 0 or sidx + 1 >= len(sdates):
                                continue
                            nr = (sdata[sdates[sidx + 1]]['close'] / sdata[d]['close'] - 1) * 100
                            sector_strongest.append(nr)
                            strongest_next_returns.append(nr)

                            fwd = self._forward_returns(sfull, d)
                            if fwd and fwd.get(5) is not None:
                                sector_ssell.append(fwd[5])
                                strongest_sell_5d.append(fwd[5])

            if len(sector_weakest) >= 10:
                sector_results[sw1] = {
                    'weakest': stats_summary(sector_weakest),
                    'strongest': stats_summary(sector_strongest),
                }

        print(f'分析板块: {len(sector_results)} 个 (≥10 样本)')

        wk = stats_summary(weakest_next_returns)
        st = stats_summary(strongest_next_returns)
        print('\n反弹日次日收益 (全部板块):')
        self._print_result_table([
            ('最弱 20%', wk),
            ('最强 20%', st),
        ])

        wk_sell = stats_summary(weakest_sell_5d)
        st_sell = stats_summary(strongest_sell_5d)
        print('反弹日卖出 5d forward return:')
        self._print_result_table([
            ('卖出最弱 20%', wk_sell),
            ('卖出最强 20%', st_sell),
        ])

        # 按板块统计符合规律的占比
        strongest_better = sum(1 for sw1, res in sector_results.items()
                              if (res['weakest']['mean'] or -999) > (res['strongest']['mean'] or 999))
        checks = []
        if wk['n'] >= 30 and st['n'] >= 30:
            checks.append((
                '最弱组次日 avg return > 最强组 (补涨效应)',
                (wk['mean'] or 0) > (st['mean'] or 0),
                f'最弱={format_pct(wk["mean"])} vs 最强={format_pct(st["mean"])}'
            ))
        else:
            checks.append(('最弱 vs 最强 次日对比', None, f'⚠️ n={wk["n"]}/{st["n"]}'))

        if wk_sell['n'] >= 30:
            checks.append((
                '卖出最弱 avg 5d return > 0 (卖了后涨了, 不该卖)',
                (wk_sell['mean'] or 0) > 0,
                f'卖出最弱 avg={format_pct(wk_sell["mean"])} (n={wk_sell["n"]})'
            ))
        else:
            checks.append(('卖出最弱 5d 收益', None, f'⚠️ n={wk_sell["n"]}'))

        if len(sector_results) > 0:
            pct = strongest_better / len(sector_results) * 100
            checks.append((
                f'≥60% 板块符合 最弱 > 最强 规律 ({strongest_better}/{len(sector_results)}={pct:.0f}%)',
                pct >= 60,
                ''
            ))

        self._print_checks(checks)
        all_pass = all(c[1] is not False for c in checks)
        self._record_result(8, '最弱票补涨', all_pass)
        print(f'结论: {"规则成立 ✅" if all_pass else "规则存疑 ⚠️"}\n')

    # ══════════════════════════════════════════════════════════
    # 规则 9: 每只股票有自己的风格
    # ══════════════════════════════════════════════════════════

    def test_rule9_stock_personality(self):
        """验证 7 只持仓的个体特征"""
        self._print_rule_header(9, '每只股票有自己的风格 — 7 只持仓特征验证')
        print('验证: trading_plan.md 中对 7 只持仓的特征描述是否在更长数据上成立')
        print(f'数据范围: 2022-01-01 ~ {DATA_END}')
        print('   注: 统计结论 ≠ 交易策略, 仅供特征验证')

        codes = list(STOCK_PERSONALITIES.keys())
        self._load_daily(codes, start='2022-01-01', end=self.end_date)

        results = {}
        all_checks_pass = 0
        total_checks = 0

        for code in codes:
            full = get_code_suffix(code)
            info = STOCK_PERSONALITIES[code]
            name = info['name']
            dates = self._get_sorted_dates(full)
            data = self._daily.get(full, {})

            if not dates:
                print(f'\n  {code} {name}: ⚠️ 无数据')
                continue

            print(f'\n  ─── {code} {name} ───')
            print(f'  描述: {info["feature"]}')
            print(f'  数据: {len(dates)} 个交易日 ({dates[0]} ~ {dates[-1]})')

            stock_checks = []

            # ── 长电科技 (600584): 高开后 8 成收跌 ──
            if code == '600584':
                high_open_count = 0
                high_open_down = 0
                for i in range(1, len(dates)):
                    prev_close = data[dates[i - 1]]['close']
                    row = data[dates[i]]
                    if row['open'] > prev_close:
                        high_open_count += 1
                        if row['close'] < row['open']:  # 低走: 收盘 < 开盘
                            high_open_down += 1
                pct = high_open_down / high_open_count * 100 if high_open_count > 0 else 0
                expected = info.get('expected_pct', 80)
                check_pass = pct >= 70
                results[code] = {'check': f'高开后低走 (close < open)', 'actual': f'{pct:.1f}%',
                                'expected': f'{expected}%', 'pass': check_pass,
                                'sample': high_open_count}
                if check_pass: all_checks_pass += 1
                total_checks += 1
                status = '✅' if check_pass else '❌'
                print(f'    {status} 高开后低走比例: {pct:.1f}% (期望 {expected}%, n={high_open_count})')
                # 也检查高开后收跌 (vs prev_close)
                high_open_close_down = sum(1 for i in range(1, len(dates))
                                          if data[dates[i]]['open'] > data[dates[i-1]]['close']
                                          and data[dates[i]]['close'] < data[dates[i-1]]['close'])
                pct2 = high_open_close_down / high_open_count * 100 if high_open_count > 0 else 0
                print(f'      注: 高开后收跌 (vs prev_close): {pct2:.1f}%')

            # ── 东山精密 (002384): 假跌破恢复率 67% ──
            elif code == '002384':
                events = self._identify_ma_breakdown(full)
                breakdowns = len(events)
                recoveries = 0
                for ed in events:
                    idx = dates.index(ed)
                    if idx + 3 < len(dates):
                        d3 = dates[idx + 3]
                        ma20_d3 = self._calc_ma20(full, d3)
                        if ma20_d3 and data[d3]['close'] > ma20_d3:
                            recoveries += 1
                rate = recoveries / breakdowns * 100 if breakdowns > 0 else 0
                expected = info.get('fake_breakdown_pct', 67)
                check_pass = rate > 60
                results[code] = {'check': '假跌破恢复率', 'actual': f'{rate:.1f}%',
                                'expected': f'{expected}%', 'pass': check_pass,
                                'sample': breakdowns}
                if check_pass: all_checks_pass += 1
                total_checks += 1
                diff = abs(rate - expected)
                status = '✅' if check_pass else '❌'
                print(f'    {status} 假跌破恢复率: {rate:.1f}% (期望 {expected}%, n={breakdowns})')
                if diff > 10:
                    print(f'      偏差 {diff:.0f}%, 原称 {expected}%, 实际 {rate:.1f}%')

                # 验证 etc: 等 3 天 vs 立刻卖
                print(f'    策略验证 (等 3 天 vs 立刻卖):')
                a_returns = []
                b_returns = []
                for ed in events:
                    if ed < BACKTEST_START:
                        continue
                    fwd_a = self._forward_returns(full, ed)
                    if fwd_a and fwd_a.get(10) is not None:
                        a_returns.append(fwd_a[10])
                    idx_e = dates.index(ed)
                    if idx_e + 3 < len(dates):
                        d3 = dates[idx_e + 3]
                        ma20_d3 = self._calc_ma20(full, d3)
                        if ma20_d3 and data[d3]['close'] > ma20_d3:
                            continue  # 站回, 不卖
                        fwd_b = self._forward_returns(full, d3)
                        if fwd_b and fwd_b.get(10) is not None:
                            b_returns.append(fwd_b[10])
                a_s = stats_summary(a_returns)
                b_s = stats_summary(b_returns)
                print(f'      立刻卖 10d: avg={format_pct(a_s["mean"])}, win={a_s["win_rate"]:.0f}% (n={a_s["n"]})')
                print(f'      等 3 天 10d: avg={format_pct(b_s["mean"])}, win={b_s["win_rate"]:.0f}% (n={b_s["n"]})')

            # ── 中芯国际 (688981): 假跌破惯性 ──
            elif code == '688981':
                events = self._identify_ma_breakdown(full)
                breakdowns = len(events)
                recoveries = 0
                for ed in events:
                    idx = dates.index(ed)
                    if idx + 3 < len(dates):
                        d3 = dates[idx + 3]
                        ma20_d3 = self._calc_ma20(full, d3)
                        if ma20_d3 and data[d3]['close'] > ma20_d3:
                            recoveries += 1
                rate = recoveries / breakdowns * 100 if breakdowns > 0 else 0
                expected = info.get('fake_breakdown_pct', 60)
                check_pass = rate > 55
                results[code] = {'check': '假跌破恢复率', 'actual': f'{rate:.1f}%',
                                'expected': f'{expected}%', 'pass': check_pass,
                                'sample': breakdowns}
                if check_pass: all_checks_pass += 1
                total_checks += 1
                status = '✅' if check_pass else '❌'
                print(f'    {status} 假跌破恢复率: {rate:.1f}% (期望 {expected}%, n={breakdowns})')
                if abs(rate - expected) > 10:
                    print(f'      偏差 {abs(rate - expected):.0f}%, 原称 {expected}%, 实际 {rate:.1f}%')

            # ── 顺络电子 (002138): 连涨 6 天不回调是常态 ──
            elif code == '002138':
                # 找到所有连续上涨事件
                streaks = []
                current_streak = 0
                for i in range(1, len(dates)):
                    if data[dates[i]]['close'] > data[dates[i - 1]]['close']:
                        current_streak += 1
                    else:
                        if current_streak >= 3:
                            streaks.append(current_streak)
                        current_streak = 0
                if current_streak >= 3:
                    streaks.append(current_streak)

                max_streak = max(streaks) if streaks else 0
                # 连续 N 天后第 N+1 天继续涨的概率
                if streaks:
                    streak_continue = {}
                    for s in range(3, min(max_streak + 1, 10)):
                        idxs = []
                        current_s = 0
                        for i in range(1, len(dates)):
                            if data[dates[i]]['close'] > data[dates[i - 1]]['close']:
                                current_s += 1
                                if current_s == s:
                                    idxs.append(i)
                            else:
                                current_s = 0
                        if idxs:
                            continued = sum(1 for idx in idxs
                                           if idx + 1 < len(dates) and
                                           data[dates[idx + 1]]['close'] > data[dates[idx]]['close'])
                            streak_continue[s] = (continued, len(idxs))
                else:
                    streak_continue = {}

                check_pass = max_streak >= 5
                results[code] = {'check': '最长连涨 ≥ 5 天', 'actual': f'{max_streak} 天',
                                'expected': '≥6 天', 'pass': check_pass,
                                'sample': len(streaks)}
                if check_pass: all_checks_pass += 1
                total_checks += 1
                status = '✅' if check_pass else '❌'
                print(f'    {status} 最长连涨: {max_streak} 天 (期望 ≥6, {len(streaks)} 段连涨)')
                for s in sorted(streak_continue.keys()):
                    c, n = streak_continue[s]
                    print(f'      连续涨 {s} 天后, 第 {s+1} 天继续涨: {c}/{n} = {c/n*100:.0f}%')

            # ── 沪电股份 (002463): 回调浅 (8-11%), 假跌破偏多 ──
            elif code == '002463':
                # 计算最大回撤分布
                peaks = []
                for i in range(20, len(dates)):
                    prev_20_high = max(data[d]['close'] for d in dates[max(0, i-20):i])
                    current = data[dates[i]]['close']
                    dd = (current / prev_20_high - 1) * 100 if prev_20_high > 0 else 0
                    if dd < 0:
                        peaks.append(dd)
                if peaks:
                    mean_dd = sum(peaks) / len(peaks)
                    median_dd = statistics.median(peaks)
                    print(f'    20 日最大回撤: mean={mean_dd:.1f}%, median={median_dd:.1f}%')
                    in_range = sum(1 for x in peaks if -11 <= x <= -8)
                    print(f'    回调在 8-11% 区间: {in_range}/{len(peaks)} = {in_range/len(peaks)*100:.1f}%')

                # 假跌破恢复率
                events = self._identify_ma_breakdown(full)
                bd = len(events)
                rc = 0
                for ed in events:
                    idx = dates.index(ed)
                    if idx + 3 < len(dates):
                        d3 = dates[idx + 3]
                        ma20_d3 = self._calc_ma20(full, d3)
                        if ma20_d3 and data[d3]['close'] > ma20_d3:
                            rc += 1
                rate = rc / bd * 100 if bd > 0 else 0
                check_pass = rate > 50
                results[code] = {'check': '假跌破恢复率 > 50%', 'actual': f'{rate:.1f}%',
                                'expected': '>50%', 'pass': check_pass, 'sample': bd}
                if check_pass: all_checks_pass += 1
                total_checks += 1
                status = '✅' if check_pass else '❌'
                print(f'    {status} 假跌破恢复率: {rate:.1f}% (期望 >50%, n={bd})')

            # ── 兆易创新 (603986): 高开低走概率最高 ──
            elif code == '603986':
                # 计算当前股的高开低走比例
                high_open_count = 0
                high_open_down = 0
                for i in range(1, len(dates)):
                    prev_close = data[dates[i - 1]]['close']
                    row = data[dates[i]]
                    if row['open'] > prev_close:
                        high_open_count += 1
                        if row['close'] < row['open']:
                            high_open_down += 1

                pct603 = high_open_down / high_open_count * 100 if high_open_count > 0 else 0
                print(f'    高开后低走 (close < open): {pct603:.1f}% (n={high_open_count})')

                # 对比其他所有持仓
                all_holdings = {
                    '600584': '长电科技', '002384': '东山精密', '688981': '中芯国际',
                    '002138': '顺络电子', '002463': '沪电股份',
                    '301591': '肯特股份'
                }
                other_pcts = {}
                for other_code, other_name in all_holdings.items():
                    other_full = get_code_suffix(other_code)
                    other_dates = self._get_sorted_dates(other_full)
                    other_data = self._daily.get(other_full, {})
                    ho = 0
                    hod = 0
                    for i in range(1, len(other_dates)):
                        pc = other_data[other_dates[i - 1]]['close']
                        r = other_data[other_dates[i]]
                        if r['open'] > pc:
                            ho += 1
                            if r['close'] < r['open']:
                                hod += 1
                    opct = hod / ho * 100 if ho > 0 else 0
                    other_pcts[other_name] = opct
                # 排序
                sorted_pcts = sorted(other_pcts.items(), key=lambda x: x[1], reverse=True)
                is_highest = all(pct603 >= v for _, v in sorted_pcts)
                check_pass = is_highest
                results[code] = {'check': '高开低走率 全持仓最高', 'actual': f'{pct603:.1f}%',
                                'expected': '最高', 'pass': check_pass,
                                'sample': high_open_count}
                if check_pass: all_checks_pass += 1
                total_checks += 1
                status = '✅' if check_pass else '❌'
                print(f'    {status} 全持仓高开低走率排名:')
                for nm, p in sorted_pcts:
                    marker = ' ← 兆易' if nm == '兆易创新' else ''
                    print(f'      {nm}: {p:.1f}%{marker}')

            # ── 肯特股份 (301591): 最长连跌 7 天 ──
            elif code == '301591':
                down_streaks = []
                current_down = 0
                down_segments = []  # 每段下跌的幅度
                for i in range(1, len(dates)):
                    if data[dates[i]]['close'] < data[dates[i - 1]]['close']:
                        if current_down == 0:
                            segment_start = data[dates[i - 1]]['close']
                        current_down += 1
                    else:
                        if current_down >= 3:
                            down_streaks.append(current_down)
                            segment_end = data[dates[i - 1]]['close']
                            down_segments.append((segment_end / segment_start - 1) * 100)
                        current_down = 0
                if current_down >= 3:
                    down_streaks.append(current_down)

                max_down = max(down_streaks) if down_streaks else 0
                expected = info.get('max_consec_down', 7)
                check_pass = max_down >= 6
                results[code] = {'check': '最长连跌 ≥ 6 天', 'actual': f'{max_down} 天',
                                'expected': f'最长 {expected} 天', 'pass': check_pass,
                                'sample': len(down_streaks)}
                if check_pass: all_checks_pass += 1
                total_checks += 1
                status = '✅' if check_pass else '❌'
                print(f'    {status} 最长连跌: {max_down} 天 (期望 ≥{expected}, {len(down_streaks)} 段连跌)')
                if down_streaks:
                    top3 = sorted(down_streaks, reverse=True)[:3]
                    print(f'    最长 3 次连跌天数: {top3}')
                if down_segments:
                    mean_seg = sum(down_segments) / len(down_segments)
                    print(f'    每段下跌平均幅度: {mean_seg:.1f}% (n={len(down_segments)})')
                    max_seg = min(down_segments)
                    print(f'    最大单段跌幅: {max_seg:.1f}%')

        # 汇总
        print(f'\n  ─── 规则 9 汇总 ───')
        for code in codes:
            if code in results:
                r = results[code]
                status = '✅' if r['pass'] else '❌'
                name = STOCK_PERSONALITIES[code]['name']
                print(f'  {status} {code} {name}: {r["check"]} = {r["actual"]} (期望 {r["expected"]}, n={r["sample"]})')
            else:
                print(f'  ⚠️ {code}: 无结果')

        print(f'\n  通过: {all_checks_pass}/{total_checks} 项检查')

        all_pass = all_checks_pass >= max(1, total_checks * 0.75)  # 至少 75% 通过
        self._record_result(9, '股票风格', all_pass)
        print(f'结论: {"整体特征成立 ✅" if all_pass else "部分不符 ⚠️"} (注: 统计结论 ≠ 交易策略)\n')

    # ══════════════════════════════════════════════════════════
    # 规则 10: 超跌反弹因子验证
    # ══════════════════════════════════════════════════════════

    def test_rule10_bounce_factors(self):
        """验证大跌日后 4 个核心因子对次日反弹的预测力"""
        self._print_rule_header(10, '超跌反弹因子验证 — 大跌日次日反弹预测')
        print('假设: 三大指数同步大跌日, "跌幅深度/MA位置/融资资金/板块主线" 能预测次日反弹')
        print(f'数据范围: {BACKTEST_START} ~ {DATA_END}')

        # Step 1: 找所有同步大跌日
        # 从 market_index_tbl 加载三大指数日K数据
        idx_codes = {'000001.SH': '上证', '000688.SH': '科创50', '399006.SZ': '创业板'}
        idx_data_raw = {}
        c = self.conn.cursor()
        for code in idx_codes:
            c.execute('''
                SELECT tradedate, close FROM market_index_tbl
                WHERE index_code=%s AND tradedate >= %s AND tradedate <= %s
                ORDER BY tradedate ASC
            ''', (code, self.start_date, self.end_date))
            rows = c.fetchall()
            idx_data_raw[code] = [(str(r[0]), float(r[1])) for r in rows]
            if not idx_data_raw[code]:
                print(f'  ⚠️ {idx_codes[code]} ({code}) 无数据')
                return
        c.close()

        # 找到大跌日: 上证≥-2%, 科创≥-2.5%, 创业板≥-3%
        crash_days = []
        for i in range(1, len(idx_data_raw['000001.SH'])):
            d = idx_data_raw['000001.SH'][i][0]
            if d < BACKTEST_START or d > DATA_END:
                continue
            sh_chg = idx_data_raw['000001.SH'][i][1] / idx_data_raw['000001.SH'][i-1][1] - 1
            # 找同日的科创50和创业板
            kc_r = self._idx_chg_from_list(idx_data_raw['000688.SH'], d)
            cy_r = self._idx_chg_from_list(idx_data_raw['399006.SZ'], d)
            if kc_r is None or cy_r is None:
                continue
            if sh_chg <= -0.02 and kc_r <= -0.025 and cy_r <= -0.03:
                crash_days.append(d)

        print(f'\n同步大跌日: {len(crash_days)} 天')
        if len(crash_days) < 3:
            print('⚠️ 大跌日样本不足, 无法做统计')
            self._record_result(10, '超跌反弹因子', False)
            return

        # Step 2: 加载全市场数据
        codes = self._get_all_codes()
        self._load_daily(codes)

        # Step 3: 对每个大跌日, 对每只股票计算因子和次日收益
        factor1 = defaultdict(list)  # 跌幅深度
        factor2 = defaultdict(list)  # MA60位置
        factor3 = defaultdict(list)  # (融资数据暂用板块代理)
        factor4 = defaultdict(list)  # 板块效应

        processed = 0
        for crash_date in crash_days:
            for code in codes:
                full = get_code_suffix(code)
                data = self._daily.get(full, {})
                if crash_date not in data:
                    continue
                row = data[crash_date]
                prev_date = self._prev_trade_date(full, crash_date)
                if prev_date is None:
                    continue
                prev_close = data[prev_date]['close']
                if prev_close <= 0:
                    continue
                today_chg = (row['close'] / prev_close - 1) * 100

                # 次日收益
                fwd = self._forward_returns(full, crash_date)
                if fwd is None or fwd.get(1) is None:
                    continue
                next_ret = fwd[1]

                # --- 因子1: 跌幅深度 ---
                if today_chg <= -8:
                    factor1['-8%+ (崩盘)'].append(next_ret)
                elif today_chg <= -5:
                    factor1['-5~-8% (深跌)'].append(next_ret)
                elif today_chg <= -3:
                    factor1['-3~-5% (中跌)'].append(next_ret)
                elif today_chg <= -1:
                    factor1['-1~-3% (小跌)'].append(next_ret)
                else:
                    factor1['+0%+ (抗跌)'].append(next_ret)

                # --- 因子2: MA60 位置 ---
                ma60 = self._calc_ma60(full, crash_date)
                if ma60 and row['close'] > ma60:
                    factor2['MA60上方'].append(next_ret)
                elif ma60:
                    factor2['MA60下方'].append(next_ret)

                # --- 因子3: 长下影/承接 (代理融资信号) ---
                body = abs(row['close'] - row['open'])
                total_range = row['high'] - row['low']
                if total_range > 0:
                    lower_shadow = min(row['close'], row['open']) - row['low']
                    lower_pct = lower_shadow / total_range
                    if lower_pct > 0.5 and body / total_range > 0.1:
                        factor3['有承接(长下影)'].append(next_ret)
                    else:
                        factor3['无承接'].append(next_ret)

                # --- 因子4: 板块主线 ---
                meta = self._meta.get(code, {})
                sw1 = meta.get('sw1', '')
                # 半导体/电子/通信 算主线
                is_mainline = any(k in (sw1 + meta.get('sw2', '') + meta.get('sw3', ''))
                                  for k in ['半导体', '电子', '通信', 'PCB', '芯片', '封测', '光模块'])
                if is_mainline:
                    factor4['主线内'].append(next_ret)
                else:
                    factor4['主线外'].append(next_ret)

                processed += 1

        print(f'分析 {processed} 条股票-大跌日记录')

        # 打印结果
        for factor_dict, label in [
            (factor1, '因子1: 跌幅深度 → 次日收益'),
            (factor2, '因子2: MA60位置 → 次日收益'),
            (factor3, '因子3: 盘中承接 → 次日收益'),
            (factor4, '因子4: 板块主线 → 次日收益'),
        ]:
            print(f'\n─── {label} ───')
            rows = []
            for key in sorted(factor_dict.keys()):
                s = stats_summary(factor_dict[key])
                if s['n'] >= 10:
                    rows.append((key, s))
            self._print_result_table(rows)

        # 检查项
        checks = []
        all_pass = True

        # 因子1: 深跌(5-8%)应该反弹最好
        f1_deep = stats_summary(factor1.get('-5~-8% (深跌)', []))
        f1_mid = stats_summary(factor1.get('-3~-5% (中跌)', []))
        f1_small = stats_summary(factor1.get('-1~-3% (小跌)', []))
        if f1_deep['n'] >= 30:
            deep_better = (f1_deep['mean'] or -99) > (f1_small['mean'] or -99)
            checks.append((f'-5~-8%深跌 avg > -1~-3%小跌', deep_better,
                          f'深跌={format_pct(f1_deep["mean"])} vs 小跌={format_pct(f1_small["mean"])}'))
            if not deep_better: all_pass = False

        # 因子2: MA60上方比下方抗跌
        f2_up = stats_summary(factor2.get('MA60上方', []))
        f2_down = stats_summary(factor2.get('MA60下方', []))
        if f2_up['n'] >= 30 and f2_down['n'] >= 30:
            up_better = (f2_up['mean'] or -99) > (f2_down['mean'] or 99)
            checks.append(('MA60上方 avg > MA60下方', up_better,
                          f'上方={format_pct(f2_up["mean"])} vs 下方={format_pct(f2_down["mean"])}'))
            if not up_better: all_pass = False

        # 因子3: 承接 > 无承接
        f3_yes = stats_summary(factor3.get('有承接(长下影)', []))
        f3_no = stats_summary(factor3.get('无承接', []))
        if f3_yes['n'] >= 30 and f3_no['n'] >= 30:
            accept_better = (f3_yes['mean'] or -99) > (f3_no['mean'] or 99)
            checks.append(('有承接 avg > 无承接', accept_better,
                          f'承接={format_pct(f3_yes["mean"])} vs 无={format_pct(f3_no["mean"])}'))
            if not accept_better: all_pass = False

        # 因子4: 主线内 > 主线外
        f4_in = stats_summary(factor4.get('主线内', []))
        f4_out = stats_summary(factor4.get('主线外', []))
        if f4_in['n'] >= 30 and f4_out['n'] >= 30:
            mainline_better = (f4_in['mean'] or -99) > (f4_out['mean'] or 99)
            checks.append(('主线内 avg > 主线外', mainline_better,
                          f'主线={format_pct(f4_in["mean"])} vs 线外={format_pct(f4_out["mean"])}'))
            if not mainline_better: all_pass = False

        # 额外: 如果全市场大跌日次日均值是正的
        all_next = []
        for v in factor1.values(): all_next.extend(v)
        all_s = stats_summary(all_next)
        checks.append((f'大跌日次日全市场均值 (n={all_s["n"]})',
                      (all_s['mean'] or 0) > 0,
                      f'avg={format_pct(all_s["mean"])}, win={all_s["win_rate"]:.0f}%'))
        if all_s['mean'] and all_s['mean'] < 0:
            all_pass = False

        self._print_checks(checks)
        self._record_result(10, '超跌反弹因子', all_pass)
        print(f'结论: {"因子有效 ✅" if all_pass else "因子存疑 ⚠️"}')

    def _idx_chg_from_list(self, data_list, date_str):
        """从 [(date,close), ...] 列表计算指定日期的涨跌"""
        for i, (d, _) in enumerate(data_list):
            if d == date_str and i > 0:
                return data_list[i][1] / data_list[i-1][1] - 1
        return None

    def _prev_trade_date(self, full_code, date_str):
        """找到 date_str 前一个交易日"""
        dates = self._get_sorted_dates(full_code)
        if date_str not in dates:
            return None
        idx = dates.index(date_str)
        return dates[idx-1] if idx > 0 else None

    # ══════════════════════════════════════════════════════════
    # 汇总
    # ══════════════════════════════════════════════════════════

    def print_summary(self):
        """打印所有规则的 PASS/FAIL 汇总"""
        print(f"\n{'=' * 70}")
        print(f"  交易规则回测验证 — PASS/FAIL 汇总")
        print(f"  时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        print(f"{'=' * 70}")
        print(f"\n  {'优先级':6s} {'规则':4s} {'标题':30s} {'结果':8s}")
        print(f"  {'-' * 50}")
        priority_map = {
            4: 'P0', 6: 'P0', 7: 'P0',
            2: 'P1', 8: 'P1', 9: 'P1',
            1: 'P2', 3: 'P2',
            5: 'P3',
        }
        for result in self._checked_results:
            p = priority_map.get(result['rule'], '--')
            status = '✅ PASS' if result['all_pass'] else '⚠️ FAIL'
            print(f"  {p:6s} {result['rule']:4d} {result['title']:30s} {status}")
        print(f"\n{'=' * 70}\n")

    def close(self):
        self.conn.close()


# ──────────────────────────────────────────────────────────────
# main
# ──────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description='交易规则回测验证 — 9 条规则量化验证')
    parser.add_argument('--rule', type=str, default=None,
                        help='运行指定规则 (如 1, 1,4,7, all=全部)')
    parser.add_argument('--summary', action='store_true',
                        help='只输出 PASS/FAIL 汇总')
    args = parser.parse_args()

    bt = RuleBacktester()

    # 确定要运行的规则
    if args.rule:
        try:
            rule_nums = [int(x.strip()) for x in args.rule.split(',')]
        except ValueError:
            print(f'无效的规则编号: {args.rule}')
            bt.close()
            return
    else:
        rule_nums = list(range(1, 10))

    # 按优先级排序
    priority_order = {4: 1, 6: 2, 7: 3, 2: 4, 8: 5, 9: 6, 1: 7, 3: 8, 5: 9}
    rule_nums.sort(key=lambda x: priority_order.get(x, 99))

    # 规则映射
    rule_methods = {
        1: bt.test_rule1_position_tier,
        2: bt.test_rule2_sox_multiplier,
        3: bt.test_rule3_rebound_priority,
        4: bt.test_rule4_sox_sell_window,
        5: bt.test_rule5_macro_events,
        6: bt.test_rule6_four_dim,
        7: bt.test_rule7_fake_breakdown,
        8: bt.test_rule8_weakest_rebound,
        9: bt.test_rule9_stock_personality,
        10: bt.test_rule10_bounce_factors,
    }

    if args.summary:
        # 仍然运行全部但只打印汇总
        for n in rule_nums:
            if n in rule_methods:
                rule_methods[n]()
        bt.print_summary()
    else:
        for n in rule_nums:
            if n in rule_methods:
                try:
                    rule_methods[n]()
                except Exception as e:
                    print(f'\n  ❌ 规则 {n} 执行出错: {e}')
                    import traceback
                    traceback.print_exc()
        if not args.rule or len(rule_nums) > 1:
            bt.print_summary()

    bt.close()


if __name__ == '__main__':
    main()
