# V2 补全设计文档 — 同板块对比 / 逻辑验证 / 仓位管理 / 量价形态

> 针对实战中暴露的四个缺口，逐一设计方案。

---

## 一、同板块对比排名

### 1.1 现状

`smart_screener.py` 将同主线板块的股票都打了分，但输出时按总分全局排序。用户看到的是"PCB 板块第1名排总榜第3，PCB 板块第2名排总榜第15"。不知道板块内谁强谁弱。

### 1.2 方案：新增板块内排名模块

集成到 `smart_screener.py` 的 `screen()` 函数，输出环节不改主逻辑，只加一段输出。

#### 板块内对比维度

对每条主线板块，将板块内候选股按以下指标横向排名：

| 维度 | 权重 | 说明 |
|------|------|------|
| 均线多头质量 | 30% | MA5/MA10/MA20 排列整齐度 + 距 MA20 乖离率 |
| 量能强度 | 20% | 近5日均量 / 前5日均量 |
| 涨停高度 | 25% | 是否今日涨停 + 连板数（从主题分析数据获取） |
| 资金认可 | 15% | 大单净流入比例 |
| 龙头加分 | 10% | 白名单标记 |

#### 输出格式

在常规输出后加一段：

```
────────────────────────────────────────────────────────
  📊 板块内横向对比

  【光模块/CPO】共 5 只候选
  排名  代码        名称      均线得分  量能  涨停  资金  总分
   1    300502    新易盛      28      15    25    12    80  ⭐龙头
   2    300308    中际旭创    25      12     0    10    47
   3    300394    天孚通信    20       8     0     8    36
   ...

  【PCB】共 8 只候选
  排名  代码        名称      均线得分  量能  涨停  资金  总分
  ...
```

#### 实现方案

```python
# 在 smart_screener.py 的 screen() 末尾添加
def rank_within_sector(results):
    """按板块分组，组内横向排名"""
    from collections import defaultdict
    groups = defaultdict(list)
    for r in results:
        sector = r['sector']
        groups[sector].append(r)

    for sector, stocks in groups.items():
        # 对各维度归一化排名
        for dim, weight in [('ma_score', 0.3), ('vol_score', 0.2),
                             ('limit_up_score', 0.25), ('fund_score', 0.15),
                             ('leader_score', 0.1)]:
            values = [s[dim] for s in stocks]
            max_v = max(values) if max(values) > 0 else 1
            for s in stocks:
                s[f'{dim}_rank'] = s[dim] / max_v * 100

        # 综合排名分
        for s in stocks:
            s['intra_sector_score'] = sum(
                s[f'{dim}_rank'] * weight for dim, weight in [
                    ('ma_score', 0.3), ('vol_score', 0.2),
                    ('limit_up_score', 0.25), ('fund_score', 0.15),
                    ('leader_score', 0.1)
                ]
            )

        # 组内排序
        stocks.sort(key=lambda x: x['intra_sector_score'], reverse=True)
        for i, s in enumerate(stocks):
            s['intra_sector_rank'] = i + 1
            s['intra_sector_total'] = len(stocks)

    return results

def print_sector_comparison(results):
    """打印板块横向对比报告"""
    from collections import defaultdict
    groups = defaultdict(list)
    for r in results:
        groups[r['sector']].append(r)

    for sector, stocks in sorted(groups.items()):
        if len(stocks) < 2:
            continue
        print(f"\n  【{sector}】共 {len(stocks)} 只候选")
        # 打印对比表...
```

**改动范围：** 只改 `smart_screener.py`，新增 ~70 行，不涉及新文件。

---

## 二、逻辑验证

### 2.1 现状

`--deep` 模式只能抓新闻中是否出现"澄清""立案"关键词，是二元判断（有/没有雷）。不能判断"上涨逻辑是否成立"。

### 2.2 方案：新增 `logic_validator.py`

一个独立的逻辑验证模块，对候选股回答三个问题：
1. **为什么涨？** — 从新闻/公告/板块归属中推断上涨原因
2. **逻辑链条是否完整？** — 政策 → 产业 → 个股，缺哪一环？
3. **有没有逻辑硬伤？** — 估值、减持、解禁、商誉四大坑

