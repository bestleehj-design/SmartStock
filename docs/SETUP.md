# SmartStock — 量化股票分析系统

## 前置要求

| 组件 | 版本 | 安装方式 |
|------|------|----------|
| Python | 3.12+ | — |
| MySQL | 8.0+ | `brew install mysql` 或官网下载 |
| Git | — | `git clone` |

---

## 一、安装

```bash
# 1. 克隆仓库
git clone <repo-url>
cd SmartStock

# 2. 安装依赖
pip3 install -r requirements.txt

# 3. 启动 MySQL
brew services start mysql    # macOS
# 或: sudo systemctl start mysql  # Linux
```

---

## 二、数据库初始化

```bash
# 方式一：一键脚本
bash scripts/init_db.sh

# 方式二：手动执行
mysql -u root -p < sql/schema.sql   # 建库 + 19张表
```

> `sql/schema.sql` 是唯一权威的建表语句，包含全部 19 张表，由当前数据库直接导出。

---

## 三、配置文件

```bash
# 从模板创建配置
cp src/data/config.example.py src/data/config.py

# 编辑 config.py，填入你的:
#   - MySQL 密码
#   - Tushare API Token (从 https://tushare.pro 获取)
```

> `src/data/config.py` 已加入 `.gitignore`，不会提交到仓库。每个开发者自己维护。

---

## 四、拉取数据（首次）

```bash
# 全市场日线数据 + 股票基本信息
/update
# 或手动运行: python3 src/data/new_get_all_stock.py

# SOX 半导体指数历史数据
python3 -c "from src.skills.morning_analysis import update_sox_db; update_sox_db()"
```

数据拉取需要较长时间（全市场 A 股日 K），建议在盘中或收盘后执行。

---

## 五、验证

```bash
# 运行盘前综合分析（会自动检查数据）
/morning

# 如果看到持股新闻 + 美股/港股数据 + T+0 计划，说明一切正常
```

---

## 数据库结构有变动怎么办

两种场景，两种方式：

### 场景 A：还没建过库（全新安装）

```bash
mysql -u root -p < sql/schema.sql
```

### 场景 B：已经建过库（增量更新）

```bash
# 一键增量迁移（自动对比，只执行新的）
bash scripts/migrate_db.sh
```

**工作原理：**

```
sql/migrations/                      ← 迁移文件目录 (按编号顺序)
├── 000_init_migration_system.sql    ← 建迁移追踪表
├── 001_add_column_xxx.sql           ← 以后加字段/改结构的写这里
├── 002_new_table_yyy.sql
└── ...

schema_migrations 表                  ← 自动记录哪些已执行
├── 000 | 2026-06-11 10:00
├── 001 | 2026-06-15 14:30
└── ...
```

**作者侧 — 改表后如何让其他人同步：**

```bash
# 1. 在本地 MySQL 改表，测试通过

# 2. 把 ALTER TABLE / CREATE TABLE 写进迁移文件
cat > sql/migrations/003_add_xxx.sql << 'EOF'
ALTER TABLE daily_info_tbl ADD COLUMN new_field DOUBLE;
EOF

# 3. 同时更新 schema.sql（给新人用）
mysqldump -u root -p --no-data gp2 > sql/schema.sql

# 4. 提交
git add sql/migrations/ sql/schema.sql
git commit -m "新增 daily_info_tbl.new_field 字段"
git push
```

**使用者侧 — 拉代码后更新数据库：**

```bash
git pull
bash scripts/migrate_db.sh    # 自动跑新增的迁移文件
```

> `migrate_db.sh` 只执行尚未跑过的迁移，已执行的自动跳过，不会重复执行。

---

## 全部 Skill 一览

