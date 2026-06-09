#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# Ensure src/ directory is in sys.path for package imports
import sys, os
_SRC_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _SRC_DIR not in sys.path:
    sys.path.insert(0, _SRC_DIR)

"""
盘中实时监控持仓
用法: python3 live_monitor.py --plan --interval 10
"""

import argparse
import re
import time
import signal
from datetime import datetime, timedelta

from skills.zhaban_check import (
    get_market_suffix, get_db_code, get_realtime, get_history,
    calc_limit, SINA_URL, SINA_HEADERS,
)


# ─── 行情判断 ───────────────────────────────────────────────

def is_trading_time():
    """判断当前是否在 A 股交易时段（含集合竞价）"""
    now = datetime.now()
    if now.weekday() >= 5:
        return False
    t = now.hour * 60 + now.minute
    return 545 <= t <= 905  # 09:25-15:05


def is_market_closed():
    """收盘后（或非交易日）返回 True"""
    return not is_trading_time()


# ─── 交易计划解析 ───────────────────────────────────────────

def extract_triggers(text):
    """从触发条件文本中提取止损、止盈、股数"""
    result = {'stop_loss': None, 'target': None, 'shares': None}

    if not text or text.strip() in ('—', '-', ''):
        return result

    # 止损: 跌破MA20(451)
    m = re.search(r'跌破MA20\((\d+\.?\d*)\)', text)
    if m:
        result['stop_loss'] = float(m.group(1))

    # 止盈: 止盈=56.70
    m = re.search(r'止盈[=＝](\d+\.?\d*)', text)
    if m:
        result['target'] = float(m.group(1))

    # 股数: 留350股
    m = re.search(r'留(\d+)股', text)
    if m:
        result['shares'] = int(m.group(1))

    return result


def is_cleared(text, op_text):
    """判断是否已清仓"""
    cleared_markers = ['✅已清', '已清仓', '已清']
    for m in cleared_markers:
        if m in text or m in op_text:
            return True
    return False


def parse_trading_plan(filepath):
    """从 trading_plan.md 解析当前持仓"""
    holdings = {}

    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
    except FileNotFoundError:
        print(f"⚠️ 找不到交易计划文件: {filepath}")
        return holdings

    # 定位 当前持仓 表格
    sec_match = re.search(r'##\s+当前持仓\s*\n(.*?)(?=\n##|\Z)', content, re.DOTALL)
    if not sec_match:
        print("⚠️ 未找到「当前持仓」章节")
        return holdings

    section = sec_match.group(1)
    lines = section.strip().split('\n')

    in_table = False
    for line in lines:
        line = line.strip()
        if not line:
            continue
        if line.startswith('|---'):
            in_table = True
            continue
        if line.startswith('|') and in_table:
            parts = [p.strip() for p in line.split('|') if p.strip()]
            if len(parts) < 5:
                continue
            # 表头行
            if parts[0] in ('代码', 'Code'):
                continue

            code_raw = parts[0]
            name = parts[1]
            op = parts[3] if len(parts) > 3 else ''
            trigger = parts[4] if len(parts) > 4 else ''

            # 跳过港股
            if '.HK' in code_raw.upper():
                continue

            # 跳过已清仓
            if is_cleared(trigger, op):
                continue

            # 提取纯数字代码
            code = code_raw.replace('.SH', '').replace('.SZ', '').strip()

            # 解析触发条件
            triggers = extract_triggers(trigger)

            holdings[code] = {
                'name': name,
                'stop_loss': triggers['stop_loss'],
                'target': triggers['target'],
                'shares': triggers['shares'],
                'op': op,
                'trigger': trigger,
            }

    return holdings


# ─── 历史数据加载 ───────────────────────────────────────────

def load_historical_data(codes):
    """加载每个代码的 MA20 和 60日均量"""
    ma20_map = {}
    avg_vol_map = {}

    for code in codes:
        hist = get_history(code)
        if hist.get('error'):
            print(f"  ⚠️ {code} 历史数据获取失败: {hist['error']}")
            continue

        closes = hist['closes']
        volumes = hist['volumes']

        if len(closes) >= 20:
            ma20_map[code] = round(sum(closes[-20:]) / 20, 2)

        if volumes:
            # 60日均量 (DB 单位为手)
            avg_vol_map[code] = sum(volumes) / len(volumes)

    return ma20_map, avg_vol_map


