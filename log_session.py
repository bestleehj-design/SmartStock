# -*- coding: utf-8 -*-
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

NAME_MAP = {
    '600584': '长电科技', '688981': '中芯国际', '603986': '兆易创新',
    '002463': '沪电股份', '002138': '顺络电子', '002384': '东山精密',
    '301591': '肯特股份', '603296': '华勤技术', '688008': '澜起科技',
    '00981': '中芯国际(HK)', '06809': '澜起科技(HK)',
    '600522': '中天科技', '600703': '三安光电', '002273': '水晶光电',
    '300162': '雷曼光电', '300296': '利亚德', '002456': '欧菲光',
}

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