### 2.3 验证框架

```python
class LogicValidator:
    """上涨逻辑验证器"""

    def validate(self, code, name, sector, news_list, funda_data):
        """
        返回:
        {
            'logic_chain': str,          # 上涨逻辑描述
            'chain_completeness': float, # 逻辑完整度 0-100
            'missing_link': str,         # 缺失环节
            'hard_faults': [str],        # 逻辑硬伤列表
            'risk_flags': [str],         # 风险信号
            'verdict': str,              # 结论: 'strong' / 'ok' / 'weak' / 'reject'
        }
        """

    def _infer_logic(self, code, name, sector, news_list):
        """从新闻+板块推断上涨逻辑"""
        ...

    def _check_chain(self, sector, funda_data):
        """检查逻辑链条: 政策 → 产业 → 个股"""
        ...

    def _check_hard_faults(self, code, funda_data):
        """检查逻辑硬伤: 减持/解禁/商誉/高质押"""
        ...
```

### 2.4 逻辑链条检查

```
政策支持 ──→ 产业趋势 ──→ 个股受益
   │             │            │
   │ ✅ 有政策    │ ✅ 行业景气  │ ✅ 公司是核心标的
   │ ⚠️ 政策不确定│ ⚠️ 竞争加剧  │ ⚠️ 公司是蹭概念
   │ ❌ 无政策    │ ❌ 行业下行  │ ❌ 公司质地差
```

每条链给一个状态（✅ / ⚠️ / ❌），完整度 = ✅数量 / 3。

### 2.5 逻辑硬伤检查

| 硬伤 | 检查方式 | 阈值 |
|------|---------|------|
| 大股东减持 | 查 news_stock_daily_tbl 最近30天减持公告 | 出现过 → 硬伤 |
| 质押风险 | `pledge_ratio` > 50% | 触发警告 |
| 商誉风险 | `goodwill / net_assets` > 30% | 触发警告 |
| 限售解禁 | 查解禁日期在30天内 | 触发警告 |
| 业绩暴雷 | `netprofit_yoy` < -50% | 触发警告 |

### 2.6 集成方式

集成到 `strategy_pipeline.py` 的 step3 中，在基本面分析之后运行。

**改动范围：**
- 新增 `logic_validator.py` 一个文件
- `strategy_pipeline.py` 加一行调用

---

## 三、仓位管理

### 3.1 现状

完全没有仓位管理。只知道"这只票能买"，不知道"买多少"。

### 3.2 方案：新增 `position_sizer.py`

基于凯利公式 + 市场情绪调整的仓位计算器。

### 3.3 核心公式

#### 凯利仓位

```
f* = (p × b - (1-p)) / b

其中:
  p  = 预测胜率（来自 uptrend_model.py 的置信度）
  b  = 赔率（预期盈利 / 预期亏损）
      = 止盈幅度 / 止损幅度
```

示例：
- 如果 10天涨>20% 概率 70%，止损 8%
- 赔率 b = 20% / 8% = 2.5
- f* = (0.7 × 2.5 - 0.3) / 2.5 = 0.58
- 理论仓位 = 总资金 × 58%

#### 实际仓位 = 凯利仓位 × 调整系数

调整系数考虑以下因素：

| 因素 | 系数 | 条件 |
|------|------|------|
| 市场情绪 | 0.3 ~ 1.3 | 恐慌日 1.3 / 亢奋日 0.5 / 正常 1.0 |
| 主线纯度 | 0.5 ~ 1.0 | 第一主线 1.0 / 次主线 0.7 / 非主线 0.5 |
| 单票上限 | cap | 不超过总仓位 × 25% |
| 总仓位上限 | — | 不超过总资金 × 80% |
| 现金保留 | — | 至少留 20% 现金 |

### 3.4 市场情绪判断

从当日行情数据判断：

