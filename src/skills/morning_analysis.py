# -*- coding: utf-8 -*-
"""
每日盘前综合分析
每天早上 8:00 自动运行，分析：
  1. 隔夜美股走势（道琼斯、纳斯达克、标普500、费城半导体SOX）
  2. 港股走势（恒生指数、国企指数、恒生科技）
  3. 相关板块概念行情（半导体、芯片、PCB、光通信等）
  4. 持仓个股最新新闻舆情（长电科技、中芯国际、兆易创新、沪电股份）

用法:
  python morning_analysis.py                 # 分析最新日期
  python morning_analysis.py 2026-05-29      # 分析指定日期
"""
import sys
import os
import datetime
import time
import traceback
import re

# Ensure src/ directory is in sys.path for package imports
import sys, os
_SRC_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _SRC_DIR not in sys.path:
    sys.path.insert(0, _SRC_DIR)


import akshare as ak
import pymysql

# 数据库配置
DB_CONFIG = {
    'host': 'localhost', 'port': 3306,
    'user': 'root', 'password': '12345678',
    'database': 'gp2', 'charset': 'utf8mb4',
}

# T+0 交易计划配置
TRADING_PLAN = {
    '600584': {'name': '长电科技', 'cost': 78.46, 'shares': 500, 'max_shares': 600, 't_unit': 100},
}

# 卖出计划（含原始目标价，会被 SOX 乘数自动调节）
SELL_PLANS = [
    {'code': '06809', 'name': '澜起科技(HK)', 'action': '必清', 'orig_target': 360},
    {'code': '00981', 'name': '中芯国际(HK)', 'action': '减仓可等', 'orig_target': 74},
    {'code': '688981', 'name': '中芯国际(A)', 'action': '清仓', 'orig_target': 0},
    {'code': '600584', 'name': '长电科技', 'action': '减30%', 'orig_target': 73},
]

# ============================================================
# 配置
# ============================================================

HOLDINGS = [
    # A股
    {'code': '600584', 'name': '长电科技', 'sector': '半导体封测', 'market': 'A'},
    {'code': '688981', 'name': '中芯国际', 'sector': '晶圆代工', 'market': 'A'},
    {'code': '603986', 'name': '兆易创新', 'sector': '存储芯片', 'market': 'A'},
    {'code': '002463', 'name': '沪电股份', 'sector': 'PCB', 'market': 'A'},
    {'code': '002138', 'name': '顺络电子', 'sector': '被动元件/电感', 'market': 'A'},
    {'code': '002384', 'name': '东山精密', 'sector': 'PCB/精密制造', 'market': 'A'},
    {'code': '301591', 'name': '肯特股份', 'sector': '工程塑料', 'market': 'A'},
    # 港股
    {'code': '00981', 'name': '中芯国际(HK)', 'sector': '晶圆代工', 'market': 'HK'},
    {'code': '06809', 'name': '澜起科技(HK)', 'sector': '内存接口芯片/DDR5', 'market': 'HK'},
]

# 相关板块关键词
RELATED_SECTORS = ['半导体', '芯片', 'PCB', '集成电路', '光通信', 'CPO', '先进封装',
                   '存储芯片', '电子元件', '消费电子', '第三代半导体', '算力',
                   'AI PC', 'AI手机', '英伟达', 'DDR5', '内存', '精密制造',
                   '服务器', '数据中心']

# 情感分析关键词库
NEGATIVE_KEYWORDS = {
    -3: ['跌停', '违规', '立案', '调查', '监管', '处罚', '问询函',
         '业绩变脸', '退市风险', '质押爆仓', '债务违约', '商誉减值', '停产'],
    -2: ['利空', '减持', '亏损', '暴跌', '诉讼', '爆雷', '被处罚',
         '资金占用', '大股东占款', '信息披露违规', '财务造假', '终止重组',
         '资产减值', '被ST', '*ST', '审计非标', '担保风险'],
    -1: ['预亏', '下滑', '下降', '预降', '退市', '暴雷', '停牌', '限售解禁',
         '股东减持', '股权冻结'],
}

POSITIVE_KEYWORDS = {
    +2: ['涨停', '利好', '增持', '回购', '业绩预增', '超预期', '中标', '重组成功', '签订合同'],
    +1: ['增长', '突破', '新产品', '获批', '分红', '政策支持', '产能释放', '订单增长',
         '业绩大增', '扭亏', '预盈'],
}


def analyze_sentiment(title, content=''):
    """关键词匹配情感分析，返回 (score, label, matched_keywords)"""
    text = (title + ' ' + content[:150]).lower()
    total_score = 0
    matched = []
    for weight, keywords in NEGATIVE_KEYWORDS.items():
        for kw in keywords:
            if kw in text:
                total_score += weight
                matched.append({'keyword': kw, 'weight': weight})
    for weight, keywords in POSITIVE_KEYWORDS.items():
        for kw in keywords:
            if kw in text:
                total_score += weight
                matched.append({'keyword': kw, 'weight': weight})
    if total_score < 0:
        label = 'negative'
    elif total_score > 0:
        label = 'positive'
    else:
        label = 'neutral'
    return total_score, label, matched


