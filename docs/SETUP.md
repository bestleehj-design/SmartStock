# SmarkStock — 量化股票分析系统

## 快速上手

### 环境要求
- Python 3.12+
- MySQL 8.0+（本地运行）
- macOS / Linux

### 安装

```bash
pip3 install akshare pymysql
brew services start mysql
```

---

## 全部 Skill 一览

| 命令 | 功能 | 何时用 |
|------|------|--------|
| `/morning` | 盘前综合分析 | 每天早晨，自动回调昨日判断 |
| `/check <code>` | 单票快速分析 | 随时查任意股票 |
| `/zhaban <code>` | 涨停炸板四维分析 | 持仓涨停后开板时 |
| `/theme` | 主线题材分析 | 想了解当前市场主线 |
| `/close` | 收盘分析（量能/涨跌比/指数） | 每天收盘后 15:00 |
| `选股` | 全市场智能选股（保存到 DB） | 每天收盘后 |
| `/log` | 存储今日手动判断 | 每天收盘后 |
| `/recall [date]` | 加载历史判断 | 新会话开场，回顾昨日 |
| `/backtest` | 回填收益 + 选股器分析 + 判断准确率 | **每天回溯昨天选股** |

---

## 每日标准工作流

### 盘前: `/morning`

```
1. 自动回调昨日判断（recall_log.py）
2. 跑盘前数据（morning_analysis.py）
3. 读取 trading_plan.md 获取持仓和计划
4. 输出：隔夜美股/港股、板块轮动、持仓新闻、T+0计划
5. 对比昨日判断 vs 今日盘面
```

### 盘中: `/check` + `/zhaban`

```
/check 600584     → 单票分析，判断该买还是该卖
/zhaban 002138    → 涨停炸板，四维自动打分
```

### 收盘后: `选股` + `/log` + `/close`

```
选股 → 422只候选入库 smart_screen_results（含 sector_index_rise）
/close → 收盘量能/涨跌比/指数数据
/log → 记录今日手动判断到 claude_trades
```

### 每天盘后: `/backtest`

```
回填昨日选股收益 → 5维度分析报告：
  1. 得分区间收益 → 高分是否真高收益
  2. 龙头 vs 非龙头 → 白名单是否有效
  3. 板块收益排名 → 阶段性强弱
  4. 板块动量分析 → sector_index_rise vs 个股收益（攒10天数据后生效）
  5. 最近一期胜率
```

---

## 完整交易日操作流程

### 阶段一：盘前（8:00-9:15）

**1. 启动环境**
```
启动 MySQL
```

**2. 跑晨间报告**
```
输入: /morning

输出内容：
├── 昨日判断回顾（recall_log.py）
├── 隔夜美股涨跌（道琼斯、纳指、标普500、费城半导体SOX）
├── 港股走势（恒生、国企、恒生科技）
├── 板块轮动（全市场涨幅TOP10/跌幅TOP5 + 资金流）
├── 持仓个股新闻 + 情感分析
├── 综合多空判断
└── 长电科技 T+0 操作计划（支撑/阻力/三种情景）
```

**3. 确认策略**
```
- "今天大盘怎么看？"
- "SOX +5.6%，今天该不该操作？"
- "我的持仓哪些需要减仓？"
```

### 阶段二：开盘后（9:30-11:30）

**4. 监控竞价和开盘**
```
- "XX票竞价多少？"
- "港股XX竞价多少？"
```

**5. 逐个检查持仓**
```
/check 600584 → 看分时 + 量能 + 均线
问："长电需要减仓吗？"
```

**6. 涨停炸板专项**
```
/zhaban 002138 → 四维自动分析，出结论
```

**原则：10 点前不操作**，只观察。

### 阶段三：盘中交易（10:30-14:30）

**7. 发现机会/风险**
```
- "XX票现在可以买吗？"
- "XX票一直跌，需要止损吗？"
- "有没有主流题材票值得入手？"
```

**8. 执行买卖**
```
止损：放量破关键位 → "走" 或 "卖一半"
止盈：涨停开板/冲高回落 → "卖一半锁利润"
建仓：尾盘缩量止跌 + 在计划区间 → "进第一批，止损XX"
```

### 阶段四：尾盘决策（14:30-15:00）

**9. 最终检查**
```
逐只检查持仓：
- "分析XX尾盘，量能在缩吗？要不要走？"
```

### 阶段五：收盘后（15:00 后）

**10. 记录判断**
```
输入: /log
→ 批量写入今日所有判断到 claude_trades 表
```

**11. 规划明天**
```
- "明天纳指怎么看？"
- "T+0 怎么操作降成本？"
```

---

## 判断回溯体系

### 闭环逻辑

```
早晨                    盘中                   收盘后
/morning ─────────→  /check /zhaban ─────────→  /log
  │ 回调昨日             实时决策                  │ 存判断
  │                                                 │
  └──────── /backtest 每周验证 ◀────────────────────┘
```