```python
def assess_market_sentiment():
    """
    从当日数据判断市场情绪
    返回: (sentiment, multiplier)
    """
    # 1. 跌停家数 vs 涨停家数
    # 2. 大盘指数跌幅
    # 3. 主力资金净流入/流出

    if 跌停 > 50 or 大盘跌 > 3%:
        return 'panic', 1.3      # 恐慌日，性价比最高
    elif 涨停 > 100 and 大盘涨 > 1%:
        return 'euphoric', 0.5   # 亢奋日，追高风险
    elif 涨停 > 50 and 大盘涨 > 0.5%:
        return 'bullish', 0.8
    else:
        return 'neutral', 1.0
```

### 3.5 分批建仓计划

```
总计划仓位 = 100 万

方案A: 一次性建仓（凯利仓位 < 15%）
  → 一笔买入凯利仓位

方案B: 金字塔建仓（凯利仓位 > 15%）
  → 第一笔: 凯利仓位的 50%（试探）
  → 第二笔: 回踩 MA20 再加 30%（回踩确认）
  → 第三笔: 放量突破前高再加 20%（确认趋势）
```

### 3.6 输出格式

```
────────────────────────────────────────────────
  💰 仓位建议 — 顺络电子 (002138)

  预测胜率 (10天涨>20%): 72%
  止损幅度: -8%
  预期盈利: +20%
  赔率: 2.5

  凯利仓位: 58%  ×  市场情绪(恐慌 1.3)  ×  主线纯度(主线 1.0)
  → 调整后仓位: 75%
  → 受单票上限 25% 约束 → 最终仓位: 25%

  📋 分批计划:
    第1笔: 12.5%（当前价建仓）
    第2笔: 7.5%（回踩 MA20=31.5 加仓）
    第3笔: 5.0%（放量突破前高 38.0 加仓）
    止损: 31.5（-10.5%）
────────────────────────────────────────────────
```

### 3.7 集成方式

新增独立文件，在 `strategy_pipeline.py` step3 末尾调用。

**改动范围：**
- 新增 `position_sizer.py`

---

## 四、量价形态识别

### 4.1 现状

`stock_check.py` 只能识别最简单的日分时走势（持续拉升/横盘/先涨后跌），无法识别经典的K线形态。

### 4.2 方案：新增 `pattern_recognition.py`

基于收盘价序列 + 成交量序列的模式识别器。

### 4.3 识别形态清单

#### 看涨形态

| 形态 | 核心特征 | 可靠性 | 验证条件 |
|------|---------|--------|---------|
| **W底** | 两个相近低点，中间反弹，右底抬升 | 中 | 右底成交量 > 左底 |
| **头肩底** | 左肩→头部(新低)→右肩(高于头)，上升颈线 | 高 | 突破颈线时放量 |
| **三重底** | 三次触及相同底部区域 | 高 | 第三次时缩量 |
| **杯柄形态** | 缓升→回调(½)→突破前高，杯深1/3 | 高 | 突破时放量 |
| **突破前高** | 收盘站上N日最高价 | 高 | 放量突破 |
| **旗形整理** | 大涨后横向整理，区间缩窄 | 中 | 向上突破放量 |
| **均线粘合后发散** | 3条均线粘合后MA5率先向上突破 | 中 | 放量确认 |

#### 看跌形态

| 形态 | 核心特征 | 可靠性 | 验证条件 |
|------|---------|--------|---------|
| **M顶** | 两个相近高点，中间回调，右顶不创新高 | 中 | 右顶缩量 |
| **头肩顶** | 左肩→头部→右肩(更低)，颈线支撑 | 高 | 跌破颈线放量 |
| **量价背离** | 价创新高 + 量萎缩 | 高 | 连续3天出现 |

### 4.4 识别算法

以 W底 为例：