# ============================================================
# 1. 隔夜美股
# ============================================================

def update_sox_db():
    """从akshare拉最新SOX数据并更新MySQL（增量，不重复插入）"""
    try:
        df = ak.macro_global_sox_index()
        if df is None or len(df) == 0:
            return
        conn = pymysql.connect(**DB_CONFIG)
        cursor = conn.cursor()
        latest = df.tail(5)  # 只更新最近5天
        count = 0
        for _, row in latest.iterrows():
            try:
                cursor.execute('''
                    INSERT INTO sox_index_tbl (tradedate, close, chg_pct, chg_3m, chg_6m, chg_1y)
                    VALUES (%s,%s,%s,%s,%s,%s)
                    ON DUPLICATE KEY UPDATE close=VALUES(close), chg_pct=VALUES(chg_pct)
                ''', (
                    str(row['日期']), float(row['最新值']),
                    float(row['涨跌幅']) if row['涨跌幅'] and row['涨跌幅'] != 'None' else None,
                    float(row.get('近3月涨跌幅', 0) or 0) if row.get('近3月涨跌幅') else None,
                    float(row.get('近6月涨跌幅', 0) or 0) if row.get('近6月涨跌幅') else None,
                    float(row.get('近1年涨跌幅', 0) or 0) if row.get('近1年涨跌幅') else None,
                ))
                count += 1
            except:
                pass
        conn.commit()
        cursor.close()
        conn.close()
    except Exception:
        pass  # 更新失败不影响主流程


def fetch_us_market():
    """获取美股主要指数行情"""
    print(">>> 获取美股指数数据...")
    # 先更新SOX数据库
    try:
        update_sox_db()
    except:
        pass
    indices = {
        '.DJI': '道琼斯工业',
        '.IXIC': '纳斯达克',
        '.INX': '标普500',
        '.NDX': '纳斯达克100',
    }
    result = {}

    for symbol, name in indices.items():
        try:
            df = ak.index_us_stock_sina(symbol=symbol)
            latest = df.iloc[-1]
            prev = df.iloc[-2] if len(df) > 1 else latest
            close_val = float(latest['close'])
            prev_close = float(prev['close'])
            change = close_val - prev_close
            change_pct = (change / prev_close * 100) if prev_close != 0 else 0
            result[symbol] = {
                'name': name,
                'close': close_val,
                'change': round(float(change), 2),
                'change_pct': round(float(change_pct), 2),
                'date': str(latest['date']),
            }
            print(f"  {name}: {result[symbol]['close']:.2f} ({result[symbol]['change_pct']:+.2f}%)")
            time.sleep(0.5)
        except Exception as e:
            print(f"  {name}: 获取失败 - {e}")

    # 费城半导体指数 SOX（从 MySQL 读取）
    try:
        conn_sox = pymysql.connect(**DB_CONFIG)
        cur_sox = conn_sox.cursor()
        cur_sox.execute("SELECT close FROM sox_index_tbl ORDER BY tradedate DESC LIMIT 2")
        rows_sox = cur_sox.fetchall()
        cur_sox.close()
        conn_sox.close()
        if rows_sox and len(rows_sox) >= 2:
            close_val = float(rows_sox[0][0])
            prev_val = float(rows_sox[1][0])
            change = close_val - prev_val
            change_pct = (change / prev_val * 100) if prev_val else 0
            result['SOX'] = {
                'name': '费城半导体',
                'close': close_val,
                'change': round(float(change), 2),
                'change_pct': round(float(change_pct), 2),
                'date': '',
            }
            print(f"  费城半导体: {result['SOX']['close']:.2f} ({result['SOX']['change_pct']:+.2f}%)")
        else:
            print(f"  费城半导体: MySQL 数据不完整")
    except Exception as e:
        print(f"  费城半导体: 获取失败 - {e}")

    return result


# ============================================================
# 2. 港股走势
# ============================================================

def fetch_hk_market():
    """获取港股主要指数"""
    print("\n>>> 获取港股指数数据...")
    indices = {
        'HSI': '恒生指数',
        'HSCEI': '国企指数',
        'HSTECH': '恒生科技',
    }
    result = {}

    for symbol, name in indices.items():
        try:
            df = ak.stock_hk_index_daily_sina(symbol=symbol)
            if df is not None and len(df) > 1:
                latest = df.iloc[-1]
                prev = df.iloc[-2]
                change = latest['close'] - prev['close']
                change_pct = (change / prev['close'] * 100) if prev['close'] else 0
                result[symbol] = {
                    'name': name,
                    'close': float(latest['close']),
                    'change': round(float(change), 2),
                    'change_pct': round(float(change_pct), 2),
                    'date': str(latest['date']),
                }
                print(f"  {name}: {result[symbol]['close']:.2f} ({result[symbol]['change_pct']:+.2f}%)")
            time.sleep(0.5)
        except Exception as e:
            print(f"  {name}: 获取失败 - {e}")

    return result


