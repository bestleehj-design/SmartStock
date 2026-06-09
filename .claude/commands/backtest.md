# /backtest — 回溯验证 Claude 的历史分析

回填未来收益数据，生成准确率验证报告。

**用法:** `/backtest` 或直接说「请回溯」

**执行逻辑:**
1. 运行 `python3 verify_analysis.py --backfill` 回填所有未验证记录的收益
2. 运行 `python3 verify_analysis.py --report` 生成准确率报告
3. 总结关键发现：按操作类型/信心等级的准确率、最佳最差判断、优化建议

**数据来源:** `claude_trades` 表 + 本地 MySQL `daily_info_tbl`

**什么时候用:**
- 每周回溯一次，看过去一周的判断准确率
- 优化 `smart_screener.py` 的评分权重时参考
