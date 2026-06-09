# -*- coding: utf-8 -*-
"""
查询主题分析结果
用法:
  python query_theme_result.py              # 查询最新日期的结果
  python query_theme_result.py 2026-05-29   # 查询指定日期
  python query_theme_result.py --long       # 查询长期主线
  python query_theme_result.py --leaders    # 查询主线龙头票
"""
import sys
import os
import json
import datetime

# Ensure src/ directory is in sys.path for package imports
import sys, os
_SRC_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _SRC_DIR not in sys.path:
    sys.path.insert(0, _SRC_DIR)

from data.newstocklib import initMySQL


def query_latest_date():
    db = initMySQL()
    c = db.cursor()
    c.execute("SELECT MAX(trade_date) FROM theme_daily_score_tbl")
    row = c.fetchone()
    c.close()
    db.close()
    if row and row[0]:
        return row[0]
    return None


def query_daily_themes(date_str=None, top_n=15):
    """查询单日主线题材"""
    db = initMySQL()
    c = db.cursor()

    if date_str is None:
        date_str = query_latest_date()
        if date_str is None:
            print("暂无数据")
            return
    if isinstance(date_str, datetime.date):
        date_str = date_str.strftime('%Y-%m-%d')

    c.execute("""
        SELECT theme_code, theme_name, total_score, is_main_theme,
               score_zt_ratio, score_echelon, score_sustainability,
               score_capital_flow, score_index_rise, score_turnover_ratio,
               zt_count, zt_total, high_board_count, first_board_count,
               leader_codes, leader_names
        FROM theme_daily_score_tbl
        WHERE trade_date = %s
        ORDER BY total_score DESC
        LIMIT %s
    """, (date_str, top_n))

    rows = c.fetchall()
    if not rows:
        print(f"\n{date_str} 无数据，请先运行分析")
        return []

    print(f"\n{'='*70}")
    print(f"主线题材分析: {date_str}")
    print(f"{'='*70}")

    results = []
    for i, row in enumerate(rows, 1):
        (theme_code, theme_name, total, is_main, s1, s2, s3, s4, s5, s6,
         zt_c, zt_t, hb, fb, leader_codes, leader_names) = row
        main_mark = '**[主线]**' if is_main else ''
        results.append({
            'theme_name': theme_name, 'total_score': total, 'is_main': is_main,
            'zt_count': zt_c, 'zt_total': zt_t, 'high_board': hb, 'first_board': fb,
            'leader_codes': leader_codes, 'leader_names': leader_names,
        })

        leaders_str = ''
        if leader_names:
            try:
                names = json.loads(leader_names) if isinstance(leader_names, str) else leader_names
                leaders_str = ', '.join(names[:3])
            except:
                pass

        print(f"  {i:>2}. {theme_name:<18s} {main_mark} 总分={total:6.1f}  "
              f"涨停={zt_c}/{zt_t}  高标={hb}  首板={fb}")
        if leaders_str:
            print(f"      龙头: {leaders_str}")
        print(f"      占比={s1}  梯队={s2}  持续={s3}  资金={s4}  涨幅={s5}  成交={s6}")

    c.close()
    db.close()
    return results


