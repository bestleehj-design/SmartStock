# -*- coding: utf-8 -*-
"""
Smart Screener v2 — 优化版
核心改进: 行情一把拉全、数据库算技术面、TOP 结果再查新闻/板块

用法:
  python3 smart_screener.py                # 默认: 主线板块 + TOP20
  python3 smart_screener.py --panic        # 恐慌日模式
  python3 smart_screener.py --sector PCB   # 指定板块
  python3 smart_screener.py --top 10       # 只看前10
  python3 smart_screener.py --deep         # 深度模式(连新闻也查)
  python3 smart_screener.py --no-seasonal  # 禁用季节性题材加权
  python3 smart_screener.py --no-dynamic   # 禁用动态主线加载
"""
import sys
import os
import argparse
import datetime
import time
from collections import defaultdict

# Ensure src/ directory is in sys.path for package imports
import sys, os
_SRC_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _SRC_DIR not in sys.path:
    sys.path.insert(0, _SRC_DIR)


import pymysql
import akshare as ak
import json
from theme.sector_calendar import get_active_themes, print_calendar, get_keyword_boost_map

# ============================================================
# 配置
# ============================================================

DB_CONFIG = {
    'host': 'localhost', 'port': 3306,
    'user': 'root', 'password': '12345678',
    'database': 'gp2', 'charset': 'utf8mb4',
}

TRACKED_SECTORS = [
    'PCB', '光通信', '被动元件', '存储芯片', '半导体', '先进封装',
    'CPO', '算力', 'AI服务器', '服务器', '电感', '封装', '封测',
    '英伟达概念', 'Chiplet', '第三代半导体', '汽车电子', '光模块',
    '集成电路', '芯片', '消费电子', '铜缆', 'DDR5', 'HBM',
]

SECTOR_TO_KEYWORD = {
    '光模块/CPO': ['光模块', '光通信', 'CPO', '800G', '1.6T', '光器件'],
    'PCB': ['PCB', '印制电路板', '覆铜板'],
    '电感/被动元件': ['电感', '被动元件', 'MLCC', '电阻', '电容'],
    'AI服务器': ['服务器', '算力', '液冷', '数据中心'],
    '存储芯片': ['存储', 'HBM', 'DDR5', 'DRAM', 'NAND'],
    '半导体封测': ['封测', '封装', 'Chiplet', '先进封装'],
    '半导体设备': ['刻蚀', '薄膜', '光刻'],
    '晶圆代工': ['晶圆', '代工', 'Foundry'],
}

# 龙头白名单（按板块手工维护）
# 格式: 板块 -> [龙头股代码列表]
LEADER_WHITELIST = {
    '光模块/CPO':      ['300502', '300308', '300394', '300570', '688498'],
    'PCB':             ['002463', '002916', '300476', '002384', '603228'],
    '电感/被动元件':    ['002138', '300408', '603678'],
    'AI服务器':        ['601138', '000938', '300502', '688041', '603019'],
    '存储芯片':        ['603986', '688525', '001309', '688981'],
    '半导体封测':      ['600584', '002156', '603005', '688981'],
    '半导体设备':      ['002371', '688012', '688072', '688120', '688082'],
    '晶圆代工':        ['688981', '688347', '688396'],
}

# 行业纯度校验（排除名不副实的票）
# 用申万行业前缀做二次验证
SECTOR_PURITY_RULES = {
    '光模块/CPO':      ['通信', '电子'],
    'PCB':             ['电子'],
    '电感/被动元件':    ['电子'],
    'AI服务器':        ['电子', '计算机', '通信'],
    '存储芯片':        ['电子'],
    '半导体封测':      ['电子'],
    '半导体设备':      ['电子', '机械设备'],
    '晶圆代工':        ['电子'],
}

# ============================================================
# 数据库查询
# ============================================================

def get_db():
    return pymysql.connect(**DB_CONFIG)


def today_str():
    return datetime.date.today().strftime('%Y-%m-%d')


def ma(values, n):
    if len(values) < n:
        return values[-1] if values else 0
    return sum(values[-n:]) / n


def load_all_stocks():
    """从数据库加载所有 A 股"""
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT code, name, sw1, sw2, sw3 FROM stock_basic_info_tbl WHERE status=1")
    rows = c.fetchall()
    c.close()
    conn.close()

    stocks = []
    for code_full, name, sw1, sw2, sw3 in rows:
        code = code_full.replace('.SH', '').replace('.SZ', '')
        if len(code) == 6 and code.isdigit():
            stocks.append({'code': code, 'name': name, 'sw1': sw1 or '', 'sw2': sw2 or '', 'sw3': sw3 or ''})
    return stocks


# 直接读 DB，不再实例化 ThemeAnalyzer（避免重复加载 1172 个概念和 1557 天交易日历）
_MACRO_INDEX_KW = [
    '同花顺全A', '同花顺沪深', '同花顺主板', '同花顺大盘',
    '同花顺陆股通', '同花顺深股通', '同花顺低估值',
    '同花顺中证', '同花顺高估值', '同花顺小盘', '同花顺小市值',
    '同花顺大市值', '同花顺低盈利', '同花顺热股',
    '同花顺情绪指数', '同花顺',
    '深市新主板', '沪市',
    '融资融券', '深股通', '沪股通',
    '昨日打板', '昨日涨停', '昨日首板', '昨日非ST',
    '沪深主板昨日涨停', '龙虎榜指数', '近期新高',
    '业绩预亏', '减持新规', '增发预案指数', '低市盈率',
    '广东(除深圳)', '粤港澳大湾区', '京津冀一体化',
    '长三角', '海南', '雄安',
    '国企改革',
]


