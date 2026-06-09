# -*- coding: utf-8 -*-
"""
热股筛选器
基于人气榜和振幅数据，从策略1候选池中进一步筛选热点股票

用法:
  python3 hot_stock_screener.py                           # 全市场热股筛选
  python3 hot_stock_screener.py --cross codes.txt          # 与策略1池交叉筛选
  python3 hot_stock_screener.py --amplitude 30             # 30天振幅>30%的票
"""
import sys
import os
import datetime
import argparse

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
os.chdir(SCRIPT_DIR)
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

import pymysql

DB_CONFIG = {
    'host': 'localhost', 'port': 3306,
    'user': 'root', 'password': '12345678',
    'database': 'gp2', 'charset': 'utf8mb4',
}


# ============================================================
# 筛选器
# ============================================================

class HotStockScreener:
    """热股筛选器，基于人气 + 振幅 + 策略1交叉"""

    def __init__(self):
        pass

    def get_db(self):
        return pymysql.connect(**DB_CONFIG)

    def screen_by_heat_rank(self, min_appear_days=3, lookback_days=14):
        """
        从人气榜中筛选持续在榜的热股
        返回: [{code, name, appear_days, avg_rank, min_rank}, ...]
        """
        conn = self.get_db()
        c = conn.cursor()

        c.execute("""
            SELECT stock_code, stock_name,
                   COUNT(*) as appear_days,
                   AVG(hot_rank) as avg_rank,
                   MIN(hot_rank) as min_rank
            FROM hot_stock_rank_daily
            WHERE rank_date >= DATE_SUB(CURDATE(), INTERVAL %s DAY)
            GROUP BY stock_code, stock_name
            HAVING appear_days >= %s
            ORDER BY appear_days DESC, avg_rank ASC
        """, (lookback_days, min_appear_days))

        results = []
        for row in c.fetchall():
            results.append({
                'code': row[0],
                'name': row[1],
                'appear_days': row[2],
                'avg_rank': round(float(row[3]), 1),
                'min_rank': int(row[4]),
            })

        c.close()
        conn.close()
        return results

    def screen_by_range_amplitude(self, days=30, min_ampl_pct=30, max_ampl_pct=80,
                                   max_20d_chg=60, min_avg_vol=500000):
        """
        扫描日K数据: N天内（最低点→最高点）涨幅 >= min_ampl%
        排除：振幅过大（异常波动）、20日已涨太多、流动性差

        返回: [{code, name, ampl_pct, recent_chg, high_price, low_price, ...}, ...]
        """
        conn = self.get_db()
        c = conn.cursor()

        # 获取所有股票代码和最新数据
        c.execute("SELECT code, name FROM stock_basic_info_tbl WHERE type=0")
        all_stocks = {row[0]: row[1] for row in c.fetchall()}

        results = []
        batch_size = 500
        codes = list(all_stocks.keys())

        for i in range(0, len(codes), batch_size):
            batch = codes[i:i + batch_size]
            placeholders = ','.join(['%s'] * len(batch))

            # 对每只股票计算: 近N天高低点涨幅、近20日涨幅、近20日均量
            # 用子查询避免group_concat截断
            for code in batch:
                try:
                    c.execute("""
                        SELECT MAX(high), MIN(low), AVG(volume)
                        FROM daily_info_tbl
                        WHERE code = %s
                          AND tradedate >= DATE_SUB(CURDATE(), INTERVAL %s DAY)
                    """, (code, days))
                    row = c.fetchone()
                    if not row or row[0] is None:
                        continue
                    max_high, min_low, avg_vol = float(row[0] or 0), float(row[1] or 0), float(row[2] or 0)

                    if min_low <= 0 or avg_vol < min_avg_vol:
                        continue

                    ampl_pct = (max_high - min_low) / min_low * 100

                    if not (min_ampl_pct <= ampl_pct <= max_ampl_pct):
                        continue

                    # 查20日涨幅
                    c.execute("""
                        SELECT close FROM daily_info_tbl
                        WHERE code = %s
                        ORDER BY tradedate DESC LIMIT 21
                    """, (code,))
                    closes = [float(r[0]) for r in c.fetchall()]
                    recent_chg = 0
                    if len(closes) >= 21:
                        recent_chg = (closes[0] - closes[-1]) / closes[-1] * 100

                    # 排除已涨太多的
                    if recent_chg > max_20d_chg:
                        continue

                    results.append({
                        'code': code,
                        'name': all_stocks.get(code, ''),
                        'ampl_pct': round(ampl_pct, 2),
                        'recent_chg': round(recent_chg, 2),
                        'max_high': round(max_high, 2),
                        'min_low': round(min_low, 2),
                        'avg_vol': int(avg_vol),
                    })
                except Exception:
                    pass

        c.close()
        conn.close()

        # 按振幅降序
        results.sort(key=lambda x: x['ampl_pct'], reverse=True)
        return results

    def cross_screen_with_heat(self, amplitude_stocks, heat_stocks):
        """
        交叉筛选：振幅股票 ∩ 人气榜
        返回交集列表，附加热度信息
        """
        heat_map = {s['code']: s for s in heat_stocks}
        crossed = []
        for s in amplitude_stocks:
            if s['code'] in heat_map:
                h = heat_map[s['code']]
                crossed.append({
                    **s,
                    'appear_days': h['appear_days'],
                    'avg_rank': h['avg_rank'],
                    'heat_bonus': min(h['appear_days'] * 3, 15),  # 热度加分
                })
        return crossed

    def cross_with_strategy1(self, stock_list, strategy1_codes):
        """
        与策略1候选池交叉
        stock_list: [{code, ...}, ...]
        strategy1_codes: set of codes
        返回: 在策略1池中的股票
        """
        return [s for s in stock_list if s['code'] in strategy1_codes]

    def run_full_screen(self, strategy1_codes=None, min_ampl=30, min_heat_days=2):
        """
        完整筛选流程
        """
        print(f"\n{'='*60}")
        print(f"  🔥 热股筛选器")
        print(f"  {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}")
        print(f"{'='*60}")

        # 1. 人气榜筛选
        print(f"\n📊 人气榜持续在榜 (≥{min_heat_days}天):")
        heat_stocks = self.screen_by_heat_rank(min_appear_days=min_heat_days)
        print(f"  共 {len(heat_stocks)} 只")
        for s in heat_stocks[:10]:
            print(f"  {s['code']} {s['name']:<10} 在榜{s['appear_days']}天 均排{s['avg_rank']} 最佳{s['min_rank']}")

        # 2. 振幅筛选
        print(f"\n📊 30天振幅 ≥ {min_ampl}%:")
        amplitude_stocks = self.screen_by_range_amplitude(
            days=30, min_ampl_pct=min_ampl, max_ampl_pct=80, max_20d_chg=60
        )
        print(f"  共 {len(amplitude_stocks)} 只")
        for s in amplitude_stocks[:10]:
            print(f"  {s['code']} {s['name']:<10} 振幅{s['ampl_pct']:.1f}% 近20日{s['recent_chg']:+.1f}%")

        # 3. 交叉筛选
        print(f"\n📊 人气 ∩ 振幅 交叉验证:")
        crossed = self.cross_screen_with_heat(amplitude_stocks, heat_stocks)
        print(f"  共 {len(crossed)} 只同时满足人气+振幅条件")

        # 4. 与策略1交叉
        if strategy1_codes:
            crossed = self.cross_with_strategy1(crossed, strategy1_codes)
            print(f"\n📊 策略1池交叉验证:")
            print(f"  在策略1候选池中的共 {len(crossed)} 只")

        # 5. 输出
        if crossed:
            print(f"\n{'='*60}")
            print(f"  🎯 策略2候选（热门+振幅+策略1） TOP 20")
            print(f"{'='*60}")
            for i, s in enumerate(crossed[:20], 1):
                print(f"  {i:>2}. {s['code']} {s['name']:<10} "
                      f"振幅{s['ampl_pct']:.1f}% "
                      f"人气{s.get('appear_days','?')}天 "
                      f"热度+{s.get('heat_bonus',0)}")

        return crossed


def main():
    parser = argparse.ArgumentParser(description='热股筛选器')
    parser.add_argument('--cross', type=str, help='策略1候选代码列表文件')
    parser.add_argument('--amplitude', type=int, default=30, help='最低振幅阈值(%%)')
    parser.add_argument('--heat-days', type=int, default=2, help='人气榜最少在榜天数')
    args = parser.parse_args()

    screener = HotStockScreener()

    s1_codes = None
    if args.cross:
        with open(args.cross) as f:
            s1_codes = set(line.strip() for line in f if line.strip())

    screener.run_full_screen(
        strategy1_codes=s1_codes,
        min_ampl=args.amplitude,
        min_heat_days=args.heat_days,
    )


if __name__ == '__main__':
    main()