# ============================================================
# 3. 板块概念行情
# ============================================================

def fetch_sector_data():
    """
    获取全市场概念板块排名，不再用固定关键词过滤。
    返回: { 'all_concepts': 全部板块(涨幅排序), 'holding_concepts': 持仓关联板块 }
    """
    print("\n>>> 获取板块轮动数据...")
    result = {'all_concepts': [], 'holding_concepts': [], 'fund_flow': []}

    # 全市场概念板块 (涨幅TOP + 跌幅TOP)
    try:
        df = ak.stock_board_concept_spot_em()
        if df is not None and len(df) > 0:
            all_list = []
            for _, row in df.iterrows():
                name = str(row.get('板块名称', '') or row.get('name', ''))
                chg = float(row.get('涨跌幅', 0) or 0)
                all_list.append({
                    'name': name,
                    'change_pct': chg,
                    'lead_stock': str(row.get('领涨股', '') or ''),
                })
                # 同时收集持仓关联板块
                if any(k in name for k in RELATED_SECTORS):
                    result['holding_concepts'].append(all_list[-1])
            # 全部按涨幅排序
            result['all_concepts'] = sorted(all_list, key=lambda x: x['change_pct'], reverse=True)
            result['holding_concepts'].sort(key=lambda x: x['change_pct'], reverse=True)
            print(f"  概念板块: 全市场 {len(all_list)} 个, 持仓关联 {len(result['holding_concepts'])} 个")
    except Exception as e:
        print(f"  概念板块: 获取失败 - {e}")

    time.sleep(1)

    # 板块资金流 (检测资金从哪流出、流向哪)
    try:
        df = ak.stock_sector_fund_flow_rank(indicator='今日', sector_type='行业资金流')
        if df is not None and len(df) > 0:
            for _, row in df.iterrows():
                name = str(row.get('名称', '') or '')
                net_flow = float(row.get('主力净流入-净额', 0) or 0)
                result['fund_flow'].append({
                    'name': name,
                    'net_flow': net_flow,
                })
            result['fund_flow'].sort(key=lambda x: x['net_flow'], reverse=True)
            print(f"  板块资金流: 获取 {len(result['fund_flow'])} 个行业")
    except Exception as e:
        print(f"  板块资金流: 获取失败 - {e}")

    return result


# ============================================================
# 4. 持仓个股新闻
# ============================================================

def fetch_stock_news():
    """获取每只持仓个股的最新新闻并做情感分析（支持A股和港股）"""
    print("\n>>> 获取持仓个股新闻...")
    result = {}

    for stock in HOLDINGS:
        code = stock['code']
        name = stock['name']
        market = stock.get('market', 'A')
        label_market = 'A股' if market == 'A' else '港股'
        print(f"\n  [{name}] {code} ({label_market})")

        df = None
        try:
            if market == 'A':
                # A股新闻
                df = ak.stock_news_em(symbol=code)
            else:
                # 港股新闻：尝试东方财富港股新闻接口
                try:
                    df = ak.stock_news_em(symbol=code)
                except Exception:
                    pass
                if df is None or len(df) == 0:
                    # 降级：尝试通过 stock_hk_hist 获取近期走势作为参考
                    result[code] = {
                        'name': name, 'sector': stock.get('sector', ''),
                        'news': [], 'total': 0, 'neg_count': 0,
                        'summary': '港股新闻源暂不可用',
                    }
                    print(f"    港股新闻源暂不可用")
                    continue

            if df is None or len(df) == 0:
                result[code] = {'name': name, 'sector': stock.get('sector', ''),
                                'news': [], 'total': 0, 'neg_count': 0,
                                'summary': '无新闻'}
                print(f"    未获取到新闻")
                continue

            news_list = []
            neg_count = 0

            for _, row in df.head(30).iterrows():
                title = str(row.get('新闻标题', '') or row.get('content', '') or '').strip()
                content = str(row.get('新闻内容', '') or '').strip()
                pub_date = str(row.get('发布时间', '') or row.get('datetime', '')).strip()
                source = str(row.get('文章来源', '') or row.get('source', '') or '东方财富').strip()

                if not title:
                    continue

                score, label, matched = analyze_sentiment(title, content)
                if label == 'negative':
                    neg_count += 1

                news_item = {
                    'title': title[:120],
                    'date': pub_date[:10],
                    'source': source,
                    'score': score,
                    'label': label,
                    'matched': matched,
                }
                if len(news_list) < 10:
                    news_list.append(news_item)

            result[code] = {
                'name': name,
                'sector': stock.get('sector', ''),
                'news': news_list,
                'total': min(len(df), 30),
                'neg_count': neg_count,
            }
            print(f"    共 {len(df)} 条, 负面 {neg_count} 条")

        except Exception as e:
            result[code] = {'name': name, 'news': [], 'summary': f'获取失败: {e}'}
            print(f"    获取失败: {e}")

        time.sleep(1)

    return result


