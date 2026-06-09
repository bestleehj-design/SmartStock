# SmarkStock — 量化股票分析系统

## 快速上手（同事版）

### 环境要求
- Python 3.12+
- MySQL 8.0+（本地运行）
- macOS / Linux（Windows 未测试）

### 安装

```bash
# 1. 安装依赖
pip3 install akshare pymysql

# 2. 修改 DB_CONFIG
# 编辑 stock_check.py 和 morning_analysis.py，把 DB_CONFIG 改成你的数据库
# 如果有 config.py，也可统一管理

# 3. 启动 MySQL
brew services start mysql
```

### 两个核心 Skill

---

## `/check` — 单票快速分析

**用法：**
```bash
python3 stock_check.py 600584          # A股
python3 stock_check.py 00981 HK        # 港股
```

**输出：** 基本面 + 今日分时 + 日K/均线 + 近5日K + 财务数据 + 近期新闻

**数据源：** 东方财富（akshare） + 本地 MySQL 数据库

**依赖的数据库表：** `stock_basic_info_tbl`（股票基本信息）

---

## `/morning` — 每日盘前综合报告

**用法：**
```bash
python3 morning_analysis.py
```

**输出内容：**
1. 隔夜美股（道琼斯、纳斯达克、标普500、费城半导体SOX）
2. 港股三大指数
3. 全市场概念板块排名 + 板块资金流向
4. 持仓个股最新新闻 + 情感分析
5. 综合多空判断
6. 长电科技 T+0 交易计划（支撑/阻力/操作情景）

**依赖的数据库表：** `daily_info_tbl`（日K线数据，用于计算MA均线）

---

## 配置修改清单

到同事机器上后需要改的：

### 1. 数据库配置

`morning_analysis.py` 和 `stock_check.py` 中的：
```python
DB_CONFIG = {
    'host': 'localhost',
    'port': 3306,
    'user': 'root',
    'password': '12345678',    # ← 改成同事的密码
    'database': 'gp2',
    'charset': 'utf8mb4',
}
```

### 2. 持仓列表

`morning_analysis.py` 中的 `HOLDINGS` 列表，改成同事自己的持仓。

### 3. T+0 交易计划

`morning_analysis.py` 中的 `TRADING_PLAN`，改成同事想跟踪的标的和成本。

---

## 数据库依赖

| 脚本 | 需要的表 |
|------|---------|
| `stock_check.py` | `stock_basic_info_tbl`（股票名称/行业） |
| `morning_analysis.py` | `daily_info_tbl`（日K线，用于T+0计划的MA计算） |

如果没有数据库，这俩功能会受限：
- stock_check：没有行业分类和财务数据，但分时/K线/新闻不受影响
- morning_analysis：T+0计划的MA支撑位无法计算，但报告其他部分正常

---

## Claude Code 命令配置

如果同事也用 Claude Code，把 `.claude/commands/` 目录拷过去：

```bash
cp -r .claude/commands ~/.claude/commands/
```

然后在 `.claude/settings.local.json` 加权限：
```json
{
  "permissions": {
    "allow": [
      "Bash(python3:*)"
    ]
  }
}
```

之后在 Claude Code 对话中直接输入 `/check 600584` 或 `/morning` 即可。

---

## 数据源说明

| 数据 | 接口 | 来源 |
|------|------|------|
| A股分时/日K | `akshare.stock_zh_a_minute` / `stock_zh_a_daily` | 东方财富 / 新浪 |
| 港股日K | `akshare.stock_hk_daily` | 新浪 |
| 美股指数 | `akshare.index_us_stock_sina` | 新浪 |
| 费城半导体 | `akshare.macro_global_sox_index` | AKShare |
| 美股期货 | `akshare.futures_global_spot_em` | 东方财富 |
| 概念/行业板块 | `akshare.stock_board_concept_spot_em` | 东方财富 |
| 财务数据 | `akshare.stock_financial_abstract_ths` | 同花顺 |
| 个股新闻 | `akshare.stock_news_em` | 东方财富 |

**注意：** 部分东方财富接口对境外 IP 有限制，VPN 环境下可能报 `RemoteDisconnected`。降级方案是使用新浪数据源（`stock_zh_a_daily`）。

---

## 完整交易日操作流程

### 阶段一：盘前（8:00-9:15）

**1. 启动环境**
```
在 Claude Code 里说：启动 MySQL
→ Claude Code 执行 brew services start mysql
```