def query_long_term_themes(date_str=None, top_n=20):
    """查询长期主线 (需要至少3天数据)"""
    db = initMySQL()
    c = db.cursor()

    if date_str is None:
        date_str = query_latest_date()
        if date_str is None:
            print("暂无数据")
            return
    if isinstance(date_str, datetime.date):
        date_str = date_str.strftime('%Y-%m-%d')

    # 获取近20个交易日数据
    c.execute("""
        SELECT DISTINCT trade_date FROM theme_daily_score_tbl
        ORDER BY trade_date DESC LIMIT 20
    """)
    dates = [row[0] for row in c.fetchall()]
    if not dates:
        print("暂无历史数据")
        return

    # 按题材聚合
    c.execute("""
        SELECT theme_code, theme_name, trade_date, total_score, is_main_theme,
               zt_count, high_board_count, first_board_count,
               leader_codes, leader_names
        FROM theme_daily_score_tbl
        WHERE trade_date IN (SELECT DISTINCT trade_date FROM theme_daily_score_tbl ORDER BY trade_date DESC LIMIT 20)
        ORDER BY theme_code, trade_date
    """)

    rows = c.fetchall()
    if not rows:
        print("暂无数据")
        return

    # 组织数据
    theme_data = {}
    for row in rows:
        tc, tn, td, ts, im, zc, hb, fb, lc, ln = row
        if tc not in theme_data:
            theme_data[tc] = {'name': tn, 'scores': [], 'dates': [], 'is_main': 0, 'zt_counts': [], 'leaders': []}
        theme_data[tc]['scores'].append(float(ts) if ts else 0)
        theme_data[tc]['dates'].append(td)
        theme_data[tc]['is_main'] += (1 if im else 0)
        theme_data[tc]['zt_counts'].append(zc or 0)
        if ln:
            try:
                names = json.loads(ln) if isinstance(ln, str) else ln
                if names:
                    theme_data[tc]['leaders'] = names[:3]
            except:
                pass

    # 计算长期指标
    stats = []
    for tc, data in theme_data.items():
        scores = data['scores']
        zt_all = data['zt_counts']
        active = len(scores)
        if active < 3:
            continue
        total = sum(scores)
        avg = total / active
        top_main = data['is_main']

        # 简单趋势
        if len(scores) >= 3:
            recent = scores[:3]
            if recent[0] > recent[1] > recent[2]:
                trend = 'rising'
            elif recent[0] < recent[1] < recent[2]:
                trend = 'declining'
            elif recent[0] >= recent[1] and recent[0] >= recent[2]:
                trend = 'stable_up'
            else:
                trend = 'stable'
        else:
            trend = 'unknown'

        stats.append({
            'name': data['name'], 'active': active, 'total': total, 'avg': avg,
            'top_main': top_main, 'trend': trend,
            'leaders': data['leaders'], 'latest_zt': zt_all[-1] if zt_all else 0,
        })

    stats.sort(key=lambda x: x['total'], reverse=True)

    # 打印
    print(f"\n{'='*80}")
    print(f"长期主线题材 (近20个交易日)")
    print(f"{'='*80}")
    print(f"{'排名':<5}{'题材名称':<18}{'累计分':<8}{'日均':<7}{'活跃':<6}{'主线次数':<8}{'趋势':<10}{'最新涨停':<8}")
    print('-' * 80)

    for i, s in enumerate(stats[:top_n], 1):
        trend_icon = {'rising': '↑上升', 'declining': '↓下降', 'stable_up': '→偏强', 'stable': '→平稳'}.get(s['trend'], s['trend'])
        print(f"{i:<5}{s['name']:<18}{s['total']:<8.1f}{s['avg']:<7.1f}"
              f"{s['active']}/20{'':<2}{s['top_main']:<8}{trend_icon:<10}{s['latest_zt']}")

    c.close()
    db.close()
    return stats


def query_main_theme_leaders(date_str=None):
    """查询主线的龙头票"""
    db = initMySQL()
    c = db.cursor()

    if date_str is None:
        date_str = query_latest_date()
        if date_str is None:
            print("暂无数据")
            return
    if isinstance(date_str, datetime.date):
        date_str = date_str.strftime('%Y-%m-%d')

    c.execute("""
        SELECT theme_name, leader_codes, leader_names, total_score,
               zt_count, zt_total, high_board_count, first_board_count
        FROM theme_daily_score_tbl
        WHERE trade_date = %s AND is_main_theme = 1
        ORDER BY total_score DESC
    """, (date_str,))

    rows = c.fetchall()
    if not rows:
        print(f"\n{date_str} 无主线题材数据")
        return

    print(f"\n{'='*70}")
    print(f"主线题材龙头票: {date_str}")
    print(f"{'='*70}")

    for row in rows:
        theme_name, lc, ln, ts, zc, zt, hb, fb = row
        leaders = json.loads(ln) if isinstance(ln, str) else (ln or [])

        print(f"\n  [{theme_name}] 总分={ts if ts else 0:.1f}  涨停={zc}/{zt}  高标={hb}  首板={fb}")
        if leaders:
            for j, name in enumerate(leaders[:5], 1):
                code = json.loads(lc)[j-1] if lc and isinstance(lc, str) else ''
                print(f"    {j}. {code} {name}")

    c.close()
    db.close()


if __name__ == '__main__':
    args = sys.argv[1:]

    if '--long' in args:
        date_arg = args[0] if args and not args[0].startswith('--') else None
        query_long_term_themes(date_arg)
    elif '--leaders' in args:
        date_arg = args[0] if args and not args[0].startswith('--') else None
        query_main_theme_leaders(date_arg)
    else:
        date_arg = args[0] if args else None
        query_daily_themes(date_arg)
