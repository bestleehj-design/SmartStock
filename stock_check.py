# -*- coding: utf-8 -*-
"""
单票快速分析 — Skill: /check
用法:
  python3 stock_check.py 600584          # A股
  python3 stock_check.py 00981 HK        # 港股

输出: 基本信息、今日分时、日K、均线、财务、新闻、概念板块
"""
import sys
import os
import datetime

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
os.chdir(SCRIPT_DIR)
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

import akshare as ak
import pymysql

DB_CONFIG = {
    'host': 'localhost', 'port': 3306,
    'user': 'root', 'password': '12345678',
    'database': 'gp2', 'charset': 'utf8mb4',
}


def get_stock_basic(code, market='A'):
    """从数据库获取基本面信息"""
    suffix = '.SH' if code.startswith('6') else '.SZ'
    full_code = code + suffix
    try:
        conn = pymysql.connect(**DB_CONFIG)
        c = conn.cursor()
        c.execute("SELECT name, sw1, sw2, sw3, market FROM stock_basic_info_tbl WHERE code = %s", (full_code,))
        row = c.fetchone()
        c.close()
        conn.close()
        if row:
            return {'name': row[0], 'sw1': row[1], 'sw2': row[2], 'sw3': row[3], 'market': row[4]}
    except Exception:
        pass
    return {}


def get_intraday(code, market='A'):
    """获取今日分时"""
    sym = ('sh' if code.startswith('6') else 'sz') + code
    try:
        df = ak.stock_zh_a_minute(symbol=sym, period='1')
        today = df[df['day'].astype(str).str.startswith(datetime.date.today().strftime('%Y-%m-%d'))]
        if len(today) == 0:
            return None
        closes = today['close'].astype(float)
        highs = today['high'].astype(float)
        lows = today['low'].astype(float)
        opens = today['open'].astype(float)
        return {
            'open': opens.iloc[0],
            'high': highs.max(),
            'low': lows.min(),
            'latest': closes.iloc[-1],
            'data': today,
            'closes': closes,
        }
    except Exception as e:
        print(f'  分时数据获取失败: {e}')
        return None


def get_daily_k(code, market='A'):
    """获取近期日K和均线"""
    sym = ('sh' if code.startswith('6') else 'sz') + code
    try:
        df = ak.stock_zh_a_daily(symbol=sym, start_date='20260401', end_date='20260608', adjust='qfq')
    except Exception:
        try:
            df = ak.stock_zh_a_hist(symbol=code, period='daily', start_date='20260401', end_date='20260608', adjust='qfq')
        except Exception:
            return None
    if df is None or len(df) == 0:
        return None
    closes = [float(r['close']) for _, r in df.iterrows()]
    current = closes[-1]
    ma5 = sum(closes[-5:]) / 5 if len(closes) >= 5 else current
    ma10 = sum(closes[-10:]) / 10 if len(closes) >= 10 else current
    ma20 = sum(closes[-20:]) / 20 if len(closes) >= 20 else sum(closes) / len(closes)

    return {
        'df': df,
        'closes': closes,
        'current': current,
        'ma5': ma5,
        'ma10': ma10,
        'ma20': ma20,
        'high_20': max(closes[-20:]),
        'low_20': min(closes[-20:]),
    }


def get_financial(code):
    """获取近期财务数据"""
    try:
        df = ak.stock_financial_abstract_ths(symbol=code, indicator='按报告期')
        recent = df.tail(5)
        result = []
        for _, r in recent.iterrows():
            result.append({
                'period': str(r['报告期']),
                'profit': str(r['净利润']),
                'profit_yoy': str(r['净利润同比增长率']),
                'revenue': str(r['营业总收入']),
                'rev_yoy': str(r.get('营业总收入同比增长率', '')),
            })
        return result
    except Exception:
        return []


