# -*- coding: utf-8 -*-
"""
盘后综合分析 — 结合大盘、持仓、量价做明日预判
用法: python3 close_analysis.py
"""
import sys, os, re, datetime, requests, pymysql, subprocess

# Ensure src/ directory is in sys.path for package imports
import sys, os
_SRC_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _SRC_DIR not in sys.path:
    sys.path.insert(0, _SRC_DIR)


DB_CONFIG = {
    'host': 'localhost', 'port': 3306,
    'user': 'root', 'password': '12345678',
    'database': 'gp2', 'charset': 'utf8mb4',
}

# 数据管道路径
DATA_DIR = os.path.join(_SRC_DIR, 'data')

SINA_HEADERS = {'Referer': 'https://finance.sina.com.cn'}


def _get_trading_plan_path():
    """定位 trading_plan.md — 从技能脚本路径推导项目根目录"""
    skill_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(os.path.dirname(skill_dir))
    return os.path.join(project_root, 'trading_plan.md')


def _load_holdings_from_md():
    """从 trading_plan.md 读取当前活跃持仓。
    返回 list of dict: [{'code': '600584.SH', 'name': '长电科技', 'plan': '...'}]
    自动跳过已清仓(✅已清)和不活跃的持仓。
    """
    import re
    holdings = []
    plan_path = _get_trading_plan_path()
    if not os.path.exists(plan_path):
        return holdings

    with open(plan_path, 'r') as f:
        content = f.read()

    # 提取 "当前持仓" 表格
    m = re.search(r'## 当前持仓\s*\n\s*\n(.*?)(?=\n## |\n---|\Z)', content, re.DOTALL)
    if not m:
        return holdings
    table_text = m.group(1)

    # 解析表格行: | code | name | market | action | trigger |
    for line in table_text.strip().split('\n'):
        # 跳过表头/分隔行
        if not line.strip().startswith('|') or '---' in line or '代码' in line:
            continue
        cols = [c.strip() for c in line.strip().split('|')[1:-1]]
        if len(cols) < 4:
            continue

        code = cols[0]
        name = cols[1]
        action = cols[3]
        trigger = cols[4] if len(cols) > 4 else ''

        # 跳过已清仓
        if '✅已清' in trigger or '✅已清' in action:
            continue
        # 跳过港股
        if '.HK' in code or action == '港股':
            continue
        # 校验A股代码格式
        if not re.match(r'\d{6}\.(SZ|SH)$', code):
            continue

        plan_text = f"{action} | {trigger}" if action and trigger else (action or trigger)
        holdings.append({'code': code, 'name': name, 'plan': plan_text})

    return holdings


# 指数映射
INDICES = [
    ('sh000001', '上证指数'),
    ('sz399006', '创业板指'),
    ('sh000688', '科创50'),
]


def sync_index_db():
    """从tushare增量更新大盘数据到MySQL"""
    try:
        import tushare as ts
        pro = ts.pro_api()
        conn = pymysql.connect(**DB_CONFIG)
        cursor = conn.cursor()
        for code in ['000001.SH', '399006.SZ', '000688.SH']:
            df = pro.index_daily(ts_code=code, limit=5)
            for _, r in df.iterrows():
                try:
                    cursor.execute('''
                        INSERT INTO market_index_tbl (index_code,tradedate,open,high,low,close,chg_pct,volume,amount)
                        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
                        ON DUPLICATE KEY UPDATE close=VALUES(close),chg_pct=VALUES(chg_pct),amount=VALUES(amount)
                    ''', (code, r['trade_date'], float(r['open']), float(r['high']),
                          float(r['low']), float(r['close']), float(r['pct_chg']),
                          float(r['vol']), float(r['amount'])))
                except:
                    pass
        conn.commit()
        cursor.close()
        conn.close()
    except:
        pass


