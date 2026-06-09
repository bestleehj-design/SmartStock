# -*- coding: utf-8 -*-
"""
仓位管理器
基于凯利公式 + 市场情绪调整 + 分批建仓计划，输出仓位建议

核心公式:
  f* = (p × b - (1-p)) / b
  其中 p=预测胜率, b=赔率(止盈/止损)

用法:
  python3 position_sizer.py CODE                # 单票仓位建议
  python3 position_sizer.py CODE --p 0.7 --b 2.5  # 手动指定参数
"""
import sys
import os
import datetime

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
os.chdir(SCRIPT_DIR)
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

import pymysql

DB_CONFIG = {
    'host': 'localhost', 'port': 3306,
    'user': 'root', 'password': '12345678',
    'database': 'gp2', 'charset': 'utf8mb4',
}


class PositionSizer:
    """仓位计算器"""

    # 默认参数
    MAX_SINGLE_POS = 0.25        # 单票上限 25%
    MAX_TOTAL_POS = 0.80         # 总仓位上限 80%
    MIN_CASH = 0.20              # 最少保留现金 20%
    DEFAULT_STOP_LOSS_PCT = 0.08  # 默认止损 -8%

    def __init__(self, total_capital=None):
        """
        total_capital: 总资金（默认从配置或环境变量读取，这里用 None 表示按比例输出）
        """
        self.total_capital = total_capital

    # ================================================================
    # 市场情绪判断
    # ================================================================

    def assess_market_sentiment(self):
        """
        从数据库当日行情数据判断市场情绪
        返回: (sentiment, multiplier)
        """
        conn = pymysql.connect(**DB_CONFIG)
        c = conn.cursor()

        try:
            # 获取最新交易日
            c.execute("SELECT MAX(tradedate) FROM daily_info_tbl")
            latest_date = c.fetchone()[0]
            if not latest_date:
                return 'neutral', 1.0

            # 统计涨跌停数量（简化：涨幅>9.5%计涨停，跌幅<-9.5%计跌停）
            c.execute("""
                SELECT close, adj_factor FROM daily_info_tbl WHERE tradedate = %s
            """, (latest_date,))
            today_rows = c.fetchall()

            # 查昨收
            yesterday = latest_date
            c.execute("SELECT MAX(tradedate) FROM daily_info_tbl WHERE tradedate < %s", (latest_date,))
            prev = c.fetchone()
            if prev:
                yesterday = prev[0]

            c.execute("SELECT code, close, adj_factor FROM daily_info_tbl WHERE tradedate = %s", (yesterday,))
            prev_map = {}
            for row in c.fetchall():
                prev_map[row[0]] = float(row[1] or 0) * float(row[2] or 1)

            up_limit = 0
            down_limit = 0
            for row in today_rows:
                code = row[0]
                p = float(row[1] or 0) * float(row[2] or 1)
                prev_p = prev_map.get(code, p)
                if prev_p <= 0:
                    continue
                chg = (p - prev_p) / prev_p
                if chg >= 0.095:
                    up_limit += 1
                elif chg <= -0.095:
                    down_limit += 1

            # 大盘判断（用上证指数代理）
            c.execute("""
                SELECT close, adj_factor FROM daily_info_tbl
                WHERE code = '000001.SH' AND tradedate = %s
            """, (latest_date,))
            sh_row = c.fetchone()
            market_chg = 0
            if sh_row:
                sh_close = float(sh_row[0] or 0) * float(sh_row[1] or 1)
                sh_prev = prev_map.get('000001.SH', sh_close)
                if sh_prev > 0:
                    market_chg = (sh_close - sh_prev) / sh_prev * 100

            # 判断
            if down_limit > 100 or market_chg < -3:
                return 'panic', 1.3
            elif up_limit > 100 and market_chg > 1:
                return 'euphoric', 0.5
            elif up_limit > 50 and market_chg > 0.5:
                return 'bullish', 0.8
            elif market_chg < -1:
                return 'bearish', 0.6
            else:
                return 'neutral', 1.0

        except Exception as e:
            print(f"  ⚠️ 市场情绪判断失败: {e}")
            return 'neutral', 1.0
        finally:
            c.close()
            conn.close()

    # ================================================================
    # 仓位计算
    # ================================================================

    def calc_kelly(self, win_prob, payoff_ratio):
        """
        凯利公式
        win_prob: 胜率 (0~1)
        payoff_ratio: 赔率 = 预期盈利 / 预期亏损
        """
        if payoff_ratio <= 0:
            return 0
        f = (win_prob * payoff_ratio - (1 - win_prob)) / payoff_ratio
        return max(0, f)

    def calc_position(self, win_prob, payoff_ratio=None,
                       stop_loss_pct=None, target_profit_pct=None,
                       theme_level='main', sentiment=None):
        """
        计算建议仓位

        参数:
          win_prob: 预测胜率 (来自 uptrend_model)
          payoff_ratio: 赔率（如果为None，用 target/stop 推算）
          stop_loss_pct: 止损幅度
          target_profit_pct: 预期盈利幅度
          theme_level: 'main' / 'sub' / 'none' 主线级别
          sentiment: 市场情绪（None则自动判断）

        返回: {
            'kelly_pct': float,        # 凯利仓位
            'adjusted_pct': float,     # 调整后仓位
            'final_pct': float,        # 最终仓位（受上限约束）
            'batch_plan': [...],       # 分批计划
            'sentiment': str,
            'sentiment_multiplier': float,
            'theme_multiplier': float,
            'stop_loss_pct': float,
            'target_profit_pct': float,
            'payoff_ratio': float,
        }
        """
        # 计算赔率
        if payoff_ratio is None:
            stop = stop_loss_pct or self.DEFAULT_STOP_LOSS_PCT
            target = target_profit_pct or 0.20
            payoff_ratio = target / stop if stop > 0 else 2.0

        # 凯利仓位
        kelly = self.calc_kelly(win_prob, payoff_ratio)

        # 主题纯度系数
        theme_map = {'main': 1.0, 'sub': 0.7, 'none': 0.5}
        theme_mult = theme_map.get(theme_level, 0.7)

        # 市场情绪
        if sentiment is None:
            sentiment, sent_mult = self.assess_market_sentiment()
        else:
            sent_map = {'panic': 1.3, 'neutral': 1.0, 'euphoric': 0.5,
                        'bullish': 0.8, 'bearish': 0.6}
            sent_mult = sent_map.get(sentiment, 1.0)

        # 调整后仓位
        adjusted = kelly * sent_mult * theme_mult

        # 单票上限约束
        final = min(adjusted, self.MAX_SINGLE_POS)

        # 强制保留现金
        if 1 - final < self.MIN_CASH:
            final = 1 - self.MIN_CASH

        final = max(0, round(final, 3))

        # 分批计划
        batch_plan = self._build_batch_plan(final, stop_loss_pct or self.DEFAULT_STOP_LOSS_PCT)

        return {
            'kelly_pct': round(kelly, 3),
            'adjusted_pct': round(adjusted, 3),
            'final_pct': final,
            'batch_plan': batch_plan,
            'sentiment': sentiment,
            'sentiment_multiplier': sent_mult,
            'theme_multiplier': theme_mult,
            'stop_loss_pct': stop_loss_pct or self.DEFAULT_STOP_LOSS_PCT,
            'target_profit_pct': target_profit_pct or 0.20,
            'payoff_ratio': round(payoff_ratio, 2),
        }

    def _build_batch_plan(self, final_pct, stop_loss_pct):
        """构建分批建仓计划"""
        if final_pct == 0:
            return []

        if final_pct < 0.15:
            # 小仓位一笔
            return [{
                'batch': 1, 'pct': final_pct,
                'reason': '一次性建仓', 'condition': '当前价'
            }]
        else:
            # 金字塔建仓
            batches = []
            b1 = round(final_pct * 0.5, 3)
            b2 = round(final_pct * 0.3, 3)
            b3 = round(final_pct * 0.2, 3)
            batches.append({'batch': 1, 'pct': b1, 'reason': '试探建仓', 'condition': '当前价'})
            batches.append({'batch': 2, 'pct': b2, 'reason': '回踩确认', 'condition': '回踩MA20或趋势线'})
            batches.append({'batch': 3, 'pct': b3, 'reason': '突破确认', 'condition': '放量突破前高'})
            return batches

    # ================================================================
    # 输出
    # ================================================================

    def print_report(self, result, name, code, current_price=None, stop_price=None):
        """打印仓位建议报告"""
        if not result:
            return

        print(f"\n  ┌─ 仓位管理 ───────────────────────────────")
        print(f"  │ {name} ({code})")

        pct = result['final_pct']
        bar = '█' * int(pct * 30) + '░' * (30 - int(pct * 30))
        print(f"  │ 建议仓位: {pct:.0%} [{bar}]")

        # 计算金额
        if self.total_capital:
            amount = self.total_capital * pct
            print(f"  │ 建议金额: {amount:,.0f} 元")

        print(f"  │")
        print(f"  │ 凯利仓位: {result['kelly_pct']:.0%}")
        print(f"  │ 市场情绪: {result['sentiment']} (×{result['sentiment_multiplier']:.1f})")
        print(f"  │ 赔率: {result['payoff_ratio']:.1f}")
        print(f"  │ 止损: -{result['stop_loss_pct']:.0%}")

        # 分批计划
        plan = result.get('batch_plan', [])
        if plan:
            print(f"  │")
            print(f"  │ 分批建仓:")
            total = 0
            for b in plan:
                total += b['pct']
                amount_str = f" ({self.total_capital * b['pct']:,.0f}元)" if self.total_capital else ""
                print(f"  │   第{b['batch']}批: {b['pct']:.0%}{amount_str} — {b['reason']}")
                print(f"  │          条件: {b['condition']}")

        print(f"  └──────────────────────────────────────────")