# ─── 告警检测 ──────────────────────────────────────────────

def check_alerts(code, name, price, info, ma20, avg_vol, vol_shou,
                 limit_up, yest_close):
    """检测 5 种告警条件"""
    alerts = []

    # 1. 🔴 止损触发
    stop_loss = info.get('stop_loss')
    if stop_loss and price <= stop_loss:
        loss_pct = (price / stop_loss - 1) * 100
        alerts.append((
            '🔴', '紧急',
            f'止损触发！{name} 现价={price:.2f} 止损={stop_loss:.2f} '
            f'跌幅={loss_pct:.1f}% 建议立即卖出'
        ))

    # 2. 🟡 MA20 跌破
    if ma20 and price <= ma20:
        dev = (price / ma20 - 1) * 100
        alerts.append((
            '🟡', '警告',
            f'MA20跌破 {name} 现价={price:.2f} MA20={ma20:.2f} '
            f'偏离={dev:.1f}%'
        ))

    # 3. 🟡 接近涨停
    if limit_up and price > 0:
        dist = (limit_up - price) / limit_up * 100
        if dist < 3:
            alerts.append((
                '🟡', '警告',
                f'接近涨停 {name} 现价={price:.2f} 涨停={limit_up:.2f} '
                f'距涨停 {dist:.1f}% 关注炸板'
            ))

    # 4. 🟢 放量
    if avg_vol and vol_shou > 0:
        vol_ratio = vol_shou / avg_vol
        if vol_ratio > 1.5:
            chg = (price / yest_close - 1) * 100 if yest_close > 0 else 0
            alerts.append((
                '🟢', '信号',
                f'放量 {name} 现价={price:.2f} 量比={vol_ratio:.1f} '
                f'涨跌={chg:+.1f}%'
            ))

    # 5. 🟢 触及止盈
    target = info.get('target')
    if target and price >= target:
        profit = (price / yest_close - 1) * 100 if yest_close > 0 else 0
        alerts.append((
            '🟢', '信号',
            f'触及止盈 {name} 现价={price:.2f} 目标={target:.2f} '
            f'盈利={profit:+.1f}%'
        ))

    return alerts


# ─── 行情获取（合并请求） ────────────────────────────────────

def fetch_realtime_batch(codes):
    """批量获取实时行情"""
    import requests
    sina_list = ','.join(get_market_suffix(c) for c in codes)
    try:
        r = requests.get(SINA_URL.format(sina_list), headers=SINA_HEADERS, timeout=15)
        r.encoding = 'gbk'
        body = r.text
    except Exception as e:
        return {'_error': str(e)}

    results = {}
    # 新浪批量返回，每行一个股票
    for code in codes:
        results[code] = _parse_sina_line(code, body)

    return results


def _parse_sina_line(code, body):
    """从批量返回中解析单只股票"""
    sina_code = get_market_suffix(code)
    # 匹配 var hq_str_<code>="...";
    pattern = rf'var hq_str_{sina_code}="([^"]*)"'
    m = re.search(pattern, body)
    if not m:
        return {'error': f'未找到 {code} 的行情数据'}
    data = m.group(1).split(',')
    if len(data) < 30:
        return {'error': f'{code} 数据字段不足'}
    try:
        return {
            'name': data[0],
            'open': float(data[1]) if data[1] else 0,
            'yest_close': float(data[2]) if data[2] else 0,
            'price': float(data[3]) if data[3] else 0,
            'high': float(data[4]) if data[4] else 0,
            'low': float(data[5]) if data[5] else 0,
            'volume': float(data[8]) if data[8] else 0,
            'amount': float(data[9]) if data[9] else 0,
        }
    except (ValueError, IndexError) as e:
        return {'error': str(e)}


# ─── 输出格式化 ─────────────────────────────────────────────

def fmt_alert_line(alert):
    """格式化告警行"""
    emoji, level, msg = alert
    return f"    {emoji} {level:4s} {msg}"