# ============================================================
# 5. 打印报告
# ============================================================

# ============================================================
# T+0 交易计划
# ============================================================

def get_technical_data(code):
    """从数据库获取个股技术指标和支撑位"""
    try:
        conn = pymysql.connect(**DB_CONFIG)
        cursor = conn.cursor()
        cursor.execute('''
            SELECT close FROM daily_info_tbl
            WHERE code = %s ORDER BY tradedate ASC
        ''', (code + '.SH',))
        rows = cursor.fetchall()
        cursor.close()
        conn.close()

        if len(rows) < 60:
            return None

        closes = [float(r[0]) for r in rows[-90:]]
        current = closes[-1]

        def ma(arr, n):
            return sum(arr[-n:]) / n if len(arr) >= n else arr[-1]

        # 找关键支撑位
        swing_high = max(closes[-15:]) if len(closes) >= 15 else max(closes)

        # 在当前回调段内找支撑：从近期高点以来（排除今天）的最低点
        # 如果当前就在创新低，说明近端支撑全破，用MA20作为下一参考
        high_idx = closes[-15:].index(swing_high) + len(closes) - 15
        pullback_data = closes[high_idx:-1]  # 从高点到昨天
        near_support = min(pullback_data) if pullback_data else None

        # 如果近端支撑仍在现价上方 → 已破位，显示"暂无近端支撑"
        if near_support is None or near_support > current:
            support1 = None  # 触发"正在创新低"逻辑
        else:
            support1 = near_support

        return {
            'close': current,
            'ma5': ma(closes, 5),
            'ma10': ma(closes, 10),
            'ma20': ma(closes, 20),
            'ma30': ma(closes, 30),
            'support1': support1,
            'swing_high': swing_high,
        }
    except Exception as e:
        print(f"  ⚠️ 获取技术数据失败: {e}")
        return None


