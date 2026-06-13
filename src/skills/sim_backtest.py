#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
模拟交易回溯 — 检查推荐的买点/卖点是否触发, 计算盈亏

用法:
  python3 sim_backtest.py                   # 回溯所有模拟交易
  python3 sim_backtest.py --report          # 输出统计报告
  python3 sim_backtest.py --add             # 手动交互添加推荐
  python3 sim_backtest.py --reevaluate      # 重新评估 waiting 中的买卖点

数据流:
  sim_trades (waiting) → reevaluate_waiting() 重新评估买卖点
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


def reevaluate_waiting():
    """重新评估 waiting 状态中未触及买点的股票

    根据最新行情判断:
      - 趋势破坏 → 标记为 expired (废除推荐)
      - 趋势仍在但价格变化 → 更新 buy_price / target_price / stop_loss
      - 趋势不变 → 保持原样
    """
    conn = pymysql.connect(**DB_CONFIG)
    cur = conn.cursor()

    today = date.today()

    # 取所有 waiting 记录，推荐日已过至少 1 天
    cur.execute("""
        SELECT id, code, name, buy_price, target_price, stop_loss, rec_date, score
        FROM sim_trades
        WHERE status='waiting' AND rec_date < %s
    """, (today,))
    waiting = cur.fetchall()

    if not waiting:
        cur.close()
        conn.close()
        return 0, 0

    updated = 0
    expired = 0

    for tid, code, name, buy_price, target_price, stop_loss, rec_date, old_score in waiting:
        # 拉取最近 60 个交易日数据
        cur.execute("""
            SELECT tradedate, open, high, low, close, volume
            FROM daily_info_tbl
            WHERE code=%s AND tradedate <= %s
            ORDER BY tradedate DESC LIMIT 60
        """, (code, today))
        rows = cur.fetchall()

        if len(rows) < 20:
            continue  # 数据不足，跳过

        # 转为升序（日期从旧到新）
        rows = list(reversed(rows))
        closes = [float(r[4]) for r in rows]
        highs = [float(r[2]) for r in rows]
        lows = [float(r[3]) for r in rows]
        volumes = [float(r[5]) for r in rows]
        current = closes[-1]

        # === 计算技术指标 ===
        n_days = len(closes)
        ma5 = sum(closes[-5:]) / 5 if n_days >= 5 else closes[-1]
        ma10 = sum(closes[-10:]) / 10 if n_days >= 10 else closes[-1]
        ma20_val = sum(closes[-20:]) / 20 if n_days >= 20 else closes[-1]

        vol_5 = sum(volumes[-5:]) / 5
        vol_20 = sum(volumes[-20:]) / 20

        decay_reason = ''

        # ----- 1. MA 趋势破坏 -----
        if ma5 < ma20_val and ma10 < ma20_val and n_days >= 20:
            decay_reason = 'MA5/MA10 双双跌破 MA20，短期趋势破坏'

        # ----- 2. 收盘价远离 MA20 支撑 -----
        if not decay_reason and ma20_val > 0 and current < ma20_val * 0.94:
            dist_pct = round((current / ma20_val - 1) * 100, 1)
            decay_reason = f'收盘价低于 MA20 {abs(dist_pct)}%，支撑失效'

        # ----- 3. 连续下跌 -----
        if not decay_reason and n_days >= 4:
            if closes[-1] < closes[-2] < closes[-3] < closes[-4]:
                decay_reason = '连跌 3 天，趋势转弱'

        # ----- 4. 近期暴跌 -----
        if not decay_reason and n_days >= 6:
            chg_5d = (closes[-1] / closes[-6] - 1) * 100
            if chg_5d < -12:
                decay_reason = f'近 5 日暴跌 {chg_5d:.1f}%'

        # ----- 5. 量能极度萎缩（资金撤退）-----
        if not decay_reason and vol_5 > 0 and vol_20 > 0 and vol_5 < vol_20 * 0.35:
            decay_reason = '近期量能萎缩至 35% 以下，资金撤退'

        # === 决策 & 执行 ===
        if decay_reason:
            # 趋势已坏 → 废除推荐
            cur.execute("""
                UPDATE sim_trades
                SET status='expired', exit_reason=%s, exit_date=%s
                WHERE id=%s
            """, (f'[重新评估废除] {decay_reason}', today, tid))
            expired += 1
            code_short = code[:6]
            print(f'  ✗ {code_short} {name}: {decay_reason} → 废除')
            continue

        # 趋势未坏 → 重新计算买卖点
        # 止损价: min(MA20, 近 10 日最低价) * 0.97 (与 smart_screener 一致)
        low_10 = min(lows[-10:]) if len(lows) >= 10 else min(lows)
        stop_ref = min(ma20_val, low_10)
        new_stop = round(stop_ref * 0.97, 2)

        # 建议买入价: MA20 支撑位买入，但不低于当前价的 95%
        # 场景 A: 股价贴近 MA20 → 买在 MA20（本质等价）
        # 场景 B: 股价远高于 MA20 → 限在 95% 处，避免等永远等不来的回调
        # 场景 C: 股价低于 MA20 → 买在 MA20（博反弹回支撑位）
        new_buy = round(max(ma20_val, current * 0.95), 2)

        # 目标价: 当前价 + 2 倍 ATR
        atr_sum = 0.0
        atr_n = 0
        for i in range(-1, -11, -1):
            if abs(i) > n_days - 1:
                break
            atr_sum += highs[i] - lows[i]
            atr_n += 1
        atr = atr_sum / atr_n if atr_n > 0 else 0.02 * current
        new_target = round(current + atr * 2, 2)

        # 重新评分（简化版 0-100）
        new_score = 30  # 基础分
        if ma5 > ma10 > ma20_val:
            new_score += 20
        elif ma5 > ma20_val:
            new_score += 10
        if current > ma20_val:
            new_score += 10
            dist_pct = (current / ma20_val - 1) * 100
            if 0 < dist_pct < 10:
                new_score += 8
        if vol_5 > vol_20 * 1.3:
            new_score += 10
        elif vol_5 > vol_20 * 0.8:
            new_score += 5
        # 跌幅合理性
        if n_days >= 6:
            chg_5d = (closes[-1] / closes[-6] - 1) * 100
            if chg_5d < -8:
                new_score -= 8
        # 连跌扣分
        if n_days >= 4 and closes[-1] < closes[-2] < closes[-3]:
            new_score -= 5

        new_score = max(0, min(100, new_score))

        # 判断买卖点是否有实质变化（变化 < 1% 则不更新）
        buy_changed = abs(new_buy - (float(buy_price) if buy_price else 0)) / max(float(buy_price) if buy_price else 1, 0.01) > 0.008
        target_changed = abs(new_target - (float(target_price) if target_price else 0)) / max(float(target_price) if target_price else 1, 0.01) > 0.01
        stop_changed = abs(new_stop - (float(stop_loss) if stop_loss else 0)) / max(float(stop_loss) if stop_loss else 1, 0.01) > 0.008

        if buy_changed or target_changed or stop_changed:
            cur.execute("""
                UPDATE sim_trades
                SET buy_price=%s, target_price=%s, stop_loss=%s,
                    score=%s, rec_date=%s,
                    reason=CONCAT(IFNULL(reason,''),
                        ' [', %s, ' 重新评估]')
                WHERE id=%s
            """, (new_buy, new_target, new_stop, new_score, today,
                  today.strftime('%m-%d'), tid))
            updated += 1
            code_short = code[:6]
            old_b = f'{float(buy_price):.2f}' if buy_price else 'N/A'
            old_t = f'{float(target_price):.2f}' if target_price else 'N/A'
            old_s = f'{float(stop_loss):.2f}' if stop_loss else 'N/A'
            print(f'  ↻ {code_short} {name}: 买 {old_b}→{new_buy:.2f}  '
                  f'目标 {old_t}→{new_target:.2f}  '
                  f'止损 {old_s}→{new_stop:.2f}  '
                  f'评分 {old_score or "?"}→{new_score}')
        # else: 变动 < 1%，维持原样，不做更新

    conn.commit()

    if updated or expired:
        print(f'\n    废除了 {expired} 笔，更新了 {updated} 笔')

    cur.close()
    conn.close()
    return updated, expired


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
    elif '--reevaluate' in sys.argv:
        print('=== 重新评估 waiting 股票 ===')
        updated, expired = reevaluate_waiting()
        print()
        backfill()
        report()
    else:
        backfill()
        report()
