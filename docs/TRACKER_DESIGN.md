# Claude 分析验证系统 — 设计文档

## 目标

记录 Claude Code 每次对个股的分析结论，追踪判断准确率，持续优化分析质量。

---

## 数据库表

```sql
CREATE TABLE claude_trades (
    id              INT AUTO_INCREMENT PRIMARY KEY,
    analysis_date   DATE NOT NULL,           -- 分析日期
    code            VARCHAR(10) NOT NULL,    -- 股票代码
    name            VARCHAR(50),             -- 股票名称
    source          VARCHAR(50),             -- 来源: smart_screener / manual / morning_report
    action          VARCHAR(20),             -- 操作: buy / hold / sell / wait
    entry_price     DECIMAL(10,2),           -- 建议买入价
    stop_loss       DECIMAL(10,2),           -- 建议止损价
    target_price    DECIMAL(10,2),           -- 目标价
    confidence      VARCHAR(20),             -- 信心: high / medium / low
    thesis          TEXT,                    -- 核心逻辑
    risks           TEXT,                    -- 风险点
    current_price   DECIMAL(10,2),           -- 分析时的现价

    -- 以下由验证脚本回填
    ret_1d          DECIMAL(8,4) DEFAULT NULL,
    ret_3d          DECIMAL(8,4) DEFAULT NULL,
    ret_5d          DECIMAL(8,4) DEFAULT NULL,
    ret_10d         DECIMAL(8,4) DEFAULT NULL,
    ret_20d         DECIMAL(8,4) DEFAULT NULL,

    -- 是否达到目标 / 触发止损
    hit_target      TINYINT DEFAULT NULL,     -- 1=达到目标
    hit_stop        TINYINT DEFAULT NULL,     -- 1=触发止损
    max_ret         DECIMAL(8,4) DEFAULT NULL,-- 持有期间最大收益

    -- 验证评分
    accuracy_score  INT DEFAULT NULL,         -- 0-100 准确度评分

    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_date (analysis_date),
    INDEX idx_code (code),
    INDEX idx_action (action),
    INDEX idx_source (source)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

---

## 记录脚本：`log_analysis.py`

### 用法

在 Claude Code 对话中，每次分析完一只票后运行：

```bash
python3 log_analysis.py --code 600584 --action hold \
  --stop 69.5 --thesis "7月业绩炒作+70有W底支撑" \
  --risk "尾盘收在MA20下方" --confidence medium \
  --source manual --price 70.30
```

### 参数说明

| 参数 | 含义 | 示例 |
|------|------|------|
| `--code` | 股票代码 | 600584 |
| `--action` | 操作建议 | buy / hold / sell / wait |
| `--entry` | 建议买入价 | 70.50 |
| `--stop` | 建议止损价 | 69.50 |
| `--target` | 目标价 | 78.00 |
| `--thesis` | 核心逻辑 | "7月业绩炒作" |
| `--risk` | 风险点 | "尾盘破MA20" |
| `--confidence` | 信心等级 | high / medium / low |
| `--source` | 来源 | smart_screener / manual / morning_report |
| `--price` | 分析时现价 | 70.30 |

---

## 验证脚本：`verify_analysis.py`

### 功能

1. 读取 `claude_trades` 中所有未验证的记录
2. 用数据库日K计算 1/3/5/10/20 日收益
3. 检查是否达到目标价 / 触发止损
4. 计算准确度评分
5. 输出验证报告

### 准确度评分规则

| 我的判断 | 实际结果 | 得分 |
|----------|---------|------|
| buy + 达到目标 | 实际涨到目标 | 100 |
| buy + 达到目标 | 涨了但没到目标 | 60 |
| buy + 达到目标 | 跌了 | 0 |
| hold + 没破止损 | 持有期正收益 | 80 |
| hold + 没破止损 | 持有期负收益 | 30 |
| sell + 建议卖 | 实际跌了 | 100 |
| sell + 建议卖 | 实际涨了 | 0 |
| wait + 等回调 | 实际回调到买入区 | 100 |

### 用法

```bash
# 验证所有未验证记录
python3 verify_analysis.py

