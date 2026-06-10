#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
超跌反弹选股器 — 三大指数同步大跌日筛选有资金承接的超跌票

触发条件: 上证≥2%, 科创50≥2.5%, 创业板≥3% 同步下跌 (三缺一不触发)

用法:
  python3 src/skills/bounce_screener.py              # 自动触发判断
  python3 src/skills/bounce_screener.py --force      # 强制选股(忽略触发条件)
  python3 src/skills/bounce_screener.py --top 20     # 前20只
  python3 src/skills/bounce_screener.py --backtest   # 因子回测验证

设计原则:
  1. 先回测验证 4 个核心因子, 逐个验证后再拼权重
  2. 回测通过 (胜率>55%, 超额>1%) 才纳入评分
  3. K线形态(长下影/V型反弹/尾盘拉升)不直接用, 改用资金端代理指标
  4. 复用 smart_screener.py 的数据加载 / rule_backtest.py 的回测模式
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
from datetime import datetime, date

# ============================================================
# 配置
# ============================================================

DB_CONFIG = {
    'host': 'localhost', 'port': 3306,
    'user': 'root', 'password': '12345678',
    'database': 'gp2', 'charset': 'utf8mb4',
}

# 三大指数代码
INDEX_CODES = {
    '000001.SH': '上证指数',
    '000688.SH': '科创50',
    '399006.SZ': '创业板指',
}

# 触发阈值 (Section 8.1 修正后)
TRIGGER_THRESHOLDS = {
    '000001.SH': -0.02,   # 上证 ≥ 2%
    '000688.SH': -0.025,  # 科创50 ≥ 2.5%
    '399006.SZ': -0.03,   # 创业板 ≥ 3%
}

# 白名单龙头 (反弹选股器用, 超跌后弹性好)
BOUNCE_LEADERS = {
    '002384', '600584', '002463', '002916', '300476',  # PCB/封测
    '002156', '603005',  # 封测
    '002138', '300408',  # 电感/被动元件
    '603986', '688525',  # 存储
    '300502', '300308',  # 光模块
    '688981',           # 晶圆代工
}

# 活跃主线关键词 (用于因子4板块效应)
MAINLINE_KEYWORDS = [
    '半导体', '电子', '通信', 'PCB', '芯片', '封测', '光模块',
    '算力', '服务器', '元件', '存储', '封测', 'AI', 'CPO',
]

# ============================================================
# 工具函数
# ============================================================

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

def ma(values, n):
    """简单移动平均"""
    if len(values) < n:
        return values[-1] if values else 0
    return sum(values[-n:]) / n

def calc_rsi(closes, n=6):
    """计算 RSI (Cutler's RSI, 与 uptrend_model.py 一致)"""
    import numpy as np
    if len(closes) <= n:
        return 50
    deltas = np.diff(closes[-(n+1):])
    gains = np.where(deltas > 0, deltas, 0)
    losses = np.where(deltas < 0, -deltas, 0)
    avg_gain = np.mean(gains)
    avg_loss = np.mean(losses)
    if avg_loss == 0:
        return 100.0
    return 100 - (100 / (1 + avg_gain / avg_loss))

# ============================================================
# BounceScreener 主类
# ============================================================

