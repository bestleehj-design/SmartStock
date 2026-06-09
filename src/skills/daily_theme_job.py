# -*- coding: utf-8 -*-
"""
每日主题分析定时任务
每天收盘后自动运行: 主线题材分析 + 龙头票识别 + 长期分析 + 入库
用法:
  python daily_theme_job.py                  # 分析最新交易日
  python daily_theme_job.py 2026-05-29       # 分析指定日期
  python daily_theme_job.py --backfill 10    # 回填最近10个交易日
"""
import sys
import os
import datetime
import traceback

# Ensure src/ directory is in sys.path for package imports
import sys, os
_SRC_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _SRC_DIR not in sys.path:
    sys.path.insert(0, _SRC_DIR)


LOG_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '..', 'logs')
os.makedirs(LOG_DIR, exist_ok=True)


def main():
    from data.newstocklib import initMySQL
    from theme.theme_analyzer import ThemeAnalyzer
    from theme.leader_analyzer import LeaderAnalyzer

    # 解析参数
    backfill_days = None
    target_date = None

    for i, arg in enumerate(sys.argv):
        if arg == '--backfill' and i + 1 < len(sys.argv):
            backfill_days = int(sys.argv[i + 1])
        elif arg not in ('--backfill',) and not arg.startswith('--') and i > 0:
            try:
                backfill_days = int(arg)
                if backfill_days <= 0:
                    target_date = arg
                    backfill_days = None
            except ValueError:
                target_date = arg

    # 确定目标日期
    if target_date is None:
        db = initMySQL()
        cursor = db.cursor()
        cursor.execute('SELECT MAX(tradedate) FROM daily_info_tbl')
        target_date = cursor.fetchone()[0]
        cursor.close()
        db.close()

    if isinstance(target_date, datetime.date):
        target_date_str = target_date.strftime('%Y-%m-%d')
    elif isinstance(target_date, datetime.datetime):
        target_date_str = target_date.strftime('%Y-%m-%d')
        target_date = target_date.date()
    else:
        target_date_str = str(target_date)
        target_date = datetime.datetime.strptime(target_date_str, '%Y-%m-%d').date()

    print(f"\n{'#'*60}")
    print(f"# 每日主题分析定时任务")
    print(f"# 运行时间: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"# 目标日期: {target_date_str}")
    if backfill_days:
        print(f"# 模式: 历史回填 ({backfill_days}天)")
    print(f"{'#'*60}")

    # 初始化分析器
    ta = ThemeAnalyzer()

    try:
        if backfill_days:
            # 历史回填模式
            ta.backfill_history(target_date, days=backfill_days)
        else:
            # 单日分析模式
            # 1. 每日主线分析
            daily_results = ta.analyze_daily_themes(target_date)

            if not daily_results:
                print(f"\n[{target_date_str}] 当日无涨停活动, 跳过")
                return

            # 2. 主线题材筛选
            main_themes = ta.get_main_themes(daily_results, top_n=3, min_score=20)

            # 3. 龙头票识别
            la = LeaderAnalyzer(theme_analyzer=ta)
            all_leaders = {}
            if main_themes:
                all_leaders = la.get_all_leaders(main_themes, target_date)
            la.cleanup()

            # 4. 保存到数据库(含龙头信息)
            ta.save_to_db(target_date, daily_results, all_leaders)

            # 5. 长期分析(至少需要3天数据才运行)
            lt_results = ta.analyze_long_term_themes(target_date, lookback_days=20, min_active_days=2)
            if lt_results:
                lt_main, lt_emerging = ta.get_long_term_main_themes(
                    lt_results, top_n=5, min_active_days=3, min_avg_score=10
                )

                print(f"\n{'='*60}")
                print(f"长期主线题材总结")
                print(f"{'='*60}")

                if lt_main:
                    print(f"\n[持续主线]")
                    for i, t in enumerate(lt_main[:5], 1):
                        trend_icon = {'rising': u'↑', 'declining': u'↓', 'stable': u'→'}.get(t['trend_label'], '?')
                        print(f"  {i}. {t['theme_name']:16s} 长期分={t['long_term_score']:.1f} "
                              f"日均={t['avg_daily_score']:.1f} "
                              f"活跃={t['active_days']}/{t['total_days']}天 "
                              f"趋势={trend_icon}{t['trend_label']}")

                if lt_emerging:
                    print(f"\n[新兴主线(关注)]")
                    for i, t in enumerate(lt_emerging[:3], 1):
                        print(f"  {i}. {t['theme_name']:16s} 长期分={t['long_term_score']:.1f} "
                              f"日均={t['avg_daily_score']:.1f}")

            # 6. 打印当日总结
            print(f"\n{'='*60}")
            print(f"[{target_date_str}] 分析完成")
            print(f"{'='*60}")
            if main_themes:
                print(f"今日主线: {', '.join(t['theme_name'] for t in main_themes)}")
                for t in main_themes:
                    leaders = all_leaders.get(t['theme_code'], [])
                    if leaders:
                        print(f"  {t['theme_name']} 龙头: {', '.join(l[1] for l in leaders[:3])}")
            else:
                print("今日无明确主线题材")

    except Exception as e:
        print(f"\n!!! 分析出错: {e}")
        traceback.print_exc()
        raise
    finally:
        ta.cleanup()

    print(f"\n{'#'*60}")
    print(f"# 任务完成: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'#'*60}")


if __name__ == '__main__':
    main()