def _is_macro(name):
    return any(kw in name for kw in _MACRO_INDEX_KW)


def _get_trading_days(conn, lookback=21):
    """获取最近 N 个交易日"""
    c = conn.cursor()
    c.execute(f"SELECT DISTINCT tradedate FROM daily_info_tbl ORDER BY tradedate DESC LIMIT {lookback}")
    days = [row[0] for row in c.fetchall()]
    c.close()
    return sorted(days)


def load_dynamic_themes(today=None):
    """从 theme_daily_score_tbl 读取长期主线分析结果，生成动态板块

    不再实例化 ThemeAnalyzer，直接查 DB 已有结果，秒级返回。
    返回 (dynamic_sectors, dynamic_purity) 两个 dict。
    """
    dynamic_sectors = {}
    dynamic_purity = {}

    try:
        conn = get_db()

        # 1. 获取最近 21 个交易日
        trading_days = _get_trading_days(conn, 21)
        if len(trading_days) < 5:
            return {}, {}

        # 2. 批量查 theme_daily_score_tbl
        placeholders = ','.join(['%s'] * len(trading_days))
        c = conn.cursor()
        c.execute(f"""
            SELECT theme_code, theme_name, trade_date, total_score,
                   zt_count, high_board_count, first_board_count,
                   score_index_rise
            FROM theme_daily_score_tbl
            WHERE trade_date IN ({placeholders})
            ORDER BY theme_code, trade_date
        """, trading_days)
        rows = c.fetchall()

        # 3. 组织数据: theme_code -> {date: record}
        theme_daily = defaultdict(dict)
        theme_names = {}
        for row in rows:
            tc, tn, td, ts, zc, hb, fb, sir = row
            if isinstance(td, (datetime.date, datetime.datetime)):
                td = td.strftime('%Y-%m-%d') if hasattr(td, 'strftime') else str(td)
            else:
                td = str(td)
            theme_names[tc] = tn
            theme_daily[tc][td] = {
                'total_score': float(ts) if ts else 0,
                'zt_count': zc or 0,
                'high_board_count': hb or 0,
                'first_board_count': fb or 0,
                'score_index_rise': float(sir) if sir else 0,
            }

        # 4. 每日排名（用于 top5 频率）
        daily_rankings = defaultdict(dict)
        for td in trading_days:
            td_str = td.strftime('%Y-%m-%d') if hasattr(td, 'strftime') else str(td)
            scores = [(tc, theme_daily[tc][td_str]['total_score'])
                      for tc in theme_daily if td_str in theme_daily[tc]]
            scores.sort(key=lambda x: x[1], reverse=True)
            for rank, (tc, _) in enumerate(scores, 1):
                daily_rankings[td_str][tc] = rank

        # 5. 计算长期得分
        min_active = 5
        long_themes = []
        for tc, day_map in theme_daily.items():
            name = theme_names[tc]
            if _is_macro(name):
                continue
            if name in SECTOR_TO_KEYWORD:
                continue

            # 收集有数据的日子的评分
            scores_list = []
            for td in trading_days:
                td_s = td.strftime('%Y-%m-%d') if hasattr(td, 'strftime') else str(td)
                if td_s in day_map:
                    scores_list.append(day_map[td_s]['total_score'])

            active_days = len(scores_list)
            if active_days < min_active:
                continue

            cumulative = sum(scores_list)
            avg_score = cumulative / active_days

            # 趋势：用最近有数据的 N 天做线性回归
            trend_days = list(range(active_days))
            if len(trend_days) >= 3:
                n = len(trend_days)
                sx = sum(trend_days)
                sy = sum(scores_list)
                sxy = sum(x * y for x, y in zip(trend_days, scores_list))
                sxx = sum(x * x for x in trend_days)
                denom = n * sxx - sx * sx
                slope = (n * sxy - sx * sy) / denom if denom != 0 else 0
                if slope > 0.3:
                    trend = 'rising'
                elif slope < -0.3:
                    trend = 'declining'
                else:
                    trend = 'stable'
            else:
                trend = 'stable'

            # 过滤
            if avg_score < 10:
                continue
            if trend == 'declining':
                continue

            # top5 频率
            top5_count = 0
            for td in trading_days:
                td_s = td.strftime('%Y-%m-%d') if hasattr(td, 'strftime') else str(td)
                rank = daily_rankings.get(td_s, {}).get(tc, 999)
                if rank <= 5:
                    top5_count += 1

            long_themes.append({
                'theme_code': tc,
                'theme_name': name,
                'avg_daily_score': avg_score,
                'trend_label': trend,
                'top5_count': top5_count,
            })

        # 按 avg_score 排序
        long_themes.sort(key=lambda x: x['avg_daily_score'], reverse=True)
        c.close()

        # 6. 生成 dynamic_sectors / dynamic_purity
        for theme in long_themes:
            name = theme['theme_name']
            tc = theme['theme_code']
            avg_score = theme['avg_daily_score']
            trend = theme['trend_label']

            # 查概念成分股
            c2 = conn.cursor()
            c2.execute("SELECT code, code_list FROM stock_basic_info_tbl WHERE type=2 AND code=%s", (tc,))
            row = c2.fetchone()
            c2.close()
            if not row or not row[1]:
                continue
            # code_list 已带后缀（.SH/.SZ），直接用
            stock_codes = [s.strip() for s in row[1].split(';') if s.strip()]

            # SW 分类统计
            code_suffixes = stock_codes
            sw1_counter = defaultdict(int)
            sw2_counter = defaultdict(int)
            sw3_counter = defaultdict(int)
            total_stocks = 0

            for i in range(0, len(code_suffixes), 500):
                batch = code_suffixes[i:i + 500]
                ph = ','.join(['%s'] * len(batch))
                c3 = conn.cursor()
                c3.execute(f'SELECT sw1, sw2, sw3 FROM stock_basic_info_tbl WHERE code IN ({ph}) AND type=0', batch)
                for sw1, sw2, sw3 in c3.fetchall():
                    total_stocks += 1
                    if sw1:
                        sw1_counter[sw1] += 1
                    if sw2:
                        sw2_counter[sw2] += 1
                    if sw3:
                        sw3_counter[sw3] += 1
                c3.close()

            if total_stocks == 0:
                continue

            threshold = max(1, total_stocks * 0.3)
            keywords = [name]
            for sw, cnt in sorted(sw2_counter.items(), key=lambda x: x[1], reverse=True)[:2]:
                if cnt >= threshold:
                    keywords.append(sw)
            for sw, cnt in sorted(sw3_counter.items(), key=lambda x: x[1], reverse=True)[:2]:
                if cnt >= threshold:
                    keywords.append(sw)

            purity = [sw for sw, cnt in sorted(sw1_counter.items(), key=lambda x: x[1], reverse=True)[:2]
                      if cnt >= threshold]

            dynamic_sectors[name] = keywords
            if purity:
                dynamic_purity[name] = purity

            print(f"   🔥 {name}: score={avg_score:.1f}, trend={trend}, "
                  f"kw={keywords}, purity={purity}")

        conn.close()

    except Exception as e:
        print(f"   ⚠️ 动态主线加载失败: {e}")
        import traceback
        traceback.print_exc()
        return {}, {}, {}

    # 7. 构建板块强度索引（最新交易日的 score_index_rise）
    latest_date = trading_days[-1]
    latest_date_str = latest_date.strftime('%Y-%m-%d') if hasattr(latest_date, 'strftime') else str(latest_date)
    theme_scores = {}
    for tc, name in theme_names.items():
        day_data = theme_daily.get(tc, {}).get(latest_date_str)
        if day_data:
            theme_scores[name] = day_data['score_index_rise']

    return dynamic_sectors, dynamic_purity, theme_scores


