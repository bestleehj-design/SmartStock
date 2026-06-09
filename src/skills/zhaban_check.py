# -*- coding: utf-8 -*-

# Ensure src/ directory is in sys.path for package imports
import sys, os
_SRC_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _SRC_DIR not in sys.path:
    sys.path.insert(0, _SRC_DIR)
"""
涨停炸板分析
用法: python3 zhaban_check.py <股票代码>
示例: python3 zhaban_check.py 002138
"""

import sys
import requests
import pymysql

DB_CONFIG = {
    'host': 'localhost', 'port': 3306,
    'user': 'root', 'password': '12345678',
    'database': 'gp2', 'charset': 'utf8mb4',
}

SINA_URL = 'https://hq.sinajs.cn/list={}'
SINA_HEADERS = {'Referer': 'https://finance.sina.com.cn'}

def get_market_suffix(code):
    """根据代码判断交易所后缀"""
    code = code.replace('.SH', '').replace('.SZ', '')
    if code.startswith('6') or code.startswith('9'):
        return 'sh' + code
    elif code.startswith('0') or code.startswith('3'):
        return 'sz' + code
    return 'sh' + code

def get_db_code(code):
    """获取数据库中的代码格式"""
    code = code.replace('.SH', '').replace('.SZ', '')
    if code.startswith('6') or code.startswith('9'):
        return code + '.SH'
    elif code.startswith('0') or code.startswith('3'):
        return code + '.SZ'
    return code + '.SH'

def get_realtime(code):
    """获取实时行情"""
    sina_code = get_market_suffix(code)
    try:
        r = requests.get(SINA_URL.format(sina_code), headers=SINA_HEADERS, timeout=10)
        data = r.text.split('"')[1].split(',')
        return {
            'name': data[0],
            'open': float(data[1]),
            'yest_close': float(data[2]),
            'price': float(data[3]),
            'high': float(data[4]),
            'low': float(data[5]),
            'volume': float(data[8]),
            'amount': float(data[9]),
        }
    except Exception as e:
        return {'error': str(e)}

def get_history(code):
    """获取60天历史日K"""
    db_code = get_db_code(code)
    try:
        conn = pymysql.connect(**DB_CONFIG)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT tradedate, open, high, low, close, volume FROM daily_info_tbl "
            "WHERE code=%s ORDER BY tradedate DESC LIMIT 60",
            (db_code,)
        )
        rows = list(cursor.fetchall())
        cursor.close()
        conn.close()
        rows.reverse()
        closes = [float(r[4]) for r in rows]
        volumes = [float(r[5]) for r in rows]
        highs = [float(r[2]) for r in rows]
        return {
            'closes': closes,
            'volumes': volumes,
            'highs': highs,
            'rows': rows,
        }
    except Exception as e:
        return {'error': str(e)}

def calc_limit(price, market_code):
    """计算涨停价"""
    code = market_code.replace('.SH', '').replace('.SZ', '')
    if code.startswith('3') or code.startswith('688'):
        return round(price * 1.20, 2)  # 创业板/科创板 20%
    return round(price * 1.10, 2)  # 主板 10%

