# /backtest — 回溯验证 & 选股分析

回填未来收益、验证判断准确率、分析选股器效果。

**用法:** `/backtest` 或直接说「回溯」

## 执行逻辑

### 第一步：回填收益

```
python3 src/screener/smart_screener.py --backfill
```

- 从 `daily_info_tbl` 查未来 1/3/5/10/20 天收盘价
- 更新 `smart_screen_results` 的 ret_1d ~ ret_20d

```
python3 src/skills/verify_analysis.py --backfill
```

- 回填 `claude_trades` 表的收益

### 第二步：生成报告

```
python3 src/screener/smart_screener.py --analyze
```

输出 5 个维度：

#### 1. 得分区间收益
按 score 分三档（70+/50-69/<50），看高分段是否真的收益更好

#### 2. 龙头 vs 非龙头
白名单龙头票和同板块普通票的收益差

#### 3. 板块收益排名
各主线板块的平均收益，发现阶段性强弱

#### 4. 板块动量分析（核心）
按 `sector_index_rise` 分组：
- 强板块（rise≥8）→ 个股收益？
- 弱板块（rise<2）→ 是否该避开？

**等攒够 10 天数据后，这项会告诉我们：**
- 板块在涨的时候，选它里面的票是不是更赚钱
- 追高票（个股远超板块涨幅）后续表现 vs 补涨票（个股落后板块）

#### 5. 最近一期详情
最近一个筛选日的总数、平均收益、胜率

### 第三步：手动判断

```
python3 src/skills/verify_analysis.py --report
```

- claude_trades 表的准确率报告
- 按操作类型/信心等级分类

## 何时使用

| 频率 | 操作 | 目的 |
|------|------|------|
| **每天** | `--backfill` | 把今天收益填入昨天的选股记录 |
| **每天** | `--analyze` | 看昨天选股今天表现如何 |
| **每周** | verify_analysis | 看一周判断准确率趋势 |
| **攒够10天** | 重点看维度4 | 决定是否引入板块动量加分 |

## 数据来源

- `smart_screen_results` — 选股器每日入库结果（含 sector_index_rise）
- `claude_trades` — /log 记录的手动判断
- `daily_info_tbl` — 历史日K（回填未来收益）