### 数据库表

`claude_trades` 表记录每次判断：

| 字段 | 说明 |
|------|------|
| analysis_date | 分析日期 |
| code | 股票代码 |
| action | buy/hold/sell/wait |
| confidence | high/medium/low |
| thesis | 核心逻辑 |
| risks | 风险点 |
| stop_loss | 止损价 |
| target_price | 目标价 |
| ret_1d/3d/5d/10d/20d | 实际收益（回填） |

### 数据流向

```
log_session.py  →  INSERT (记录判断)
verify_analysis.py --backfill →  UPDATE (回填未来收益)
verify_analysis.py --report  →  SELECT (生成报告)
recall_log.py  →  SELECT (加载历史判断)
```

---

## 交易规则速查（来自 trading_plan.md）

### 持仓分级制

| 标签 | 定义 | 操作原则 |
|------|------|---------|
| 必清 | 趋势确认反转 | 有溢价就出，不赌不等 |
| 减仓可等 | 逻辑在但有瑕疵 | 出一半，留一半给板块情绪 |
| 不动 | 核心持仓，逻辑无变化 | 无论涨跌都不动 |

### 板块催化剂乘数

```
SOX +3%以上 → 卖出目标 +3%
SOX +5%以上 → 卖出目标 +5%
SOX +7%以上 → 不设目标价，设移动止损
```

### 突破 vs 见顶 四维确认

| 维度 | 见顶 | 突破 |
|------|------|------|
| 成交量 | 冲高缩量 | 冲高放量 |
| 收盘位置 | 大幅回落 | 实体阳线收在压力上方 |
| K线形态 | 长上影线 | 实体阳线 |
| MA趋势 | MA5向下 | MA5持续向上 |

- 4/4 突破 → 持有，设移动止盈
- 2/2 平分 → 出一半观察
- 4/4 见顶 → 减仓或清仓

---

## 核心原则

| 原则 | 说明 |
|------|------|
| 极端恐慌日不追高 | SOX爆跌时等尾盘确认再动 |
| 放量破位 = 立刻走 | 缩量阴跌可等，放量砸盘不扛 |
| 涨停开板 → 先跑 /zhaban | 让四维框架判断 |
| 止损线定了不改（只往下调） | 纪律比判断重要 |
| 同一笔交易不来回做 | 卖了10分钟内别买回来 |
| 强票守止盈，弱票守止损 | 核心仓给空间，边缘仓快刀 |
| 每次买卖设好止损再动手 | 没有止损线不进 |
| 美股反弹是减仓窗口 | 不是加仓信号 |
| 板块催化剂 > 个股利空时上调目标 | 不因小利空清仓 |
| 宏观事件前只减不加 | CPI/FOMC前后不建新仓 |

---

## 目录结构

```
SmarkStock/
├── morning_analysis.py         ← /morning 晨间报告
├── zhaban_check.py             ← /zhaban 涨停炸板
├── stock_check.py              ← /check 单票分析
├── log_session.py              ← /log 批量存判断
├── recall_log.py               ← /recall 加载历史
├── verify_analysis.py          ← /backtest 回填+报告
├── smart_screener.py           ← 选股器
├── trading_plan.md             ← 每日交易计划+规则
├── .claude/
│   ├── commands/
│   │   ├── morning.md
│   │   ├── check.md
│   │   ├── zhaban.md
│   │   ├── log.md
│   │   ├── recall.md
│   │   ├── backtest.md
│   │   └── theme.md
│   └── settings.local.json
└── requirements.txt
```

---

## 数据源说明

| 数据 | 接口 | 来源 |
|------|------|------|
| A股分时/日K | akshare stock_zh_a_* | 东方财富/新浪 |
| 港股日K | akshare stock_hk_* | 新浪 |
| 美股指数 | akshare index_us_stock_sina | 新浪 |
| 实时行情 | hq.sinajs.cn | 新浪 |
| 板块概念 | akshare stock_board_* | 东方财富 |
| 个股新闻 | akshare stock_news_em | 东方财富 |
| 历史日K | MySQL daily_info_tbl | 本地数据库 |

**注意：** 东方财富接口对境外 IP 有限制，实时数据使用新浪 hq.sinajs.cn 降级。

---

## 配置修改清单

### 数据库配置
`morning_analysis.py` / `stock_check.py` / `zhaban_check.py` / `log_session.py` 中的 DB_CONFIG。

### 持仓列表
`morning_analysis.py` 的 HOLDINGS 列表 + `trading_plan.md` 的持仓表。

### T+0 计划
`morning_analysis.py` 的 TRADING_PLAN 字典。

### Claude Code 命令
```bash
cp -r .claude/commands ~/.claude/
```
