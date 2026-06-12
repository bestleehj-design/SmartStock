#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
模拟交易回溯 — 检查推荐的买点/卖点是否触发, 计算盈亏

用法:
  python3 sim_backtest.py                   # 回溯所有模拟交易
  python3 sim_backtest.py --report          # 输出统计报告
  python3 sim_backtest.py --add             # 手动交互添加推荐

数据流:
  sim_trades (waiting) → 检查 daily_info_tbl 是否触及买点 → entered
  sim_trades (entered) → 检查 daily_info_tbl 是否触及目标/止损 → exited
"""

import sys, os
_SRC_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _SRC_DIR not in sys.path:
    sys.path.insert(0, _SRC_DIR)

import pymysql
from datetime import date, timedelta

DB_CONFIG = {
    'host': 'localhost', 'port': 3306,
    'user': 'root', 'password': '12345678',
    'database': 'gp2', 'charset': 'utf8mb4',
}


def backfill():
    """检查所有未完成的模拟交易, 自动标记触发"""
    conn = pymysql.connect(**DB_CONFIG)
    cur = conn.cursor()

    # ---- 1. 检查 waiting → entered ----
    cur.execute("SELECT id, code, buy_price, rec_date FROM sim_trades WHERE status='waiting'")
    waiting = cur.fetchall()
    triggered = 0

    for tid, code, buy_price, rec_date in waiting:
        if buy_price is None or buy_price <= 0:
            continue
        cur.execute('''
            SELECT tradedate, close FROM daily_info_tbl
            WHERE code=%s AND tradedate > %s AND low <= %s
            ORDER BY tradedate LIMIT 1
        ''', (code, rec_date, float(buy_price)))
        row = cur.fetchone()
        if row:
            cur.execute('''
                UPDATE sim_trades SET status='entered', entry_date=%s, entry_price=%s
                WHERE id=%s
            ''', (row[0], float(row[1]), tid))
            triggered += 1

    # ---- 2. 检查 entered → exited ----
    cur.execute("SELECT id, code, target_price, stop_loss, entry_date FROM sim_trades WHERE status='entered'")
    entered = cur.fetchall()
    closed = 0

    for tid, code, target, stop, entry_date in entered:
        # 查止盈
        if target and target > 0:
            cur.execute('''
                SELECT tradedate, close FROM daily_info_tbl
                WHERE code=%s AND tradedate > %s AND high >= %s
                ORDER BY tradedate LIMIT 1
            ''', (code, entry_date, float(target)))
            row = cur.fetchone()
            if row:
                cur.execute("UPDATE sim_trades SET status='exited', exit_date=%s, exit_price=%s, exit_reason='止盈' WHERE id=%s",
                           (row[0], float(row[1]), tid))
                closed += 1
                continue

        # 查止损
        if stop and stop > 0:
            cur.execute('''
                SELECT tradedate, close FROM daily_info_tbl
                WHERE code=%s AND tradedate > %s AND low <= %s
                ORDER BY tradedate LIMIT 1
            ''', (code, entry_date, float(stop)))
            row = cur.fetchone()
            if row:
                cur.execute("UPDATE sim_trades SET status='exited', exit_date=%s, exit_price=%s, exit_reason='止损' WHERE id=%s",
                           (row[0], float(row[1]), tid))
                closed += 1
                continue

    # ---- 3. 计算盈亏 ----
    cur.execute("SELECT id, entry_price, exit_price FROM sim_trades WHERE status='exited' AND exit_price IS NOT NULL AND entry_price IS NOT NULL AND pnl_pct IS NULL")
    for tid, entry, exit_p in cur.fetchall():
        entry = float(entry)
        exit_p = float(exit_p)
        if entry > 0:
            pnl = (exit_p - entry) / entry * 100
            cur.execute("UPDATE sim_trades SET pnl_pct=%s WHERE id=%s", (round(pnl, 4), tid))

    # ---- 4. 过期处理 (>20 交易日未触发) ----
    cur.execute("SELECT id, rec_date FROM sim_trades WHERE status='waiting' AND rec_date < %s",
               (date.today() - timedelta(days=30),))
    for tid, _ in cur.fetchall():
        cur.execute("UPDATE sim_trades SET status='expired' WHERE id=%s", (tid,))

    conn.commit()

    if triggered or closed:
        print(f'📊 回溯完成: 新入场 {triggered} 笔, 新离场 {closed} 笔')
    else:
        print(f'📊 回溯完成: 无新触发 (waiting={len(waiting)}, entered={len(entered)})')

    cur.close()
    conn.close()


def report():
    """输出模拟交易统计报告"""
    conn = pymysql.connect(**DB_CONFIG)
    cur = conn.cursor()

    # 按状态统计
    cur.execute("SELECT status, COUNT(*), ROUND(AVG(pnl_pct),2) FROM sim_trades GROUP BY status")
    print('\n=== 状态概览 ===')
    for s, c, avg in cur.fetchall():
        pnl_str = f' 均盈{avg:+.1f}%' if avg else ''
        print(f'  {s:10s}  {c}笔{pnl_str}')

    # 盈亏明细
    cur.execute("SELECT rec_date, code, name, buy_price, target_price, exit_price, pnl_pct, exit_reason, reason FROM sim_trades WHERE status='exited' ORDER BY rec_date DESC LIMIT 20")
    closed = cur.fetchall()
    if closed:
        print(f'\n=== 已平仓 (最近20笔) ===')
        for r in closed:
            pnl = f'{r[6]:+.1f}%' if r[6] else 'N/A'
            print(f'  {r[0]} {r[1]:<10s} {r[2]:<10s}  买{r[3]} 卖{r[5]} {r[7]} {pnl}')

    # 等待中的
    cur.execute("SELECT rec_date, code, name, buy_price, target_price, stop_loss, reason FROM sim_trades WHERE status='waiting' ORDER BY rec_date DESC")
    waiting = cur.fetchall()
    if waiting:
        print(f'\n=== 等待触发 ({len(waiting)}笔) ===')
        for r in waiting:
            print(f'  {r[0]} {r[1]:<12s} {r[2]:<10s}  买{r[3]:.2f}  目标{r[4]:.2f}  止损{r[5]:.2f}')

    # 持仓中
    cur.execute("SELECT id, rec_date, code, name, entry_price, target_price, stop_loss FROM sim_trades WHERE status='entered'")
    holding = cur.fetchall()
    if holding:
        print(f'\n=== 持仓中 ({len(holding)}笔) ===')
        for r in holding:
            # Get current price
            cur.execute("SELECT close FROM daily_info_tbl WHERE code=%s ORDER BY tradedate DESC LIMIT 1", (r[2],))
            px = cur.fetchone()
            cur_px = f'{float(px[0]):.2f}' if px else 'N/A'
            print(f'  {r[0]:>3d} {r[1]} {r[2]:<12s} {r[3]:<10s}  入场{r[4]:.2f}  现{cur_px}  目标{r[5]}')

    # 总胜率
    cur.execute("SELECT COUNT(*), ROUND(AVG(pnl_pct),2), SUM(CASE WHEN pnl_pct>0 THEN 1 ELSE 0 END) FROM sim_trades WHERE status='exited' AND pnl_pct IS NOT NULL")
    total, avg_pnl, wins = cur.fetchone()
    if total:
        print(f'\n=== 总统计 ===')
        print(f'  总平仓: {total}笔  胜率: {wins}/{total} ({wins/total*100:.0f}%)  均盈: {avg_pnl:+.1f}%')

    conn.close()


def add_interactive():
    """交互添加推荐"""
    code = input('代码 (如 600160.SH): ').strip()
    name = input('名称: ').strip()
    sector = input('板块: ').strip()
    score = int(input('选股器得分: ') or 0)
    buy = float(input('建议买入价: ') or 0)
    target = float(input('目标卖价: ') or 0)
    stop = float(input('止损价: ') or 0)
    reason = input('理由: ').strip()

    conn = pymysql.connect(**DB_CONFIG)
    cur = conn.cursor()
    cur.execute('''
        INSERT INTO sim_trades (rec_date, code, name, sector, score, buy_price, target_price, stop_loss, reason, status)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,'waiting')
    ''', (date.today(), code, name, sector, score, buy, target, stop, reason))
    conn.commit()
    print(f'✅ {name} 已添加')
    conn.close()


if __name__ == '__main__':
    if '--report' in sys.argv:
        report()
    elif '--add' in sys.argv:
        add_interactive()
    else:
        backfill()
        report()
