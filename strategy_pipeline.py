# -*- coding: utf-8 -*-
"""
策略串联引擎
将策略1→策略2→策略3串联执行，输出最终TOP N候选股

策略1: 技术面初筛（量价齐升+均线粘合/多头）
策略2: 热点+新闻交叉验证（热榜+板块+新闻利好）
策略3: 综合评分（smart_screener评分+基本面+ML置信度）

用法:
  python3 strategy_pipeline.py                  # 完整串联筛选
  python3 strategy_pipeline.py --top 10          # 输出前10
  python3 strategy_pipeline.py --steps 1,2        # 只跑到策略2
"""
import sys
import os
import datetime
import time
import argparse
import json

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


class StrategyPipeline:
    """策略串联引擎"""

    def __init__(self):
        pass

    def _db(self):
        return pymysql.connect(**DB_CONFIG)

    def _ma(self, arr, n):
        if len(arr) < n:
            return arr[-1] if arr else 0
        return sum(arr[-n:]) / n

    def today_str(self):
        return datetime.date.today().strftime('%Y-%m-%d')

    # ================================================================
    # 策略1: 技术面初筛
    # ================================================================

    def step1_screen(self, min_vol_ratio=1.5, min_rise_pct=3.0,
                     convergence_ma=[5, 10, 30], convergence_max_pct=4.0):
        """
        策略1: 量价齐升 + 均线粘合 筛选
        返回: [{code, name, rise_pct, vol_ratio, convergence, ...}, ...]
        """
        print(f"\n{'='*60}")
        print(f"  策略1: 技术面初筛")
        print(f"  条件: 均线{convergence_ma}粘合<{convergence_max_pct}% + 量价齐升(量>{min_vol_ratio}倍, 涨>{min_rise_pct}%)")
        print(f"{'='*60}")

        conn = self._db()
        c = conn.cursor()

        # 获取所有A股
        c.execute("SELECT code, name FROM stock_basic_info_tbl WHERE type=0 AND status=1")
        all_stocks = [(r[0], r[1]) for r in c.fetchall()]
        print(f"  全市场: {len(all_stocks)} 只")

        candidates = []
        processed = 0
        batch_interval = 200

        for code, name in all_stocks:
            processed += 1
            if processed % batch_interval == 0:
                print(f"    进度: {processed}/{len(all_stocks)}")

            # 拉近90天日K
            try:
                c.execute("""
                    SELECT close, volume FROM daily_info_tbl
                    WHERE code = %s ORDER BY tradedate DESC LIMIT 90
                """, (code,))
                rows = c.fetchall()
                if len(rows) < 40:
                    continue

                closes = [float(r[0]) for r in rows[::-1]]
                volumes = [float(r[1]) for r in rows[::-1]]

                current = closes[-1]
                if current <= 0:
                    continue

                # 均线粘合检查
                ma_vals = [self._ma(closes, p) for p in convergence_ma]
                max_ma = max(ma_vals)
                min_ma = min(ma_vals)
                convergence = (max_ma - min_ma) / min_ma * 100 if min_ma > 0 else 999

                if convergence > convergence_max_pct:
                    continue

                # 量价齐升检查
                v37 = sum(volumes[-37:]) / 37 if len(volumes) >= 37 else sum(volumes) / len(volumes)
                vol_ratio = volumes[-1] / v37 if v37 > 0 else 0

                # 今日或昨日涨幅
                today_rise = (closes[-1] - closes[-2]) / closes[-2] * 100 if len(closes) >= 2 else 0
                yest_rise = (closes[-2] - closes[-3]) / closes[-3] * 100 if len(closes) >= 3 else 0

                vol_ok = vol_ratio >= min_vol_ratio
                rise_ok = today_rise >= min_rise_pct or yest_rise >= min_rise_pct

                if vol_ok and rise_ok:
                    candidates.append({
                        'code': code,
                        'name': name,
                        'rise_pct': round(max(today_rise, yest_rise), 2),
                        'vol_ratio': round(vol_ratio, 2),
                        'convergence': round(convergence, 3),
                        'price': round(current, 2),
                    })
            except Exception:
                pass

        c.close()
        conn.close()

        print(f"  策略1候选: {len(candidates)} 只")
        return candidates

    # ================================================================
    # 策略2: 热点 + 新闻交叉验证
    # ================================================================

    def step2_filter(self, s1_candidates, check_heat=True, check_news=True):
        """
        策略2: 对策略1候选股进行热点板块 + 新闻利好分类
        """
        print(f"\n{'='*60}")
        print(f"  策略2: 热点+新闻交叉验证")
        print(f"{'='*60}")

        s2_candidates = []
        s1_codes = {c['code'] for c in s1_candidates}

        # 1. 人气榜交叉
        heat_map = {}
        if check_heat:
            from hot_rank_collector import get_hot_stocks_cross_check
            try:
                heat_map = get_hot_stocks_cross_check(list(s1_codes), days=14, min_days=1)
                print(f"  人气榜命中: {len(heat_map)} 只")
            except Exception as e:
                print(f"  ⚠️ 人气榜查询失败: {e}")

        # 2. 持续热门板块
        hot_keywords = set()
        try:
            from hot_rank_collector import get_sustained_hot_boards
            boards = get_sustained_hot_boards(days=14, min_appear_days=3, top_n=30)
            for b in boards:
                hot_keywords.update(b['board_name'].split(','))
        except Exception:
            pass

        # 3. 对每只候选股打分
        for c in s1_candidates:
            code = c['code']
            bonus = 0
            reasons = []

            # 人气榜加分
            if code in heat_map:
                h = heat_map[code]
                heat_bonus = min(h['appear_days'] * 3, 10)
                bonus += heat_bonus
                reasons.append(f"人气榜在榜{h['appear_days']}天 +{heat_bonus}")

            # 板块热门加分
            name = c['name']
            matched_kw = [kw for kw in hot_keywords if kw in name]
            if matched_kw:
                bonus += 5
                reasons.append(f"热门板块 +5")

            c['s2_bonus'] = bonus
            c['s2_reasons'] = reasons
            s2_candidates.append(c)

        # 4. 按策略2加权分排序
        s2_candidates.sort(key=lambda x: x['s2_bonus'], reverse=True)

        # 5. 新闻利好分类（对TOP结果，减少API调用）
        if check_news and s2_candidates:
            print(f"\n  新闻利好分类（TOP 30）...")
            try:
                from news_sentiment_analyzer import NewsCategorizer
                import akshare as ak

                for i, c in enumerate(s2_candidates[:30]):
                    try:
                        clean_code = c['code'].replace('.SH', '').replace('.SZ', '')
                        df = ak.stock_news_em(symbol=clean_code)
                        if df is None or len(df) == 0:
                            continue

                        news_list = []
                        for _, r in df.head(15).iterrows():
                            title = str(r.get('新闻标题', '') or '')
                            if title:
                                news_list.append({'title': title})

                        if news_list:
                            top_cat, cat_scores, summary = NewsCategorizer.summarize_news(news_list)
                            bonus = NewsCategorizer.get_benefit_bonus(top_cat, cat_scores)
                            c['news_category'] = top_cat
                            c['news_summary'] = summary
                            c['news_bonus'] = bonus
                            c['s2_bonus'] += bonus

                        time.sleep(0.3)
                    except Exception:
                        pass
            except Exception as e:
                print(f"  ⚠️ 新闻分析失败: {e}")

        # 重新排序
        s2_candidates.sort(key=lambda x: x['s2_bonus'], reverse=True)

        # 输出TOP
        top_n = min(20, len(s2_candidates))
        print(f"\n  策略2候选 TOP {top_n}:")
        for i, c in enumerate(s2_candidates[:top_n], 1):
            news_info = f" 利好:{c.get('news_category', '未查')}" if check_news else ""
            print(f"  {i:>2}. {c['code']} {c['name']:<10} "
                  f"涨{c['rise_pct']:+.1f}% 量比{c['vol_ratio']:.1f} "
                  f"热度+{c['s2_bonus']:.0f}{news_info}")

        print(f"  策略2总计: {len(s2_candidates)} 只")
        return s2_candidates

    def _fetch_daily_arrays(self, code):
        """获取 closes 和 volumes 数组，供形态识别使用"""
        conn = self._db()
        c = conn.cursor()
        try:
            c.execute("""
                SELECT close, volume, adj_factor FROM daily_info_tbl
                WHERE code = %s ORDER BY tradedate ASC
            """, (code,))
            rows = c.fetchall()[-120:]
            closes = [float(r[0]) * float(r[2] or 1) for r in rows]
            volumes = [float(r[1]) for r in rows]
            return closes, volumes
        finally:
            c.close()
            conn.close()

    # ================================================================
    # 策略3: 综合评分 + 基本面 + 人工提示
    # ================================================================

    def step3_score(self, s2_candidates, top_n=10):
        """
        策略3: 综合评分排序
        - smart_screener 技术面+题材评分
        - fundamental_analyzer 基本面分析
        - 人工判断 checklist 提示
        """
        print(f"\n{'='*60}")
        print(f"  策略3: 综合评分 + 基本面 + 人工提示")
        print(f"{'='*60}")

        results = []

        for c in s2_candidates:
            code = c['code']
            name = c['name']

            # smart_screener 指标
            try:
                conn = self._db()
                cur = conn.cursor()
                cur.execute("""
                    SELECT tradedate, close, volume FROM daily_info_tbl
                    WHERE code = %s ORDER BY tradedate DESC LIMIT 60
                """, (code,))
                rows = cur.fetchall()
                cur.close()
                conn.close()

                if len(rows) < 20:
                    continue

                closes = [float(r[1]) for r in rows[::-1]]
                volumes = [float(r[2]) for r in rows[::-1]]
                current = closes[-1]

                ma5 = self._ma(closes, 5)
                ma10 = self._ma(closes, 10)
                ma20 = self._ma(closes, 20)
                ma30 = self._ma(closes, 30) if len(closes) >= 30 else ma20

                tech_score = 0
                tech_reasons = []

                # 均线
                if ma5 > ma10 > ma20:
                    tech_score += 20
                    tech_reasons.append('多头排列')
                elif ma5 > ma20:
                    tech_score += 12
                    tech_reasons.append('短多')

                dist_ma20 = (current / ma20 - 1) * 100
                if 0 < dist_ma20 < 10:
                    tech_score += 10
                    tech_reasons.append(f'MA20+{dist_ma20:.0f}%')
                elif -3 < dist_ma20 < 0:
                    tech_score += 8
                    tech_reasons.append('回踩MA20')

                # 量能
                vol5 = sum(volumes[-5:]) / 5
                vol10 = sum(volumes[-10:-5]) / 5 if len(volumes) >= 10 else vol5
                if vol5 > vol10 * 1.3:
                    tech_score += 10
                    tech_reasons.append('放量')
                elif vol5 > vol10 * 0.8:
                    tech_score += 5

                # 市值估计
                if current > 100:
                    tech_score += 5
                elif current > 30:
                    tech_score += 3

                # 20日涨幅
                chg_20d = 0
                if len(closes) >= 21:
                    chg_20d = (closes[-1] - closes[-21]) / closes[-21] * 100

                # 终极评分 = 技术分 + 策略2热度 + 基本面分
                final_score = tech_score + c.get('s2_bonus', 0)

                results.append({
                    'code': code,
                    'name': name,
                    'price': round(current, 2),
                    'score': round(final_score, 1),
                    'tech_score': tech_score,
                    's2_bonus': c.get('s2_bonus', 0),
                    'rise_pct': c['rise_pct'],
                    'vol_ratio': c['vol_ratio'],
                    'chg_20d': round(chg_20d, 2),
                    'tech_reasons': tech_reasons,
                    's2_reasons': c.get('s2_reasons', []),
                    'news_category': c.get('news_category', ''),
                    'ma5': round(ma5, 2),
                    'ma10': round(ma10, 2),
                    'ma20': round(ma20, 2),
                    'ma30': round(ma30, 2),
                })
            except Exception as e:
                print(f"  ⚠️ {code} 评分失败: {e}")

        # 排序
        results.sort(key=lambda x: x['score'], reverse=True)

        # 尝试添加基本面分析
        print(f"\n  基本面分析（对TOP 10）...")
        try:
            from fundamental_analyzer import FundamentalAnalyzer
            fa = FundamentalAnalyzer()
            for r in results[:10]:
                try:
                    funda = fa.analyze(r['code'])
                    r['funda_score'] = funda.get('score', 0)
                    r['funda_rating'] = funda.get('rating_label', '未知')
                    r['score'] += r['funda_score'] * 0.1  # 基本面加权10%
                except Exception:
                    r['funda_score'] = 0
                    r['funda_rating'] = '未查'
        except Exception:
            pass

        # 重新排序
        results.sort(key=lambda x: x['score'], reverse=True)

        # 输出
        print(f"\n{'='*70}")
        print(f"  🎯 最终候选 TOP {top_n}")
        print(f"{'='*70}")

        for i, r in enumerate(results[:top_n], 1):
            funda_str = f" 基本:{r.get('funda_rating','')}" if r.get('funda_rating') else ""
            print(f"\n  #{i} {r['name']} ({r['code']})  总分:{r['score']:.0f}")
            print(f"      价格:{r['price']:.2f}  "
                  f"涨:{r['rise_pct']:+.1f}% 量比:{r['vol_ratio']:.1f} 20日:{r['chg_20d']:+.1f}%")
            print(f"      技术: {' | '.join(r['tech_reasons'])}  "
                  f"MA5={r['ma5']:.1f} MA10={r['ma10']:.1f} MA20={r['ma20']:.1f}")
            if r['s2_reasons']:
                print(f"      热度: {' | '.join(r['s2_reasons'])}{funda_str}")
            if r.get('news_category') and r['news_category'] != '未查':
                print(f"      利好: {r['news_category']}")

            # --- 自动分析模块 ---

            # 1. 量价形态
            try:
                from pattern_recognition import PatternRecognizer
                pr = PatternRecognizer()
                closes_arr, volumes_arr = self._fetch_daily_arrays(r['code'])
                patterns = pr.analyze(closes_arr, volumes_arr)
                r['patterns'] = patterns
            except Exception:
                r['patterns'] = None

            # 2. 逻辑验证
            try:
                from logic_validator import LogicValidator
                lv = LogicValidator()
                logic_result = lv.validate(r['code'], r['name'], r.get('sector', ''),
                                          news_list=[{'title': r.get('news_summary', '')}])
                r['logic'] = logic_result
            except Exception:
                r['logic'] = None

            # 3. 仓位建议
            try:
                from position_sizer import PositionSizer
                ps = PositionSizer()
                # 用策略得分估算胜率
                estimated_prob = min(0.85, r['score'] / 120)
                payoff = 0.20 / 0.08  # 止盈20% / 止损8%
                pos_result = ps.calc_position(estimated_prob, payoff,
                                               stop_loss_pct=0.08, target_profit_pct=0.20)
                r['position'] = pos_result
            except Exception:
                r['position'] = None

            # --- 打印自动分析结果 ---

            # 形态
            patterns = r.get('patterns')
            if patterns:
                from pattern_recognition import PatternRecognizer
                pr_print = PatternRecognizer()
                pr_print.print_report(patterns, r['code'])

            # 逻辑
            logic = r.get('logic')
            if logic:
                from logic_validator import LogicValidator
                lv_print = LogicValidator()
                lv_print.print_report(logic, r['code'], r['name'])

            # 仓位
            pos = r.get('position')
            if pos:
                from position_sizer import PositionSizer
                ps_print = PositionSizer()
                ps_print.print_report(pos, r['name'], r['code'], r['price'])

            # 人工checklist提示
            print(f"      ┌─ 人工核验 ─────────────────────────────")
            print(f"      │ □ 板块政策面: 有无国家级政策支持？")
            print(f"      │ □ 产业逻辑: 上涨是概念炒作还是产业趋势？")
            print(f"      │ □ 个股质地: 核心标的 or 蹭概念？")
            print(f"      │ □ 新闻风险: 有无减持/问询/业绩暴雷？")
            print(f"      │ □ 20日涨幅: {r['chg_20d']:.1f}% {'⚠️追高风险' if r['chg_20d'] > 60 else '✓合理区间' if r['chg_20d'] < 30 else '关注涨幅'}")
            print(f"      └──────────────────────────────────────────")

        return results[:top_n]

    # ================================================================
    # 完整流水线
    # ================================================================

    def run(self, steps='1,2,3', top_n=10, step1_min_ampl=30):
        """执行完整策略流水线"""
        print(f"\n{'='*70}")
        print(f"  SmarkStock 策略串联引擎")
        print(f"  时间: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}")
        print(f"  步骤: {steps} | TOP: {top_n}")
        print(f"{'='*70}")

        steps_list = [s.strip() for s in steps.split(',')]

        s1_candidates = []
        s2_candidates = []
        final_results = []

        # Step 1
        if '1' in steps_list:
            s1_candidates = self.step1_screen(min_vol_ratio=1.5, min_rise_pct=3.0)
            if not s1_candidates:
                print("\n  ⚠️ 策略1无候选股，终止")
                return []
            if '2' not in steps_list:
                final_results = s1_candidates
        else:
            s1_candidates = []

        # Step 2
        if '2' in steps_list:
            if not s1_candidates and '1' in steps_list:
                print("\n  ⚠️ 策略1无候选, 策略2无法执行")
                return []
            s2_candidates = self.step2_filter(
                s1_candidates,
                check_heat=True,
                check_news=True,
            )
            if not s2_candidates:
                print("\n  ⚠️ 策略2无候选股，终止")
                return []
            if '3' not in steps_list:
                final_results = s2_candidates
        else:
            s2_candidates = []

        # Step 3
        if '3' in steps_list:
            pool = s2_candidates if s2_candidates else s1_candidates
            if not pool:
                print("\n  ⚠️ 无候选池输入, 策略3无法执行")
                return []
            final_results = self.step3_score(pool, top_n=top_n)

        return final_results


def main():
    parser = argparse.ArgumentParser(description='策略串联引擎')
    parser.add_argument('--steps', type=str, default='1,2,3',
                        help='执行的步骤: 1,2,3 或 1,2 等')
    parser.add_argument('--top', type=int, default=10,
                        help='输出前N名')
    parser.add_argument('--amplitude', type=int, default=30,
                        help='策略1最低振幅阈值')
    args = parser.parse_args()

    pipeline = StrategyPipeline()
    pipeline.run(
        steps=args.steps,
        top_n=args.top,
        step1_min_ampl=args.amplitude,
    )


if __name__ == '__main__':
    main()