def get_index_data():
    """从MySQL读取大盘数据（先增量更新，再读取）"""
    sync_index_db()

    conn = pymysql.connect(**DB_CONFIG)
    cursor = conn.cursor()
    result = {}

    name_map = {'000001.SH': ('sh000001', '上证指数'), '399006.SZ': ('sz399006', '创业板指'), '000688.SH': ('sh000688', '科创50')}

    for code, (sina_code, name) in name_map.items():
        try:
            cursor.execute("SELECT tradedate, open, high, low, close, chg_pct, amount FROM market_index_tbl WHERE index_code=%s ORDER BY tradedate DESC LIMIT 6", (code,))
            rows = cursor.fetchall()
            if len(rows) < 2:
                continue
            today = rows[0]
            yesterday = rows[1]
            amt_today = float(today[6]) / 1e5   # 千元→亿元
            amt_yest = float(yesterday[6]) / 1e5
            amt_ratio = amt_today / amt_yest if amt_yest > 0 else 0
            # 近5日均
            amts = [float(rows[i][6]) / 1e5 for i in range(1, min(6, len(rows)))]
            avg5 = sum(amts) / len(amts) if amts else amt_yest

            result[sina_code] = {
                'name': name, 'open': today[1], 'close': today[4],
                'high': today[2], 'low': today[3],
                'chg': round(today[5], 2), 'amount': round(amt_today, 0),
                'amt_ratio': round(amt_ratio, 2), 'avg5_amt': round(avg5, 0),
            }
        except Exception as e:
            result[sina_code] = {'name': name, 'error': str(e)}

    cursor.close()
    conn.close()
    return result


def get_market_breadth():
    """涨跌家数"""
    try:
        import akshare as ak
        df = ak.stock_market_activity_legu()
        up = int(df[df['item'] == '上涨']['value'].values[0])
        down = int(df[df['item'] == '下跌']['value'].values[0])
        limit_up = int(df[df['item'] == '涨停']['value'].values[0])
        limit_down = int(df[df['item'] == '跌停']['value'].values[0])
        return {'up': up, 'down': down, 'limit_up': limit_up, 'limit_down': limit_down,
                'ratio': round(up / max(down, 1), 2)}
    except:
        return None


def get_holding_data():
    """获取持仓今日表现 (从 trading_plan.md 读取持仓列表)"""
    conn = pymysql.connect(**DB_CONFIG)
    cursor = conn.cursor()

    holdings = _load_holdings_from_md()

    # 自动生成 sina 代码映射
    sina_map = {}
    for h in holdings:
        code_num = h['code'].replace('.SH', '').replace('.SZ', '')
        mkt = 'sh' if h['code'].endswith('.SH') else 'sz'
        sina_map[code_num] = f'{mkt}{code_num}'

    results = []
    for h in holdings:
        code = h['code'].replace('.SH', '').replace('.SZ', '')
        sina_code = sina_map.get(code)
        info = {'name': h['name'], 'plan': h['plan'], 'code': code}

        # 实时数据
        if sina_code:
            try:
                r = requests.get(f'https://hq.sinajs.cn/list={sina_code}', headers=SINA_HEADERS, timeout=5)
                d = r.text.split('"')[1].split(',')
                info['price'] = float(d[3])
                info['open'] = float(d[1])
                info['high'] = float(d[4])
                info['low'] = float(d[5])
                info['yest'] = float(d[2])
                info['chg'] = round((info['price'] - info['yest']) / info['yest'] * 100, 2)
                info['vol_today'] = float(d[8]) / 100
                # 日内形态
                o2c = (info['price'] - info['open']) / info['open'] * 100
                if info['price'] > info['open'] and info['open'] > info['low'] * 1.02:
                    info['intraday'] = '探底回升'
                elif info['price'] < info['open'] and info['high'] > info['open'] * 1.02:
                    info['intraday'] = '冲高回落'
                elif abs(o2c) < 0.5:
                    info['intraday'] = '横盘震荡'
                else:
                    info['intraday'] = '单边上涨' if o2c > 0 else '单边下跌'
            except:
                pass

        # 历史技术面
        try:
            cursor.execute("SELECT tradedate, close, volume FROM daily_info_tbl WHERE code=%s ORDER BY tradedate DESC LIMIT 30", (h['code'],))
            rows = list(cursor.fetchall())
            if rows:
                rows.reverse()
                closes = [float(r[1]) for r in rows]
                volumes = [float(r[2]) for r in rows]
                ma5 = sum(closes[-5:]) / 5
                ma20 = sum(closes[-20:]) / 20 if len(closes) >= 20 else 0
                avg_vol = sum(volumes[-20:]) / 20 if len(volumes) >= 20 else 0
                info['ma5'] = round(ma5, 2)
                info['ma20'] = round(ma20, 2)
                info['above_ma20'] = info.get('price', 0) > ma20
                info['vol_ratio'] = round(info.get('vol_today', 0) / avg_vol, 2) if avg_vol > 0 else 0
        except:
            pass

        results.append(info)
    cursor.close()
    conn.close()
    return results