| 命令 | 功能 | 何时用 |
|------|------|--------|
| `/morning` | 盘前综合分析（美股/港股/板块/新闻/T+0） | 每天早晨 |
| `/close` | 盘后综合分析（量能/涨跌比/持仓表格） | 每天 15:00 后 |
| `/check <code>` | 单票快速分析 | 盘中随时 |
| `/zhaban <code>` | 涨停炸板四维分析 | 持仓涨停后开板时 |
| `/bounce` | 超跌反弹选股器 | 三大指数同步大跌日 |
| `/theme` | 市场主线题材分析 | 了解当前主线 |
| `/monitor` | 盘中实时监控持仓 | 盘中持续跟踪 |
| `/log` | 存储今日分析结论 | 收盘后 |
| `/recall` | 回调昨日判断 | 新会话开场 |
| `/backtest` | 回溯验证 & 选股分析 | 盘后/周末 |
| `/update` | 全市场日线数据更新 | 定期更新数据 |

---

## 每日标准工作流

### 盘前 (8:00-9:15)

```
/morning → 隔夜美股/港股 + 板块轮动 + 持仓新闻 + 综合判断 + T+0 计划
→ "今天大盘怎么看？我的持仓需要注意什么？"
→ 心里有数，不在盘中做第一个决策
```

### 盘中 (9:30-15:00)

```
10 点前只观察，不动手
/check <code> → 单票实时分析
问法："XX票现在什么情况？需要减仓吗？"
问法："分析下 XX 早上的盘面，主力意图是什么？"
```

### 收盘后 (15:00 后)

```
/close → 收盘量能/持仓表格更新到 trading_plan.md
/log  → 记录今日所有判断到 claude_trades 表
/backtest → 回填收益 + 判断准确率 + 选股器分析
```

---

## 核心原则

| 原则 | 说明 |
|------|------|
| 10 点前不操作 | 前 30 分钟是噪音，等方向确认 |
| 盘中不做卖出决策 | 规则9: 等收盘确认 MA20 站不站得回 |
| 放量破位 = 立刻走 | 缩量阴跌可等，放量砸盘不扛 |
| 宏观事件前只减不加 | CPI/FOMC/地缘冲突期间不建新仓 |
| 止损线定了不改 | 纪律比判断重要 |
| 不按计划临时开仓 = 禁止 | 规则10: morning plan 说不动就不动 |

---

## 数据源

| 数据 | 接口 | 来源 |
|------|------|------|
| A 股日 K | MySQL `daily_info_tbl` | Tushare |
| 港股日 K | MySQL `daily_info_tbl` | akshare |
| 美股指数 | akshare / MySQL `market_index_tbl` | 新浪 |
| SOX 半导体 | MySQL `sox_index_tbl` | akshare |
| 实时行情 | `hq.sinajs.cn` | 新浪 |
| 板块概念 | akshare | 东方财富 |
| 个股新闻 | akshare | 东方财富 |
| 资金流向 | MySQL `daily_moneyflow_tbl_2` | Tushare |

> 东方财富接口对境外 IP 有限制，实时数据优先使用新浪 `hq.sinajs.cn`。

---

## 目录结构

```
SmartStock/
├── src/
│   ├── data/config.py              ← 数据库配置（不提交 git）
│   ├── data/config.example.py      ← 配置模板
│   ├── data/new_get_all_stock.py   ← 全市场数据拉取
│   ├── skills/
│   │   ├── morning_analysis.py     ← /morning 数据拉取引擎
│   │   ├── bounce_screener.py      ← /bounce 超跌反弹选股
│   │   └── recall_log.py           ← /recall 历史判断加载
│   ├── screener/
│   │   ├── smart_screener.py       ← 全市场智能选股
│   │   └── strategy_pipeline.py    ← 3步串联策略
│   └── theme/
│       └── theme_analyzer.py       ← 主线题材分析
├── sql/
│   └── schema.sql                  ← 完整建表语句（19张表）
├── scripts/
│   └── init_db.sh                  ← 一键数据库初始化
├── .claude/commands/               ← Skill 命令定义
│   ├── morning.md
│   ├── close.md
│   ├── bounce.md
│   ├── check.md
│   └── ...（共 11 个）
├── docs/                           ← 设计文档
├── trading_plan.md                 ← 每日交易计划 + 持仓规则
├── requirements.txt
└── .gitignore
```