def print_trading_plan():
    """打印长电科技 T+0 操作计划"""
    plan = TRADING_PLAN.get('600584')
    if not plan:
        return

    tech = get_technical_data('600584')
    if not tech:
        print(f"\n{'─'*70}")
        print(f"  📋 T+0 操作计划 - 长电科技 (600584)")
        print(f"{'─'*70}")
        print(f"  ⚠️ 无法获取技术数据，请手动确认支撑位")
        return

    cost = plan['cost']
    current = tech['close']
    shares = plan['shares']
    t_unit = plan['t_unit']
    max_shares = plan['max_shares']
    profit = (current - cost) / cost * 100

    support1 = tech.get('support1')
    support2 = tech['ma20']
    resist1 = tech['ma10']
    resist2 = tech['ma5']

    print(f"\n{'─'*70}")
    print(f"  📋 T+0 操作计划 — 长电科技 (600584)")
    print(f"{'─'*70}")

    # 仓位状态
    loss_color = '🔴' if profit < 0 else '🟢'
    print(f"\n  📊 仓位: {shares}股 | 成本 {cost} | 现价 {current:.2f} | {loss_color} {'亏损' if profit<0 else '盈利'} {profit:+.1f}%")
    print(f"  💰 可用子弹: {max_shares - shares}股 (T+0做多) 或 卖出{max_shares - (shares-t_unit)}股底仓 (T+0做空)")

    # 关键价位
    print(f"\n  🎯 关键价位")
    print(f"  ┌─────────────────────────────────────┐")
    print(f"  │ 近期高点: {tech['swing_high']:>8.2f}                    │")
    print(f"  │ 成本线:   {cost:>8.2f}  ← 你的成本         │")
    print(f"  │ MA10:     {tech['ma10']:>8.2f}  ← 反弹第一压力       │")
    print(f"  │ 现价:     {current:>8.2f}  ← 当前位置          │")
    if support1:
        print(f"  │ 近端支撑: {support1:>8.2f}  ← 下探目标/买入区     │")
    else:
        print(f"  │ 近端支撑:   ⚠️已破   ← 下一支撑MA20={tech['ma20']:.2f}  │")
    print(f"  │ MA20:     {tech['ma20']:>8.2f}  ← 强支撑/加仓位       │")
    print(f"  └─────────────────────────────────────┘")

    # 三种情景
    print(f"\n  🔮 今日三种情景与操作")
    print(f"  {'─'*55}")

    # 情景一：先下探再反弹（最可能）
    if support1:
        buy_price = round(support1 * 1.005, 2)  # 支撑位上方0.5%
        sell_price = round(resist1 * 0.995, 2) if resist1 > buy_price else round(buy_price * 1.04, 2)
        print(f"\n  📍 情景一: 低开下探 → 止跌反弹 【概率最高】")
        print(f"    ① 等待下探至 {support1:.2f} 附近")
        print(f"    ② 确认止跌信号后, 买入 {t_unit} 股 @ ~{buy_price:.2f}")
        print(f"    ③ 反弹目标 {sell_price:.2f} 卖出, 盈利 ~{max(0, (sell_price-buy_price)*t_unit):.0f} 元")
        print(f"    ④ 成本从 {cost} → {cost - max(0, (sell_price-buy_price)*t_unit/shares):.2f}")
    else:
        print(f"\n  📍 情景一: 低开下探 → 等企稳再做 ⚠️")
        print(f"    ⚠️ 近端支撑全破, 正在创新低!")
        print(f"    下一支撑看 MA20 = {tech['ma20']:.2f}")
        print(f"    建议等 K线出现下影线止跌 或 站回{current:.2f}以上再考虑操作")

    # 情景二：反弹到成本附近（做空T）
    sell_t_price = round(cost * 0.995, 2)
    buy_back_price = round(current, 2)
    if sell_t_price > current + 1:
        print(f"\n  📍 情景二: 反弹至成本附近 → 冲高回落")
        print(f"    ① 反弹至 {sell_t_price} 附近缩量滞涨")
        print(f"    ② 先卖 {t_unit} 股 @ ~{sell_t_price}")
        print(f"    ③ 回落至 {buy_back_price} 买回, 盈利 ~{max(0, (sell_t_price-buy_back_price)*t_unit):.0f} 元")

    # 情景三：破位
    print(f"\n  📍 情景三: 继续放量下跌 → 止损不做")
    print(f"    ⛔ 放量跌破 {tech['ma20']:.2f} → 止损, 不接飞刀")
    print(f"    ⛔ 今天不做T, 等明天")

    # 三步确认
    print(f"\n  ✅ 三步确认流程 (10点前不动手)")
    print(f"  {'─'*55}")
    print(f"  第①步 9:30-9:40  看开盘价")
    if support1:
        print(f"    ├→ 开在 {support1:.0f} 以上 → 偏强, 观察反弹")
        print(f"    └→ 开在 {support1:.0f} 以下 → 等下探再决定")
    else:
        print(f"    ├→ 开在 {current:.0f} 以上 → 企稳信号, 观察")
        print(f"    └→ 继续低开 → 等下探后看是否能收回")
    print(f"  第②步 9:40-10:00 等下探到位")
    if support1:
        print(f"    ├→ 跌到支撑附近横盘不创新低 → ✅ 信号出现")
    else:
        print(f"    ├→ 不创新低 + 出现下影线 → ✅ 信号出现")
    print(f"    └→ 跌破支撑且加速 → ❌ 放弃今天")
    print(f"  第③步 10:00之后   确认企稳")
    print(f"    ├→ 价格反弹 + 量缩小 → ✅ 可以买入")
    print(f"    ├→ 继续阴跌 → ❌ 继续等")
    print(f"    └→ 反弹无力 → ❌ 等尾盘")

    # 铁律
    print(f"\n  ⚠️ 铁律")
    print(f"  {'─'*55}")
    print(f"  1. 当天买必须当天卖, 绝不加仓过夜")
    print(f"  2. 不追高, 只在支撑位买入")
    print(f"  3. 有2-3元差价就收, 不贪")
    print(f"  4. 放量破位就放弃, 不接飞刀")


def extract_hot_keywords(titles, top_n=10):
    """
    从新闻标题中提取有意义的主题/概念词，发现今日热门方向。
    不依赖分词库，直接扫描预设的关键主题词库，统计出现频次。
    """
    # 主题词库: 产品/技术/公司/事件 — 按类别组织
    THEME_WORDS = [
        # AI / 算力
        '英伟达', 'NVIDIA', 'AI PC', 'AI手机', '人工智能', '算力', '大模型',
        'GPT', 'ChatGPT', 'GPU', 'HBM', '光模块', 'CPO', '800G', '1.6T',
        '服务器', '数据中心', '液冷', '铜缆', 'DAC', 'AEC',
        # 半导体
        '先进封装', 'Chiplet', '2.5D', '3D封装', '晶圆代工', '封测',
        '光刻机', '光刻胶', 'EDA', 'IP授权', 'RISC-V', 'ARM',
        '存储芯片', 'DRAM', 'NAND', 'HBM', '第三代半导体', 'SiC', 'GaN',
        # 消费电子 / PC
        '苹果', '华为', '三星', '小米', 'OPPO', 'vivo',
        'PC', '笔记本电脑', '手机', '可穿戴', 'MR', 'VR', 'AR', '眼镜',
        '折叠屏', '铰链', '钛合金', 'MIM',
        # 通讯
        '5G', '6G', '卫星通信', '低轨卫星', '星链', '商业航天',
        # 新能源
        '光伏', '储能', '锂电', '固态电池', '钠电池', '氢能',
        '新能源汽车', '自动驾驶', '智能驾驶', '激光雷达',
        # 政策 / 事件
        '国家大基金', '集成电路大基金', '中美', '关税', '制裁', '出口管制',
        '重组', 'IPO', '过会', '注册制', '退市',
        '分红', '回购', '增持', '减持', '质押', '解禁',
        # 板块
        '半导体', '芯片', 'PCB', '光通信', '消费电子', '电力', '煤炭',
        '银行', '券商', '医药', '军工',
    ]

    from collections import Counter
    word_counter = Counter()

    for title in titles:
        for word in THEME_WORDS:
            if word in title:
                word_counter[word] += 1

    # 过滤只出现1次的，取top_n
    return [(w, c) for w, c in word_counter.most_common(top_n * 2) if c >= 2][:top_n]


