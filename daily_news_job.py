# -*- coding: utf-8 -*-
"""
每日新闻舆情分析定时任务
每天早上开盘前自动抓取持仓股票最新新闻，进行情感分析并入库

用法:
  python daily_news_job.py                  # 分析最新交易日
  python daily_news_job.py 2026-05-29       # 分析指定日期
  python daily_news_job.py --backfill 10    # 回填最近10个交易日
"""
import sys
import os
import datetime
import traceback

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
os.chdir(SCRIPT_DIR)
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)


def main():
    from newstocklib import initMySQL
    from news_sentiment_analyzer import NewsSentimentAnalyzer

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
    print(f"# 每日新闻舆情分析定时任务")
    print(f"# 运行时间: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"# 目标日期: {target_date_str}")
    if backfill_days:
        print(f"# 模式: 历史回填 ({backfill_days}天)")
    print(f"{'#'*60}")

    # 初始化分析器
    analyzer = NewsSentimentAnalyzer()

    try:
        if backfill_days:
            # 历史回填模式
            for i in range(backfill_days):
                fill_date = target_date - datetime.timedelta(days=i)
                print(f"\n--- 回填第 {i+1}/{backfill_days} 天: {fill_date.strftime('%Y-%m-%d')} ---")
                try:
                    analyzer.run_for_date(fill_date)
                except Exception as e:
                    print(f"  [ERROR] 回填 {fill_date.strftime('%Y-%m-%d')} 失败: {e}")
                    traceback.print_exc()
        else:
            # 单日分析模式
            analyzer.run_for_date(target_date)

    except Exception as e:
        print(f"\n!!! 分析出错: {e}")
        traceback.print_exc()
        raise
    finally:
        analyzer.cleanup()

    print(f"\n{'#'*60}")
    print(f"# 任务完成: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'#'*60}")


if __name__ == '__main__':
    main()