def _strip_sector_label(sector_name):
    """去掉 ⭐ 和 (龙头)/（龙头）等装饰符"""
    import re
    return re.sub(r'^⭐|[*]|[（(]龙头[）)]', '', sector_name).strip()


def assign_sector(stock_info, dynamic_sectors=None, dynamic_purity=None):
    """根据股票名称/行业/白名单 归类到主线板块，返回 (match, [sectors], is_leader)"""
    name = stock_info['name']
    sw1 = stock_info.get('sw1', '')
    sw2 = stock_info.get('sw2', '')
    sw3 = stock_info.get('sw3', '')
    code = stock_info['code']
    text = f"{name} {sw1} {sw2} {sw3}"

    matched = []
    is_leader = False

    # 静态板块匹配
    for sector, keywords in SECTOR_TO_KEYWORD.items():
        if any(kw in text for kw in keywords):
            # 行业纯度校验
            purity_ok = any(sw1.startswith(p) for p in SECTOR_PURITY_RULES.get(sector, []))
            if purity_ok:
                # 检查是否是龙头
                if code in LEADER_WHITELIST.get(sector, []):
                    sector_label = f'⭐{sector}(龙头)'
                    is_leader = True
                else:
                    sector_label = sector
                matched.append(sector_label)

    # 动态板块匹配（无白名单、非龙头标记）
    if dynamic_sectors:
        for sector, keywords in dynamic_sectors.items():
            if any(kw in text for kw in keywords):
                purity_rules = (dynamic_purity or {}).get(sector, [])
                if purity_rules:
                    purity_ok = any(sw1.startswith(p) for p in purity_rules)
                else:
                    purity_ok = True
                if purity_ok:
                    matched.append(sector)

    return matched, is_leader


def load_market_cap(codes):
    """从数据库估算市值（收盘价 * 成交量推算不太准，用日K的close + count近似）"""
    # 简化：用最新日K的 close 和近期均价估算
    # 直接从 daily_info_tbl 和 stock_basic_info_tbl 获取
    caps = {}
    # 暂用简化方案：价格 > 30 视为中盘，> 100 视为大盘
    # 完整市值需要 total_shares 字段，这里做粗略估算
    return caps


def estimate_market_cap_level(price):
    """根据股价估算市值级别（粗略）"""
    if price > 100:
        return 'large', 15    # 大概率是大盘龙头
    elif price > 30:
        return 'medium', 8    # 中等市值
    else:
        return 'small', 0     # 小票


