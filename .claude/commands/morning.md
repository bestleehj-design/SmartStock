# /morning — 每日盘前综合分析

运行盘前综合分析报告，自动拉取隔夜美股、港股走势、板块轮动、持仓新闻、T+0 交易计划。

**用法:** `/morning`

**可选:** `/morning 2026-06-05` — 分析指定日期

**执行逻辑:**
1. 运行 `python3 src/skills/recall_log.py` 回调昨日判断（加载上次的决策和逻辑）
2. 运行 `python3 src/skills/morning_analysis.py` 获取全量数据
3. 阅读 `trading_plan.md` 获取最新持仓和操作计划
4. 总结关键结论：美股/港股方向、板块资金流向、持仓风险信号、综合判断
5. 输出长电科技 T+0 操作计划（支撑/阻力/三种情景）
6. 对比昨日判断和今日盘面，标注已验证/证伪的结论

**数据来源:** akshare（东方财富、新浪财经）、本地 MySQL 数据库

**依赖:**
- MySQL 服务需启动（`brew services start mysql`）
- 需在境内网络或 VPN 环境（部分板块接口对境外 IP 限制）
