# -*- coding: utf-8 -*-
"""
盘后综合分析 — 结合大盘、持仓、量价做明日预判
用法: python3 close_analysis.py
"""
import sys, os, datetime, requests, pymysql, subprocess

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
os.chdir(SCRIPT_DIR)
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

DB_CONFIG = {
    'host': 'localhost', 'port': 3306,
    'user': 'root', 'password': '12345678',
    'database': 'gp2', 'charset': 'utf8mb4',
}

SINA_HEADERS = {'Referer': 'https://finance.sina.com.cn'}

# 持仓列表
HOLDINGS = [
    {'code': '600584.SH', 'name': '长电科技', 'plan': '已减30%，留350股等Q3'},
    {'code': '002463.SZ', 'name': '沪电股份', 'plan': '不动'},
    {'code': '002138.SZ', 'name': '顺络电子', 'plan': '不动，止盈56.70'},
    {'code': '603986.SH', 'name': '兆易创新', 'plan': '不动，破MA20(451)减半'},
    {'code': '002384.SZ', 'name': '东山精密', 'plan': '站回MA20就留'},
    {'code': '301591.SZ', 'name': '肯特股份', 'plan': '不动不补'},
    {'code': '688981.SH', 'name': '中芯国际A', 'plan': '趁反弹清仓'},
]

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
    """获取持仓今日表现"""
    conn = pymysql.connect(**DB_CONFIG)
    cursor = conn.cursor()

    # 从新浪实时获取今天数据
    sina_map = {
        '600584': 'sh600584', '688981': 'sh688981', '603986': 'sh603986',
        '002463': 'sz002463', '002138': 'sz002138', '002384': 'sz002384',
        '301591': 'sz301591',
    }

    results = []
    for h in HOLDINGS:
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


def update_daily_db():
    """盘后更新个股日线数据到本地库（daily_info_tbl 等）"""
    try:
        # 先尝试直接运行（不需要 sudo）
        cmd = ['python3', 'new_get_all_stock.py', '--no-hk']
        result = subprocess.run(cmd, cwd=SCRIPT_DIR,
                                capture_output=True, text=True, timeout=600)
        if result.returncode != 0:
            # 直接运行失败，尝试 sudo（需用户在终端输入密码）
            print(">>> 需要 sudo 权限，尝试 sudo 运行...")
            result = subprocess.run(['sudo', '-S', 'python3', 'new_get_all_stock.py', '--no-hk'],
                                    cwd=SCRIPT_DIR, timeout=600)
        if result.returncode == 0:
            print(">>> 个股日线数据更新完成")
        else:
            print(f">>> 数据更新退出码: {result.returncode}")
            if hasattr(result, 'stderr') and result.stderr:
                print(f"    {result.stderr.strip()[-300:]}")
    except subprocess.TimeoutExpired:
        print(">>> 数据更新超时(10分钟)，继续分析...")
    except Exception as e:
        print(f">>> 数据更新失败: {e}，继续分析...")


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
        print(f"  📅 今晚: CPI 数据发布")

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
    print(f"  1. CPI 数据 (今晚)")
    print(f"  2. 大盘是否放量确认 ({'上证>650亿' if avg_vr < 0.95 else '继续放量'})")
    print(f"  3. 持仓最弱品种: 兆易创新 (关注是否破MA20)")
    print(f"  4. 持仓最强品种: 顺络电子 (关注涨停后持续力度)")
    print(f"  5. 待执行: 中芯国际A股清仓")

    print(f"\n{'='*65}")
    print(f"  报告完毕: {now.strftime('%H:%M:%S')}")
    print(f"{'='*65}\n")


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

    print_report(index_data, breadth, holdings, sox_chg)


if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        print(f"❌ 分析出错: {e}")
        import traceback
        traceback.print_exc()