def load_daily_data(codes, days=60):
    """批量加载日K数据（一次查询所有）"""
    conn = get_db()
    c = conn.cursor()

    # 构建批量查询
    code_suffixes = []
    for code in codes:
        suffix = '.SH' if code.startswith('6') else '.SZ'
        code_suffixes.append(code + suffix)

    result = {}
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

            # 按 code 分组
            current_code = None
            current_rows = []
            for row in rows:
                code_db, date, o, h, l, c_val, v = row
                if code_db != current_code:
                    if current_code and len(current_rows) >= days:
                        short_code = current_code.replace('.SH','').replace('.SZ','')
                        result[short_code] = current_rows[-days:]
                    current_code = code_db
                    current_rows = []
                current_rows.append({
                    'date': str(date), 'open': float(o),
                    'high': float(h), 'low': float(l),
                    'close': float(c_val), 'volume': float(v),
                })
            # 最后一个
            if current_code and len(current_rows) >= days:
                short_code = current_code.replace('.SH','').replace('.SZ','')
                result[short_code] = current_rows[-days:]
        except Exception:
            pass

    c.close()
    conn.close()
    return result


def load_realtime_quotes():
    """一把拉全市场实时行情"""
    try:
        df = ak.stock_zh_a_spot_em()
        quotes = {}
        for _, r in df.iterrows():
            code = str(r['代码'])
            quotes[code] = {
                'latest': float(r.get('最新价', 0) or 0),
                'change_pct': float(r.get('涨跌幅', 0) or 0),
                'volume': float(r.get('成交量', 0) or 0),
                'amount': float(r.get('成交额', 0) or 0),
            }
        return quotes
    except Exception as e:
        print(f"  ⚠️ 实时行情获取失败: {e}")
        return {}


# ============================================================
# 评分引擎
# ============================================================

def score_stock(code, daily, sector_info, quote=None, panic_mode=False,
                name='', seasonal_boost_map=None):
    """综合评分 0-100

    sector_info = (all_sectors_list, is_leader)
    """
    score = 0
    reasons = []
    warnings = []

    closes = [d['close'] for d in daily]
    volumes = [d['volume'] for d in daily]
    current = closes[-1]

    all_sectors, is_leader = sector_info
    main_sector = all_sectors[0] if all_sectors else '其他'

    # --- 均线 (0-30) ---
    ma5 = ma(closes, 5)
    ma10 = ma(closes, 10)
    ma20 = ma(closes, 20)

    dist_ma20 = (current / ma20 - 1) * 100

    if ma5 > ma10 > ma20:
        score += 20
        reasons.append('多头排列')
    elif ma5 > ma20:
        score += 12
        reasons.append('短多')
    elif current > ma20:
        score += 6

    if 0 < dist_ma20 < 10:
        score += 10
        reasons.append(f'MA20 +{dist_ma20:.0f}%')
    elif -3 < dist_ma20 < 0:
        score += 8
        reasons.append('回踩MA20')

    # --- 成交量 (0-15) ---
    vol_5 = sum(volumes[-5:]) / 5
    vol_10 = sum(volumes[-10:-5]) / 5 if len(volumes) >= 10 else vol_5
    if vol_5 > vol_10 * 1.3:
        score += 10
        reasons.append('放量')
    elif vol_5 > vol_10 * 0.8:
        score += 5

    # 排除成交量太小的冷门票
    if vol_5 < 500000:
        score -= 10
        warnings.append('量太小')

    # --- 题材 (0-15) ---
    if main_sector != '其他':
        score += 15
        reasons.append(f'主线: {main_sector}')
    else:
        score += 2

    # --- 龙头权重 (0-10) ---
    if is_leader:
        score += 10
        reasons.append('⭐龙头票')
    else:
        # 看是否在主线板块里（有板块但非龙头）
        if main_sector != '其他':
            score += 2  # 板块成分股，但不是龙头

    # --- 季节性题材加分 (0-8) ---
    if seasonal_boost_map:
        seasonal_boost = 0.0
        matched_theme = None
        for kw, boost_val in seasonal_boost_map.items():
            if kw in name:
                seasonal_boost = max(seasonal_boost, boost_val)
                matched_theme = kw
        if seasonal_boost > 0:
            bonus = round(seasonal_boost * 8)
            score += bonus
            reasons.append(f'📅季节性({matched_theme} +{bonus})')

    # --- 底部吸筹: 多放量但不涨 (0-5) ---
    # 近10天内，有5天满足 量>均量×1.5 且当日涨幅<2%
    v_avg = sum(volumes[-37:]) / 37 if len(volumes) >= 37 else sum(volumes) / len(volumes)
    accum_count = 0
    for i in range(-10, 0):
        if abs(i) > len(closes) - 1:
            break
        day_vol = volumes[i]
        day_chg = (closes[i] - closes[i - 1]) / closes[i - 1] if i - 1 >= -len(closes) else 0
        if v_avg > 0 and day_vol > v_avg * 1.5 and -0.03 < day_chg < 0.02:
            accum_count += 1
    if accum_count >= 5:
        score += 5
        reasons.append(f'底部吸筹({accum_count}天放量不涨)')

    # --- 碎步小阳: 多小幅持续上涨 (0-5) ---
    # 近10天内7天阳线，每日涨幅 0~3%
    grind_count = 0
    for i in range(-10, 0):
        if abs(i) > len(closes) - 1:
            break
        day_chg = (closes[i] - closes[i - 1]) / closes[i - 1] if i - 1 >= -len(closes) else 0
        if 0 < day_chg < 0.03:
            grind_count += 1
    if grind_count >= 7:
        score += 5
        reasons.append(f'碎步小阳({grind_count}天持续小涨)')

    # --- 市值级别 (0-5) ---
    cap_level, cap_bonus = estimate_market_cap_level(current)
    if cap_level == 'large':
        score += 5
        reasons.append('大盘股')
    elif cap_level == 'medium':
        score += 3
        reasons.append('中盘')

    # --- 恐慌日抗跌 (0-25) ---
    if quote and panic_mode:
        chg = quote['change_pct']
        if chg > 1:
            score += 25
            reasons.append(f'恐慌日抗跌 {chg:+.1f}%')
        elif chg > -2:
            score += 18
            reasons.append(f'恐慌日平收 {chg:+.1f}%')
        elif chg > -5:
            score += 8
        else:
            score += 2

    # --- 近期涨幅合理性 (扣分项) ---
    chg_5d = (closes[-1] / closes[-6] - 1) * 100 if len(closes) >= 6 else 0
    chg_20d = (closes[-1] / closes[-21] - 1) * 100 if len(closes) >= 21 else 0

    if chg_20d > 60:
        score -= 10
        warnings.append(f'20日涨{chg_20d:.0f}% 追高风险')
    elif chg_20d > 30:
        score -= 3

    if chg_5d < -15:
        score -= 8
        warnings.append('短期暴跌 趋势可能坏了')
    elif chg_5d < -8:
        score -= 3

    # --- 连续下跌(扣分) ---
    if len(closes) >= 4:
        if closes[-1] < closes[-2] < closes[-3] < closes[-4]:
            score -= 8
            warnings.append('连跌3天')

    return max(0, min(100, score)), reasons, warnings