def adjust_targets_by_sox(sox_chg):
    """根据 SOX 涨跌幅自动调整卖出目标价，返回调整后的列表"""
    if sox_chg is None:
        return []

    if sox_chg >= 7:
        multiplier = 1.02          # SOX+7% → 实际次日平均+2%
        note = f'SOX{sox_chg:+.1f}% → 目标上调2%'
    elif sox_chg >= 5:
        multiplier = 1.015         # SOX+5% → 实际次日平均+1.5%
        note = f'SOX{sox_chg:+.1f}% → 目标上调1.5%'
    elif sox_chg >= 3:
        multiplier = 1.01          # SOX+3% → 实际次日平均+1%
        note = f'SOX{sox_chg:+.1f}% → 目标上调1%'
    elif sox_chg <= -5:
        multiplier = 0.99          # SOX-5% → 加速出货-1%
        note = f'SOX{sox_chg:+.1f}% → 目标下调1%（加速出货）'
    else:
        return []

    result = []
    for plan in SELL_PLANS:
        orig = plan['orig_target']
        if orig == 0:
            result.append({'name': plan['name'], 'action': plan['action'],
                          'orig_target': '市价', 'adj_target': '市价'})
            continue
        adj = f'{orig * multiplier:.1f}'
        result.append({'name': plan['name'], 'action': plan['action'],
                      'orig_target': f'{orig:.0f}', 'adj_target': adj})

    return result, note


