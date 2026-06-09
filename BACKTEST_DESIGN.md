# 选股策略回溯优化系统 — 设计文档

## 目标

每天跑 smart_screener 后保存结果到数据库，积累历史数据后回溯分析，持续优化选股策略的评分权重。

---

## 整体架构

```
每天收盘后:
  smart_screener.py → 筛选结果 → 写入 smart_screen_results 表

每个周末:
  backtest_screener.py → 读历史数据 → 算未来收益 → 输出优化建议
```

---

## 数据库表设计

```sql
CREATE TABLE smart_screen_results (
    id              INT AUTO_INCREMENT PRIMARY KEY,
    screen_date     DATE NOT NULL,          -- 筛选日期
    code            VARCHAR(10) NOT NULL,   -- 股票代码
    name            VARCHAR(50),            -- 股票名称
    score           INT,                    -- 综合得分 0-100
    sector          VARCHAR(50),            -- 归属主线板块
    is_leader       TINYINT DEFAULT 0,      -- 是否龙头
    price           DECIMAL(10,2),          -- 筛选时现价
    ma20            DECIMAL(10,2),          -- MA20
    stop_loss       DECIMAL(10,2),          -- 建议止损价
    reasons         TEXT,                   -- 加分理由(JSON数组)
    warnings        TEXT,                   -- 风险提示(JSON数组)

    -- 以下字段由回溯脚本回填
    ret_1d          DECIMAL(8,4) DEFAULT NULL,   -- 1天后收益率
    ret_3d          DECIMAL(8,4) DEFAULT NULL,   -- 3天后
    ret_5d          DECIMAL(8,4) DEFAULT NULL,   -- 5天后
    ret_10d         DECIMAL(8,4) DEFAULT NULL,   -- 10天后
    ret_20d         DECIMAL(8,4) DEFAULT NULL,   -- 20天后

    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    UNIQUE KEY uk_screen_date_code (screen_date, code),
    INDEX idx_date (screen_date),
    INDEX idx_score (screen_date, score),
    INDEX idx_leader (screen_date, is_leader),
    INDEX idx_sector (screen_date, sector)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

---

## smart_screener.py 改动（仅两步）

### 步骤一：新建 `save_to_db()` 函数

```python
def save_to_db(results, screen_date):
    """将筛选结果写入 smart_screen_results 表"""
    conn = get_db()
    c = conn.cursor()

    for r in results:
        try:
            c.execute('''
                INSERT INTO smart_screen_results
                (screen_date, code, name, score, sector, is_leader,
                 price, ma20, stop_loss, reasons, warnings)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON DUPLICATE KEY UPDATE
                score=VALUES(score), price=VALUES(price),
                reasons=VALUES(reasons), warnings=VALUES(warnings)
            ''', (
                screen_date,
                r['code'], r['name'], r['score'],
                r['sector'], 1 if r.get('is_leader') else 0,
                r['price'], r['stop_loss'],
                r['stop_loss'],  # ma20 用止损推算
                json.dumps(r['reasons'], ensure_ascii=False),
                json.dumps(r['warnings'], ensure_ascii=False),
            ))
        except Exception:
            pass

    conn.commit()
    c.close()
    conn.close()
    print(f"\n💾 已保存 {len(results)} 条到数据库")
```

### 步骤二：在 `screen()` 末尾添加调用

```python
if args.save:
    save_to_db(results, today_str())
```

### 用法

```bash
# 正常跑 + 保存结果
python3 smart_screener.py --panic --top 50 --save

# 收盘后保存（crontab 用）
python3 smart_screener.py --top 50 --save
```

---

## 回溯脚本 `backtest_screener.py`

### 功能

1. 读取所有历史筛选记录
2. 对每条记录，从数据库查询第 1/3/5/10/20 个交易日后的收盘价
3. 计算收益率，回填 `ret_1d` ~ `ret_20d`
4. 按不同维度分析：得分区间、龙头/非龙头、板块、加分理由
5. 输出优化建议

### 核心分析逻辑

```python
# 1. 按得分区间统计
SELECT
    CASE
        WHEN score >= 70 THEN '70+'
        WHEN score >= 50 THEN '50-69'
        ELSE '<50'
    END as score_tier,
    COUNT(*) as cnt,
    AVG(ret_5d) as avg_ret_5d,
    AVG(ret_10d) as avg_ret_10d
FROM smart_screen_results
WHERE ret_5d IS NOT NULL
GROUP BY score_tier;

# 2. 龙头 vs 非龙头
SELECT is_leader,
    COUNT(*) as cnt,
    AVG(ret_5d) as avg_ret_5d,
    AVG(ret_10d) as avg_ret_10d
FROM smart_screen_results WHERE ret_5d IS NOT NULL
GROUP BY is_leader;

# 3. 加分理由分析（哪些理由最挣钱）
# 解析 reasons JSON，统计每个理由对应的平均收益

# 4. 板块分析
SELECT sector,
    COUNT(*) as cnt,
    AVG(ret_5d) as avg_ret_5d
FROM smart_screen_results WHERE ret_5d IS NOT NULL
GROUP BY sector
ORDER BY avg_ret_5d DESC;
```

### 输出示例

```
=== 回溯分析 ===
历史数据: 2026-06-08 ~ 2026-07-08 (20 个交易日)

📊 按得分统计:
  70+分: 15只  avg_5d=+3.2%  avg_10d=+5.1%
  50-69: 80只  avg_5d=+1.5%  avg_10d=+2.3%
  <50分: 120只 avg_5d=-0.8%  avg_10d=-1.2%

👑 龙头 vs 非龙头:
  龙头: 30只  avg_5d=+3.8%  avg_10d=+6.2%
  非龙头: 185只 avg_5d=+0.5%  avg_10d=+0.9%

🏆 最挣钱的加分理由:
  多头排列:     avg_5d=+2.8%
  恐慌日抗跌:   avg_5d=+4.1%  ← 这个因子最有效！
  放量:         avg_5d=+1.9%
  回踩MA20:     avg_5d=+1.2%

💡 优化建议:
  1. 恐慌日抗跌 权重: 建议从 25 提升到 35 (因子最有效)
  2. 多头排列 权重: 建议维持 30
  3. 题材权重: 建议维持 15，但龙头权重从 10 提升到 15
  4. 放量因子: 区分上攻放量 vs 出货放量
```

---

## 实施路线

| 阶段 | 做什么 | 多久后有用 |
|------|--------|-----------|
| **第 1 天** | 建表 + smart_screener 加 `--save` | 当天开始积累数据 |
| **第 1 周** | 跑 `backtest_screener.py --backfill` 回填 5 天收益 | 看短期信号有效性 |
| **第 2 周以后** | 跑完整回溯分析，得到优化建议 | 调整评分权重 |

**最短 2 周就能得到有意义的优化建议。** 如果回测到 1 个月的数据，龙头 vs 非龙头、哪个因子最赚钱都会非常清楚。

---

## Cron 定时任务

```bash
# 每天 15:30 收盘后自动跑
30 15 * * 1-5 cd /path/to/SmarkStock && python3 smart_screener.py --top 50 --save >> logs/smart_screen.log 2>&1

# 每周六早上回溯
0 10 * * 6 cd /path/to/SmarkStock && python3 backtest_screener.py >> logs/backtest.log 2>&1
```