**2. 跑晨间报告**
```
在 Claude Code 里说：执行早上分析 或输入 /morning

输出内容：
├── 隔夜美股涨跌（道琼斯、纳指、标普500、费城半导体SOX）
├── 港股走势（恒生、国企、恒生科技）
├── 板块轮动（全市场涨幅TOP10/跌幅TOP5 + 资金流）
├── 持仓个股新闻 + 情感分析（正面/负面关键词匹配）
├── 综合多空判断
└── 长电科技 T+0 操作计划（MA5/10/20 支撑阻力 + 三种情景）
```

**3. 确认策略**
```
问 Claude Code：
- "今天大盘怎么看？"
- "SOX -10%，今天该不该操作？"
- "我的持仓哪些需要减仓？"
→ Claude Code 结合美股数据给出盘前判断
```

### 阶段二：开盘后首小时（9:30-10:30）

**4. 监控竞价和开盘**
```
问 Claude Code：
- "长电科技竞价多少？"
- "港股中芯国际竞价多少？"
→ Claude Code 拉分时数据
```

**5. 逐个检查持仓**
```
对每只持仓：
/check 600584 → 看分时形态 + 量能 + 均线位置
问："长电需要减仓吗？"
问："沪电今天走势很强，要不要止盈？"
```

**原则：10 点前不操作**，只观察。等开盘情绪消化后再做决定。

### 阶段三：盘中交易（10:30-14:30）

**6. 发现机会/风险**
```
随时问：
- "XX票现在可以买吗？" → Claude Code 拉分时 + 日K + 财务 + 新闻
- "XX票一直跌，需要止损吗？" → Claude Code 拉分时量能判断是否放量破位
- "有没有主流题材票值得入手？" → Claude Code 扫行业/概念板块
```

**7. 执行买卖**
```
止损：放量破关键位 → "全走" 或 "卖一半"
止盈：涨停开板/冲高回落 → "卖一半锁定利润"
建仓：尾盘缩量止跌 + 在预定买入区间 → "进第一批，止损XX"
加仓：强势票回调到支撑 → "可以加，止损XX"
```

**8. 新票分析**
```
"顺络电子是做什么的？什么价位建仓？"
→ Claude Code 输出：行业 + 财务 + 估值 + 建仓区间 + 止损位
```

### 阶段四：尾盘决策（14:30-15:00）

**9. 最终检查**
```
逐只检查全部持仓：
- "分析长电科技尾盘，量能在缩吗？要不要走？"
- "华勤技术又回落了，卖点？"
→ Claude Code 拉尾盘分时 + 量能分析 + 给出操作建议
```

**10. 执行尾盘操作**
```
止损执行：尾盘确认破位 → 卖
持有决策：守住关键线 → 留到明天
止盈执行：冲高回落 → 减半仓
```

### 阶段五：收盘复盘（15:00 后）

**11. 总结当日操作**
```
问 Claude Code：
- "总结今天操作"
→ 列出：哪些卖了、盈亏、哪些持有、明天关注什么
- "仓位现在几成？"
→ 整体风险敞口
```

**12. 规划明天**
```
- "明天纳指怎么看？" → 拉美股期货
- "明天什么价位接回XX？"
- "T+0 怎么操作降成本？"
```

---

## 关键原则（今天总结的）

| 原则 | 说明 |
|------|------|
| **极端恐慌日不追高** | SOX -10% 这种日子，等尾盘确认再动 |
| **放量破位 = 立刻走** | 缩量阴跌可以等，放量砸盘不能扛 |
| **涨停开板 = 至少卖一半** | 封不住就是有人在出货 |
| **止损线定了就不改（只往下调）** | 纪律比判断重要 |
| **同一笔交易不来回做** | 卖了 10 分钟内别买回来 |
| **强票守止盈，弱票守止损** | 沪电守 130 止盈，华勤守 100 止损 |
| **每次买卖设好止损再动手** | 没有止损线不进 |

---

## 目录结构（核心文件）

```
SmarkStock/
├── stock_check.py           ← /check 单票分析
├── morning_analysis.py      ← /morning 晨间报告
├── .claude/commands/
│   ├── check.md             ← Claude Code /check 命令
│   └── morning.md           ← Claude Code /morning 命令
├── .claude/settings.local.json
├── SETUP.md                 ← 本文件
└── requirements.txt
```
