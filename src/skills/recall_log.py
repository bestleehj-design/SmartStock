# -*- coding: utf-8 -*-

# Ensure src/ directory is in sys.path for package imports
import sys, os
_SRC_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _SRC_DIR not in sys.path:
    sys.path.insert(0, _SRC_DIR)
"""回调昨日判断，用于新会话开场"""
import datetime
import pymysql

DB_CONFIG = {
    'host': 'localhost', 'port': 3306,
    'user': 'root', 'password': '12345678',
    'database': 'gp2', 'charset': 'utf8mb4',
}

def recall(date_str=None, days=1):
    conn = pymysql.connect(**DB_CONFIG)
    c = conn.cursor()

    if date_str:
        target_date = date_str
    else:
        target_date = (datetime.date.today() - datetime.timedelta(days=days)).strftime('%Y-%m-%d')

    c.execute('''
        SELECT analysis_date, code, name, action, confidence, thesis, risks, stop_loss, target_price
        FROM claude_trades
        WHERE analysis_date = %s
        ORDER BY FIELD(action,'buy','hold','sell','wait'), code
    ''', (target_date,))
    rows = c.fetchall()

    if not rows:
        print(f"📭 {target_date} 无历史判断记录")
        c.close()
        conn.close()
        return

    print(f"\n{'='*60}")
    print(f"  📋 {target_date} 历史判断")
    print(f"{'='*60}\n")

    by_action = {}
    for r in rows:
        act = r[3]
        by_action.setdefault(act, []).append(r)

    for act in ['sell', 'hold', 'wait', 'buy']:
        if act in by_action:
            emoji = {'sell': '🔴', 'hold': '🟢', 'wait': '🟡', 'buy': '📈'}
            print(f"  【{emoji.get(act,'')} {act}】")
            for r in by_action[act]:
                print(f"    {r[2]:8s} ({r[1]:10s})  {r[4]:6s}")
                if r[5]:
                    print(f"      逻辑: {r[5][:80]}")
                if r[6]:
                    print(f"      风险: {r[6][:80]}")
                if r[7]:
                    print(f"      止损: {r[7]}")
                if r[8]:
                    print(f"      目标: {r[8]}")
            print()

    c.close()
    conn.close()

if __name__ == '__main__':
    import sys
    date_arg = sys.argv[1] if len(sys.argv) > 1 else None
    recall(date_arg)
