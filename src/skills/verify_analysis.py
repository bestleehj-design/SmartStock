# -*- coding: utf-8 -*-

# Ensure src/ directory is in sys.path for package imports
import sys, os
_SRC_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _SRC_DIR not in sys.path:
    sys.path.insert(0, _SRC_DIR)
"""
验证 Claude Code 的历史分析准确率
用法:
  python3 verify_analysis.py                # 验证所有
  python3 verify_analysis.py --date 2026-06-08
  python3 verify_analysis.py --report       # 输出报告
"""
import argparse
import datetime
import pymysql
import json

DB_CONFIG = {
    'host': 'localhost', 'port': 3306,
    'user': 'root', 'password': '12345678',
    'database': 'gp2', 'charset': 'utf8mb4',
}


def backfill_returns():
    """回填未来收益到 claude_trades"""
    conn = pymysql.connect(**DB_CONFIG)
    c = conn.cursor()

    c.execute("SELECT id, analysis_date, code, current_price FROM claude_trades WHERE ret_5d IS NULL")
    rows = c.fetchall()

    updated = 0
    for row_id, analysis_date, code, price in rows:
        suffix = '.SH' if code.startswith('6') else '.SZ'
        full_code = code + suffix
        if float(price) == 0:
            continue

        for days, col in [('ret_1d', 1), ('ret_3d', 3), ('ret_5d', 5),
                           ('ret_10d', 10), ('ret_20d', 20)]:
            try:
                c.execute('''
                    SELECT close FROM daily_info_tbl
                    WHERE code=%s AND tradedate > %s
                    ORDER BY tradedate ASC LIMIT 1 OFFSET %s
                ''', (full_code, analysis_date, days - 1))
                row = c.fetchone()
                if row:
                    ret = round((float(row[0]) / float(price) - 1), 4)
                    c.execute(f'UPDATE claude_trades SET {col}=%s WHERE id=%s', (ret, row_id))

                    # 检查目标和止损
                    if col == 'ret_5d':
                        c.execute('''
                            SELECT stop_loss, target_price FROM claude_trades WHERE id=%s
                        ''', (row_id,))
                        trow = c.fetchone()
                        if trow:
                            stop = float(trow[0] or 0)
                            target = float(trow[1] or 0)
                            future_price = float(row[0])
                            hit_stop = 1 if stop > 0 and future_price < stop else 0
                            hit_target = 1 if target > 0 and future_price > target else 0
                            c.execute('UPDATE claude_trades SET hit_stop=%s, hit_target=%s WHERE id=%s',
                                      (hit_stop, hit_target, row_id))

                    updated += 1
            except Exception:
                pass

        # 算最大收益
        try:
            c.execute('''
                SELECT MAX(high) FROM daily_info_tbl
                WHERE code=%s AND tradedate > %s
                ORDER BY tradedate ASC LIMIT 20
            ''', (full_code, analysis_date))
            row = c.fetchone()
            if row and row[0]:
                max_ret = round((float(row[0]) / float(price) - 1), 4)
                c.execute('UPDATE claude_trades SET max_ret=%s WHERE id=%s', (max_ret, row_id))
                updated += 1
        except Exception:
            pass

    conn.commit()
    c.close()
    conn.close()
    print(f"✅ 回填完成，更新 {updated} 条")


def score_accuracy(action, ret_5d, hit_target, hit_stop):
    """计算准确度评分 0-100"""
    if ret_5d is None:
        return None

    if action == 'buy' or action == 'hold':
        if hit_target:
            return 100
        elif ret_5d > 0.03:
            return 75
        elif ret_5d > 0:
            return 50
        elif hit_stop:
            return 0
        elif ret_5d > -0.05:
            return 25
        else:
            return 0
    elif action == 'sell':
        if ret_5d < -0.03:
            return 100
        elif ret_5d < 0:
            return 60
        else:
            return 0
    elif action == 'wait':
        if ret_5d < 0:
            return 100
        elif ret_5d < 0.02:
            return 50
        else:
            return 0
    return None


def generate_report():
    """生成验证报告"""
    conn = pymysql.connect(**DB_CONFIG)
    c = conn.cursor()

    print(f"\n{'='*70}")
    print(f"  📊 Claude 分析准确率验证报告")
    print(f"  {datetime.date.today()}")
    print(f"{'='*70}")

    # 按 action 统计
    c.execute("""
        SELECT action, COUNT(*) as cnt,
            ROUND(AVG(ret_5d)*100,2) as avg_5d,
            ROUND(AVG(max_ret)*100,2) as avg_max
        FROM claude_trades WHERE ret_5d IS NOT NULL
        GROUP BY action
    """)
    print(f"\n  📈 按操作类型:")
    for r in c.fetchall():
        print(f"    {r[0]:6s}: {r[1]}条  5日均收益={r[2]:+.2f}%  最大收益={r[3]:+.2f}%")

    # 按信心统计
    c.execute("""
        SELECT confidence, COUNT(*) as cnt,
            ROUND(AVG(ret_5d)*100,2) as avg_5d,
            ROUND(AVG(CASE WHEN hit_target=1 OR (action='buy' AND ret_5d>0) THEN 1 ELSE 0 END)*100,1) as win_rate
        FROM claude_trades WHERE ret_5d IS NOT NULL
        GROUP BY confidence
    """)
    print(f"\n  🎯 按信心等级:")
    for r in c.fetchall():
        print(f"    {r[0]:7s}: {r[1]}条  avg5d={r[2]:+.2f}%  胜率={r[3]:.0f}%")

    # 最佳/最差
    print(f"\n  ✅ 最佳判断 (5日收益):")
    c.execute("SELECT code, name, action, ret_5d, thesis FROM claude_trades WHERE ret_5d IS NOT NULL ORDER BY ret_5d DESC LIMIT 5")
    for r in c.fetchall():
        print(f"    {r[0]} {r[1]:8s} {r[2]:5s}  ret5d={(r[3] or 0)*100:+.2f}%  {r[4][:50] if r[4] else ''}")

    print(f"\n  ❌ 最差判断:")
    c.execute("SELECT code, name, action, ret_5d, thesis FROM claude_trades WHERE ret_5d IS NOT NULL ORDER BY ret_5d ASC LIMIT 5")
    for r in c.fetchall():
        print(f"    {r[0]} {r[1]:8s} {r[2]:5s}  ret5d={(r[3] or 0)*100:+.2f}%  {r[4][:50] if r[4] else ''}")

    # 最近记录
    print(f"\n  📋 最近 10 条:")
    c.execute("SELECT analysis_date, code, name, action, ret_5d, thesis FROM claude_trades ORDER BY analysis_date DESC LIMIT 10")
    for r in c.fetchall():
        ret_str = f"ret5d={(r[4] or 0)*100:+.2f}%" if r[4] is not None else "待验证"
        print(f"    {r[0]} {r[1]} {r[2]:8s} {r[3]:5s}  {ret_str}  {r[5][:40] if r[5] else ''}")

    print(f"\n{'='*70}\n")
    conn.close()


def main():
    parser = argparse.ArgumentParser(description='验证 Claude 分析准确率')
    parser.add_argument('--date', help='指定日期')
    parser.add_argument('--report', action='store_true', help='生成报告')
    parser.add_argument('--backfill', action='store_true', help='回填收益')
    args = parser.parse_args()

    if args.backfill:
        backfill_returns()
    elif args.report:
        generate_report()
    else:
        backfill_returns()
        generate_report()


if __name__ == '__main__':
    main()
