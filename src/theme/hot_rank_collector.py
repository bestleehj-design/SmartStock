# -*- coding: utf-8 -*-
"""
热门板块/个股数据采集器
基于 akshare 拉取概念板块/行业板块涨幅排名、个股人气排名
计算持续热门板块，作为策略2热点交叉验证的数据源

用法:
  python3 hot_rank_collector.py                  # 采集当日数据
  python3 hot_rank_collector.py --backfill 14    # 回填近14天数据
  python3 hot_rank_collector.py --report         # 查看持续热门板块
"""
import sys
import os
import json
import datetime
import time
from collections import defaultdict

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
os.chdir(SCRIPT_DIR)
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

import pymysql
import akshare as ak

DB_CONFIG = {
    'host': 'localhost', 'port': 3306,
    'user': 'root', 'password': '12345678',
    'database': 'gp2', 'charset': 'utf8mb4',
}

# 板块活跃度统计天数
HOT_LOOKBACK_DAYS = 14


def get_db():
    return pymysql.connect(**DB_CONFIG)


def today_str():
    return datetime.date.today().strftime('%Y-%m-%d')


# ============================================================
# 数据采集
# ============================================================

def collect_stock_hot_rank(rank_date=None):
    """采集东方财富个股人气榜当日数据"""
    if rank_date is None:
        rank_date = today_str()
    try:
        df = ak.stock_hot_rank_em()
        records = []
        for _, r in df.iterrows():
            code_raw = str(r['代码'])
            name = str(r['股票名称'])
            rank_val = int(r['当前排名'])

            # 标准化代码格式：如 SZ000725 → 000725.SZ
            prefix = code_raw[:2]
            code_num = code_raw[2:]
            suffix = '.SH' if prefix == 'SH' else '.SZ'
            full_code = code_num + suffix

            records.append((rank_date, full_code, name, rank_val))

        return records
    except Exception as e:
        print(f"  ⚠️ 人气榜采集失败: {e}")
        return []


def collect_board_rank(report_date=None):
    """
    采集概念板块和行业板块当日涨幅排名
    返回: {board_type: [(report_date, board_code, board_name, rank), ...]}
    """
    if report_date is None:
        report_date = today_str()

    result = {'concept': [], 'industry': []}
    sleep_time = 0.5

    # 1. 概念板块
    try:
        df = ak.stock_board_concept_spot_em()
        time.sleep(sleep_time)
        # 按涨跌幅降序排名
        df_sorted = df.sort_values('涨跌幅', ascending=False).head(100)
        for rank, (_, r) in enumerate(df_sorted.iterrows(), 1):
            board_code = str(r['代码'])
            board_name = str(r['名称'])
            chg = float(r['涨跌幅'])
            result['concept'].append({
                'rank_date': report_date,
                'board_code': board_code,
                'board_name': board_name,
                'rank': rank,
                'change_pct': chg,
            })
    except Exception as e:
        print(f"  ⚠️ 概念板块采集失败: {e}")

    # 2. 行业板块
    try:
        df = ak.stock_board_industry_spot_em()
        time.sleep(sleep_time)
        df_sorted = df.sort_values('涨跌幅', ascending=False).head(100)
        for rank, (_, r) in enumerate(df_sorted.iterrows(), 1):
            board_code = str(r['代码'])
            board_name = str(r['名称'])
            chg = float(r['涨跌幅'])
            result['industry'].append({
                'rank_date': report_date,
                'board_code': board_code,
                'board_name': board_name,
                'rank': rank,
                'change_pct': chg,
            })
    except Exception as e:
        print(f"  ⚠️ 行业板块采集失败: {e}")

    return result


