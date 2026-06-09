# -*- coding: utf-8 -*-

# Ensure src/ directory is in sys.path for package imports
import sys, os
_SRC_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _SRC_DIR not in sys.path:
    sys.path.insert(0, _SRC_DIR)
"""
记录 Claude Code 每次分析结论到数据库
用法:
  python3 log_analysis.py --code 600584 --action hold --stop 69.5 --thesis "W底+7月业绩"
"""
import argparse
import datetime
import pymysql

DB_CONFIG = {
    'host': 'localhost', 'port': 3306,
    'user': 'root', 'password': '12345678',
    'database': 'gp2', 'charset': 'utf8mb4',
}


def log_trade(args):
    conn = pymysql.connect(**DB_CONFIG)
    c = conn.cursor()

    # 自动补全名称
    name = args.name
    if not name:
        suffix = '.SH' if args.code.startswith('6') else '.SZ'
        try:
            c.execute("SELECT name FROM stock_basic_info_tbl WHERE code=%s", (args.code + suffix,))
            row = c.fetchone()
            if row:
                name = row[0]
        except Exception:
            name = args.code

    analysis_date = args.date or datetime.date.today().strftime('%Y-%m-%d')

    c.execute('''
        INSERT INTO claude_trades
        (analysis_date, code, name, source, action,
         entry_price, stop_loss, target_price,
         confidence, thesis, risks, current_price)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
    ''', (
        analysis_date,
        args.code, name, args.source, args.action,
        args.entry, args.stop, args.target,
        args.confidence, args.thesis, args.risk, args.price,
    ))
    conn.commit()
    c.close()
    conn.close()
    print(f"✅ 已记录: {name}({args.code})  {args.action}  {args.confidence}")


def main():
    parser = argparse.ArgumentParser(description='记录 Claude 分析结论')
    parser.add_argument('--code', required=True, help='股票代码')
    parser.add_argument('--name', help='股票名称（可选，自动查询）')
    parser.add_argument('--action', required=True,
                        choices=['buy', 'hold', 'sell', 'wait'],
                        help='操作: buy=买入, hold=持有, sell=卖出, wait=等待')
    parser.add_argument('--entry', type=float, help='建议买入价')
    parser.add_argument('--stop', type=float, help='止损价')
    parser.add_argument('--target', type=float, help='目标价')
    parser.add_argument('--thesis', default='', help='核心逻辑')
    parser.add_argument('--risk', default='', help='风险点')
    parser.add_argument('--confidence', default='medium',
                        choices=['high', 'medium', 'low'], help='信心等级')
    parser.add_argument('--source', default='manual',
                        choices=['smart_screener', 'manual', 'morning_report'],
                        help='分析来源')
    parser.add_argument('--price', type=float, default=0, help='分析时现价')
    parser.add_argument('--date', help='分析日期(默认今天)')
    args = parser.parse_args()
    log_trade(args)


if __name__ == '__main__':
    main()
