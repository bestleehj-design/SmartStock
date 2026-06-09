#!/bin/bash
# 每日盘前综合分析定时任务 - 由 crontab 调用
# 用法: ./run_daily_news.sh              # 分析今日
#       ./run_daily_news.sh 2026-05-29   # 分析指定日期
#
# Cron 建议: 工作日上午 8:00 执行
#   0 8 * * 1-5 /Users/alessa.tang/Develop/work/smark_stock/SmarkStock/run_daily_news.sh

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

PYTHON="/Users/alessa.tang/Develop/work/mfc_stock/venv/bin/python"
LOG_DIR="$SCRIPT_DIR/logs"
LOG_DATE="$(date +%Y%m%d)"
LOG_FILE="$LOG_DIR/morning_$LOG_DATE.log"

mkdir -p "$LOG_DIR"

date '+%Y-%m-%d %H:%M:%S' >> "$LOG_FILE"
echo "每日盘前综合分析开始" >> "$LOG_FILE"

"$PYTHON" -u "$SCRIPT_DIR/morning_analysis.py" "$@" >> "$LOG_FILE" 2>&1

date '+%Y-%m-%d %H:%M:%S 完成' >> "$LOG_FILE"
