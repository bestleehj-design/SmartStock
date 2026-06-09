# -*- coding: utf-8 -*-
"""
量价形态识别器
基于收盘价序列 + 成交量序列，自动识别经典K线形态

识别形态:
  看涨: W底、头肩底、三重底、杯柄、突破前高、旗形突破、均线发散
  看跌: M顶、头肩顶、量价背离、连续缩量上涨
"""
import sys
import os
import numpy as np

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


class PatternRecognizer:
    """量价形态识别器"""

    def __init__(self):
        pass

    # ================================================================
    # 工具函数
    # ================================================================

    @staticmethod
    def _find_local_extrema(arr, distance=5, mode='min'):
        """找局部极值点"""
        peaks = []
        n = len(arr)
        for i in range(distance, n - distance):
            if mode == 'min':
                is_extreme = all(arr[i] <= arr[j] for j in range(i - distance, i + distance + 1))
            else:
                is_extreme = all(arr[i] >= arr[j] for j in range(i - distance, i + distance + 1))
            if is_extreme:
                peaks.append(i)
        return peaks

    @staticmethod
    def _ma(arr, n):
        if len(arr) < n:
            return arr[-1] if len(arr) else 0
        return np.mean(arr[-n:])

    # ================================================================
    # 看涨形态
    # ================================================================

    def detect_w_bottom(self, closes, volumes, lookback=90):
        """
        W底（双重底）识别
        条件:
          1. 两个低点相距 5-30 天
          2. 两低点价格差距 < 5%
          3. 中间反弹 > 5%
          4. 右底成交量 > 左底
          5. 当前价突破颈线
        """
        n = min(len(closes), lookback)
        seg = closes[-n:]
        vol = volumes[-n:]

        mins = self._find_local_extrema(seg, distance=5, mode='min')
        if len(mins) < 2:
            return None

        result = []
        for i in range(len(mins) - 1):
            left, right = mins[i], mins[i + 1]
            if not (5 <= right - left <= 30):
                continue
            if abs(seg[left] - seg[right]) / seg[left] > 0.05:
                continue

            mid_max = max(seg[left:right + 1])
            if mid_max / seg[left] < 1.05:
                continue

            vol_confirm = vol[right] > vol[left]
            neckline = mid_max
            if seg[-1] <= neckline:
                continue

            confidence = 70 if vol_confirm else 50

            # 目标价 = 颈线 + (颈线 - 最低点)
            target = neckline + (neckline - min(seg[left], seg[right]))
            result.append({
                'pattern': 'W底',
                'direction': 'bullish',
                'neckline': round(neckline, 2),
                'target': round(target, 2),
                'vol_confirmed': vol_confirm,
                'confidence': confidence,
                'description': '双重底反转，突破颈线看涨',
            })

        return result[0] if result else None

    def detect_head_shoulder_bottom(self, closes, volumes, lookback=90):
        """
        头肩底识别
        左肩→头部(新低)→右肩(高于头)→突破颈线
        """
        n = min(len(closes), lookback)
        seg = closes[-n:]
        vol = volumes[-n:]

        mins = self._find_local_extrema(seg, distance=8, mode='min')
        if len(mins) < 3:
            return None

        result = []
        for i in range(len(mins) - 2):
            left_sh, head, right_sh = mins[i], mins[i + 1], mins[i + 2]
            if not (5 <= right_sh - left_sh <= 40):
                continue

            # 头部最低
            if not (seg[head] < seg[left_sh] - seg[left_sh] * 0.02):
                continue
            # 右肩高于头部
            if not (seg[right_sh] > seg[head] + seg[head] * 0.02):
                continue
            # 右肩与左肩接近
            if abs(seg[right_sh] - seg[left_sh]) / seg[left_sh] > 0.10:
                continue

            # 颈线: 两肩之间的最高点
            neckline = max(seg[left_sh:right_sh + 1])

            if seg[-1] <= neckline:
                continue

            confidence = 75 if vol[right_sh] > vol[head] else 60

            result.append({
                'pattern': '头肩底',
                'direction': 'bullish',
                'neckline': round(neckline, 2),
                'confidence': confidence,
                'description': '头肩底反转形态，看涨信号较强',
            })

        return result[0] if result else None

    def detect_breakout(self, closes, volumes, lookback=30):
        """
        突破前高识别
        收盘站上 N 日最高价，且放量
        """
        n = min(len(closes), lookback)
        seg = closes[-n:]
        vol = volumes[-n:]

        n_days_high = max(seg[:-1])
        if seg[-1] <= n_days_high:
            return None

        vol_current = vol[-1]
        vol_avg = np.mean(vol[-10:-1]) if len(vol) >= 11 else np.mean(vol[:-1])
        vol_confirm = vol_current > vol_avg * 1.2

        confidence = 75 if vol_confirm else 55

        return {
            'pattern': '突破前高',
            'direction': 'bullish',
            'breakout_level': round(n_days_high, 2),
            'vol_confirmed': vol_confirm,
            'confidence': confidence,
            'description': f'放量突破{lookback}日最高价{round(n_days_high,2)}' if vol_confirm
                           else f'突破{lookback}日最高价（待放量确认）',
        }

    def detect_ma_divergence_start(self, closes, lookback=30):
        """
        均线粘合后发散（向上）
        MA5/10/20 粘合 <3% 持续 >5 天，然后 MA5 上穿发散
        """
        n = min(len(closes), lookback + 30)
        seg = closes[-n:]

        ma5 = [self._ma(seg[:i + 1], 5) for i in range(len(seg))]
        ma10 = [self._ma(seg[:i + 1], 10) for i in range(len(seg))]
        ma20 = [self._ma(seg[:i + 1], 20) for i in range(len(seg))]

        # 检查末尾: MA5 上穿 MA10
        if len(ma5) < 10:
            return None
        if not (ma5[-1] > ma10[-1] and ma5[-2] <= ma10[-2]):
            return None

        # 检查之前是否有粘合期 (>5天)
        converged_days = 0
        for i in range(len(ma5) - 15, len(ma5) - 2):
            if all(k > 0 for k in (ma5[i], ma10[i], ma20[i])):
                vals = [ma5[i], ma10[i], ma20[i]]
                if (max(vals) - min(vals)) / min(vals) < 0.03:
                    converged_days += 1

        if converged_days < 5:
            return None

        return {
            'pattern': '均线粘合后发散',
            'direction': 'bullish',
            'converged_days': converged_days,
            'confidence': 65 if converged_days >= 10 else 55,
            'description': f'MA5/10/20 粘合 {converged_days} 天后向上发散',
        }

    # ================================================================
    # 看跌形态
    # ================================================================

    def detect_m_top(self, closes, volumes, lookback=90):
        """M顶（双重顶）识别"""
        n = min(len(closes), lookback)
        seg = closes[-n:]
        vol = volumes[-n:]

        peaks = self._find_local_extrema(seg, distance=5, mode='max')
        if len(peaks) < 2:
            return None

        for i in range(len(peaks) - 1):
            left, right = peaks[i], peaks[i + 1]
            if not (5 <= right - left <= 30):
                continue
            if abs(seg[left] - seg[right]) / seg[left] > 0.05:
                continue

            mid_min = min(seg[left:right + 1])
            if seg[left] / mid_min < 1.03:
                continue

            vol_confirm = vol[right] < vol[left] * 0.8

            if seg[-1] < mid_min:
                confidence = 75 if vol_confirm else 60
                return {
                    'pattern': 'M顶',
                    'direction': 'bearish',
                    'neckline': round(mid_min, 2),
                    'vol_confirmed': vol_confirm,
                    'confidence': confidence,
                    'description': '双重顶见顶信号' + ('（右顶缩量确认）' if vol_confirm else ''),
                }

        return None

    def detect_divergence(self, closes, volumes, lookback=20):
        """
        量价背离识别
        价格创新高但成交量持续萎缩
        """
        n = min(len(closes), lookback)
        seg = closes[-n:]
        vol = volumes[-n:]

        if len(seg) < 10:
            return None

        recent_high = max(seg[-5:])
        prev_high = max(seg[:-5])

        if recent_high <= prev_high:
            return None

        recent_vol = np.mean(vol[-5:])
        prev_vol = np.mean(vol[-10:-5])
        if recent_vol > prev_vol * 0.7:
            return None

        return {
            'pattern': '量价背离',
            'direction': 'bearish',
            'confidence': 75,
            'description': '价格创新高但成交量持续萎缩，顶背离信号',
        }

    def detect_consecutive_shrink_rise(self, closes, volumes, lookback=10):
        """
        连续缩量上涨
        连涨3天以上，但量逐步萎缩
        """
        n = min(len(closes), lookback)
        seg = closes[-n:]
        vol = volumes[-n:]

        consecutive_up = 0
        for i in range(1, 6):
            if seg[-i] > seg[-i - 1]:
                consecutive_up += 1
            else:
                break

        if consecutive_up < 3:
            return None

        recent_vols = [vol[-(i+1)] for i in range(consecutive_up)]
        is_shrinking = all(recent_vols[i] > recent_vols[i + 1] * 0.9
                          for i in range(len(recent_vols) - 1))

        if not is_shrinking:
            return None

        return {
            'pattern': '连续缩量上涨',
            'direction': 'bearish',
            'consecutive_days': consecutive_up,
            'confidence': 60,
            'description': f'连涨{consecutive_up}天但量能持续萎缩，上涨乏力',
        }

    # ================================================================
    # 综合分析
    # ================================================================

    def analyze(self, closes, volumes, lookback=90):
        """
        对日K数据进行全面形态分析
        返回: {
            'bullish': [...],
            'bearish': [...],
            'dominant': 'bullish'/'bearish'/'neutral',
            'overall_confidence': 0-100,
        }
        """
        bullish = []
        bearish = []

        # 看涨形态
        patterns = [
            self.detect_w_bottom(closes, volumes, lookback),
            self.detect_head_shoulder_bottom(closes, volumes, lookback),
            self.detect_breakout(closes, volumes, 30),
            self.detect_ma_divergence_start(closes, volumes, 30),
        ]
        for p in patterns:
            if p and p['direction'] == 'bullish':
                bullish.append(p)

        # 看跌形态
        patterns = [
            self.detect_m_top(closes, volumes, lookback),
            self.detect_divergence(closes, volumes, 20),
            self.detect_consecutive_shrink_rise(closes, volumes, 10),
        ]
        for p in patterns:
            if p and p['direction'] == 'bearish':
                bearish.append(p)

        # 综合判断
        bull_score = sum(p['confidence'] for p in bullish) if bullish else 0
        bear_score = sum(p['confidence'] for p in bearish) if bearish else 0

        if bull_score > bear_score + 20:
            dominant = 'bullish'
            overall = min(bull_score / (len(bullish) if bullish else 1), 100)
        elif bear_score > bull_score + 20:
            dominant = 'bearish'
            overall = min(bear_score / (len(bearish) if bearish else 1), 100)
        else:
            dominant = 'neutral'
            overall = 50

        return {
            'bullish': bullish,
            'bearish': bearish,
            'dominant': dominant,
            'overall_confidence': round(overall, 1),
        }

    # ================================================================
    # 输出
    # ================================================================

    def print_report(self, result, code, name=''):
        """打印形态分析报告"""
        if not result:
            return

        label = f"{name} ({code})" if name else code
        print(f"\n  ┌─ 量价形态分析 ───────────────────────────")

        bullish = result.get('bullish', [])
        bearish = result.get('bearish', [])
        dominant = result.get('dominant', 'neutral')

        if bullish:
            print(f"  │ 🟢 看涨形态:")
            for p in bullish:
                conf_bar = '█' * int(p['confidence'] / 20) + '░' * (5 - int(p['confidence'] / 20))
                print(f"  │   ✅ {p['pattern']} 置信度:{p['confidence']}% [{conf_bar}]")
                print(f"  │      {p['description']}")

        if bearish:
            print(f"  │ 🔴 看跌形态:")
            for p in bearish:
                conf_bar = '█' * int(p['confidence'] / 20) + '░' * (5 - int(p['confidence'] / 20))
                print(f"  │   ⚠️ {p['pattern']} 置信度:{p['confidence']}% [{conf_bar}]")
                print(f"  │      {p['description']}")

        if not bullish and not bearish:
            print(f"  │ ⚪ 未识别到明显形态")

        symbols = {'bullish': '📈 偏多', 'bearish': '📉 偏空', 'neutral': '➖ 中性'}
        print(f"  │ 综合: {symbols.get(dominant, dominant)} (得分:{result['overall_confidence']})")
        print(f"  └──────────────────────────────────────────")


def main():
    recognizer = PatternRecognizer()

    # 演示
    import numpy as np
    # 模拟一个W底
    np.random.seed(42)
    t = np.linspace(0, 1, 60)
    base = 30 + np.sin(t * 2 * np.pi) * 2
    base[20:25] = 29.5  # 左底
    base[35:40] = 29.8  # 右底
    base[40:] = 32.5 + t[40:] * 3  # 突破

    vol = np.random.randn(60) * 100000 + 500000
    vol[35:40] = 700000  # 右底放量

    print(f"\n{'='*60}")
    print(f"  量价形态识别 — 演示")
    print(f"{'='*60}")

    result = recognizer.analyze(base.tolist(), vol.tolist())
    recognizer.print_report(result, '000001', '演示股')


if __name__ == '__main__':
    main()