def match_index_pattern(index_data):
    """匹配历史相似大盘形态"""
    try:
        conn = pymysql.connect(**DB_CONFIG)
        cursor = conn.cursor()
        # 从sox_index_tbl获取最近交易日的SOX
        cursor.execute("SELECT chg_pct FROM sox_index_tbl ORDER BY tradedate DESC LIMIT 1")
        r = cursor.fetchone()
        sox_chg = round(float(r[0]), 2) if r and r[0] else 0
        cursor.close()
        conn.close()
        return sox_chg
    except:
        return 0


def _show_macro_events(today):
    """根据当前日期判断宏观事件状态，避免显示已过去的事件"""
    MACRO_CALENDAR = [
        # (日期, 标题, 结果/描述)
        ('2026-06-10', '美国5月CPI', '同比+4.2% 核心+2.9% 核心环比0.2%低于预期'),
        ('2026-06-10', '美国5月PPI', '同比+6.5% 核心+3.1%'),
        ('2026-06-12', 'SpaceX IPO', '定价$135 募资$750亿'),
    ]
    today_str = today.strftime('%Y-%m-%d')

    # 找最近已发生的
    recent = [(d, t, r) for d, t, r in MACRO_CALENDAR if d <= today_str]
    # 找未来待发生的
    upcoming = [(d, t, r) for d, t, r in MACRO_CALENDAR if d > today_str]

    if recent:
        for d, t, r in recent[-2:]:  # show last 2 recent events
            print(f"  📊 {t} ({d}): {r}")
    if upcoming:
        next_event = upcoming[0]
        print(f"  📅 下一个: {next_event[1]} ({next_event[0]})")


def update_daily_db():
    """盘后增量更新持仓A股日线 (新浪源, 快速).
    全市场更新需运行 Tushare 管道: python3 src/data/new_get_all_stock.py --no-hk
    """
    import urllib.request
    updated = 0
    conn = pymysql.connect(**DB_CONFIG)
    c = conn.cursor()
    today_str = datetime.date.today().strftime('%Y-%m-%d')

    holdings = _load_holdings_from_md()
    for h in holdings:
        full_code = h['code']
        try:
            mkt = 'sh' if full_code.endswith('.SH') else 'sz'
            code_num = full_code.replace('.SH', '').replace('.SZ', '')
            url = f'https://hq.sinajs.cn/list={mkt}{code_num}'
            req = urllib.request.Request(url, headers={'Referer': 'https://finance.sina.com.cn'})
            data = urllib.request.urlopen(req, timeout=5).read().decode('gbk')
            parts = data.split('"')[1].split(',')
            if len(parts) < 6:
                continue
            cur = float(parts[3]); op = float(parts[1]); prev = float(parts[2])
            hi = float(parts[4]); lo = float(parts[5]); vol = int(parts[8]) if len(parts) > 8 else 0

            # 检查今天是否已有数据
            c.execute('SELECT 1 FROM daily_info_tbl WHERE code=%s AND tradedate=%s', (full_code, today_str))
            if c.fetchone():
                continue

            c.execute('''
                INSERT INTO daily_info_tbl (code, tradedate, open, high, low, close, volume, adj_factor)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
            ''', (full_code, today_str, op, hi, lo, cur, vol, 1))
            updated += 1
        except Exception:
            pass

    conn.commit()
    c.close()
    conn.close()
    if updated > 0:
        print(f">>> A股持仓日线更新 {updated} 条")


