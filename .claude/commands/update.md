# /update — 全市场日线数据更新

从 Tushare 拉取全市场 A 股最新日K线数据入库。

**用法:** `/update`

**执行逻辑:**
1. 运行 `sudo python3 src/data/new_get_all_stock.py --no-hk`
2. 拉取今日全市场 A 股日线数据到 `daily_info_tbl`
3. 耗时约 3-10 分钟，需输入 sudo 密码

**何时使用:**
- 每天收盘后跑一次，保证数据最新
- 回溯验证前跑，确保 ret_Nd 能计算出准确收益
- `/close` 已自动更新持仓股日线，全市场管道用 `/update` 补全

**依赖:**
- Tushare token (已配置)
- sudo 权限
- 境内网络
