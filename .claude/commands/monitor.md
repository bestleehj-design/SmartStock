# /monitor — 盘中实时监控持仓

用法: /monitor 或 说「监控持仓」

执行: python3 src/skills/live_monitor.py --plan --interval 10

输出: 每 N 秒刷新持仓价格 + 告警

告警类型:
- 🔴 止损触发 → 建议立即操作
- 🟡 MA20跌破 / 接近涨停 → 关注
- 🟢 放量 / 触及止盈 → 信号

选项:
- --plan          从 trading_plan.md 加载持仓
- --watch A,B,C   手动指定监控代码
- --interval N    轮询间隔(秒)，默认 10
- --silent        只在触发告警时打印

退出: Ctrl+C 打印汇总
