# SmarkStock 优化路线图

> 版本: v2.1 | 更新: 2026-06-12
> 
> 基于实际工程审计结果编写

---

## 一、总体目标

| # | 目标 | 说明 |
|---|------|------|
| A | **配置统一化** | 20 个文件硬编码 → 全部统一 `from data.config import DB_CONFIG` |
| B | **私有数据隔离** | 本地配置本地放，后续按账户独立 |
| C | **统一持仓来源** | 4 套不一致的持仓 → 统一从 `trading_plan.md` 读取 |
| D | **自动化运行** | 本地 crontab 自动跑，不用手动操作 |
| E | **消息推送** | 分析结果自动发到微信群/企微 |
| F | **体验/安全优化** | 日志、SQL注入修复、连接标准化 |
| G | **云部署** | 数据库 + 定时任务迁移到内网服务器 |

---

## 二、实施阶段

---

### 🔴 第一阶段：基础设施清洗（高优先级，本周可做）

---

#### 1. 配置统一管理

**现状：** `data/config.example.py` 已经是正确的模板模式。但 **20 个文件各自硬编码了独立的 `DB_CONFIG = {...}`**，只有 4 个文件正确地从 `data.config` 导入。

**已正确导入的文件（不动）：**
- `data/newstocklib.py:20` — `from data.config import DB_CONFIG`
- `theme/theme_analyzer.py:18` — 同上
- `theme/leader_analyzer.py:18` — 同上
- `data/new_get_all_stock.py:20` — `from data.config import TUSHARE_TOKEN`

**需修复的文件清单（20 个）：**

| 文件 | 行号 | 操作 |
|------|------|------|
| `skills/morning_analysis.py` | 32-41 | 删硬编码，加 `from data.config import DB_CONFIG` |
| `skills/close_analysis.py` | 15-24 | 同上 |
| `skills/bounce_screener.py` | 37-46 | 同上 |
| `skills/zhaban_check.py` | 18-27 | 同上 |
| `skills/stock_check.py` | 24-33 | 同上 |
| `skills/log_analysis.py` | 17-26 | 同上 |
| `skills/log_session.py` | 17-26 | 同上 |
| `skills/recall_log.py` | 12-21 | 同上 |
| `skills/verify_analysis.py` | 20-29 | 同上 |
| `skills/rule_backtest.py` | 44-53 | 同上 |
| `screener/smart_screener.py` | 38-47 | 同上 |
| `screener/uptrend_model.py` | 33-42 | 同上 |
| `screener/logic_validator.py` | 19-28 | 同上 |
| `screener/position_sizer.py` | 25-34 | 同上 |
| `screener/pattern_recognition.py` | 21-30 | 同上 |
| `screener/strategy_pipeline.py` | 31-40 | 同上 |
| `screener/hot_stock_screener.py` | 23-32 | 同上 |
| `theme/hot_rank_collector.py` | 27-36 | 同上 |
| `ml/generate_training_data.py` | 38-47 | 同上 |
| `data/newstocklib.py` | 23-32 | 只保留 try 块中 import，删除 except 中的回退硬编码（22-32 行） |

**步骤：**

- [ ] 1.1 逐个文件删除独立的 `DB_CONFIG = {...}` 定义
- [ ] 1.2 每个文件加 `from data.config import DB_CONFIG`（注意项目根目录需在 sys.path 中）
- [ ] 1.3 `newstocklib.py` 删除 `except ImportError` 里的回退硬编码（22-32 行），没有 config.py 就报错，不要静默
- [ ] 1.4 逐个文件运行测试连接

---

#### 2. 私有数据独立存储

**现状：** `data/config.py`（含真实密码和 token）已在 `.gitignore` 中，但所有私有配置挤在一个文件里。

- [ ] 2.1 确认 `.gitignore` 已排除 `src/data/config.py`（已有，第 5 行）
- [ ] 2.2 `config.example.py` 保持为模板，后续新增推送 webhook URL 等字段也在模板里加注释
- [ ] 2.3 **远期多账户**：通过环境变量 `SMARKSTOCK_PROFILE` 切换配置文件名

---

#### 3. 统一持仓配置

**现状：** 存在 4 个不同的持仓来源，互不同步：

| 来源 | 内容 | 问题 |
|------|------|------|
| `morning_analysis.py:55` | 10 只（7A + 3HK） | 硬编码 |
| `close_analysis.py:25` | 7 只 A 股（含京东方） | 硬编码，与 morning 不一致 |
| `live_monitor.py` | 解析 `trading_plan.md` | ✅ 好方案，但 trading_plan.md 还不存在 |
| `position_monitor.py` | 读取 `selected_stocks` 表 | 策略追踪，不冲突 |

**方案：** `trading_plan.md` 作为唯一权威来源，各脚本改读此文件

**trading_plan.md 标准格式：**