def print_report(index_data, breadth, holdings, sox_chg):
    """格式化输出"""
    now = datetime.datetime.now()

    print(f"\n{'='*65}")
    print(f"  📊 盘后综合分析 — {now.strftime('%Y-%m-%d')} (星期{['一','二','三','四','五','六','日'][now.weekday()]})")
    print(f"{'='*65}")

    # ---- 大盘 ----
    print(f"\n{'─'*65}")
    print(f"  📈 大盘指数")
    print(f"{'─'*65}")

    vol_ratios = []
    for sym, data in index_data.items():
        if 'error' in data:
            print(f"  {data['name']}: 获取失败")
            continue
        arrow = '📈' if data['chg'] > 0 else '📉'
        amt_tag = '缩量' if data['amt_ratio'] < 0.95 else ('放量' if data['amt_ratio'] > 1.05 else '持平')
        vol_ratios.append(data['amt_ratio'])
        print(f"  {arrow} {data['name']:6s}  {data['close']:>8.0f}  {data['chg']:+.2f}%  "
              f"额{data['amount']:.0f}亿({amt_tag} {data['amt_ratio']:.2f}x vs昨)")

    avg_vr = sum(vol_ratios) / len(vol_ratios) if vol_ratios else 1

    # 市场广度
    if breadth:
        print(f"\n  📋 涨跌: {breadth['up']}↑ / {breadth['down']}↓  "
              f"比 {breadth['ratio']}:1  涨停{breadth['limit_up']}  跌停{breadth['limit_down']}")

    # ---- 量价结构 ----
    print(f"\n{'─'*65}")
    print(f"  🔍 量价结构判断")
    print(f"{'─'*65}")

    # 以上证为主判断量价结构
    main_vr = vol_ratios[0] if len(vol_ratios) > 0 else 1
    if main_vr < 0.95:
        if all(data.get('chg', 0) > 0 for data in index_data.values() if 'error' not in data):
            structure = '缩量反弹'
        else:
            structure = '缩量下跌'
    elif main_vr > 1.05:
        if all(data.get('chg', 0) > 0 for data in index_data.values() if 'error' not in data):
            structure = '放量上涨'
        else:
            structure = '放量下跌'
    else:
        structure = '量价持平'

    levels = {
        '放量上涨': '最强信号，趋势确认向上',
        '缩量反弹': '上涨但量不足，需要明天放量确认',
        '量价持平': '方向不明确，等待信号',
        '缩量下跌': '卖压减弱但买盘未进场',
        '放量下跌': '最弱信号，恐慌未结束',
    }
    print(f"  今日: {structure} — {levels.get(structure, '')}")

    if structure == '缩量反弹':
        print(f"\n  ⚡ 明日确认条件:")
        print(f"    ✅ 放量上涨 → 趋势向上确认，持仓")
        print(f"    ⚡ 缩量横盘 → 筑底中，继续观察")
        print(f"    ❌ 放量下跌 → 反弹失败，防御")

    if sox_chg:
        print(f"\n  🌍 隔夜SOX: {sox_chg:+.2f}%")
        _show_macro_events(now)

    # ---- 持仓 ----
    print(f"\n{'─'*65}")
    print(f"  💼 持仓表现 & 明日建议")
    print(f"{'─'*65}")
    print(f"  {'名称':<8s} {'涨跌':>7s} {'量比':>5s} {'MA20':>6s} {'形态':<8s}  明日操作")
    print(f"  {'─'*55}")

    for h in holdings:
        chg_str = f"{h.get('chg', 0):+.1f}%" if h.get('chg') is not None else '—'
        vol_str = f"{h.get('vol_ratio', 0):.1f}x" if h.get('vol_ratio') else '—'
        ma_str = '✅' if h.get('above_ma20') else ('⚠️' if h.get('above_ma20') is False else '—')
        intra = h.get('intraday', '—')

        # 明日建议
        advice = h.get('plan', '')

        # 加急信号: 高开放量/低开缩量
        if h.get('above_ma20') and h.get('vol_ratio', 0) > 1.5:
            advice += ' | 放量站回MA20→可持有'
        elif h.get('above_ma20') is False and h.get('chg', 0) < -3:
            advice += ' | 跌破MA20+持续走弱→注意止损'

        print(f"  {h['name']:<8s} {chg_str:>7s} {vol_str:>5s} {ma_str:>6s} {intra:<8s}  {advice}")

    # ---- 明日关键 ----
    print(f"\n{'─'*65}")
    print(f"  🎯 明日关注")
    print(f"{'─'*65}")
    # 找最弱/最强持仓
    valid = [h for h in holdings if h.get('chg') is not None]
    if valid:
        weakest = min(valid, key=lambda x: x.get('chg', 0))
        strongest = max(valid, key=lambda x: x.get('chg', 0))
        print(f"  2. 大盘是否放量确认 ({'上证>650亿' if avg_vr < 0.95 else '继续放量'})")
        print(f"  3. 持仓最弱: {weakest['name']} ({weakest.get('chg', 0):+.1f}%, {'跌破MA20' if weakest.get('above_ma20') is False else '关注'})")
        print(f"  4. 持仓最强: {strongest['name']} ({strongest.get('chg', 0):+.1f}%)")

    print(f"\n{'='*65}")
    print(f"  报告完毕: {now.strftime('%H:%M:%S')}")
    print(f"{'='*65}\n")

    return structure