def get_news(code):
    """获取近期新闻"""
    try:
        df = ak.stock_news_em(symbol=code)
        news = []
        for _, r in df.head(8).iterrows():
            title = str(r.get('新闻标题', '') or r.get('content', ''))[:100]
            date = str(r.get('发布时间', '') or r.get('datetime', ''))[:16]
            news.append({'title': title, 'date': date})
        return news
    except Exception:
        return []


def check_stock(code, market='A'):
    """主函数: 综合输出分析报告"""
    basic = get_stock_basic(code, market)
    name = basic.get('name', code)

    print(f"\n{'='*60}")
    print(f"  {name} ({code})  分析时间: {datetime.datetime.now().strftime('%H:%M')}")
    print(f"{'='*60}")

    # 基本资料
    if basic:
        print(f"\n  📋 基本资料")
        print(f"  行业: {basic.get('sw1','')} → {basic.get('sw2','')} → {basic.get('sw3','')}")
        print(f"  市场: {basic.get('market','')}")

    # 分时
    intra = get_intraday(code, market)
    if intra:
        print(f"\n  📈 今日分时")
        print(f"  开盘: {intra['open']:.2f}  最高: {intra['high']:.2f}  最低: {intra['low']:.2f}  最新: {intra['latest']:.2f}")
        # 走势描述
        opens_val = intra['closes'].iloc[0]
        mid_val = intra['closes'].iloc[min(30, len(intra['closes'])-1)]
        trend = '↑ 持续拉升' if intra['latest'] > mid_val > opens_val else \
                '↓ 持续走弱' if intra['latest'] < mid_val < opens_val else \
                '→ 横盘震荡' if abs(intra['latest'] - mid_val) / mid_val < 0.02 else \
                '↗ 先跌后涨' if opens_val < intra['latest'] else '↘ 先涨后跌'
        print(f"  走势: {trend}")

    # 日K + 均线
    daily = get_daily_k(code, market)
    if daily:
        yest = daily['df'].iloc[-2]['close'] if len(daily['df']) > 1 else daily['current']
        chg = (intra['latest'] / yest - 1) * 100 if intra else 0
        print(f"\n  📊 技术指标")
        print(f"  昨收: {yest:.2f}  最新: {intra['latest']:.2f}  涨跌: {chg:+.2f}%")
        print(f"  MA5:  {daily['ma5']:.2f}")
        print(f"  MA10: {daily['ma10']:.2f}")
        print(f"  MA20: {daily['ma20']:.2f}")
        print(f"  20日最高: {daily['high_20']:.2f}  20日最低: {daily['low_20']:.2f}")

        # 均线乖离
        if intra:
            print(f"  距MA5:  {(intra['latest']/daily['ma5']-1)*100:+.1f}%")
            print(f"  距MA20: {(intra['latest']/daily['ma20']-1)*100:+.1f}%")

    # 近期日K
    if daily:
        print(f"\n  📅 近5日收盘")
        for _, r in daily['df'].tail(6).iterrows():
            c = float(r['close'])
            v = int(r['volume'])
            print(f"  {r['date']}  C={c:>8.2f}  V={v:>10.0f}")

    # 财务
    fin = get_financial(code)
    if fin:
        print(f"\n  💰 近期财务")
        for f in fin[-4:]:
            print(f"  {f['period']}  净利={f['profit']}  YoY={f['profit_yoy']}")

    # 新闻
    news = get_news(code)
    if news:
        print(f"\n  📰 近期新闻 TOP5")
        for n in news[:5]:
            print(f"  [{n['date']}] {n['title']}")

    print(f"\n{'='*60}\n")


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("用法: python3 stock_check.py <代码> [HK]")
        print("示例: python3 stock_check.py 600584")
        print("      python3 stock_check.py 00981 HK")
        sys.exit(1)

    code = sys.argv[1]
    market = 'HK' if len(sys.argv) > 2 and sys.argv[2].upper() == 'HK' else 'A'

    try:
        check_stock(code, market)
    except Exception as e:
        print(f"\n  分析出错: {e}")
        import traceback
        traceback.print_exc()