def main():
    sizer = PositionSizer(total_capital=1000000)

    if len(sys.argv) > 1:
        code = sys.argv[1]
        # 手动解析参数
        win_prob = 0.72
        payoff = None
        stop_loss = 0.08
        target = 0.20

        for i, arg in enumerate(sys.argv[2:], 2):
            if arg == '--p' and i + 1 < len(sys.argv):
                win_prob = float(sys.argv[i + 1])
            elif arg == '--b' and i + 1 < len(sys.argv):
                payoff = float(sys.argv[i + 1])
            elif arg == '--stop' and i + 1 < len(sys.argv):
                stop_loss = float(sys.argv[i + 1])
            elif arg == '--target' and i + 1 < len(sys.argv):
                target = float(sys.argv[i + 1])

        # 获取名称
        conn = pymysql.connect(**DB_CONFIG)
        c = conn.cursor()
        code_full = code if ('.SH' in code or '.SZ' in code) else (
            code + ('.SH' if code.startswith('6') else '.SZ'))
        c.execute("SELECT name FROM stock_basic_info_tbl WHERE code=%s", (code_full,))
        row = c.fetchone()
        name = row[0] if row else code
        c.close()
        conn.close()

        result = sizer.calc_position(win_prob, payoff, stop_loss, target)
        sizer.print_report(result, name, code)
    else:
        # 演示
        result = sizer.calc_position(0.72, stop_loss_pct=0.08, target_profit_pct=0.20)
        sizer.print_report(result, '示例股', '000001')


if __name__ == '__main__':
    main()