def update_trading_plan(holdings, index_data, breadth, sox_chg, structure):
    """基于盘后分析结果自动更新 trading_plan.md"""
    now = datetime.datetime.now()
    today_str = now.strftime('%Y-%m-%d')
    today_short = f"{now.month}/{now.day}"

    project_root = os.path.dirname(_SRC_DIR)
    plan_path = os.path.join(project_root, 'trading_plan.md')

    if not os.path.exists(plan_path):
        print(">>> trading_plan.md 不存在，跳过更新")
        return

    with open(plan_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # 1. Update title date
    content = re.sub(r'# 交易计划 — \d{4}-\d{2}-\d{2}',
                     f'# 交易计划 — {today_str}', content)

    # Skip if today's status section already exists
    if f'## {today_short} 收盘状态' in content:
        print(f">>> {today_short} 收盘状态 已存在，跳过更新")
        return

    # 2. Build 收盘状态 table
    status_lines = [f'## {today_short} 收盘状态', '']
    status_lines.append('| 代码 | 名称 | 收盘 | 涨跌 | MA20 | 量比 | 日内形态 | 自动判断 |')
    status_lines.append('|------|------|------|------|------|------|---------|---------|')

    for h in holdings:
        code = h.get('code', '—')
        name = h.get('name', '—')
        price = h.get('price')
        price_str = f"{price:.2f}" if isinstance(price, (int, float)) else '—'
        chg_val = h.get('chg')
        chg = f"{chg_val:+.1f}%" if chg_val is not None else '—'

        above = h.get('above_ma20')
        if above is True:
            ma20 = '✅站'
        elif above is False:
            ma20 = '⚠️破'
        else:
            ma20 = '—'

        vr = h.get('vol_ratio')
        vol_str = f"{vr:.1f}x" if vr is not None and vr > 0 else '—'
        intra = h.get('intraday', '—')

        # Auto judgment
        chg_num = chg_val if chg_val is not None else 0
        if above is True and chg_num > 0:
            judgment = '持有'
        elif above is False and chg_num < -3:
            judgment = '关注止损'
        elif above is False:
            judgment = '观察'
        elif chg_num < -3:
            judgment = '关注止损'
        else:
            judgment = '持有'

        status_lines.append(
            f'| {code} | {name} | {price_str} | {chg} | {ma20} | {vol_str} | {intra} | {judgment} |')

    status_section = '\n'.join(status_lines)

    # 3. Build 操作执行记录 template
    record_lines = [f'## {today_short} 操作执行记录', '']
    record_lines.append('| 标的 | 计划 | 实际 | 结果 |')
    record_lines.append('|------|------|------|------|')

    for h in holdings:
        name = h.get('name', '—')
        plan = h.get('plan', '—')
        record_lines.append(f'| {name} | {plan} | 待填写 | 待填写 |')

    record_section = '\n'.join(record_lines)

    # 4. Insert both sections after 当前持仓 table (before next ## section)
    match = re.search(r'(## 当前持仓.*?\n\n)(## )', content, re.DOTALL)
    if match:
        insert_at = match.start(2)
        combined = status_section + '\n\n' + record_section + '\n\n'
        content = content[:insert_at] + combined + content[insert_at:]
    else:
        print(">>> 无法定位「当前持仓」章节结尾，跳过更新")
        return

    # 5. Prepend analysis record to 盘前分析记录
    up_count = sum(1 for h in holdings if (h.get('chg') or 0) > 0)
    down_count = sum(1 for h in holdings if (h.get('chg') or 0) < 0)
    sox_str = f"SOX {sox_chg:+.1f}%" if sox_chg else ''
    summary = f"- {today_str}收盘: {structure} | {sox_str} | 持仓{up_count}涨{down_count}跌"

    pan_start = content.find('## 盘前分析记录')
    if pan_start != -1:
        after_heading = content[pan_start:]
        first_dash = re.search(r'\n(- 20\d\d)', after_heading)
        if first_dash:
            dash_pos = pan_start + first_dash.start(1)
            content = content[:dash_pos] + summary + '\n' + content[dash_pos:]

    # 6. Write back
    with open(plan_path, 'w', encoding='utf-8') as f:
        f.write(content)

    print(f">>> trading_plan.md 已更新 ({today_str})")


def main():
    print(">>> 更新个股日线数据...")
    update_daily_db()

    print(">>> 获取大盘数据...")
    index_data = get_index_data()

    print(">>> 获取市场广度...")
    breadth = get_market_breadth()

    print(">>> 获取持仓数据...")
    holdings = get_holding_data()

    print(">>> 获取SOX催化...")
    sox_chg = match_index_pattern(index_data)

    structure = print_report(index_data, breadth, holdings, sox_chg)

    print(">>> 更新 trading_plan.md ...")
    update_trading_plan(holdings, index_data, breadth, sox_chg, structure)


if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        print(f"❌ 分析出错: {e}")
        import traceback
        traceback.print_exc()