def calc_stop_loss(daily):
    closes = [d['close'] for d in daily]
    lows = [d['low'] for d in daily]
    low_10 = min(lows[-10:])
    m20 = ma(closes, 20)
    stop_ref = min(m20, low_10)
    stop = round(stop_ref * 0.97, 2)
    return {
        'ma20': round(m20, 2),
        'recent_low': round(low_10, 2),
        'stop_loss': stop,
        'risk_pct': round((closes[-1] / stop - 1) * 100, 1) if stop > 0 else 999,
    }


# ============================================================
# 深度模式（仅对 TOP 结果拉新闻）
# ============================================================

def deep_check(code):
    """对单支票检查新闻和逻辑硬伤"""
    flags = []
    try:
        df = ak.stock_news_em(symbol=code)
        if df is not None:
            for _, r in df.head(15).iterrows():
                title = str(r.get('新闻标题', '') or '')
                content = str(r.get('新闻内容', '') or '')
                text = title + content
                if any(kw in text for kw in ['暂未开展业务', '澄清', '不存在业务']):
                    flags.append('公司澄清')
                    break
                if any(kw in text for kw in ['立案', '处罚', '违规']):
                    flags.append('监管风险')
                    break
    except Exception:
        pass
    return flags


# ============================================================
# 板块内横向对比
# ============================================================

def rank_within_sector(results):
    """按板块分组，组内计算五维归一化排名"""
    from collections import defaultdict
    groups = defaultdict(list)
    for r in results:
        sector = r.get('sector', '其他')
        groups[sector].append(r)

    for sector, stocks in groups.items():
        if len(stocks) < 2:
            for s in stocks:
                s['intra_sector_rank'] = 1
                s['intra_sector_total'] = 1
            continue

        # 计算各维度的最大值用于归一化
        ma_scores = [s.get('score', 0) for s in stocks]  # 使用综合分作为均线代理
        for s in stocks:
            # 均线: 用已有评分中的一部分
            ma_rel = s['score'] / max(ma_scores) if max(ma_scores) > 0 else 0

            # 量能: 从 reasons 中提取
            has_volume = any('放量' in reason for reason in s.get('reasons', []))
            vol_rel = 1.0 if has_volume else 0.5

            # 龙头加分
            leader_rel = 1.0 if s.get('is_leader') else 0.2

            # 板块内分数
            s['intra_sector_score'] = round(
                ma_rel * 0.35 + vol_rel * 0.25 + leader_rel * 0.25 + (1.0 / len(stocks)) * 0.15, 2
            )

        stocks.sort(key=lambda x: x['intra_sector_score'], reverse=True)
        for i, s in enumerate(stocks):
            s['intra_sector_rank'] = i + 1
            s['intra_sector_total'] = len(stocks)

    return results


def print_sector_comparison(results):
    """打印板块横向对比报告"""
    from collections import defaultdict
    groups = defaultdict(list)
    for r in results:
        sector = r.get('sector', '其他')
        groups[sector].append(r)

    # 只对候选数≥2的板块做对比
    multi_groups = {k: v for k, v in groups.items() if len(v) >= 2}
    if not multi_groups:
        return

    print(f"\n{'─'*80}")
    print(f"  📊 板块内横向对比")
    print(f"{'─'*80}")

    for sector in sorted(multi_groups.keys()):
        stocks = multi_groups[sector]
        if len(stocks) < 2:
            continue

        rank_within_sector(stocks)
        print(f"\n  【{sector}】 共 {len(stocks)} 只候选")
        print(f"  {'排名':<5}{'代码':<12}{'名称':<12}{'得分':<7}{'板块内分':<9}{'龙头'}")
        print(f"  {'-'*50}")
        for s in sorted(stocks, key=lambda x: x.get('intra_sector_rank', 99)):
            rank = s.get('intra_sector_rank', '?')
            leader = '⭐龙头' if s.get('is_leader') else ''
            print(f"  {rank}/{s.get('intra_sector_total','?')}"
                  f"   {s['code']:<10}{s['name']:<12}"
                  f"{s['score']:<7}{s.get('intra_sector_score', 0):<9.2f}{leader}")
    print()