```markdown
# 交易计划

## 当前持仓

| 代码 | 名称 | 成本 | 持有数 | 止盈 | 止损 | 分级 | 备注 |
|------|------|------|--------|------|------|------|------|
| 600584 | 长电科技 | 78.46 | 500 | 88.19 | 70.30 | 1 | T+0 标的 |

## T+0 计划

| 代码 | 名称 | 底仓数 | 可用做多 | 可用做空 |
|------|------|--------|---------|---------|
| 600584 | 长电科技 | 500 | 100 | 200 |

## 卖出计划

| 代码 | 名称 | 计划 | 原因 |
|------|------|------|------|
| 688981 | 中芯国际A | 趁反弹清仓 | 降仓位 |
```

**步骤：**

- [ ] 3.1 创建 `trading_plan.md` 初始模板（从用户实际持仓填写）
- [ ] 3.2 编写 `src/data/holdings.py` 工具模块：`load_holdings_from_md()` 解析 trading_plan.md
- [ ] 3.3 改造 `morning_analysis.py`：从 `trading_plan.md` 读取持仓，删除硬编码 HOLDINGS
- [ ] 3.4 改造 `close_analysis.py`：同上
- [ ] 3.5 改造 `stock_check.py`、`bounce_screener.py` 等：默认分析持仓票
- [ ] 3.6 `close_analysis.py` 收盘后自动更新 `trading_plan.md` 中的当日盈亏

---

### 🟡 第二阶段：自动化运行 + 消息推送（中优先级，下周）

---

#### 4. 本地定时任务

**现状：** 目前所有操作手动跑

- [ ] 4.1 修复 `scripts/run_daily_news.sh`：
  - 把 `/Users/alessa.tang/.../venv/bin/python` 改为本机 `python3`
  - 修改路径为当前仓库实际路径
- [ ] 4.2 本机写 crontab：
  ```cron
  # 盘前 8:00 综合分析
  0 8 * * 1-5 cd /Users/spark/works/GitHup/stock/SmarkStock_share && python3 src/skills/morning_analysis.py >> logs/morning.log 2>&1
  
  # 收盘 15:30 收盘分析
  30 15 * * 1-5 cd /Users/spark/works/GitHup/stock/SmarkStock_share && python3 src/skills/close_analysis.py >> logs/close.log 2>&1
  ```
- [ ] 4.3 验证：查看日志文件确认输出正常

---

#### 5. 消息推送（企业微信/微信群）

**现状：** 完全没有推送代码，分析结果只在终端输出

**步骤：**

- [ ] 5.1 新建 `src/notify/` 推送模块：

```
src/notify/
├── __init__.py
├── wecom.py       ← 企业微信机器人推送
├── formatter.py   ← 格式化分析结果为推送文本
└── sender.py      ← 发送调度（分段、重试、限频）
```

- [ ] 5.2 `wecom.py` 核心实现：

```python
import requests

def send_wecom(message: str, webhook_url: str, msg_type: str = 'markdown'):
    """发送消息到企业微信机器人"""
    payload = {"msgtype": msg_type, msg_type: {"content": message}}
    resp = requests.post(webhook_url, json=payload, timeout=10)
    resp.raise_for_status()
```

- [ ] 5.3 `formatter.py` 格式化各场景推送内容：

| 触发 | 内容 | 推送时机 |
|------|------|---------|
| 盘前分析完成 | 美股/港股走势 + 综合判断 + T+0 计划摘要 | 8:05 |
| 收盘分析完成 | 大盘复盘 + 持仓涨跌 + 明日计划 | 15:35 |
| 数据拉取失败 | 错误摘要 + 影响范围 | 实时 |
| 数据库断连 | 告警 | 实时 |

- [ ] 5.4 webhook URL 存在 `data/config.py` 中，不提交 git
- [ ] 5.5 `config.example.py` 新增推送配置占位：
  ```python
  # 企业微信推送（可选）
  WECOM_WEBHOOK_URL = ''  # 填入机器人 webhook 地址
  ```

---

#### 6. 数据新鲜度保证

**现状：** 手动跑 `/update`，忘跑就用旧数据

- [ ] 6.1 各脚本启动时检查 `daily_info_tbl` 最新交易日
- [ ] 6.2 如果数据早于 2 个交易日，在报告中标注 `⚠️ 数据滞后` 提示
- [ ] 6.3 crontab 跑完数据更新后发推送确认

---

### 🟢 第三阶段：体验/安全优化（低优先级，有空做）

---

#### 7. SQL 安全改造

**现状：** 大量 f-string 拼接 SQL

- [ ] 7.1 审计 `newstocklib.py` 中所有公共数据库函数：`check_if_X_record_exist`、`insert_into_tbl_all_values`、`delete_data_by_date`
- [ ] 7.2 改为参数化查询（值部分用 `%s` 占位）
- [ ] 7.3 表名/列名做白名单校验（不适用参数化的部分）

---

#### 8. 数据库连接标准化

