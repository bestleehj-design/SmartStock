# /log — 存储今日分析结论

将今天对话中我做过的所有判断写入数据库，第二天可以回溯验证。

**用法:** `/log`

**执行逻辑:**
1. 回顾本次会话中的所有判断（买入/卖出/持有/等待建议）
2. 将每条判断格式化为: `code|action|thesis|stop|target|confidence|risk`
3. 运行 `python3 src/skills/log_session.py` 批量写入 `claude_trades` 表
4. 输出记录摘要

**备选用法:** `/log 2026-06-09` — 指定分析日期（默认今天）

**数据写入:** MySQL `claude_trades` 表

**何时使用:**
- 每天收盘后记录，形成交易日志
- 配合 `/recall` 和 `/backtest` 做持续优化