def save_board_ranks(board_ranks):
    """保存板块排名到数据库"""
    conn = get_db()
    c = conn.cursor()

    # 确保表存在
    c.execute("""
        CREATE TABLE IF NOT EXISTS hot_board_rank_daily (
            id INT AUTO_INCREMENT PRIMARY KEY,
            rank_date DATE NOT NULL,
            board_code VARCHAR(20) NOT NULL,
            board_name VARCHAR(50),
            board_type ENUM('concept', 'industry') NOT NULL,
            hot_rank INT,
            change_pct FLOAT,
            UNIQUE KEY uk_date_code (rank_date, board_code),
            INDEX idx_date (rank_date),
            INDEX idx_type_date (board_type, rank_date)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)

    saved = 0
    for board_type in ['concept', 'industry']:
        for item in board_ranks.get(board_type, []):
            try:
                c.execute(
                    "INSERT INTO hot_board_rank_daily "
                    "(rank_date, board_code, board_name, board_type, hot_rank, change_pct) "
                    "VALUES (%s,%s,%s,%s,%s,%s) "
                    "ON DUPLICATE KEY UPDATE hot_rank=%s, change_pct=%s",
                    (item['rank_date'], item['board_code'], item['board_name'],
                     board_type, item['rank'], item['change_pct'],
                     item['rank'], item['change_pct'])
                )
                saved += 1
            except Exception:
                pass

    conn.commit()
    c.close()
    conn.close()
    return saved


def save_stock_hot_ranks(records):
    """保存个股人气排名到数据库"""
    if not records:
        return 0
    conn = get_db()
    c = conn.cursor()

    c.execute("""
        CREATE TABLE IF NOT EXISTS hot_stock_rank_daily (
            id INT AUTO_INCREMENT PRIMARY KEY,
            rank_date DATE NOT NULL,
            stock_code VARCHAR(20) NOT NULL,
            stock_name VARCHAR(30),
            hot_rank INT,
            UNIQUE KEY uk_date_code (rank_date, stock_code),
            INDEX idx_date (rank_date),
            INDEX idx_code (stock_code)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)

    saved = 0
    for rec in records:
        try:
            c.execute(
                "INSERT INTO hot_stock_rank_daily (rank_date, stock_code, stock_name, hot_rank) "
                "VALUES (%s,%s,%s,%s) "
                "ON DUPLICATE KEY UPDATE hot_rank=%s",
                (rec[0], rec[1], rec[2], rec[3], rec[3])
            )
            saved += 1
        except Exception:
            pass

    conn.commit()
    c.close()
    conn.close()
    return saved


# ============================================================
# 查询：持续热门板块
# ============================================================

def get_sustained_hot_boards(days=14, min_appear_days=3, top_n=30):
    """
    查询近 days 天内持续热门的板块
    - min_appear_days: 最少出现在榜单天数
    - top_n: 每天取前 N 名统计

    返回: 按综合热度分排序的板块列表
    """
    conn = get_db()
    c = conn.cursor()

    # 近N天日期范围
    c.execute("SELECT DISTINCT rank_date FROM hot_board_rank_daily "
              "WHERE rank_date >= DATE_SUB(CURDATE(), INTERVAL %s DAY) "
              "ORDER BY rank_date", (days,))
    date_rows = c.fetchall()
    total_days = len(date_rows)

    if total_days < min_appear_days:
        print(f"  数据不足: 仅有 {total_days} 天数据")
        c.close()
        conn.close()
        return []

    # 查询每天前 N 名的板块
    c.execute("""
        SELECT board_code, board_name, board_type,
               COUNT(*) as appear_days,
               AVG(hot_rank) as avg_rank,
               AVG(change_pct) as avg_chg,
               GROUP_CONCAT(
                   CONCAT(rank_date, ':', hot_rank, ':', change_pct)
                   ORDER BY rank_date SEPARATOR '|'
               ) as rank_history
        FROM hot_board_rank_daily
        WHERE rank_date >= DATE_SUB(CURDATE(), INTERVAL %s DAY)
          AND hot_rank <= %s
        GROUP BY board_code, board_name, board_type
        HAVING appear_days >= %s
        ORDER BY appear_days DESC, avg_rank ASC
        LIMIT 50
    """, (days, top_n, min_appear_days))

    results = []
    for row in c.fetchall():
        board_code, board_name, board_type, appear_days, avg_rank, avg_chg, hist = row

        # 计算趋势：最近的排名 vs 最早的排名
        entries = hist.split('|')
        ranks = []
        for e in entries:
            parts = e.split(':')
            if len(parts) >= 2:
                ranks.append(int(parts[1]))

        trend = 'stable'
        if len(ranks) >= 3:
            recent_avg = sum(ranks[:3]) / 3
            early_avg = sum(ranks[-3:]) / 3
            if recent_avg < early_avg - 2:
                trend = 'rising'     # 排名在上升（数字越小越好）
            elif recent_avg > early_avg + 2:
                trend = 'declining'

        # 综合热度分 = 出现率 × 50 + 排名分(倒序) × 30 + 涨幅分 × 20
        appear_rate = appear_days / total_days
        rank_score = max(0, (top_n - avg_rank) / top_n)
        chg_score = min(avg_chg / 5, 1) if avg_chg else 0

        heat_score = round(
            appear_rate * 50 + rank_score * 30 + chg_score * 20, 1
        )

        results.append({
            'board_code': board_code,
            'board_name': board_name,
            'board_type': board_type,
            'appear_days': appear_days,
            'total_days': total_days,
            'avg_rank': round(avg_rank, 1),
            'avg_chg': round(avg_chg, 2),
            'trend': trend,
            'heat_score': heat_score,
        })

    c.close()
    conn.close()

    # 排序
    results.sort(key=lambda x: x['heat_score'], reverse=True)
    return results


def get_hot_stocks_cross_check(codes, days=14, min_days=2):
    """
    检查给定股票代码列表中，哪些在近 days 天内上过人气榜
    返回: {code: {appear_days, avg_rank}, ...}
    """
    conn = get_db()
    c = conn.cursor()

    if not codes:
        return {}

    placeholders = ','.join(['%s'] * len(codes))
    c.execute(f"""
        SELECT stock_code, COUNT(*) as days, AVG(hot_rank) as avg_rk
        FROM hot_stock_rank_daily
        WHERE stock_code IN ({placeholders})
          AND rank_date >= DATE_SUB(CURDATE(), INTERVAL %s DAY)
        GROUP BY stock_code
    """, list(codes) + [days])

    result = {}
    for row in c.fetchall():
        result[row[0]] = {
            'appear_days': row[1],
            'avg_rank': round(float(row[2]), 1),
        }

    c.close()
    conn.close()
    return result


# ============================================================
# 主流程
# ============================================================

def collect_daily():
    """采集当日所有数据"""
    today = today_str()
    print(f"\n{'='*60}")
    print(f"  热门排名数据采集 — {today}")
    print(f"{'='*60}")

    # 1. 个股人气榜
    print(f"\n📊 采集个股人气榜...")
    hot_records = collect_stock_hot_rank(today)
    n_saved = save_stock_hot_ranks(hot_records)
    print(f"  已保存 {n_saved} 条个股人气数据")

    # 2. 板块涨幅排名
    print(f"\n📊 采集板块涨幅排名...")
    board_ranks = collect_board_rank(today)
    n_board = save_board_ranks(board_ranks)
    print(f"  已保存 {n_board} 条板块排名数据")
    print(f"  (概念: {len(board_ranks.get('concept', []))} 条, "
          f"行业: {len(board_ranks.get('industry', []))} 条)")

    # 3. 持续热门板块
    print(f"\n📊 近 {HOT_LOOKBACK_DAYS} 天持续热门板块...")
    sustained = get_sustained_hot_boards(days=HOT_LOOKBACK_DAYS,
                                          min_appear_days=3, top_n=30)
    print_sustained_boards(sustained)

    print(f"\n✅ 采集完成\n")


def print_sustained_boards(boards, top_n=20):
    """打印持续热门板块"""
    if not boards:
        print("  无满足条件的板块")
        return

    trend_labels = {'rising': '↑上升', 'declining': '↓下降', 'stable': '→平稳'}
    print(f"\n  持续热门板块 TOP {top_n}:")
    print(f"  {'排名':<5}{'板块名称':<18}{'类型':<8}{'热度分':<8}"
          f"{'在榜':<8}{'均排':<8}{'均涨':<10}{'趋势'}")
    print(f"  {'-'*70}")
    for i, b in enumerate(boards[:top_n], 1):
        trend = trend_labels.get(b['trend'], b['trend'])
        appear_str = f"{b['appear_days']}/{b['total_days']}"
        print(f"  {i:<5}{b['board_name']:<18}{b['board_type']:<8}"
              f"{b['heat_score']:<8.0f}{appear_str:<8}"
              f"{b['avg_rank']:<8.0f}{b['avg_chg']:<+10.2f}{trend}")


def backfill(days=14):
    """回填历史数据"""
    end_date = datetime.date.today()
    for i in range(days):
        d = end_date - datetime.timedelta(days=i)
        d_str = d.strftime('%Y-%m-%d')
        print(f"\n[{i+1}/{days}] {d_str}")

        # 检查该日是否已有数据
        conn = get_db()
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM hot_board_rank_daily WHERE rank_date=%s", (d_str,))
        existing = c.fetchone()[0]
        c.close()
        conn.close()

        if existing > 10:
            print(f"  已有 {existing} 条数据，跳过")
            continue

        # 板块数据
        board_ranks = collect_board_rank(d_str)
        save_board_ranks(board_ranks)
        time.sleep(1)

        # 人气榜数据可能回溯不了（只提供当日），尝试采集
        hot_records = collect_stock_hot_rank(d_str)
        if hot_records:
            save_stock_hot_ranks(hot_records)


def main():
    if len(sys.argv) > 1:
        arg = sys.argv[1]
        if arg == '--backfill':
            days = int(sys.argv[2]) if len(sys.argv) > 2 else 14
            backfill(days)
        elif arg == '--report':
            boards = get_sustained_hot_boards(days=14, min_appear_days=3, top_n=30)
            print_sustained_boards(boards, top_n=50)
        else:
            print("用法: python3 hot_rank_collector.py [--backfill N | --report]")
    else:
        collect_daily()


if __name__ == '__main__':
    main()