**现状：** 23 个文件用 `pymysql` + 1 个文件用 `mysql.connector`（newstocklib.py）

- [ ] 8.1 `newstocklib.py` 的 `initMySQL()` 改为用 `pymysql`，消除 `mysql-connector-python` 依赖
- [ ] 8.2 统一错误处理：连接失败统一抛异常，不静默

---

#### 9. 日志系统

**现状：** 全项目 `print()` 输出

- [ ] 9.1 配置 `logging` 模块，输出到 `logs/` 目录
- [ ] 9.2 日志级别：日常 INFO / 错误 ERROR
- [ ] 9.3 格式：`[2026-06-12 09:29:01] [morning_analysis] INFO 美股数据拉取成功`

---

#### 10. 脚本启动入口统一

- [ ] 10.1 新建 `main.py` 作为统一入口：
  ```
  python3 main.py morning          # 同 /morning
  python3 main.py close            # 同 /close
  python3 main.py check 600584     # 同 /check 600584
  ```

---

#### 11. 盘中监控完善

- [ ] 11.1 持仓票盘中异动（跌幅 > 3%、放量破 MA20）主动推送到企微
- [ ] 11.2 阈值可配（`config.py` 中定义）

---

### 🔵 第四阶段：云部署（最后做）

---

#### 12. 数据库迁移到内网服务器

**现状：** MySQL 在本地 Mac 上，关机断网就不可用。内网已有服务器 `10.10.65.11`。

> ⏳ 先把前面 11 项做完后再搞这个。在此之前本地开发测试不受影响。

**步骤：**

- [ ] 12.1 确认服务器 `10.10.65.11` 已安装 MySQL 8.0+
- [ ] 12.2 如未安装 MySQL，在服务器上安装
- [ ] 12.3 本地 `mysqldump` 导出 gp2 库
- [ ] 12.4 将备份文件传到服务器并导入
- [ ] 12.5 创建专用数据库用户（不用 root）
- [ ] 12.6 改 `data/config.py` 中 `DB_CONFIG.host` 为 `10.10.65.11`
- [ ] 12.7 验证所有脚本连接正常

---

#### 13. 定时任务迁移到服务器

**现状：** 第二阶段搞了本地 crontab，现在迁移到服务器

- [ ] 13.1 服务器 git clone 项目代码
- [ ] 13.2 服务器创建 `config.py`
- [ ] 13.3 服务器写 crontab（参考第二阶段配置）
- [ ] 13.4 本地 crontab 停掉，避免重复跑
- [ ] 13.5 验证服务器上 akshare 板块数据可正常获取（服务器 IP 归属国内）

---

#### 14. 数据库备份

- [ ] 14.1 服务器 crontab 每日凌晨 `mysqldump`
- [ ] 14.2 保留最近 7 天备份

---

#### 15. Web 看板（远期）

- [ ] 15.1 基于已有 Flask 架构，加一个看板页面
- [ ] 15.2 展示：持仓一览 + 大盘状态 + 信号摘要

---

## 三、优先级总览

```
阶段一：基础设施清洗（🔴 本周）       阶段二：自动化（🟡 下周）         阶段三：优化（🟢 有空做）
────────────────────────────        ──────────────────────          ────────────────────
□ 1. 配置统一（20个文件修硬编码）       □ 4. 本地定时任务                  □ 7. SQL安全改造
□ 2. 私有数据独立存储                 □ 5. 消息推送（企微机器人）         □ 8. 数据库连接标准化
□ 3. 统一持仓配置（trading_plan.md）   □ 6. 数据新鲜度检查                □ 9. 日志系统
                                                                        □ 10. main.py统一入口
                                                                        □ 11. 盘中监控完善

阶段四：云部署（🔵 最后）
────────────────────────────
□ 12. 数据库迁移到服务器
□ 13. 定时任务迁移到服务器
□ 14. 数据库备份
□ 15. Web 看板
```

---

## 四、现有资源（不需要重复造轮子）

审计确认以下已存在，计划中不会重复列出：

| 资源 | 位置 | 状态 |
|------|------|------|
| `config.example.py` 模板 | `src/data/config.example.py` | ✅ 已有，做模板用 |
| `config.py`（含真实密码） | `src/data/config.py` | ✅ 已在 `.gitignore` |
| 19 张表（含 claude_trades、sox_index_tbl） | `sql/schema.sql` | ✅ 已定义 |
| 迁移系统（schema_migrations） | `sql/migrations/` + `scripts/migrate_db.sh` | ✅ 已可用 |
| 盘前分析 crontab 脚本 | `scripts/run_daily_news.sh` | ✅ 已有但路径需要修 |
| 主题分析 crontab 脚本 | `scripts/run_daily_theme.sh` | ✅ 已有 |
| `live_monitor.py` 读 trading_plan.md | `src/skills/live_monitor.py` | ✅ 好方案，推广 |
| Flask 项目框架 | 根目录 | ✅ 已有，Web看板可直接用 |