class BounceScreener:
    def __init__(self):
        self.conn = pymysql.connect(**DB_CONFIG)
        self._meta = {}       # {short_code: {name, sw1, sw2, sw3}}
        self._meta_loaded = False
        self._daily = {}      # {full_code: [[date, o, h, l, c, v], ...]
        self._idx_data = {}   # {index_code: [(date, close), ...]}

    # ============================================================
    # 数据加载
    # ============================================================

    def _load_index_data(self, start=None, end=None):
        """从 market_index_tbl 加载三大指数日K"""
        if start is None:
            start = '2019-01-01'
        if end is None:
            end = date.today().strftime('%Y-%m-%d')

        c = self.conn.cursor()
        for code in INDEX_CODES:
            c.execute('''
                SELECT tradedate, close FROM market_index_tbl
                WHERE index_code=%s AND tradedate >= %s AND tradedate <= %s
                ORDER BY tradedate ASC
            ''', (code, start, end))
            rows = c.fetchall()
            if rows:
                self._idx_data[code] = [(str(r[0]), float(r[1])) for r in rows]
        c.close()

    def _get_today_index_changes(self):
        """获取今日三大指数涨跌幅"""
        today = date.today().strftime('%Y-%m-%d')
        self._load_index_data(start=(date.today() - date.resolution*10).strftime('%Y-%m-%d'))

        result = {}
        for code, name in INDEX_CODES.items():
            data = self._idx_data.get(code, [])
            if len(data) < 2:
                result[code] = {'name': name, 'chg': None, 'close': None}
                continue
            # 找今天和昨天的数据
            today_row = None
            yesterday_row = None
            for i, (d, c) in enumerate(data):
                if d == today:
                    today_row = (d, c)
                    if i > 0:
                        yesterday_row = data[i-1]
                    break
            if today_row is None:
                # 可能还没收盘, 用最后一条
                if len(data) >= 2:
                    today_row = data[-1]
                    yesterday_row = data[-2]
                else:
                    result[code] = {'name': name, 'chg': None, 'close': None}
                    continue

            if yesterday_row and yesterday_row[1] > 0:
                chg = (today_row[1] / yesterday_row[1] - 1)
            else:
                chg = 0
            result[code] = {'name': name, 'chg': chg, 'close': today_row[1]}
        return result

    def _check_trigger(self):
        """检查今天是否触发超跌反弹条件.
        返回: (triggered: bool, info: dict)
        """
        idx_changes = self._get_today_index_changes()
        triggered = True
        info = {'indices': idx_changes, 'failures': []}

        for code, threshold in TRIGGER_THRESHOLDS.items():
            chg = idx_changes[code]['chg']
            if chg is None:
                triggered = False
                info['failures'].append(f"{INDEX_CODES[code]}无数据")
            elif chg > threshold:  # chg 是负数，chg > threshold 意味着跌幅不够
                triggered = False
                info['failures'].append(
                    f"{INDEX_CODES[code]}{chg*100:+.1f}% > {threshold*100:+.0f}%阈值"
                )
            else:
                info['failures'].append(
                    f"{INDEX_CODES[code]}{chg*100:+.1f}% ≤ {threshold*100:+.0f}% ✓"
                )

        return triggered, info

    def _load_stock_meta(self):
        """加载所有 A 股的行业分类 (默认过滤 ST/退市)"""
        if self._meta_loaded:
            return
        c = self.conn.cursor()
        c.execute("SELECT code, name, sw1, sw2, sw3 FROM stock_basic_info_tbl WHERE status=1")
        for row in c.fetchall():
            full_code, name, sw1, sw2, sw3 = row
            short = full_code.replace('.SH', '').replace('.SZ', '')
            if len(short) == 6 and short.isdigit():
                self._meta[short] = {
                    'name': name, 'sw1': sw1 or '', 'sw2': sw2 or '', 'sw3': sw3 or ''
                }
        c.close()
        self._meta_loaded = True

    def _load_daily(self, codes, days=60):
        """批量加载日K数据 (复用 smart_screener 模式)"""
        to_load = [c for c in codes if c not in self._daily]
        if not to_load:
            return

        conn = pymysql.connect(**DB_CONFIG)
        c = conn.cursor()
        code_suffixes = [c + ('.SH' if c.startswith('6') else '.SZ') for c in to_load]
        batch_size = 500
        for i in range(0, len(code_suffixes), batch_size):
            batch = code_suffixes[i:i+batch_size]
            placeholders = ','.join(['%s'] * len(batch))
            try:
                c.execute(f'''
                    SELECT code, tradedate, open, high, low, close, volume
                    FROM daily_info_tbl WHERE code IN ({placeholders})
                    ORDER BY code, tradedate ASC
                ''', batch)
                rows = c.fetchall()

                # 按 code 分组, 取最近 days 条
                current_code = None
                current_rows = []
                for row in rows:
                    code_db, d, o, h, l, cl, v = row
                    if code_db != current_code:
                        if current_code and len(current_rows) >= days:
                            self._daily[current_code.replace('.SH','').replace('.SZ','')] = current_rows[-days:]
                        current_code = code_db
                        current_rows = []
                    current_rows.append({
                        'date': str(d), 'open': float(o), 'high': float(h),
                        'low': float(l), 'close': float(cl), 'volume': float(v),
                    })
                if current_code and len(current_rows) >= days:
                    self._daily[current_code.replace('.SH','').replace('.SZ','')] = current_rows[-days:]
            except Exception:
                pass
        c.close()
        conn.close()

    def _get_all_codes(self):
        self._load_stock_meta()
        return list(self._meta.keys())

    # ============================================================
    # 否决条件
    # ============================================================

    def _veto_reason(self, code, daily_rows):
        """检查否决条件, 返回 None 表示通过, 返回字符串表示被否原因.

        回测结论 (2026-06-10):
        - MA60下方: 次日+3.18%, 胜率95.7% — MA60不是有效否决条件, 已移除
        - 长下影承接: 次日+1.58% — 量化资金诱多, 不做否决但做负分信号
        - 保留: 跌停/放量破位 (极端情况)
        """
        if not daily_rows or len(daily_rows) < 2:
            return '数据不足'

        today = daily_rows[-1]
        yesterday = daily_rows[-2]
        volumes = [d['volume'] for d in daily_rows]

        # 1. 今日触及跌停 (当前价 / 昨收 ≤ 0.902)
        if yesterday['close'] > 0:
            chg_today = (today['close'] / yesterday['close'] - 1)
            if chg_today <= -0.098:
                return '触及跌停'

        # 2. 放量破位 (量 > 3倍均量 AND 跌 > 8%)
        if len(volumes) >= 20:
            avg_vol = sum(volumes[-21:-1]) / 20
            if avg_vol > 0:
                vol_ratio = today['volume'] / avg_vol
                if chg_today < -0.08 and vol_ratio > 3:
                    return f'放量破位 (量{vol_ratio:.1f}x, 跌{chg_today*100:.1f}%)'

        return None  # 通过

    # ============================================================
    # 评分模型
    # ============================================================

    def _score_stock(self, code, daily_rows):
        """
        对一只股票在大跌日的反弹潜力打分 (总分 100)

        回测验证后的因子 (2026-06-10):
        ✅ 跌幅深度 — 深跌(-5~-8%)次日+3.80% vs 小跌(-1~-3%)+2.06%
        ✅ 板块主线 — 主线+3.33% vs 线外+3.12%
        ❌ MA60位置 — 上方3.13% vs 下方3.18% (无差异)
        ❌ 长下影承接 — 有承接+1.58% vs 无承接+3.19% (量化诱多, 改为负分)

        因子1: 跌幅深度 (35分)
        因子2: 趋势基础 (15分) — MA60/年线/非加速
        因子3: 风险减分 (罚分) — 长下影/高位滞涨
        因子4: 板块/资金 (20分)
        加分项 (10分)
        """
        if not daily_rows or len(daily_rows) < 60:
            return 0, []

        closes = [d['close'] for d in daily_rows]
        volumes = [d['volume'] for d in daily_rows]
        current = closes[-1]
        today = daily_rows[-1]
        yesterday = daily_rows[-2]

        score = 0
        reasons = []
        warnings = []
        chg_today = (today['close'] / yesterday['close'] - 1) * 100
        ma20_val = ma(closes, 20)
        ma60_val = ma(closes, 60)

        # ============================================================
        # 因子1: 跌幅深度 (35分) — 回测验证 ✅
        # ============================================================
        if chg_today <= -8:
            # 崩盘级别: 次日也能反弹 +4.3%, 但风险大, 给中等分
            score += 20
            reasons.append(f'崩盘跌{chg_today:.1f}% (+20)')
        elif chg_today <= -5:
            score += 25
            reasons.append(f'深跌{chg_today:.1f}% (+25)')
        elif chg_today <= -3:
            score += 15
            reasons.append(f'中跌{chg_today:.1f}% (+15)')
        elif chg_today <= -1:
            score += 5
            reasons.append(f'小跌{chg_today:.1f}% (+5)')
        # else: 抗跌票反弹空间有限

        # RSI6 极度超卖 (反弹更强)
        if len(closes) >= 60:
            rsival = calc_rsi(closes, 6)
            if rsival < 25:
                score += 10
                reasons.append(f'RSI6={rsival:.0f}超卖 (+10)')
            elif rsival < 35:
                score += 5
                reasons.append(f'RSI6={rsival:.0f}偏超卖 (+5)')

        # ============================================================
        # 因子2: 趋势基础 (15分)
        # ============================================================
        # 注: 回测显示MA60上方/下方次日反弹无差异, MA60不作为加分
        # 但回踩MA20支撑区 (MA60上方+MA20下方) 仍有结构意义

        # 年线多头: MA60 > MA120 > MA250
        if len(closes) >= 250:
            ma120 = ma(closes, 120)
            ma250 = ma(closes, 250)
            if ma60_val > ma120 > ma250:
                score += 8
                reasons.append('年线多头 (+8)')

        # 近5日不是加速下跌: 今日跌幅 ≤ 前3日均跌幅 × 1.5
        if len(daily_rows) >= 5:
            prev_changes = []
            for i in range(-4, -1):
                prev_changes.append(
                    (daily_rows[i]['close'] / daily_rows[i-1]['close'] - 1) * 100
                )
            avg_prev_chg = sum(prev_changes) / len(prev_changes)
            if abs(chg_today) <= abs(avg_prev_chg) * 1.5:
                score += 7
                reasons.append('非加速下跌 (+7)')
            elif avg_prev_chg < 0 and abs(chg_today) > abs(avg_prev_chg) * 1.5:
                warnings.append('加速下跌')

        # ============================================================
        # 因子3: 风险减分 — 回测验证: 长下影是量化诱多信号
        # ============================================================
        o, h, l_v, c = today['open'], today['high'], today['low'], today['close']
        total_range = h - l_v
        body = abs(c - o)

        if total_range > 0 and body > 0:
            lower_shadow = min(c, o) - l_v
            upper_shadow = h - max(c, o)

            # 长下影线 (量化诱多信号) → 负分!
            if lower_shadow > body * 1.5 and lower_shadow > upper_shadow:
                score -= 10
                warnings.append(f'长下影诱多 (-10)')

            # 长上影 (空方压力)
            if upper_shadow > body * 1.5 and upper_shadow > lower_shadow * 1.5:
                score -= 5
                warnings.append(f'长上影压力 (-5)')

        # ============================================================
        # 因子4: 板块/资金 (20分)
        # ============================================================
        meta = self._meta.get(code, {})
        sw_text = meta.get('sw1', '') + meta.get('sw2', '') + meta.get('sw3', '')
        is_mainline = any(k in sw_text for k in MAINLINE_KEYWORDS)
        if is_mainline:
            score += 12
            reasons.append('主线板块 (+12)')

        # 白名单龙头
        if code in BOUNCE_LEADERS:
            score += 8
            reasons.append('白名单龙头 (+8)')

        # ============================================================
        # 加分项 (10分)
        # ============================================================
        # MA20 附近 (弹性好, 回踩支撑位)
        if current > ma60_val and ma20_val > 0:
            dist_to_ma20 = (current / ma20_val - 1)
            if -0.05 < dist_to_ma20 < 0.03:
                score += 5
                reasons.append('MA20支撑区 (+5)')

        # 缩量下跌 (非恐慌抛售)
        if len(volumes) >= 20:
            avg_vol = sum(volumes[-21:-1]) / 20
            if avg_vol > 0:
                vol_ratio = today['volume'] / avg_vol
                if vol_ratio < 0.7:
                    score += 5
                    reasons.append(f'缩量下跌 (量{vol_ratio:.1f}x) (+5)')

        # ============================================================
        # 因子5: 大单资金流 (5分) — 回测验证: 净买+3.55% vs 净卖+3.37%
        # ============================================================
        net_lg = getattr(self, '_screener_mf', {}).get(code)
        if net_lg is not None:
            # 占成交额比例
            if net_lg > 0:
                amt = today['close'] * today['volume']
                lg_pct = abs(net_lg) / amt * 100 if amt > 0 else 0
                if lg_pct > 1:
                    score += 5
                    reasons.append(f'大额净买入 ({lg_pct:.1f}%) (+5)')
                else:
                    score += 3
                    reasons.append('大单净买入 (+3)')

        return score, reasons, warnings

    # ============================================================
    # 因子回测
    # ============================================================

    def _idx_chg_from_list(self, data_list, date_str):
        """从 [(date,close), ...] 列表计算指定日期的涨跌"""
        for i, (d, _) in enumerate(data_list):
            if d == date_str and i > 0:
                return data_list[i][1] / data_list[i-1][1] - 1
        return None

    def _find_crash_days(self, start='2022-01-01', end=None):
        """找到所有同步大跌日"""
        if end is None:
            end = date.today().strftime('%Y-%m-%d')

        self._load_index_data(start=start, end=end)

        if not all(c in self._idx_data for c in INDEX_CODES):
            print('  ⚠️ 指数数据不足')
            return []

        crash_days = []
        sh_data = self._idx_data['000001.SH']
        kc_data = self._idx_data['000688.SH']
        cy_data = self._idx_data['399006.SZ']

        for i in range(1, len(sh_data)):
            d = sh_data[i][0]
            if d < start or d > end:
                continue
            sh_chg = sh_data[i][1] / sh_data[i-1][1] - 1
            kc_chg = self._idx_chg_from_list(kc_data, d)
            cy_chg = self._idx_chg_from_list(cy_data, d)
            if kc_chg is None or cy_chg is None:
                continue
            if sh_chg <= -0.02 and kc_chg <= -0.025 and cy_chg <= -0.03:
                crash_days.append((d, sh_chg, kc_chg, cy_chg))

        return crash_days

    def _prev_trade_date(self, full_code, date_str, dates):
        """找到 date_str 前一个交易日"""
        if date_str not in dates:
            return None
        idx = dates.index(date_str)
        return dates[idx-1] if idx > 0 else None

    def _load_moneyflow(self, codes, dates):
        """加载指定股票在指定日期的大单资金流。
        返回: 存入 self._mf_data: {(full_code, date_str): net_lg_amount}
        """
        if not hasattr(self, '_mf_data'):
            self._mf_data = {}
        to_load = set()
        for code in codes:
            full = get_code_suffix(code)
            for d in dates:
                key = (full, d)
                if key not in self._mf_data:
                    to_load.add(key)

        if not to_load:
            return

        c = self.conn.cursor()
        date_set = sorted(set(d for _, d in to_load))
        code_set = sorted(set(c for c, _ in to_load))
        batch_size = 500

        for i in range(0, len(code_set), batch_size):
            batch_codes = code_set[i:i+batch_size]
            placeholders_c = ','.join(['%s'] * len(batch_codes))
            placeholders_d = ','.join(['%s'] * len(date_set))
            c.execute(f'''
                SELECT code, tradedate, net_lg_amount
                FROM daily_moneyflow_tbl
                WHERE code IN ({placeholders_c}) AND tradedate IN ({placeholders_d})
            ''', batch_codes + date_set)
            for row in c.fetchall():
                full_code, d, amt = row
                self._mf_data[(full_code, str(d))] = float(amt) if amt else 0
        c.close()

    def run_backtest(self):
        """运行 4 因子回测验证"""
        print(f"\n{'=' * 70}")
        print(f"  超跌反弹选股器 — 因子回测验证")
        print(f"  时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        print(f"{'=' * 70}")

        crash_days_list = self._find_crash_days()
        crash_dates = [cd[0] for cd in crash_days_list]
        print(f'\n同步大跌日: {len(crash_days_list)} 天: {", ".join(crash_dates)}')

        if len(crash_days_list) < 5:
            print('⚠️ 大跌日样本不足 (<5), 无法做统计')
            return

        # 加载全市场数据
        codes = self._get_all_codes()
        print(f'加载 {len(codes)} 只股票日K数据...')
        self._load_daily(codes, days=120)

        print(f'加载大单资金流数据...')
        self._load_moneyflow(codes, crash_dates)

        # 收集数据
        factor1 = defaultdict(list)  # 跌幅深度
        factor2 = defaultdict(list)  # MA60位置
        factor3 = defaultdict(list)  # 盘中承接
        factor4 = defaultdict(list)  # 板块主线
        factor5 = defaultdict(list)  # 大单资金流
        factor_cross = defaultdict(list)  # 交叉: 跌幅 × 资金流
        mf_total, mf_missing = 0, 0

        processed = 0
        for cd_date, sh_c, kc_c, cy_c in crash_days_list:
            for code in codes:
                daily = self._daily.get(code, [])
                if not daily:
                    continue

                # 找到 crash_date 对应的行
                crash_idx = None
                for i, d in enumerate(daily):
                    if d['date'] == cd_date:
                        crash_idx = i
                        break
                if crash_idx is None or crash_idx < 1:
                    continue

                today = daily[crash_idx]
                yesterday = daily[crash_idx - 1]
                if yesterday['close'] <= 0:
                    continue

                chg_today = (today['close'] / yesterday['close'] - 1) * 100

                # 次日收益
                if crash_idx + 1 >= len(daily):
                    continue
                tomorrow = daily[crash_idx + 1]
                next_ret = (tomorrow['close'] / today['close'] - 1) * 100

                # --- 因子5: 大单资金流 ---
                full_code = get_code_suffix(code)
                net_lg = self._mf_data.get((full_code, cd_date))
                if net_lg is not None:
                    mf_total += 1
                    if net_lg > 0:
                        factor5['大单净买入'].append(next_ret)
                    elif net_lg < 0:
                        factor5['大单净卖出'].append(next_ret)
                    else:
                        factor5['大单持平'].append(next_ret)
                    # 按资金流占成交额比例分档
                    amt_today = today['close'] * today['volume']
                    if amt_today > 0 and abs(net_lg) > 0:
                        lg_pct = abs(net_lg) / amt_today * 100
                        if lg_pct > 1:
                            if net_lg > 0:
                                factor5['大额净买入(>1%)'].append(next_ret)
                            else:
                                factor5['大额净卖出(>1%)'].append(next_ret)
                else:
                    mf_missing += 1

                # --- 交叉: 跌幅深度 × 资金流 ---
                if chg_today <= -8:
                    depth_label = '崩盘'
                elif chg_today <= -5:
                    depth_label = '深跌'
                elif chg_today <= -3:
                    depth_label = '中跌'
                elif chg_today <= -1:
                    depth_label = '小跌'
                else:
                    depth_label = '抗跌'
                if net_lg is not None:
                    flow_label = '净买' if net_lg > 0 else ('净卖' if net_lg < 0 else '持平')
                    factor_cross[f'{depth_label}+{flow_label}'].append(next_ret)
                else:
                    factor_cross[f'{depth_label}+无数据'].append(next_ret)

                # --- 因子1: 跌幅深度 ---
                if chg_today <= -8:
                    factor1['崩盘(-8%+)'].append(next_ret)
                elif chg_today <= -5:
                    factor1['深跌(-5~-8%)'].append(next_ret)
                elif chg_today <= -3:
                    factor1['中跌(-3~-5%)'].append(next_ret)
                elif chg_today <= -1:
                    factor1['小跌(-1~-3%)'].append(next_ret)
                else:
                    factor1['抗跌(0+)'].append(next_ret)

                # --- 因子2: MA60 位置 ---
                closes = [d['close'] for d in daily[:crash_idx+1]]
                ma60_val = ma(closes, 60) if len(closes) >= 60 else None
                if ma60_val:
                    if today['close'] > ma60_val:
                        factor2['MA60上方'].append(next_ret)
                    else:
                        factor2['MA60下方'].append(next_ret)

                # --- 因子3: 盘中承接 (长下影代理) ---
                o, h, l_v, c = today['open'], today['high'], today['low'], today['close']
                total_range = h - l_v
                body = abs(c - o)
                if total_range > 0 and body > 0:
                    lower_shadow = min(c, o) - l_v
                    upper_shadow = h - max(c, o)
                    if lower_shadow > body * 1.5 and lower_shadow > upper_shadow:
                        factor3['有承接(长下影)'].append(next_ret)
                    else:
                        factor3['无承接'].append(next_ret)

                # --- 因子4: 板块主线 ---
                meta = self._meta.get(code, {})
                sw_text = meta.get('sw1', '') + meta.get('sw2', '') + meta.get('sw3', '')
                is_mainline = any(k in sw_text for k in MAINLINE_KEYWORDS)
                if is_mainline:
                    factor4['主线内'].append(next_ret)
                else:
                    factor4['主线外'].append(next_ret)

                processed += 1

        print(f'分析 {processed} 条记录, 资金流覆盖 {mf_total} 条 (缺失 {mf_missing} 条)\n')

        # 打印各因子结果
        headers = ['分组', '均值', '中位数', '胜率', '标准差', '样本']

        for title, factor_dict in [
            ('因子1: 跌幅深度 → 次日收益', factor1),
            ('因子2: MA60 位置 → 次日收益', factor2),
            ('因子3: 盘中承接 → 次日收益', factor3),
            ('因子4: 板块主线 → 次日收益', factor4),
        ]:
            print(f'─── {title} ───')
            rows = []
            for key in sorted(factor_dict.keys()):
                s = stats_summary(factor_dict[key])
                if s['n'] >= 20:
                    rows.append((key, s))
            if rows:
                _print_result_table(rows, headers)
            print()

        # 因子5: 资金流
        print(f'─── 因子5: 大单资金流 → 次日收益 ───')
        rows5 = []
        for key in ['大额净买入(>1%)', '大单净买入', '大单持平', '大单净卖出', '大额净卖出(>1%)']:
            s = stats_summary(factor5.get(key, []))
            if s['n'] >= 20:
                rows5.append((key, s))
        if rows5:
            _print_result_table(rows5, headers)
        print()

        # 交叉分析: 跌幅 × 资金流
        print(f'─── 交叉分析: 跌幅深度 × 资金流 → 次日收益 ───')
        cross_rows = []
        for key in sorted(factor_cross.keys()):
            s = stats_summary(factor_cross[key])
            if s['n'] >= 20:
                cross_rows.append((key, s))
        if cross_rows:
            _print_result_table(cross_rows, headers)
        print()

        # 检查项
        print('─── 验证结果 ───')
        checks = []

        # 因子1: -5~-8% 深跌组应该比 -1~-3% 小跌组反弹更猛
        f1_deep = stats_summary(factor1.get('深跌(-5~-8%)', []))
        f1_mid = stats_summary(factor1.get('中跌(-3~-5%)', []))
        f1_small = stats_summary(factor1.get('小跌(-1~-3%)', []))
        if f1_deep['n'] >= 30 and f1_small['n'] >= 30:
            better = (f1_deep['mean'] or -99) > (f1_small['mean'] or -99)
            checks.append((
                f'深跌(-5~-8%) > 小跌(-1~-3%) 次日',
                better,
                f'深跌={format_pct(f1_deep["mean"])} vs 小跌={format_pct(f1_small["mean"])}, n={f1_deep["n"]}'
            ))

        # 因子2: MA60上方 > 下方
        f2_up = stats_summary(factor2.get('MA60上方', []))
        f2_down = stats_summary(factor2.get('MA60下方', []))
        if f2_up['n'] >= 30 and f2_down['n'] >= 30:
            up_better = (f2_up['mean'] or -99) > (f2_down['mean'] or 99)
            checks.append((
                'MA60上方 > MA60下方 次日',
                up_better,
                f'上方={format_pct(f2_up["mean"])} vs 下方={format_pct(f2_down["mean"])}, n={f2_up["n"]}'
            ))

        # 因子3: 有承接 > 无承接
        f3_yes = stats_summary(factor3.get('有承接(长下影)', []))
        f3_no = stats_summary(factor3.get('无承接', []))
        if f3_yes['n'] >= 30 and f3_no['n'] >= 30:
            accept_better = (f3_yes['mean'] or -99) > (f3_no['mean'] or 99)
            checks.append((
                '有承接(长下影) > 无承接 次日',
                accept_better,
                f'承接={format_pct(f3_yes["mean"])} vs 无={format_pct(f3_no["mean"])}, n={f3_yes["n"]}'
            ))

        # 因子4: 主线内 > 主线外
        f4_in = stats_summary(factor4.get('主线内', []))
        f4_out = stats_summary(factor4.get('主线外', []))
        if f4_in['n'] >= 30 and f4_out['n'] >= 30:
            mainline_better = (f4_in['mean'] or -99) > (f4_out['mean'] or 99)
            checks.append((
                '主线内 > 主线外 次日',
                mainline_better,
                f'主线={format_pct(f4_in["mean"])} vs 线外={format_pct(f4_out["mean"])}, n={f4_in["n"]}'
            ))

        # 因子5: 大单净买入 > 净卖出
        f5_buy = stats_summary(factor5.get('大单净买入', []))
        f5_sell = stats_summary(factor5.get('大单净卖出', []))
        if f5_buy['n'] >= 30 and f5_sell['n'] >= 30:
            flow_better = (f5_buy['mean'] or -99) > (f5_sell['mean'] or 99)
            checks.append((
                '大单净买入 > 大单净卖出',
                flow_better,
                f'净买={format_pct(f5_buy["mean"])} vs 净卖={format_pct(f5_sell["mean"])}, n={f5_buy["n"]}'
            ))

        # 因子5b: 深跌+净买 vs 深跌+净卖 (核心假设)
        f5_deep_buy = stats_summary(factor_cross.get('深跌+净买', []))
        f5_deep_sell = stats_summary(factor_cross.get('深跌+净卖', []))
        if f5_deep_buy['n'] >= 30 and f5_deep_sell['n'] >= 30:
            deep_flow = (f5_deep_buy['mean'] or -99) > (f5_deep_sell['mean'] or 99)
            checks.append((
                '深跌+净买 > 深跌+净卖 (核心假设)',
                deep_flow,
                f'净买={format_pct(f5_deep_buy["mean"])} vs 净卖={format_pct(f5_deep_sell["mean"])}, n={f5_deep_buy["n"]}'
            ))

        # 全市场次日均值
        all_next = []
        for v in factor1.values():
            all_next.extend(v)
        all_s = stats_summary(all_next)
        checks.append((
            f'大跌日次日全市场均值 (n={all_s["n"]})',
            (all_s['mean'] or 0) > 0,
            f'avg={format_pct(all_s["mean"])}, win={all_s["win_rate"]:.0f}%'
        ))

        _print_checks(checks)

        # 汇总
        all_pass = all(c[1] is not False for c in checks)
        print(f'\n结论: {"4因子有效 ✅" if all_pass else "部分因子存疑 ⚠️"}')
        if not all_pass:
            print('  建议: 仅纳入通过验证的因子到评分模型中')

    # ============================================================
    # 实时选股
    # ============================================================

    def run_screen(self, top_n=10, force=False):
        """执行实时超跌反弹选股"""
        print(f"\n{'=' * 70}")
        print(f"  超跌反弹选股 — {date.today().strftime('%Y-%m-%d')}")
        print(f"{'=' * 70}\n")

        # Step 1: 检查触发条件
        triggered, trigger_info = self._check_trigger()

        print('触发条件检查:')
        for code, info in trigger_info['indices'].items():
            name = info['name']
            chg = info['chg']
            if chg is not None:
                print(f'  {name:6s}  {chg*100:+.2f}%')
            else:
                print(f'  {name:6s}  无数据')

        if not triggered:
            for f in trigger_info['failures']:
                if '✓' not in f:
                    print(f'  原因: {f}')
            if force:
                print(f'\n触发结果: ❌ 未触发 (--force 强制运行)')
            else:
                print(f'\n触发结果: ❌ 未触发')
                print('\n使用 --force 强制选股')
                return []

        # Step 2: 加载全市场数据
        codes = self._get_all_codes()
        print(f'\n加载 {len(codes)} 只股票日K数据...')
        self._load_daily(codes, days=250)

        # 加载今日大单资金流
        today_str = date.today().strftime('%Y-%m-%d')
        print(f'加载大单资金流...')
        self._load_moneyflow(codes, [today_str])
        # 存入 self._screener_mf 供 _score_stock 使用
        self._screener_mf = {}
        for code in codes:
            full = get_code_suffix(code)
            val = self._mf_data.get((full, today_str))
            if val is not None:
                self._screener_mf[code] = val

        # Step 3: 筛选评分
        print(f'评分中...')
        results = []
        vetoed = 0

        for code in codes:
            daily = self._daily.get(code, [])
            if not daily:
                continue

            # 否决检查
            veto = self._veto_reason(code, daily)
            if veto:
                vetoed += 1
                continue

            # 评分
            score, reasons, warnings = self._score_stock(code, daily)
            if score > 0:
                meta = self._meta.get(code, {})
                name = meta.get('name', '?')
                today = daily[-1]
                yesterday = daily[-2]
                chg_today = (today['close'] / yesterday['close'] - 1) * 100
                # 计算形态标签
                o, h, l_v, c = today['open'], today['high'], today['low'], today['close']
                form_tag = ''
                total_range = h - l_v
                if total_range > 0:
                    close_pos = (c - l_v) / total_range
                    if close_pos > 0.5:
                        form_tag = 'V型'
                    body = abs(c - o)
                    if body > 0:
                        lower_shadow = min(c, o) - l_v
                        if lower_shadow > body * 1.5:
                            form_tag += '+长下影⚠️' if form_tag else '长下影⚠️'
                if not form_tag:
                    if chg_today > 0:
                        form_tag = '低开高走' if today['open'] < yesterday['close'] else '收红'
                    else:
                        form_tag = '缩量阴跌'

                results.append({
                    'code': code, 'name': name, 'score': score,
                    'reasons': reasons, 'warnings': warnings,
                    'chg': chg_today, 'form': form_tag,
                })

        # Step 4: 排序输出
        results.sort(key=lambda x: x['score'], reverse=True)
        top = results[:top_n]

        print(f'\n筛选完成: {len(results)} 只通过否决, {vetoed} 只被否决\n')
        print(f'TOP {min(top_n, len(top))}:\n')
        print(f'  {"排名":4s} {"得分":4s} {"代码":8s} {"名称":8s} {"今日%":7s} {"形态":12s}')
        print(f'  {"-" * 50}')

        for i, r in enumerate(top):
            rank = f'{i+1}/{len(results)}'
            warn_mark = '⚠️' if r.get('warnings') else '  '
            print(f'  {rank:4s} {r["score"]:4d}  {r["code"]:8s} {r["name"]:8s} {r["chg"]:+6.1f}% {r["form"]:14s}')
            if r['reasons']:
                print(f'  {"":4s} {"":4s}  {"":8s} {", ".join(r["reasons"])}')
            if r.get('warnings'):
                print(f'  {"":4s} {"":4s}  {"":8s} ⚠️  {", ".join(r["warnings"])}')

        print(f'\n操作建议:')
        print(f'  目标: 2-5% 反弹, 止损: 今日最低价')
        print(f'  仓位: ≤ 20% (反弹博弈, 非趋势持有)')
        print(f'  持有周期: 1-3 天, 反弹了就走')

        return top

    def close(self):
        self.conn.close()


# ============================================================
# 输出辅助
# ============================================================

def _print_result_table(rows, headers=None):
    """打印回测结果表"""
    if headers is None:
        headers = ['分组', '均值', '中位数', '胜率', '标准差', '样本']

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

    sep = '-' * (sum(col_widths) + len(col_widths) * 3 + 1)
    header_line = ' | '.join(h.ljust(col_widths[i]) for i, h in enumerate(headers))
    print(sep)
    print(header_line)
    print(sep)
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
    print(sep)

def _print_checks(checks):
    """打印检查项列表"""
    print(f'\n  {"检查项":45s} {"结果":6s} {"详情"}')
    print(f'  {"-" * 80}')
    for label, passed, detail in checks:
        if passed is True:
            status = '✅ PASS'
        elif passed is None:
            status = '⚠️ N/A'
        else:
            status = '❌ FAIL'
        print(f'  {label:45s} {status:6s} {detail}')


# ============================================================
# main
# ============================================================

def main():
    parser = argparse.ArgumentParser(
        description='超跌反弹选股器 — 三大指数同步大跌日筛选有资金承接的超跌票'
    )
    parser.add_argument('--force', action='store_true',
                        help='强制选股 (忽略触发条件)')
    parser.add_argument('--top', type=int, default=10,
                        help='输出前 N 只 (默认 10)')
    parser.add_argument('--backtest', action='store_true',
                        help='运行因子回测验证')
    args = parser.parse_args()

    bs = BounceScreener()

    try:
        if args.backtest:
            bs.run_backtest()
        else:
            bs.run_screen(top_n=args.top, force=args.force)
    finally:
        bs.close()


if __name__ == '__main__':
    main()
