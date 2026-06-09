#!/bin/bash
# 每日主题分析定时任务 - 由 crontab 调用
# 用法: ./run_daily_theme.sh          # 分析最新交易日
#       ./run_daily_theme.sh 5        # 回填最近5天

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

PYTHON="python3"
LOG_DIR="$SCRIPT_DIR/logs"
LOG_DATE="$(date +%Y%m%d)"
LOG_FILE="$LOG_DIR/theme_$LOG_DATE.log"

mkdir -p "$LOG_DIR"

date '+%Y-%m-%d %H:%M:%S' >> "$LOG_FILE"
echo "每日主题分析开始" >> "$LOG_FILE"

"$PYTHON" -u "$SCRIPT_DIR/src/skills/daily_theme_job.py" "$@" >> "$LOG_FILE" 2>&1

date '+%Y-%m-%d %H:%M:%S 完成' >> "$LOG_FILE"