# 验证指定日期
python3 verify_analysis.py --date 2026-06-08

# 生成报告
python3 verify_analysis.py --report
```

---

## 验证报告示例

```
=== Claude 分析验证报告 ===
验证日期: 2026-06-15 (7天后)
分析记录: 12 条

📊 整体准确率:
  buy 信号: 5条  准确率 80%  平均收益 +4.2%
  hold 信号: 4条  准确率 75%
  sell 信号: 1条  准确率 100%
  wait 信号: 2条  准确率 50%

🎯 最佳判断:
  ✅ 中天科技: 建议卖出 @48 → 实际跌到 44  (-8.3%)
  ✅ 沪电股份: 建议持有 → 实际涨到 142  (+4.4%)
  ✅ 东山精密: 建议 wait → 实际继续跌 符合预期

⚠️ 最差判断:
  ❌ 长电科技: 建议买回 @70.4 → 实际跌到 68  (-3.4%)
     问题: 尾盘没确认就动手，太冲动
     改进: 加一条规则「尾盘放量收跌不进场」
  ❌ 华勤技术: 建议等反弹 → 继续暴跌到 95
     问题: 100 止损给太晚了
     改进: 连续 3 天创新低自动降级

💡 优化建议:
  1. buy 信号的准确率 80%，但追高买入的准确率只有 40%
     → 限制评分规则: MA20距离 >15% 时最高只能给 hold
  2. 龙头票的 hold 信号准确率 100%，非龙头只有 50%
     → 非龙头票降低信心等级
  3. 恐慌日买入机会的确更好 (avg +6.2%)
     → 恐慌日模式下提高龙头权重
```

---

## 实施步骤

### 1. 建表

```bash
python3 create_tracker_tables.py
```

### 2. 今天手动录入

把今天讨论过的所有票录入：

```bash
# 买入/持有类
python3 log_analysis.py --code 002463 --action hold --thesis "PCB龙头+恐慌日翻红+2027年前订单锁定" --confidence high --price 135.46 --stop 130
python3 log_analysis.py --code 002138 --action buy --entry 55.50 --stop 53.5 --target 62 --thesis "电感龙头+涨停次日横盘" --confidence high --price 55.66
python3 log_analysis.py --code 600584 --action hold --stop 69.5 --thesis "W底+7月业绩" --confidence medium --price 70.30 --risk "尾盘收在MA20下方"
python3 log_analysis.py --code 300502 --action wait --entry 710 --thesis "光模块龙头等回调" --confidence high --price 732
python3 log_analysis.py --code 002384 --action hold --stop 210 --thesis "PCB龙头回踩MA20" --confidence medium --price 213

# 卖出/回避类
python3 log_analysis.py --code 600522 --action sell --thesis "涨停开板+年内涨150%利好兑现" --confidence high --price 50
python3 log_analysis.py --code 000725 --action wait --thesis "好公司但涨60%太高" --confidence high --price 6.44
python3 log_analysis.py --code 300296 --action wait --thesis "底部形态但Q1利润崩" --confidence low --price 7.19
python3 log_analysis.py --code 300687 --action wait --thesis "等24附近横住再进" --confidence medium --price 24.80
```

### 3. 每次分析后自动记录

在 Claude Code 对话中，我分析完一只票后，可以自动调用 `log_analysis.py`。

### 4. 每周回顾

```bash
python3 verify_analysis.py --report
```

---

## 文件清单

| 文件 | 用途 |
|------|------|
| `create_tracker_tables.py` | 建表 |
| `log_analysis.py` | 记录分析 |
| `verify_analysis.py` | 验证回溯 |
| `TRACKER_DESIGN.md` | 本文档 |