# ============================================================
# 主流程
# ============================================================

def screen(args):
    print(f"\n{'='*70}")
    print(f"  Smart Screener v2 — 全市场智能选股")
    print(f"  {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}")
    if args.panic:
        print(f"  ⚠️ 恐慌日模式")
    if args.sector:
        print(f"  🎯 板块: {args.sector}")
    print(f"{'='*70}")

    # 0. 加载题材日历
    seasonal_boost_map = {}
    if not args.no_seasonal:
        seasonal_boost_map = get_keyword_boost_map()
        if seasonal_boost_map:
            print(f"\n📅 季节性题材活跃窗口:")
            for theme in get_active_themes():
                label = {'preheat': '🔥预热', 'active': '🟢活跃', 'cooldown': '🌙退潮'}.get(theme['status'], '')
                kw_preview = ', '.join(theme['keywords'][:5])
                print(f"   {label} {theme['name']} (强度{theme['boost']:.0%}): {kw_preview}...")

    # 0.5 加载动态主线
    dynamic_sectors, dynamic_purity, theme_scores_map = {}, {}, {}
    if not args.no_dynamic:
        print(f"\n🔍 动态主线分析...")
        dynamic_sectors, dynamic_purity, theme_scores_map = load_dynamic_themes(
            datetime.date.today()
        )
        if dynamic_sectors:
            print(f"   ✅ 加载 {len(dynamic_sectors)} 条动态主线")
        else:
            print(f"   ℹ️ 无新增动态主线，使用默认8条科技主线")
    else:
        print(f"\n🔍 动态主线: 已禁用")

    # 1. 加载股票列表
    all_stocks = load_all_stocks()
    print(f"\n📊 A 股总数: {len(all_stocks)}")

    # 2. 加载实时行情
    quotes = load_realtime_quotes()
    if quotes:
        print(f"📈 实时行情: {len(quotes)} 只")

    # 3. 批量加载日K
    print(f"📅 加载日K数据...")
    codes = [s['code'] for s in all_stocks]
    daily_map = load_daily_data(codes, days=60)
    print(f"   有60天数据的: {len(daily_map)} 只")

    # 4. 逐只评分
    print(f"\n🔍 评分中...")
    results = []
    idx = 0
    total = len(daily_map)

    for code, daily in daily_map.items():
        idx += 1
        if idx % 500 == 0:
            print(f"   进度: {idx}/{total} ({idx/total*100:.0f}%)")

        # 找对应股票信息
        stock_info = next((s for s in all_stocks if s['code'] == code), None)
        if not stock_info:
            continue

        # 归属板块 (新返回格式: sectors列, is_leader)
        sectors, is_leader = assign_sector(stock_info, dynamic_sectors, dynamic_purity)

        # 板块过滤
        if args.sector:
            if not any(args.sector.lower() in s.lower() for s in sectors):
                continue
        elif not args.all:
            if not sectors:
                continue

        # 成交量过滤
        closes = [d['close'] for d in daily]
        volumes = [d['volume'] for d in daily]
        avg_vol_20 = sum(volumes[-20:]) / 20
        if avg_vol_20 < 500000:
            continue

        quote = quotes.get(code)

        # 评分
        score, reasons, warnings = score_stock(
            code, daily, (sectors, is_leader), quote,
            panic_mode=args.panic, name=stock_info['name'],
            seasonal_boost_map=seasonal_boost_map,
        )

        # 止损
        stop_info = calc_stop_loss(daily)

        main_sector = sectors[0] if sectors else '其他'

        # 板块指数涨幅分（用于后续回溯验证板块动量）
        # 选股器的板块简称 → DB 主题全称 映射（仅需覆盖 SECTOR_TO_KEYWORD 的 key）
        _SECTOR_TO_SCORE_NAME = {
            '光模块/CPO': '共封装光学(CPO)',
            'PCB': 'PCB概念',
            '电感/被动元件': '被动元件',
            'AI服务器': '液冷服务器',
            '半导体封测': '先进封装',
            '晶圆代工': '中芯国际概念',
        }
        clean = _strip_sector_label(main_sector)
        sector_rise = theme_scores_map.get(clean)
        if sector_rise is None:
            mapped = _SECTOR_TO_SCORE_NAME.get(clean)
            if mapped:
                sector_rise = theme_scores_map.get(mapped)
        # 兜底：尝试加"概念"后缀
        if sector_rise is None:
            sector_rise = theme_scores_map.get(clean + '概念')

        results.append({
            'code': code,
            'name': stock_info['name'],
            'sw1': stock_info['sw1'],
            'sector': main_sector,
            'is_leader': is_leader,
            'all_sectors': sectors,
            'price': closes[-1],
            'quote': quote,
            'score': score,
            'reasons': reasons,
            'warnings': warnings,
            'stop_loss': stop_info['stop_loss'],
            'risk_pct': stop_info['risk_pct'],
            'sector_index_rise': sector_rise,
        })

    # 5. 排序
    results.sort(key=lambda x: x['score'], reverse=True)
    top_n = args.top or 20

    # 6. 深度检查（仅对 TOP 结果）
    if args.deep and len(results) > 0:
        print(f"\n🔬 深度检查 TOP {min(10, len(results))}...")
        for i, r in enumerate(results[:10]):
            try:
                flags = deep_check(r['code'])
                if flags:
                    r['warnings'].extend(flags)
                    r['score'] = max(0, r['score'] - 15)
                time.sleep(0.5)
            except Exception:
                pass

    # 7. 输出
    print(f"\n{'='*80}")
    print(f"  🎯 TOP {top_n}  总候选: {len(results)}")
    if args.panic:
        print(f"  ⚠️ 恐慌日模式: 优先选抗跌翻红票")
    print(f"{'='*80}")

    for i, r in enumerate(results[:top_n]):
        leader_tag = ' ⭐龙头' if r.get('is_leader') else ''
        strike = ' ⚠️⚠️' if r['warnings'] else ''
        print(f"\n  #{i+1}  {r['name']} ({r['code']})  得分: {r['score']}{strike}{leader_tag}")
        print(f"      行业: {r['sw1']}  板块: {r['sector']}  现价: {r['price']:.2f}")
        if r['quote']:
            print(f"      涨跌: {r['quote']['change_pct']:+.2f}%  成交额: {r['quote']['amount']/1e8:.1f}亿")
        print(f"      加分: {' | '.join(r['reasons'])}")
        if r['warnings']:
            print(f"      ⚠️ 风险: {' | '.join(r['warnings'])}")
        print(f"      止损: {r['stop_loss']}  风险: {r['risk_pct']}%")

    # 5.5 板块内横向对比
    print_sector_comparison(results)

    # 统计
    high = sum(1 for r in results if r['score'] >= 70)
    mid = sum(1 for r in results if 50 <= r['score'] < 70)
    print(f"\n{'='*80}")
    print(f"  📊 高分(>=70): {high}  中等(50-69): {mid}  总候选: {len(results)}")
    print(f"{'='*80}\n")

    # 保存到数据库
    if args.save and len(results) > 0:
        save_to_db(results, today_str())