def analyze(code):
    """四维分析"""
    rt = get_realtime(code)
    hist = get_history(code)

    if rt.get('error'):
        return f"获取实时数据失败: {rt['error']}"
    if hist.get('error'):
        return f"获取历史数据失败: {hist['error']}"

    yest = rt['yest_close']
    limit_up = calc_limit(yest, get_db_code(code))
    high = rt['high']
    price = rt['price']
    close = rt['price']  # current as close
    open_p = rt['open']

    closes = hist['closes']
    volumes = hist['volumes']

    ma5 = sum(closes[-5:]) / 5 if len(closes) >= 5 else closes[-1]
    ma10 = sum(closes[-10:]) / 10 if len(closes) >= 10 else closes[-1]
    ma20 = sum(closes[-20:]) / 20 if len(closes) >= 20 else closes[-1]

    avg_vol_20 = sum(volumes[-20:]) / 20 if len(volumes) >= 20 else 0
    # Sina返回股，DB存手(100股)，统一换算
    today_vol_shou = rt['volume'] / 100
    vol_ratio = today_vol_shou / avg_vol_20 if avg_vol_20 > 0 else 0
    prev_ma5 = sum(closes[-6:-1]) / 5 if len(closes) >= 6 else ma5

    # 是否触及涨停
    touched_limit = abs(high - limit_up) / limit_up < 0.005 if limit_up > 0 else False
    broke_limit = touched_limit and (limit_up - price) / limit_up > 0.003

    print(f"\n{'='*55}")
    print(f"  📊 涨停炸板分析 — {rt['name']} ({code})")
    print(f"{'='*55}")
    print(f"  昨收: {yest:.2f}  涨停价: {limit_up:.2f}")
    print(f"  今开: {open_p:.2f}  最高: {high:.2f}  现价: {price:.2f}")
    print(f"  涨幅: {(price-yest)/yest*100:+.2f}%")
    print(f"  从涨停回落: {limit_up-price:.2f}元 ({(limit_up-price)/limit_up*100:.1f}%)")
    print(f"  成交量: {rt['volume']/1e6:.0f}万股")

    if not touched_limit:
        print(f"  ⚠️ 今日未触及涨停，非炸板场景")
        return

    if not broke_limit:
        print(f"  ✅ 涨停封板中，暂未开板")
        return

    # ---- 四维分析 ----
    print(f"\n  {'─'*50}")
    print(f"  🔍 四维分析")
    print(f"  {'─'*50}")

    score_breakout = 0
    score_top = 0

    # 维度1: 成交量
    print(f"\n  维度1: 成交量")
    print(f"    今日量/{today_vol_shou/1e4:.0f}万手  20日均量/{avg_vol_20/1e4:.0f}万手  量比{vol_ratio:.1f}")
    if vol_ratio > 1.5:
        print(f"    ✅ 放量 → +1 突破")
        score_breakout += 1
    else:
        print(f"    ⚠️ 缩量 → +1 见顶")
        score_top += 1

    # 维度2: 收盘位置
    drop_from_limit = (limit_up - price) / limit_up * 100
    print(f"\n  维度2: 收盘位置")
    print(f"    现价距涨停 {drop_from_limit:.1f}%")
    if drop_from_limit < 3:
        print(f"    ✅ 回落 <3%，维持在涨停附近 → +1 突破")
        score_breakout += 1
    elif drop_from_limit < 5:
        print(f"    ⚡ 回落 3-5%，分歧较大 → 中立")
    else:
        print(f"    ⚠️ 回落 >5%，高位抛压重 → +1 见顶")
        score_top += 1

    # 维度3: K线形态
    body = abs(price - open_p)
    upper_shadow = high - max(price, open_p)
    total_range = high - rt['low']
    print(f"\n  维度3: K线形态")
    print(f"    实体:{body:.2f}  上影:{upper_shadow:.2f}  振幅:{total_range:.2f}")
    if price > open_p and upper_shadow < body * 0.5:
        print(f"    ✅ 实体阳线，上影线短 → +1 突破")
        score_breakout += 1
    elif price < open_p or upper_shadow > body:
        print(f"    ⚠️ 阴线或长上影线 → +1 见顶")
        score_top += 1
    else:
        print(f"    ⚡ 中性K线 → 中立")

    # 维度4: MA趋势
    ma5_trend = ma5 - prev_ma5
    print(f"\n  维度4: MA趋势")
    print(f"    MA5:{ma5:.2f}  MA10:{ma10:.2f}  MA20:{ma20:.2f}")
    print(f"    现货 vs MA5: {'✅站上' if price > ma5 else '⚠️跌破'}")
    if ma5_trend > 0 and price > ma5:
        print(f"    ✅ MA5向上+站上 → +1 突破")
        score_breakout += 1
    elif price < ma5:
        print(f"    ⚠️ 跌破MA5 → +1 见顶")
        score_top += 1
    else:
        print(f"    ⚡ 趋势不明 → 中立")

    # ---- 结论 ----
    print(f"\n  {'─'*50}")
    print(f"  🎯 结论: 突破 {score_breakout} vs 见顶 {score_top}")
    print(f"  {'─'*50}")

    if score_breakout >= 3:
        print(f"\n  ✅ 突破信号 ({score_breakout}/{4})  — 继续持有")
        print(f"  📌 建议: 不卖出。设移动止盈 = 今日最低价{rt['low']:.2f}")
    elif score_breakout == 2 and score_top == 2:
        print(f"\n  ⚡ 信号平局 (2:2)  — 出一半观察")
        print(f"  📌 建议: 卖出一半锁利润，留一半等明天确认方向")
    elif score_top >= 3:
        print(f"\n  ⚠️ 见顶信号 ({score_top}/{4})  — 建议减仓或清仓")
        print(f"  📌 建议: 至少减半。如果持仓成本低可设MA5止损，MA10全清")
    else:
        print(f"\n  ⚡ 信号混合 — 出一半观察")
        print(f"  突破分:{score_breakout}  见顶分:{score_top}")
        print(f"  📌 建议: 先出一半，留一半观察。设 MA20{ma20:.2f} 止损")

    print()

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("用法: python3 zhaban_check.py <股票代码>")
        print("示例: python3 zhaban_check.py 002138")
        sys.exit(1)

    code = sys.argv[1]
    analyze(code)