def fmt_stock_line(code, name, price, yest_close, vol_shou, avg_vol, ma20):
    """格式化单只股票行情行"""
    chg = (price / yest_close - 1) * 100 if yest_close > 0 else 0
    vol_ratio = vol_shou / avg_vol if avg_vol and vol_shou > 0 else 0
    arrow = '⬆' if price > yest_close else ('⬇' if price < yest_close else '→')
    ma20_str = f'{ma20:.2f}' if ma20 else 'N/A'

    return (f"  {code:<8s} {name:<8s} "
            f"价格={price:<8.2f} {chg:+5.1f}%  "
            f"量比={vol_ratio:<5.2f} MA20={ma20_str:<8s} {arrow}")


# ─── 主逻辑 ─────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description='盘中实时监控持仓')
    parser.add_argument('--watch', type=str, default='',
                        help='手动指定代码，逗号分隔 (如 002384,600584)')
    parser.add_argument('--plan', action='store_true',
                        help='从 trading_plan.md 自动加载持仓')
    parser.add_argument('--interval', type=int, default=10,
                        help='轮询间隔秒数 (默认10)')
    parser.add_argument('--silent', action='store_true',
                        help='只在触发告警时打印')
    args = parser.parse_args()

    # ── 构建持仓 ──
    holdings = {}
    if args.plan:
        # 尝试项目根目录的 trading_plan.md
        plan_paths = [
            'trading_plan.md',
            '../trading_plan.md',
            '../../trading_plan.md',
        ]
        found = False
        for p in plan_paths:
            if os.path.exists(p):
                holdings = parse_trading_plan(p)
                found = True
                break
        if not found:
            print("⚠️ 找不到 trading_plan.md")
    elif args.watch:
        for c in args.watch.split(','):
            c = c.strip()
            if c:
                holdings[c] = {'name': c, 'stop_loss': None,
                               'target': None, 'shares': None,
                               'op': '', 'trigger': ''}

    if not holdings:
        print("请指定 --plan 或 --watch <代码>")
        print("示例: python3 live_monitor.py --plan --interval 10")
        print("示例: python3 live_monitor.py --watch 002384,600584 --interval 5")
        sys.exit(1)

    codes = list(holdings.keys())

    print(f"\n{'='*56}")
    print(f"  📊 盘中实时监控 — {len(codes)} 只持仓")
    print(f"  轮询间隔: {args.interval}s  |  模式: "
          f"{'静默' if args.silent else '正常'}")
    print(f"{'='*56}")
    print(f"  监控代码: {', '.join(codes)}")
    print()

    # ── 加载历史数据 ──
    print("  加载历史行情数据...")
    ma20_map, avg_vol_map = load_historical_data(codes)
    print(f"  MA20 可用: {len(ma20_map)}/{len(codes)}  "
          f"均量可用: {len(avg_vol_map)}/{len(codes)}")
    print()

    # ── 统计 ──
    stats = {
        'rounds': 0,
        'stop_loss_hits': 0,
        'ma20_breaks': 0,
        'near_limit': 0,
        'volume_spikes': 0,
        'target_hits': 0,
        'errors': 0,
        'start_time': datetime.now(),
    }
    last_alerts = {}  # code -> set of alert keys, 用于去重

    print("  开始轮询 (Ctrl+C 退出)...\n")

    def show_header():
        now = datetime.now()
        status = '🟢 交易中' if is_trading_time() else '⚫ 已收盘'
        print(f"\n🕐 {now.strftime('%H:%M:%S')}  {status}  "
              f"第 {stats['rounds']} 轮")

    # ── 主循环 ──
    try:
        while True:
            stats['rounds'] += 1
            rt_map = fetch_realtime_batch(codes)

            if rt_map.get('_error'):
                stats['errors'] += 1
                if not args.silent:
                    show_header()
                    print(f"  ⚠️ 网络错误: {rt_map['_error']}")
                time.sleep(args.interval)
                continue

            round_alerts = {}  # code -> list of alerts

            for code in codes:
                rt = rt_map.get(code, {})
                if rt.get('error'):
                    stats['errors'] += 1
                    continue

                price = rt['price']
                yest = rt['yest_close']
                vol_shou = rt['volume'] / 100  # 股 → 手
                avg_vol = avg_vol_map.get(code)
                ma20 = ma20_map.get(code)
                info = holdings[code]
                name = info.get('name', code)

                # 计算涨停价
                limit_up = calc_limit(yest, get_db_code(code)) if yest > 0 else 0

                # 告警检测
                alerts = check_alerts(code, name, price, info, ma20,
                                      avg_vol, vol_shou, limit_up, yest)

                # 去重：相同告警不重复输出
                alert_keys = {a[2] for a in alerts}  # 用告警内容做 key
                prev_keys = last_alerts.get(code, set())
                new_alerts = [a for a in alerts if a[2] not in prev_keys]

                round_alerts[code] = (rt, new_alerts if new_alerts else [])
                last_alerts[code] = alert_keys

                # 统计
                for a in alerts:
                    if a[0] == '🔴':
                        stats['stop_loss_hits'] += 1
                    elif a[0] == '🟡' and 'MA20' in a[2]:
                        stats['ma20_breaks'] += 1
                    elif a[0] == '🟡' and '涨停' in a[2]:
                        stats['near_limit'] += 1
                    elif a[0] == '🟢' and '放量' in a[2]:
                        stats['volume_spikes'] += 1
                    elif a[0] == '🟢' and '止盈' in a[2]:
                        stats['target_hits'] += 1

            # ── 输出 ──
            has_any_alert = any(alerts for _, alerts in round_alerts.values())

            if args.silent:
                # 静默模式：只在有告警时输出
                if has_any_alert:
                    show_header()
                    for code in codes:
                        rt, alerts = round_alerts[code]
                        if not alerts and rt.get('price', 0) == 0:
                            continue
                        name = holdings[code].get('name', code)
                        price = rt.get('price', 0)
                        yest = rt.get('yest_close', 0)
                        vol_shou = rt.get('volume', 0) / 100
                        avg_vol = avg_vol_map.get(code)
                        ma20 = ma20_map.get(code)
                        line = fmt_stock_line(code, name, price, yest,
                                              vol_shou, avg_vol, ma20)
                        tag = ' '.join(a[0] for a in alerts[:3])
                        print(f"{line}  {tag}")
                        for a in alerts:
                            print(fmt_alert_line(a))
                    print('─' * 56)
            else:
                # 正常模式：每轮都输出
                show_header()
                for code in codes:
                    rt, alerts = round_alerts[code]
                    name = holdings[code].get('name', code)
                    price = rt.get('price', 0)
                    yest = rt.get('yest_close', 0)

                    if price == 0 and rt.get('volume', 0) == 0:
                        print(f"  {code:<8s} {name:<8s}  —— 暂无成交 ——")
                        continue

                    vol_shou = rt.get('volume', 0) / 100
                    avg_vol = avg_vol_map.get(code)
                    ma20 = ma20_map.get(code)

                    line = fmt_stock_line(code, name, price, yest,
                                          vol_shou, avg_vol, ma20)
                    if alerts:
                        tag = ' ' + ' '.join(a[0] for a in alerts[:3])
                        print(line + tag)
                        for a in alerts:
                            print(fmt_alert_line(a))
                    else:
                        print(line)

                print('─' * 56)

            time.sleep(args.interval)

    except KeyboardInterrupt:
        print("\n")
        print("=" * 56)
        print("  📊 当日监控汇总")
        print("=" * 56)
        elapsed = stats['start_time']
        now = datetime.now()
        dur = now - elapsed
        print(f"  开始时间: {elapsed.strftime('%H:%M:%S')}")
        print(f"  结束时间: {now.strftime('%H:%M:%S')}")
        print(f"  运行时长: {int(dur.total_seconds() // 60)}分"
              f"{int(dur.total_seconds() % 60)}秒")
        print(f"  轮询次数: {stats['rounds']}")
        print(f"  {'─'*50}")
        print(f"  🔴 止损触发: {stats['stop_loss_hits']} 次")
        print(f"  🟡 MA20跌破: {stats['ma20_breaks']} 次")
        print(f"  🟡 接近涨停: {stats['near_limit']} 次")
        print(f"  🟢 放量信号: {stats['volume_spikes']} 次")
        print(f"  🟢 止盈触及: {stats['target_hits']} 次")
        if stats['errors']:
            print(f"  ⚠️ 网络错误: {stats['errors']} 次")
        print("=" * 56)
        print("\n监控结束。\n")


if __name__ == '__main__':
    main()