def print_report(us_data, hk_data, sector_data, news_data):
    """格式化输出盘前分析报告"""
    now = datetime.datetime.now()
    print(f"\n\n{'='*70}")
    print(f"    📊 每日盘前综合分析报告")
    print(f"    {now.strftime('%Y-%m-%d %H:%M')} (星期{['一','二','三','四','五','六','日'][now.weekday()]})")
    print(f"{'='*70}")

    # ---- 隔夜美股 ----
    print(f"\n{'─'*70}")
    print(f"  🇺🇸 隔夜美股")
    print(f"{'─'*70}")
    if us_data:
        for sym, data in us_data.items():
            name = data['name']
            close = data['close']
            chg_pct = data['change_pct']
            arrow = '🔴' if chg_pct < 0 else '🟢'
            print(f"  {arrow} {name:12s}: {close:>12.2f}  ({chg_pct:+.2f}%)")
    else:
        print("  (暂无数据)")

    # 美股对A股影响判断
    nasdaq_chg = 0
    sox_chg = 0
    if us_data:
        nasdaq = us_data.get('.IXIC', {})
        sox = us_data.get('SOX', {})
        nasdaq_chg = nasdaq.get('change_pct', 0)
        sox_chg = sox.get('change_pct', 0)
        if nasdaq_chg > 1:
            print(f"  💡 纳指涨{nasdaq_chg:+.2f}%，利好科技股情绪")
        elif nasdaq_chg < -1:
            print(f"  ⚠️  纳指跌{nasdaq_chg:+.2f}%，科技股承压")
        if sox_chg > 2:
            print(f"  💡 费城半导体涨{sox_chg:+.2f}%，利好半导体板块")
        elif sox_chg < -2:
            print(f"  ⚠️  费城半导体跌{sox_chg:+.2f}%，半导体板块承压")

    # ---- SOX 目标价自动调整 ----
    if us_data:
        sox_chg_val = us_data.get('SOX', {}).get('change_pct', 0)
        adj_result = adjust_targets_by_sox(sox_chg_val)
        if adj_result:
            adjusted, note = adj_result
            print(f"\n  🎯 卖出目标自动调整 ({note})")
            for item in adjusted:
                arrow = '⬆' if '上调' in note else '⬇' if '下调' in note else '→'
                print(f"    {arrow} {item['name']:14s} [{item['action']}]  "
                      f"{item['orig_target']} → {item['adj_target']}")

    # ---- 港股 ----
    print(f"\n{'─'*70}")
    print(f"  🇭🇰 港股走势")
    print(f"{'─'*70}")
    if hk_data:
        for sym, data in hk_data.items():
            name = data['name']
            close = data['close']
            chg_pct = data['change_pct']
            arrow = '🔴' if chg_pct < 0 else '🟢'
            print(f"  {arrow} {name:12s}: {close:>12.2f}  ({chg_pct:+.2f}%)")
    else:
        print("  (暂无数据)")

    # ---- 板块轮动风向标 ----
    print(f"\n{'─'*70}")
    print(f"  🔥 板块轮动风向标")
    print(f"{'─'*70}")

    all_concepts = sector_data.get('all_concepts', [])
    holding_concepts = sector_data.get('holding_concepts', [])
    fund_flow = sector_data.get('fund_flow', [])

    if all_concepts:
        # 全市场涨幅TOP10 → 发现今日热门方向
        top10 = all_concepts[:10]
        print(f"\n  📈 全市场涨幅 TOP10 (资金往哪去)")
        for i, item in enumerate(top10, 1):
            arrow = '🔴' if item['change_pct'] < 0 else '🟢'
            lead = f" →{item['lead_stock']}" if item.get('lead_stock') and item['lead_stock'] != '无' else ''
            print(f"    {i:2d}. {arrow} {item['name']:14s} {item['change_pct']:+.2f}%{lead}")

        # 全市场跌幅TOP5 → 发现弃子
        bottom5 = all_concepts[-5:]
        bottom5.reverse()
        print(f"\n  📉 全市场跌幅 TOP5 (钱从哪走)")
        for i, item in enumerate(bottom5, 1):
            lead = f" →{item['lead_stock']}" if item.get('lead_stock') and item['lead_stock'] != '无' else ''
            print(f"    {i:2d}. 🔴 {item['name']:14s} {item['change_pct']:+.2f}%{lead}")

        # 资金流入流出TOP3
        if fund_flow:
            print(f"\n  💰 板块资金流 TOP3")
            print(f"    流入:  ", end='')
            inflows = [f for f in fund_flow[:15] if f['net_flow'] > 0][:3]
            print(' | '.join(f"{f['name']} +{f['net_flow']/1e8:.1f}亿" for f in inflows))
            print(f"    流出:  ", end='')
            outflows = [f for f in reversed(fund_flow[-15:]) if f['net_flow'] < 0][:3]
            print(' | '.join(f"{f['name']} {f['net_flow']/1e8:.1f}亿" for f in outflows))

    if holding_concepts:
        print(f"\n  🎯 持仓关联概念 (你的持仓在什么风向上)")
        for item in holding_concepts[:12]:
            arrow = '🔴' if item['change_pct'] < 0 else '🟢'
            print(f"    {arrow} {item['name']:14s} {item['change_pct']:+.2f}%")
    else:
        print(f"\n  🎯 持仓关联概念: (暂无数据，请在国内网络环境运行)")

    # ---- 新闻热词 ----
    print(f"\n  📊 今日新闻热词")
    all_titles = []
    for stock in HOLDINGS:
        data = news_data.get(stock['code'], {})
        for n in data.get('news', []):
            all_titles.append(n.get('title', ''))
    hot_words = extract_hot_keywords(all_titles)
    if hot_words:
        for word, count in hot_words[:10]:
            print(f"    🔑 {word}: 出现 {count} 次")
    else:
        print(f"    (暂无)")

    # ---- 持仓新闻 ----
    print(f"\n{'─'*70}")
    print(f"  📰 持仓个股新闻舆情")
    print(f"{'─'*70}")

    for stock in HOLDINGS:
        code = stock['code']
        name = stock['name']
        data = news_data.get(code, {})
        news_list = data.get('news', [])
        neg_count = data.get('neg_count', 0)

        print(f"\n  [{name}] {stock['sector']} ({code})")
        if not news_list:
            print(f"    暂无近期新闻")
            continue

        # 负面统计
        if neg_count > 0:
            print(f"    ⚠️  负面新闻: {neg_count} 条")
        else:
            print(f"    ✅ 无负面新闻")

        for i, n in enumerate(news_list[:5]):
            emoji = '🔴' if n['label'] == 'negative' else '🟢' if n['label'] == 'positive' else '⚪'
            kw_str = ''
            if n['matched']:
                kw_str = ' [' + ', '.join(f"{m['keyword']}({m['weight']})" for m in n['matched']) + ']'
            print(f"    {emoji} [{n['date']}] {n['title'][:80]}{kw_str}")

    # ---- 综合判断 ----
    print(f"\n{'─'*70}")
    print(f"  🎯 综合判断")
    print(f"{'─'*70}")

    # 美股影响
    bull_signals = 0
    bear_signals = 0
    if us_data:
        nasdaq_chg = us_data.get('.IXIC', {}).get('change_pct', 0)
        sox_chg = us_data.get('SOX', {}).get('change_pct', 0)
        if nasdaq_chg > 0.5:
            bull_signals += 1
        elif nasdaq_chg < -0.5:
            bear_signals += 1
        if sox_chg > 1:
            bull_signals += 2
        elif sox_chg < -1:
            bear_signals += 2

    # 板块走势
    if sector_data.get('concepts'):
        avg_pct = sum(c['change_pct'] for c in sector_data['concepts']) / len(sector_data['concepts'])
        if avg_pct > 1:
            bull_signals += 1
        elif avg_pct < -1:
            bear_signals += 1

    # 个股负面新闻
    total_neg = sum(data.get('neg_count', 0) for data in news_data.values())
    if total_neg > 5:
        bear_signals += 2
    elif total_neg > 2:
        bear_signals += 1

    if bull_signals > bear_signals + 2:
        judgment = '偏多'
        print(f"  🟢 偏多信号 (利好因素较多，关注科技股反弹机会)")
    elif bear_signals > bull_signals + 2:
        judgment = '偏空'
        print(f"  🔴 偏空信号 (利空因素较多，注意风险控制)")
    elif bear_signals > bull_signals:
        judgment = '偏谨慎'
        print(f"  🟡 偏谨慎 (略偏空，建议观望)")
    elif bull_signals > bear_signals:
        judgment = '偏乐观'
        print(f"  🟡 偏乐观 (略偏多，可适当参与)")
    else:
        judgment = '中性'
        print(f"  ⚪ 中性 (多空平衡，待方向明确)")

    print(f"  多头信号: {bull_signals}  空头信号: {bear_signals}")

    # ---- T+0 操作计划 ----
    print_trading_plan()

    print(f"\n{'='*70}")
    print(f"  报告完毕: {now.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*70}\n")

    return {
        'sox_chg': sox_chg,
        'nasdaq_chg': nasdaq_chg,
        'bull_signals': bull_signals,
        'bear_signals': bear_signals,
        'judgment': judgment,
        'hot_words': hot_words[:3],
    }