def save_to_db(results, screen_date):
    """将筛选结果写入数据库"""
    conn = get_db()
    c = conn.cursor()
    saved = 0
    for r in results:
        try:
            c.execute('''
                INSERT INTO smart_screen_results
                (screen_date, code, name, score, sector, is_leader,
                 price, stop_loss, reasons, warnings, sector_index_rise)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON DUPLICATE KEY UPDATE
                score=VALUES(score), price=VALUES(price),
                is_leader=VALUES(is_leader),
                sector_index_rise=VALUES(sector_index_rise),
                reasons=VALUES(reasons), warnings=VALUES(warnings)
            ''', (
                screen_date,
                r['code'], r['name'], r['score'],
                r['sector'], 1 if r.get('is_leader') else 0,
                r['price'], r['stop_loss'],
                json.dumps(r['reasons'], ensure_ascii=False),
                json.dumps(r['warnings'], ensure_ascii=False),
                r.get('sector_index_rise'),
            ))
            saved += 1
        except Exception:
            pass
    conn.commit()
    c.close()
    conn.close()
    print(f"\n💾 已保存 {saved} 条到 smart_screen_results 表")


def backfill_returns():
    """回填历史筛选结果的未来收益"""
    print("\n📊 开始回填收益...")
    conn = get_db()
    c = conn.cursor()

    # 找到所有尚未回填的记录
    c.execute("""
        SELECT id, screen_date, code, price FROM smart_screen_results
        WHERE ret_5d IS NULL
        ORDER BY screen_date, code
    """)
    rows = c.fetchall()

    updated = 0
    for row_id, screen_date, code, price in rows:
        suffix = '.SH' if code.startswith('6') else '.SZ'
        full_code = code + suffix

        # 查询未来第 N 个交易日的收盘价
        for days, col in [(1, 'ret_1d'), (3, 'ret_3d'), (5, 'ret_5d'),
                           (10, 'ret_10d'), (20, 'ret_20d')]:
            try:
                c.execute('''
                    SELECT close FROM daily_info_tbl
                    WHERE code=%s AND tradedate > %s
                    ORDER BY tradedate ASC LIMIT 1 OFFSET %s
                ''', (full_code, screen_date, days - 1))
                row = c.fetchone()
                if row:
                    ret = (float(row[0]) / float(price) - 1)
                    c.execute(f'UPDATE smart_screen_results SET {col}=%s WHERE id=%s', (round(ret, 4), row_id))
                    updated += 1
            except Exception:
                pass

    conn.commit()
    c.close()
    conn.close()
    print(f"✅ 回填完成，更新 {updated} 条收益记录")


