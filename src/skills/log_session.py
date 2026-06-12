# -*- coding: utf-8 -*-

# Ensure src/ directory is in sys.path for package imports
import sys, os
_SRC_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _SRC_DIR not in sys.path:
    sys.path.insert(0, _SRC_DIR)
"""
批量记录当日所有判断到 claude_trades 表
用法: python3 log_session.py --file <judgments.txt>
     或标准输入:  echo "600584|sell|73|71|...|中" | python3 log_session.py
"""
import sys
import datetime
import pymysql

DB_CONFIG = {
    'host': 'localhost', 'port': 3306,
    'user': 'root', 'password': '12345678',
    'database': 'gp2', 'charset': 'utf8mb4',
}

# 从 trading_plan.md 加载代码名称映射 (含已清仓, 含港股)
def _load_name_map():
    import re
    skill_dir = os.path.dirname(os.path.abspath(__file__))
    plan_path = os.path.join(os.path.dirname(os.path.dirname(skill_dir)), 'trading_plan.md')
    if not os.path.exists(plan_path):
        return {}
    with open(plan_path, 'r', encoding='utf-8') as f:
        content = f.read()

    m = re.search(r'## 当前持仓\s*\n\s*\n(.*?)(?=\n## |\n---|\Z)', content, re.DOTALL)
    if not m:
        return {}

    name_map = {}
    for line in m.group(1).strip().split('\n'):
        if not line.strip().startswith('|') or '---' in line or '代码' in line:
            continue
        cols = [c.strip() for c in line.strip().split('|')[1:-1]]
        if len(cols) < 2:
            continue
        raw_code = cols[0]
        name = cols[1]
        # 去掉 .SH / .SZ / .HK 后缀，统一为 6 位数字代码
        code = raw_code.replace('.SH', '').replace('.SZ', '').replace('.HK', '')
        name_map[code] = name
    return name_map


NAME_MAP = _load_name_map()

# 不在持仓表里的关注票 (手动补充)
_NAME_MAP_EXTRA = {
    '603296': '华勤技术',
    '688008': '澜起科技',
}
NAME_MAP.update(_NAME_MAP_EXTRA)

def log_one(code, action, thesis, stop, target, confidence, source, risk):
    conn = pymysql.connect(**DB_CONFIG)
    c = conn.cursor()
    name = NAME_MAP.get(code, code)

    # 获取今日现价
    price = 0
    suffix = '.SH' if (code.startswith('6') or code.startswith('9')) else '.SZ'
    if code.startswith('0') and len(code) == 5:
        suffix = ''  # HK stock
    try:
        db_code = code + suffix
        c.execute("SELECT close FROM daily_info_tbl WHERE code=%s ORDER BY tradedate DESC LIMIT 1", (db_code,))
        row = c.fetchone()
        if row:
            price = float(row[0])
    except:
        pass

    today = datetime.date.today().strftime('%Y-%m-%d')
    c.execute('''
        INSERT INTO claude_trades
        (analysis_date, code, name, source, action,
         entry_price, stop_loss, target_price,
         confidence, thesis, risks, current_price)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
    ''', (today, code, name, source, action, 0, stop, target, confidence, thesis, risk, price))

    conn.commit()
    c.close()
    conn.close()
    return name

def log_batch(lines):
    """批量记录，每行格式: code|action|thesis|stop|target|confidence|risk"""
    for line in lines:
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        parts = line.split('|')
        if len(parts) < 6:
            print(f"  ⚠️ 跳过格式错误行: {line}")
            continue
        code = parts[0].strip()
        action = parts[1].strip()
        thesis = parts[2].strip() if len(parts) > 2 else ''
        stop = float(parts[3]) if len(parts) > 3 and parts[3] else 0
        target = float(parts[4]) if len(parts) > 4 and parts[4] else 0
        confidence = parts[5].strip() if len(parts) > 5 else 'medium'
        risk = parts[6].strip() if len(parts) > 6 else ''
        source = 'manual'
        name = log_one(code, action, thesis, stop, target, confidence, source, risk)
        print(f"  ✅ {name}({code}) {action:6s} {confidence:6s} | {thesis[:40]}")


if __name__ == '__main__':
    lines = []
    if len(sys.argv) > 1 and sys.argv[1] == '--file':
        with open(sys.argv[2]) as f:
            lines = f.readlines()
    else:
        lines = sys.stdin.read().strip().split('\n')
        if not lines or lines == ['']:
            print("用法: python3 log_session.py < 记录文件")
            print("     或: echo 'code|action|thesis|...' | python3 log_session.py")
            sys.exit(1)

    print(f"记录 {len([l for l in lines if l.strip() and not l.startswith('#')])} 条判断...")
    log_batch(lines)
    print("完成。")