def update_trading_plan(summary_data):
    """将盘前分析摘要写入 trading_plan.md"""
    now = datetime.datetime.now()
    today_str = now.strftime('%Y-%m-%d')

    project_root = os.path.dirname(_SRC_DIR)
    plan_path = os.path.join(project_root, 'trading_plan.md')

    if not os.path.exists(plan_path):
        print(">>> trading_plan.md 不存在，跳过更新")
        return

    with open(plan_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # 1. Update title date
    content = re.sub(r'# 交易计划 — \d{4}-\d{2}-\d{2}',
                     f'# 交易计划 — {today_str}', content)

    # 2. Build morning summary line
    sox = summary_data['sox_chg']
    nasdaq = summary_data['nasdaq_chg']
    bull = summary_data['bull_signals']
    bear = summary_data['bear_signals']
    judgment = summary_data['judgment']
    hot_words = summary_data['hot_words']

    summary = f"- {today_str}盘前: SOX {sox:+.1f}%, 纳指 {nasdaq:+.1f}% | {judgment}(多{bull}空{bear})"
    if hot_words:
        words = ', '.join(w for w, _ in hot_words)
        summary += f" | 热门: {words}"

    # Skip if this morning's record already exists
    if f'- {today_str}盘前:' in content:
        print(f">>> {today_str} 盘前记录已存在，跳过更新")
        return

    # 3. Prepend to 盘前分析记录 section
    pan_start = content.find('## 盘前分析记录')
    if pan_start != -1:
        after_heading = content[pan_start:]
        first_dash = re.search(r'\n(- 20\d\d)', after_heading)
        if first_dash:
            dash_pos = pan_start + first_dash.start(1)
            content = content[:dash_pos] + summary + '\n' + content[dash_pos:]

    # 4. Write back
    with open(plan_path, 'w', encoding='utf-8') as f:
        f.write(content)

    print(f">>> trading_plan.md 已更新盘前摘要 ({today_str})")


# ============================================================
# 主入口
# ============================================================

def main():
    print(f"\n{'#'*70}")
    print(f"# 每日盘前综合分析")
    print(f"# 运行时间: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"# 持仓: {', '.join(s['name'] for s in HOLDINGS)}")
    print(f"{'#'*70}")

    # 1. 隔夜美股
    us_data = fetch_us_market()

    # 2. 港股走势
    hk_data = fetch_hk_market()

    # 3. 板块概念行情
    sector_data = fetch_sector_data()

    # 4. 持仓个股新闻
    news_data = fetch_stock_news()

    # 5. 打印报告
    summary_data = print_report(us_data, hk_data, sector_data, news_data)

    # 6. 更新 trading_plan.md
    print(">>> 更新 trading_plan.md 盘前摘要...")
    update_trading_plan(summary_data)


if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        print(f"\n!!! 分析出错: {e}")
        traceback.print_exc()