```python
def detect_w_bottom(closes, volumes, lookback=60):
    """
    用极值点检测 + 约束条件判断 W 底形态
    """
    local_mins = find_local_minima(closes, distance=5)

    if len(local_mins) < 2:
        return None

    # 找最近两个低点
    for i in range(len(local_mins)-2, -1, -1):
        left_idx, right_idx = local_mins[i], local_mins[i+1]

        # 条件1: 两低点距离 5~30 天
        if not (5 <= right_idx - left_idx <= 30):
            continue

        # 条件2: 两低点价格差距 < 5%
        left_price = closes[left_idx]
        right_price = closes[right_idx]
        if abs(left_price - right_price) / left_price > 0.05:
            continue

        # 条件3: 中间有反弹（高点 > 低点 + 5%）
        mid_max = max(closes[left_idx:right_idx+1])
        if mid_max / left_price < 1.05:
            continue

        # 条件4: 右底成交量 > 左底
        right_vol = volumes[right_idx]
        left_vol = volumes[left_idx]
        vol_confirm = right_vol > left_vol

        # 条件5: 当前价已突破颈线（中间最高点）
        neckline = mid_max
        if closes[-1] <= neckline:
            continue

        return {
            'pattern': 'W底',
            'direction': 'bullish',
            'left_bottom': left_idx,
            'right_bottom': right_idx,
            'neckline': neckline,
            'vol_confirmed': vol_confirm,
            'confidence': 70 if vol_confirm else 50,
        }

    return None
```

### 4.5 形态综合报告

```python
def analyze_patterns(code, daily_data, lookback=90):
    """
    对一只股票分析所有形态
    返回: 检测到的所有形态 + 综合技术判断
    """
    patterns = []
    patterns.append(detect_w_bottom(closes, volumes))
    patterns.append(detect_head_shoulder(closes, volumes))
    patterns.append(detect_breakout(closes, volumes))
    # ...

    # 去重（同一区域可能有多种形态解释）
    patterns = deduplicate(patterns)

    # 综合判断
    bullish = [p for p in patterns if p['direction'] == 'bullish']
    bearish = [p for p in patterns if p['direction'] == 'bearish']

    return {
        'bullish_patterns': bullish,
        'bearish_patterns': bearish,
        'dominant_signal': 'bullish' if total_bull > total_bear else 'bearish',
        'confidence': max(p['confidence'] for p in patterns) if patterns else 0,
    }
```

### 4.6 输出格式

```
────────────────────────────────────────────────
  📊 量价形态分析 — 顺络电子 (002138)

  🟢 看涨形态:
    ✅ W底
       左底: 2026-05-20  31.20  (量 820万)
       右底: 2026-06-02  31.50  (量 1050万)  放量确认 ✓
       颈线: 34.80  当前 35.20  已突破 ✓
       置信度: 70%

    ⚠️ 均线粘合后发散
       MA5-10-20 粘合 12 天，今日 MA5 上穿 MA10
       置信度: 60% (待放量确认)

  🔴 看跌形态:
    无

  📈 综合判断: 偏多（看涨形态占优）
────────────────────────────────────────────────
```

### 4.7 集成方式

在 `strategy_pipeline.py` step3 中，对最终候选股调用形态识别。

**改动范围：**
- 新增 `pattern_recognition.py`
- `strategy_pipeline.py` 加调用

---

## 五、改动清单

### 新增文件 (3个)

| 文件 | 对应缺口 | 核心功能 |
|------|---------|---------|
| `logic_validator.py` | 逻辑验证 | 上涨逻辑推断 + 逻辑硬伤检查 |
| `position_sizer.py` | 仓位管理 | 凯利公式 + 市场情绪调整 + 分批计划 |
| `pattern_recognition.py` | 量价形态 | W底/M顶/头肩/突破/杯柄 等 12 种形态识别 |

### 修改文件 (2个)

| 文件 | 对应缺口 | 改动内容 |
|------|---------|---------|
| `smart_screener.py` | 同板块对比 | 新增 `rank_within_sector()` + `print_sector_comparison()` |
| `strategy_pipeline.py` | 串联集成 | step3 中调用 logic_validator + position_sizer + pattern_recognition |

### 不增加的数据表

三个模块都基于已有数据运行，不新增数据库表。

---

## 六、实现优先级

| 优先级 | 模块 | 理由 |
|--------|------|------|
| **P0** | 仓位管理 | 实盘最关键，没有仓位管理就是赌博 |
| **P0** | 同板块对比 | 改动最小，收益明显 |
| **P1** | 量价形态 | 经典技术分析的核心，提升判断质量 |
| **P2** | 逻辑验证 | 逻辑判断本就需要人工，自动化容易误判 |

前三项（P0+P1）可以一起做，逻辑验证放最后。