def analyze_results():
    """分析历史筛选效果，含板块动量维度"""
    conn = get_db()
    c = conn.cursor()

    # 找到有收益数据的记录
    c.execute("SELECT COUNT(*) FROM smart_screen_results WHERE ret_1d IS NOT NULL")
    has_1d = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM smart_screen_results WHERE ret_5d IS NOT NULL")
    has_5d = c.fetchone()[0]

    ret_col = 'ret_1d' if has_1d > 0 and has_5d == 0 else ('ret_5d' if has_5d > 0 else None)
    if ret_col is None:
        print("\n  ⚠️ 尚无回填收益数据，请先执行 --backfill")
        conn.close()
        return

    ret_label = {'ret_1d': '1日', 'ret_5d': '5日'}.get(ret_col, ret_col)

    print(f"\n{'='*70}")
    print(f"  📊 回溯分析报告（基于 {ret_label} 收益）")
    print(f"{'='*70}")

    # --- 1. 得分区间 ---
    c.execute(f"""
        SELECT CASE WHEN score>=70 THEN '70+'
                     WHEN score>=50 THEN '50-69'
                     ELSE '<50' END as tier,
            COUNT(*), ROUND(AVG({ret_col})*100,2)
        FROM smart_screen_results WHERE {ret_col} IS NOT NULL
        GROUP BY tier ORDER BY tier DESC
    """)
    rows = c.fetchall()
    if rows:
        print(f"\n  📊 按得分区间（{ret_label}）：")
        for r in rows:
            print(f"    {r[0]:8s}: {r[1]}只  avg={r[2]:+.2f}%")

    # --- 2. 龙头 vs 非龙头 ---
    c.execute(f"""
        SELECT is_leader, COUNT(*), ROUND(AVG({ret_col})*100,2)
        FROM smart_screen_results WHERE {ret_col} IS NOT NULL
        GROUP BY is_leader
    """)
    rows = c.fetchall()
    if rows:
        print(f"\n  👑 龙头 vs 非龙头（{ret_label}）：")
        for r in rows:
            label = '⭐龙头' if r[0] else '非龙头'
            print(f"    {label:8s}: {r[1]}只  avg={r[2]:+.2f}%")

    # --- 3. 板块收益 ---
    c.execute(f"""
        SELECT sector, COUNT(*) as cnt, ROUND(AVG({ret_col})*100,2) as avg_ret
        FROM smart_screen_results WHERE {ret_col} IS NOT NULL
        GROUP BY sector HAVING cnt>=3
        ORDER BY avg_ret DESC LIMIT 10
    """)
    rows = c.fetchall()
    if rows:
        print(f"\n  🏆 板块收益 TOP10（{ret_label}）：")
        for r in rows:
            print(f"    {r[0]:25s}: {r[1]}只  avg={r[2]:+.2f}%")

    # --- 4. 板块动量分析（sector_index_rise）---
    c.execute(f"""
        SELECT CASE WHEN sector_index_rise >= 8 THEN '强(8-10)'
                     WHEN sector_index_rise >= 5 THEN '中(5-8)'
                     WHEN sector_index_rise >= 2 THEN '弱(2-5)'
                     WHEN sector_index_rise IS NOT NULL THEN '极弱(<2)'
                     ELSE '无数据' END as tier,
            COUNT(*), ROUND(AVG({ret_col})*100,2) as avg_ret
        FROM smart_screen_results WHERE {ret_col} IS NOT NULL
        GROUP BY tier ORDER BY tier
    """)
    rows = c.fetchall()
    if rows and any(r[0] != '无数据' for r in rows):
        print(f"\n  📈 板块强度 vs 个股收益（{ret_label}，攒数据中）：")
        print(f"    {'板块强度':12s} {'数量':>5s} {'平均收益':>10s} {'结论':s}")
        print(f"    {'-'*42}")
        for r in rows:
            conclusion = ''
            if '强' in r[0] and r[2] and r[2] > 0:
                conclusion = '← 强板块赚钱效应'
            elif '极弱' in r[0] and r[2] and r[2] < 0:
                conclusion = '← 弱板块拖累'
            print(f"    {r[0]:12s} {r[1]:>5d}  {r[2]:>+10.2f}%  {conclusion}")

    # --- 5. 最近一期详情 ---
    c.execute("SELECT MAX(screen_date) FROM smart_screen_results WHERE ret_1d IS NOT NULL")
    latest = c.fetchone()[0]
    if latest:
        c.execute(f"""
            SELECT COUNT(*), ROUND(AVG(ret_1d)*100,2),
                   COUNT(CASE WHEN ret_1d>0 THEN 1 END)
            FROM smart_screen_results
            WHERE screen_date=%s AND ret_1d IS NOT NULL
        """, (latest,))
        total, avg, win = c.fetchone()
        print(f"\n  📅 {latest} 当日：")
        print(f"    共 {total} 只, 平均 ret_1d={avg:+.2f}%, 胜率={win}/{total} ({win/total*100:.0f}%)")

    conn.close()
    print(f"\n{'='*70}\n")


def main():
    parser = argparse.ArgumentParser(description='Smart Screener v2')
    parser.add_argument('--sector', type=str, help='指定板块')
    parser.add_argument('--panic', action='store_true', help='恐慌日模式')
    parser.add_argument('--all', action='store_true', help='全市场（不限主线）')
    parser.add_argument('--deep', action='store_true', help='深度模式(拉新闻)')
    parser.add_argument('--no-seasonal', action='store_true', help='禁用季节性题材加权')
    parser.add_argument('--no-dynamic', action='store_true', help='禁用动态主线加载')
    parser.add_argument('--top', type=int, default=20, help='输出前 N 名')
    parser.add_argument('--save', action='store_true', help='保存结果到数据库')
    parser.add_argument('--backfill', action='store_true', help='回填历史收益')
    parser.add_argument('--analyze', action='store_true', help='回溯分析')
    args = parser.parse_args()

    if args.backfill:
        backfill_returns()
    elif args.analyze:
        analyze_results()
    else:
        screen(args)


if __name__ == '__main__':
    main()
