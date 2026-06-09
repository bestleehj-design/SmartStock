# -*- coding: utf-8 -*-
"""
查询刚开启主升浪的主线龙头票
结合: 主线题材 + 龙头识别 + 策略1起涨信号(均线粘合+放量上涨)
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


def query_uptrend_leaders(date_str=None):
    """
    找出在主线题材中、刚开启主升浪的龙头票
    条件:
    1. 属于当日主线题材的龙头票
    2. 连板数1-2（刚启动，不算已拉很高）
    3. 近5日均线开始发散上行（MA5 > MA10 > MA20趋势确认）
    4. 当日放量（成交量高于V37平均）
    """
    db = initMySQL()
    c = db.cursor()

    # 确定日期
    if date_str is None:
        c.execute("SELECT MAX(tradedate) FROM daily_info_tbl")
        date_str = c.fetchone()[0]
    if isinstance(date_str, datetime.date):
        date_str = date_str.strftime('%Y-%m-%d')

    # 1. 获取当日主线题材的龙头票
    c.execute("""
        SELECT theme_name, leader_codes, leader_names, total_score,
               zt_count, zt_total, high_board_count, first_board_count
        FROM theme_daily_score_tbl
        WHERE trade_date = %s AND is_main_theme = 1
        ORDER BY total_score DESC
    """, (date_str,))

    theme_rows = c.fetchall()
    if not theme_rows:
        print(f"\n{date_str} 暂无明显主线题材")
        return

    print(f"\n{'='*80}")
    print(f"主升浪龙头票筛选 ({date_str})")
    print(f"{'='*80}")

    results = []

    for row in theme_rows:
        theme_name, lc, ln, ts, zc, zt, hb, fb = row
        if not lc:
            continue

        leader_codes = json.loads(lc) if isinstance(lc, str) else lc
        leader_names = json.loads(ln) if isinstance(ln, str) else ln

        for idx, code in enumerate(leader_codes):
            name = leader_names[idx] if idx < len(leader_names) else code

            # 2. 获取该股近60天日线数据
            c.execute("""
                SELECT tradedate, close, volume, adj_factor
                FROM daily_info_tbl
                WHERE code = %s AND tradedate <= %s
                ORDER BY tradedate DESC LIMIT 60
            """, (code, date_str))
            daily_rows = c.fetchall()

            if len(daily_rows) < 40:
                continue

            # 转换为列表(最新在前)
            dates = []
            closes = []
            volumes = []
            for dr in daily_rows:
                dates.append(dr[0])
                adj = float(dr[3]) if dr[3] else 1.0
                closes.append(float(dr[1]) * adj)      # close * adj_factor
                volumes.append(float(dr[2]) if dr[2] else 0)  # volume不需要乘以adj

            # 3. 计算当日涨跌幅
            if len(closes) < 2:
                continue
            today_change = (closes[0] - closes[1]) / closes[1] * 100

            # 4. 计算均线 MA5, MA10, MA20, MA30
            def calc_ma(prices, period):
                if len(prices) < period:
                    return None
                return sum(prices[:period]) / period

            ma5 = calc_ma(closes, 5)
            ma10 = calc_ma(closes, 10)
            ma20 = calc_ma(closes, 20)
            ma30 = calc_ma(closes, 30)

            if not all([ma5, ma10, ma20, ma30]):
                continue

            # 均线多头: MA5 > MA10 > MA20 > MA30
            is_bull_ma = (ma5 > ma10 > ma20 > ma30)

            # 5. 计算15天前的均线粘合程度
            ma5_15d = calc_ma(closes[15:], 5)  # 15天前的MA5
            ma30_15d = calc_ma(closes[15:], 30)

            convergence_15d = None
            if ma5_15d and ma30_15d and ma30_15d > 0:
                convergence_15d = abs(ma5_15d - ma30_15d) / ma30_15d
                # <3% 视为粘合

            # 当前均线发散程度
            current_divergence = None
            if ma30 > 0:
                current_divergence = (ma5 - ma30) / ma30

            # 6. 量比 (V / V37)
            v37 = sum(volumes[:37]) / 37 if len(volumes) >= 37 else sum(volumes) / len(volumes)
            volume_ratio = volumes[0] / v37 if v37 > 0 else 0

            # 7. 连板数判断
            c.execute("""
                SELECT analysis_detail FROM theme_daily_score_tbl
                WHERE trade_date = %s AND theme_name = %s
            """, (date_str, theme_name))
            detail_row = c.fetchone()
            consecutive_zt = 0
            if detail_row and detail_row[0]:
                try:
                    detail = json.loads(detail_row[0]) if isinstance(detail_row[0], str) else detail_row[0]
                    zt_info = detail.get('consecutive_zt', {})
                    consecutive_zt = zt_info.get(code, 0)
                except:
                    pass

            # 8. 获取基本面数据 (column order: code, tradedate, turnover_rate_f, pe, pe_ttm, pb, total_share, float_share, total_mv, circ_mv, free_share)
            c.execute("""
                SELECT turnover_rate_f, circ_mv
                FROM daily_basic_tbl
                WHERE code = %s AND tradedate = %s
            """, (code, date_str))
            basic = c.fetchone()
            turnover = float(basic[0]) if basic and basic[0] else 0
            circ_mv = float(basic[1]) if basic and basic[1] else 0
            circ_mv_yi = circ_mv / 10000 if circ_mv else 0

            # 9. 资金流向
            c.execute("""
                SELECT net_lg_amount, net_elg_amount
                FROM daily_moneyflow_tbl
                WHERE code = %s AND tradedate = %s
            """, (code, date_str))
            mf = c.fetchone()
            net_big = (float(mf[0] or 0) + float(mf[1] or 0)) if mf else 0

            # --- 主升浪判断 ---
            # A. 已处于主升浪（连板>=3，趋势确立但已不早）
            # B. 刚开启主升浪（连板1-2 + 15天前有粘合 + 当前均线发散 + 放量）
            # C. 潜在主升浪（今日首板 + 15天内有粘合迹象 + 放量异动）

            is_early_uptrend = False
            status_label = ''
            status_reasons = []

            # 基本条件
            if volume_ratio >= 1.2:
                status_reasons.append(u'放量(量比{:.1f})'.format(volume_ratio))
            if is_bull_ma:
                status_reasons.append(u'多头排列')
            if convergence_15d is not None and convergence_15d < 0.05:
                status_reasons.append(u'15天前粘合({:.1f}%)'.format(convergence_15d * 100))
            if today_change >= 3:
                status_reasons.append(u'今日涨幅{:.1f}%'.format(today_change))

            if consecutive_zt >= 3:
                status_label = '主升浪中(已连板)'
            elif (consecutive_zt >= 1 and consecutive_zt <= 2
                  and is_bull_ma and volume_ratio >= 1.2
                  and (convergence_15d is None or convergence_15d < 0.05)):
                status_label = '>>> 刚开启主升浪 <<<'
                is_early_uptrend = True
            elif (consecutive_zt == 1
                  and volume_ratio >= 1.5
                  and (is_bull_ma or (convergence_15d is not None and convergence_15d < 0.03))):
                status_label = '潜在主升浪(首板放量)'
            elif is_bull_ma and volume_ratio >= 1.5:
                status_label = '关注(放量多头)'
            else:
                status_label = '观望'

            results.append({
                'code': code,
                'name': name,
                'theme': theme_name,
                'theme_score': ts if ts else 0,
                'consecutive_zt': consecutive_zt,
                'today_change': round(today_change, 2),
                'volume_ratio': round(volume_ratio, 2),
                'is_bull_ma': is_bull_ma,
                'convergence_15d': convergence_15d,
                'current_divergence': current_divergence,
                'turnover': round(turnover, 2),
                'circ_mv_yi': round(circ_mv_yi, 2),
                'net_big': round(net_big, 2),
                'status': status_label,
                'is_early_uptrend': is_early_uptrend,
                'reasons': status_reasons,
            })

    # 去重: 同一只票可能属于多个概念板块，按最佳状态保留
    priority = {
        '>>> 刚开启主升浪 <<<': 0,
        '潜在主升浪(首板放量)': 1,
        '关注(放量多头)': 2,
        '主升浪中(已连板)': 3,
        '观望': 4,
    }

    deduped = {}
    for r in results:
        code = r['code']
        if code not in deduped:
            deduped[code] = r
        else:
            # 保留状态更好的
            existing_priority = priority.get(deduped[code]['status'], 5)
            current_priority = priority.get(r['status'], 5)
            if current_priority < existing_priority:
                deduped[code] = r
            elif current_priority == existing_priority and r['volume_ratio'] > deduped[code]['volume_ratio']:
                deduped[code] = r
    results = list(deduped.values())

    # 按优先级排序
    results.sort(key=lambda x: (priority.get(x['status'], 5), -x['volume_ratio']))

    # 打印
    print(f"\n{'题材':<16s}{'股票':<12s}{'状态':<22s}{'连板':<6}{'涨幅%':<8}{'量比':<7}{'换手%':<8}{'市值亿':<8}{'信号'}")
    print('-' * 110)
    for r in results:
        reasons_str = '; '.join(r['reasons'][:3])
        print(f"{r['theme']:<16s}{r['name']:<12s}{r['status']:<22s}{r['consecutive_zt']:<6}"
              f"{r['today_change']:<8.2f}{r['volume_ratio']:<7.2f}{r['turnover']:<8.2f}"
              f"{r['circ_mv_yi']:<8.1f}{reasons_str}")

    # 买入建议
    early_candidates = [r for r in results if r['is_early_uptrend']]
    potential = [r for r in results if r['status'] == '潜在主升浪(首板放量)']

    if early_candidates:
        print(f"\n{'='*80}")
        print(f"买入建议 - 刚开启主升浪的龙头票")
        print(f"{'='*80}")
        for i, r in enumerate(early_candidates, 1):
            print(f"\n  {i}. {r['name']}({r['code']}) - {r['theme']}")
            print(f"     涨幅: {r['today_change']:.1f}%  连板: {r['consecutive_zt']}  量比: {r['volume_ratio']:.1f}")
            print(f"     均线: {'多头' if r['is_bull_ma'] else '非多头'}  "
                  f"换手: {r['turnover']:.1f}%  流通市值: {r['circ_mv_yi']:.0f}亿")
            if r['convergence_15d'] is not None:
                print(f"     15天前粘合度: {r['convergence_15d']*100:.1f}%  "
                      f"当前发散度: {r['current_divergence']*100:.1f}%")
    elif potential:
        print(f"\n{'='*80}")
        print(f"关注(尚未确认，但值得跟踪)")
        print(f"{'='*80}")
        for i, r in enumerate(potential, 1):
            print(f"\n  {i}. {r['name']}({r['code']}) - {r['theme']}")
            print(f"     涨幅: {r['today_change']:.1f}%  量比: {r['volume_ratio']:.1f}  换手: {r['turnover']:.1f}%")
    else:
        print(f"\n{'='*80}")
        print(f"当前主线龙头票已处于拉升阶段，暂无刚启动的买点")
        print(f"建议等待主线内首板放量的新龙头出现")
        print(f"{'='*80}")

    c.close()
    db.close()
    return results


if __name__ == '__main__':
    date_arg = sys.argv[1] if len(sys.argv) > 1 else None
    query_uptrend_leaders(date_arg)
