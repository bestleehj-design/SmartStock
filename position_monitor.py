# -*- coding: utf-8 -*-
"""
持仓卖点监控系统
对持仓股票进行多维度卖出信号分析，输出买卖建议

用法:
  python position_monitor.py                  # 检查所有持仓
  python position_monitor.py 603986.SH        # 检查指定股票
  python position_monitor.py --add 603986.SH  # 将股票加入追踪(需指定买入价)
"""
import sys
import os
import json
import datetime
import numpy as np

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
os.chdir(SCRIPT_DIR)
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

from newstocklib import initMySQL


# ============================================================
# 卖出信号维度及评分
# ============================================================
# 每个维度得分0-20, 得分越高越危险, 总分0-100
# >= 70: 强烈卖出
# 50-69: 建议减仓
# 30-49: 警惕持有
# < 30: 继续持有

class PositionMonitor:
    """持仓卖点监控器"""

    def __init__(self):
        self.db = initMySQL()
        self.c = self.db.cursor()

    def _get_stock_data(self, code, days=60):
        """获取股票日线数据, 返回 DataFrame-like dict"""
        self.c.execute("""
            SELECT tradedate, open, high, low, close, volume, adj_factor
            FROM daily_info_tbl
            WHERE code = %s
            ORDER BY tradedate ASC
        """, (code,))
        rows = self.c.fetchall()
        if len(rows) < 40:
            return None

        rows = rows[-days:]
        data = {
            'dates': [], 'opens': [], 'highs': [], 'lows': [],
            'closes': [], 'volumes': [], 'adj_factors': []
        }
        for r in rows:
            adj = float(r[6]) if r[6] else 1.0
            data['dates'].append(r[0])
            data['opens'].append(float(r[1]) * adj)
            data['highs'].append(float(r[2]) * adj)
            data['lows'].append(float(r[3]) * adj)
            data['closes'].append(float(r[4]) * adj)
            data['volumes'].append(float(r[5]) if r[5] else 0)
            data['adj_factors'].append(adj)
        return data

    def _ma(self, arr, period):
        if len(arr) < period:
            return arr[-1] if len(arr) > 0 else 0
        return np.mean(arr[-period:])

    def _ema(self, arr, period):
        if len(arr) < 2:
            return arr[-1] if len(arr) > 0 else 0
        k = 2.0 / (period + 1)
        ema = arr[0]
        for val in arr[1:]:
            ema = val * k + ema * (1 - k)
        return ema

    def analyze_position(self, code, buy_price=None, buy_date=None):
        """
        对持仓股票进行多维度卖出分析
        返回: {
            'code': str, 'name': str,
            'current_price': float, 'profit_pct': float,
            'signals': [{name, score, detail, is_triggered}],
            'total_risk_score': float (0-100),
            'recommendation': str,
            'recommendation_level': int (1=强烈卖出, 2=建议减仓, 3=警惕, 4=持有)
        }
        """
        # 获取股票名称
        self.c.execute("SELECT name FROM stock_basic_info_tbl WHERE code = %s", (code,))
        row = self.c.fetchone()
        name = row[0] if row else code

        # 获取日线数据
        data = self._get_stock_data(code, 90)
        if data is None:
            return {'code': code, 'name': name, 'error': '数据不足'}

        closes = data['closes']
        highs = data['highs']
        lows = data['lows']
        volumes = data['volumes']
        current_price = closes[-1]

        # 如果没有指定买入价, 尝试从 selected_stocks 表读取
        if buy_price is None:
            self.c.execute(
                "SELECT selected_price, selected_date FROM selected_stocks "
                "WHERE code = %s AND status = 'tracking' ORDER BY id DESC LIMIT 1",
                (code,)
            )
            row = self.c.fetchone()
            if row:
                buy_price = float(row[0]) if row[0] else None
                buy_date = row[1] if row[1] else None

        profit_pct = ((current_price - buy_price) / buy_price * 100) if buy_price else None

        # 计算技术指标
        ma5 = self._ma(closes, 5)
        ma10 = self._ma(closes, 10)
        ma20 = self._ma(closes, 20)
        ma30 = self._ma(closes, 30)
        ma60 = self._ma(closes, 60) if len(closes) >= 60 else ma30

        v37 = np.mean(volumes[-37:]) if len(volumes) >= 37 else np.mean(volumes)
        vol_ratio = volumes[-1] / v37 if v37 > 0 else 1

        # RSI(6), RSI(14)
        rs = self._rsi(closes, 6)
        rs2 = self._rsi(closes, 14)

        # MACD
        macd, signal, histogram = self._macd(closes)
        hist_prev = self._macd_hist_prev(closes)

        # ATR(14)
        atr = self._atr(highs, lows, closes, 14)

        # 近N日最高价
        high_10d = max(highs[-10:]) if len(highs) >= 10 else max(highs)
        high_20d = max(highs[-20:]) if len(highs) >= 20 else max(highs)

        # 涨幅计算
        rise_5d = (closes[-1] - closes[-6]) / closes[-6] * 100 if len(closes) >= 6 else 0
        rise_10d = (closes[-1] - closes[-11]) / closes[-11] * 100 if len(closes) >= 11 else 0

        # ---- 10个卖出信号维度 ----
        signals = []

        # A. 趋势反转: MA5 < MA10 死叉 (0-20分)
        ma_death_cross = (ma5 < ma10 and len(closes) >= 6 and
                          self._ma(closes[:-1], 5) >= self._ma(closes[:-1], 10))
        ma_trend_reversal = ma5 < ma10 < ma20  # 完全空头
        score_a = 20 if (ma_death_cross or ma_trend_reversal) else (
            10 if ma5 < ma10 else (5 if ma5 < ma20 else 0))
        signals.append({
            'name': '趋势反转', 'score': score_a, 'max': 20,
            'triggered': score_a >= 10,
            'detail': f"MA5={ma5:.1f} MA10={ma10:.1f} MA20={ma20:.1f} "
                      f"{'死叉!' if ma_death_cross else '多头' if ma5>ma10 else '走弱'}"
        })

        # B. MACD 死叉/红柱缩短 (0-15分)
        macd_death = (histogram < 0 and hist_prev > 0)
        macd_weakening = (histogram > 0 and histogram < hist_prev * 0.5)
        score_b = 15 if macd_death else (10 if macd_weakening else (5 if histogram < 0 else 0))
        signals.append({
            'name': 'MACD转弱', 'score': score_b, 'max': 15,
            'triggered': score_b >= 10,
            'detail': f"MACD={macd:.2f} Signal={signal:.2f} Hist={histogram:.2f} "
                      f"{'死叉!' if macd_death else '缩短中' if macd_weakening else '正常' if histogram > 0 else '空头'}"
        })

        # C. 高位回撤: 从近期高点回落 (0-15分)
        drawdown_10d = (current_price - high_10d) / high_10d * 100 if high_10d > 0 else 0
        drawdown_20d = (current_price - high_20d) / high_20d * 100 if high_20d > 0 else 0
        score_c = 15 if drawdown_10d < -8 else (10 if drawdown_10d < -5 else (
            5 if drawdown_10d < -3 else 0))
        signals.append({
            'name': '高位回撤', 'score': score_c, 'max': 15,
            'triggered': score_c >= 10,
            'detail': f"10日高点={high_10d:.1f} 回撤={drawdown_10d:.1f}% "
                      f"20日高点={high_20d:.1f} 回撤={drawdown_20d:.1f}%"
        })

        # D. 连续下跌 + 放量 (0-12分)
        consecutive_down = 0
        for i in range(1, min(6, len(closes))):
            if closes[-i] < closes[-i-1]:
                consecutive_down += 1
            else:
                break
        avg_vol_down = np.mean(volumes[-consecutive_down:]) if consecutive_down > 0 else 0
        vol_amplify = (avg_vol_down > v37 * 1.2) if consecutive_down >= 3 else False
        score_d = 12 if (consecutive_down >= 3 and vol_amplify) else (
            8 if consecutive_down >= 3 else (4 if consecutive_down >= 2 else 0))
        signals.append({
            'name': '连续下跌', 'score': score_d, 'max': 12,
            'triggered': score_d >= 8,
            'detail': f"连跌{consecutive_down}天 "
                      f"{'且放量!' if vol_amplify else ''}"
        })

        # E. 量价背离: 价涨量缩 (0-10分)
        price_up = closes[-1] > closes[-5] if len(closes) >= 5 else False
        vol_down = np.mean(volumes[-3:]) < np.mean(volumes[-8:-3]) * 0.8 if len(volumes) >= 8 else False
        vol_avg_3 = np.mean(volumes[-3:]) if len(volumes) >= 3 else 0
        vol_avg_5_prev = np.mean(volumes[-8:-3]) if len(volumes) >= 8 else 0
        divergence = price_up and vol_down
        score_e = 10 if divergence else 0
        signals.append({
            'name': '量价背离', 'score': score_e, 'max': 10,
            'triggered': divergence,
            'detail': f"近3日均量={vol_avg_3:.0f} vs前5日均量={vol_avg_5_prev:.0f}"
        })

        # F. RSI 超买/转弱 (0-8分)
        rsi_overbought = (rs > 75)
        rsi_turn = (rs < 50 and len(closes) >= 4 and self._rsi(closes[:-1], 6) >= 50)
        score_f = 8 if rsi_turn else (5 if rsi_overbought else (3 if rs < 40 else 0))
        signals.append({
            'name': 'RSI转弱', 'score': score_f, 'max': 8,
            'triggered': score_f >= 5,
            'detail': f"RSI(6)={rs:.1f} RSI(14)={rs2:.1f} "
                      f"{'超买' if rsi_overbought else '转弱' if rsi_turn else '正常' if rs>50 else '弱势'}"
        })

        # G. 跌破均线支撑 (0-8分)
        below_ma20_on_vol = (current_price < ma20 and vol_ratio > 1.3 and closes[-1] < closes[-2])
        below_ma30 = (current_price < ma30)
        score_g = 8 if below_ma20_on_vol else (5 if below_ma30 else 0)
        signals.append({
            'name': '均线破位', 'score': score_g, 'max': 8,
            'triggered': score_g >= 5,
            'detail': f"MA20={ma20:.1f} MA30={ma30:.1f} "
                      f"{'跌破MA20+放量!' if below_ma20_on_vol else '跌破MA30' if below_ma30 else '均线上方'}"
        })

        # H. 移动止盈触发 (0-7分): 从买入后最高点回落>8%
        if buy_price and profit_pct is not None and profit_pct > 10:
            # 买入后已盈利>10%, 用移动止盈
            buy_pos = None
            for i, date in enumerate(data['dates']):
                if buy_date and str(date) >= str(buy_date):
                    buy_pos = i
                    break
            if buy_pos is None:
                buy_pos = len(closes) - 30

            peak_since_buy = max(highs[buy_pos:]) if buy_pos < len(highs) else max(highs)
            peak_drawdown = (current_price - peak_since_buy) / peak_since_buy * 100 if peak_since_buy > 0 else 0
            trailing_triggered = peak_drawdown < -8
            score_h = 7 if trailing_triggered else 0
            signals.append({
                'name': '移动止盈', 'score': score_h, 'max': 7,
                'triggered': trailing_triggered,
                'detail': f"买入后最高={peak_since_buy:.1f} 回撤={peak_drawdown:.1f}% "
                          f"{'触发!' if trailing_triggered else '未触发'}"
            })
        else:
            signals.append({
                'name': '移动止盈', 'score': 0, 'max': 7,
                'triggered': False,
                'detail': f"{'未盈利>10%, 不适用' if profit_pct is not None else '无买入价'}"
            })

        # I. 放量滞涨/放量下跌 (0-5分) - 当天放量但不涨反跌
        stuck = (vol_ratio > 1.8 and closes[-1] <= closes[-2])
        score_i = 5 if stuck else 0
        signals.append({
            'name': '放量滞涨', 'score': score_i, 'max': 5,
            'triggered': stuck,
            'detail': f"量比={vol_ratio:.1f} "
                      f"{'放量不涨/下跌!' if stuck else '正常'}"
        })

        # J. 短期涨幅过大 (0-5分) - 均值回归风险
        score_j = 0
        if rise_5d > 20:
            score_j = 5
        elif rise_5d > 15:
            score_j = 3
        elif rise_10d > 30:
            score_j = 4
        signals.append({
            'name': '短线过热', 'score': score_j, 'max': 5,
            'triggered': score_j >= 3,
            'detail': f"5日涨幅={rise_5d:.1f}% 10日涨幅={rise_10d:.1f}%"
        })

        # ---- 汇总风险分 ----
        total_risk = sum(s['score'] for s in signals)

        # 建议等级
        if total_risk >= 70:
            rec = '【强烈卖出】多项卖出信号共振，建议立即卖出'
            rec_level = 1
        elif total_risk >= 50:
            rec = '【建议减仓】卖出信号较明显，建议减仓或设紧止损'
            rec_level = 2
        elif total_risk >= 30:
            rec = '【警惕持有】出现一些风险信号，注意观察后续走势'
            rec_level = 3
        else:
            rec = '【继续持有】暂时没有明显的卖出信号'
            rec_level = 4

        result = {
            'code': code,
            'name': name,
            'current_price': round(current_price, 2),
            'buy_price': round(buy_price, 2) if buy_price else None,
            'profit_pct': round(profit_pct, 2) if profit_pct is not None else None,
            'signals': signals,
            'total_risk_score': round(total_risk, 1),
            'recommendation': rec,
            'recommendation_level': rec_level,
            'key_metrics': {
                'ma5': round(ma5, 2), 'ma10': round(ma10, 2),
                'ma20': round(ma20, 2), 'ma30': round(ma30, 2),
                'vol_ratio': round(vol_ratio, 2),
                'rsi6': round(rs, 1), 'rsi14': round(rs2, 1),
                'macd_hist': round(histogram, 3),
                'drawdown_10d': round(drawdown_10d, 2),
                'consecutive_down': consecutive_down,
                'rise_5d': round(rise_5d, 2),
                'rise_10d': round(rise_10d, 2),
            }
        }
        return result

    def _rsi(self, closes, period=14):
        if len(closes) < period + 1:
            return 50
        deltas = np.diff(closes[-(period+1):])
        gains = np.where(deltas > 0, deltas, 0)
        losses = np.where(deltas < 0, -deltas, 0)
        avg_gain = np.mean(gains)
        avg_loss = np.mean(losses)
        if avg_loss == 0:
            return 100
        rs = avg_gain / avg_loss
        return 100 - (100 / (1 + rs))

    def _macd(self, closes):
        if len(closes) < 26:
            return 0, 0, 0
        ema12 = self._ema(closes, 12)
        ema26 = self._ema(closes, 26)
        macd = ema12 - ema26
        signal = self._ema([0] * 8 + [macd], 9)  # approximate
        histogram = macd - signal
        return macd, signal, histogram

    def _macd_hist_prev(self, closes):
        """计算前一天的MACD柱"""
        if len(closes) < 27:
            return 0
        prev_closes = closes[:-1]
        _, _, hist = self._macd(prev_closes)
        return hist

    def _atr(self, highs, lows, closes, period=14):
        if len(closes) < period + 1:
            return 0
        tr_list = []
        for i in range(1, len(closes)):
            tr = max(
                highs[i] - lows[i],
                abs(highs[i] - closes[i-1]),
                abs(lows[i] - closes[i-1])
            )
            tr_list.append(tr)
        return np.mean(tr_list[-period:]) if tr_list else 0

    def run_all(self):
        """检查所有持仓"""
        self.c.execute(
            "SELECT code, name, selected_price, selected_date, profit_pct "
            "FROM selected_stocks WHERE status = 'tracking' ORDER BY selected_date DESC"
        )
        positions = self.c.fetchall()

        if not positions:
            print("\n当前无追踪中的持仓")
            return

        print(f"\n{'='*85}")
        print(f"持仓卖点监控报告 - {datetime.date.today()}")
        print(f"{'='*85}")

        for row in positions:
            code, name, buy_px, buy_dt, profit = row
            buy_px = float(buy_px) if buy_px else None

            result = self.analyze_position(code, buy_px, buy_dt)
            if result.get('error'):
                print(f"\n  {name}({code}) - {result['error']}")
                continue

            self._print_single(result)

    def _print_single(self, r):
        """打印单只股票分析结果"""
        risk = r['total_risk_score']
        rec_level = r['recommendation_level']

        # 风险条
        bar_len = 30
        filled = int(risk / 100 * bar_len)
        if risk >= 70:
            bar_color = '🔴'
        elif risk >= 50:
            bar_color = '🟠'
        elif risk >= 30:
            bar_color = '🟡'
        else:
            bar_color = '🟢'

        risk_bar = '█' * filled + '░' * (bar_len - filled)

        print(f"\n{'─'*85}")
        profit_str = f" {r['profit_pct']:+.1f}%" if r['profit_pct'] is not None else " N/A"
        buy_str = f"买入:{r['buy_price']:.1f}" if r['buy_price'] else ""
        print(f"  {r['name']}({r['code']})  现价:{r['current_price']:.2f}  {buy_str}  盈亏:{profit_str}")
        print(f"  风险评分: {bar_color} {risk:.0f}/100 {risk_bar}")
        print(f"  {r['recommendation']}")

        # 触发的信号
        triggered = [s for s in r['signals'] if s['triggered']]
        if triggered:
            print(f"\n  ⚠️ 触发信号:")
            for s in triggered:
                print(f"     [{s['score']}/{s['max']}] {s['name']}: {s['detail']}")
        else:
            print(f"\n  ✅ 无触发信号")

        # 技术指标
        km = r['key_metrics']
        print(f"\n  MA: 5={km['ma5']:.1f} 10={km['ma10']:.1f} 20={km['ma20']:.1f} 30={km['ma30']:.1f}")
        print(f"  RSI(6)={km['rsi6']:.1f}  RSI(14)={km['rsi14']:.1f}  MACD柱={km['macd_hist']:.3f}")
        print(f"  量比={km['vol_ratio']:.1f}  10日回撤={km['drawdown_10d']:.1f}%  连跌={km['consecutive_down']}天")
        print(f"  5日涨幅={km['rise_5d']:.1f}%  10日涨幅={km['rise_10d']:.1f}%")

    def cleanup(self):
        try:
            self.c.close()
        except:
            pass
        try:
            self.db.close()
        except:
            pass


def main():
    monitor = PositionMonitor()
    try:
        if len(sys.argv) > 1:
            arg = sys.argv[1]
            if arg == '--add':
                code = sys.argv[2] if len(sys.argv) > 2 else None
                price = float(sys.argv[3]) if len(sys.argv) > 3 else None
                if code and price:
                    # 获取名称
                    monitor.c.execute("SELECT name FROM stock_basic_info_tbl WHERE code=%s", (code,))
                    row = monitor.c.fetchone()
                    name = row[0] if row else code
                    monitor.c.execute(
                        "INSERT INTO selected_stocks (code, name, selected_price, status) VALUES (%s,%s,%s,'tracking')",
                        (code, name, price)
                    )
                    monitor.db.commit()
                    print(f"已添加: {name}({code}) 买入价={price}")
                else:
                    print("用法: python position_monitor.py --add CODE PRICE")
                    print("例如: python position_monitor.py --add 603986.SH 2500.00")
            else:
                # 分析指定股票
                result = monitor.analyze_position(arg)
                if result.get('error'):
                    print(f"错误: {result['error']}")
                else:
                    monitor._print_single(result)
        else:
            monitor.run_all()
    finally:
        monitor.cleanup()


if __name__ == '__main__':
    main()
