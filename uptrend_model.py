# -*- coding: utf-8 -*-
"""
主升浪模式识别模型
基于历史日K数据，训练XGBoost多输出分类器
预测不同时间窗口内不同涨幅阈值的概率

核心功能:
  1. 从历史数据自动标注主升浪区间
  2. 提取策略1候选股的技术特征
  3. 训练多阈值概率估计器
  4. 输出如: "10天后涨>30%的概率为85%"

用法:
  python3 uptrend_model.py --train            # 训练模型
  python3 uptrend_model.py --predict CODE     # 预测单只股票
  python3 uptrend_model.py --predict-batch    # 批量预测策略1候选股
"""
import sys
import os
import json
import datetime
import pickle
import numpy as np
from collections import defaultdict

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

# 预测参数
PREDICT_HORIZONS = [5, 10, 20]        # 预测天数
RISE_THRESHOLDS = [0.05, 0.10, 0.20, 0.30, 0.50]  # 涨幅阈值
MAIN_UP_MIN_RISE = 0.30               # 主升浪最低涨幅
MAIN_UP_MAX_DAYS = 30                 # 主升浪最长时间窗口
MAIN_UP_MIN_DAYS = 5                  # 主升浪最短时间窗口
MODEL_DIR = 'models'


class UptrendModel:
    """主升浪模式识别模型"""

    def __init__(self):
        self.models = {}               # {horizon: xgb_model}
        self.scaler = None
        self.feature_names = []
        self._load_if_exists()

    def _load_if_exists(self):
        """尝试加载已有模型"""
        os.makedirs(MODEL_DIR, exist_ok=True)
        meta_path = os.path.join(MODEL_DIR, 'uptrend_meta.json')
        if os.path.exists(meta_path):
            try:
                with open(meta_path) as f:
                    meta = json.load(f)
                self.feature_names = meta.get('features', [])
                # 加载各时间窗口模型
                for h in PREDICT_HORIZONS:
                    path = os.path.join(MODEL_DIR, f'uptrend_{h}d.pkl')
                    if os.path.exists(path):
                        self.models[h] = pickle.load(open(path, 'rb'))
                # 加载scaler
                scaler_path = os.path.join(MODEL_DIR, 'uptrend_scaler.pkl')
                if os.path.exists(scaler_path):
                    self.scaler = pickle.load(open(scaler_path, 'rb'))
            except Exception:
                pass

    def is_loaded(self):
        return len(self.models) > 0

    # ================================================================
    # 数据准备
    # ================================================================

    def _fetch_stock_daily(self, code, days=600):
        """从数据库获取单只股票日K"""
        conn = pymysql.connect(**DB_CONFIG)
        c = conn.cursor()
        c.execute("""
            SELECT tradedate, open, high, low, close, volume, adj_factor
            FROM daily_info_tbl WHERE code = %s
            ORDER BY tradedate ASC
        """, (code,))
        rows = c.fetchall()[-days:]
        c.close()
        conn.close()
        return rows

    def _fetch_moneyflow(self, code, start_date):
        """获取资金流向"""
        conn = pymysql.connect(**DB_CONFIG)
        c = conn.cursor()
        c.execute("""
            SELECT tradedate, net_lg_amount, net_elg_amount
            FROM daily_moneyflow_tbl
            WHERE code = %s AND tradedate >= %s
            ORDER BY tradedate ASC
        """, (code, start_date))
        rows = {(r[0]): (float(r[1] or 0), float(r[2] or 0)) for r in c.fetchall()}
        c.close()
        conn.close()
        return rows

    def _fetch_sector_index(self, code, start_date):
        """获取该股票所属主要概念板块指数"""
        conn = pymysql.connect(**DB_CONFIG)
        c = conn.cursor()
        # 找该股票归属的概念板块
        c.execute("""
            SELECT code_list, name FROM stock_basic_info_tbl
            WHERE type=2 AND code_list LIKE CONCAT('%', %s, '%')
            LIMIT 5
        """, (code,))
        concept_codes = [r[0] for r in c.fetchall()]
        c.close()
        conn.close()
        # 暂不查板块指数K线（数据量大），返回板块代码列表
        return concept_codes

    # ================================================================
    # 主升浪标注
    # ================================================================

    def _label_main_uptrend(self, closes, min_rise=MAIN_UP_MIN_RISE,
                             max_days=MAIN_UP_MAX_DAYS, min_days=MAIN_UP_MIN_DAYS):
        """
        扫描收盘价序列，标记主升浪起始日
        返回: [start_indices], 每个起点对应的(终点, 涨幅, 天数)
        """
        n = len(closes)
        labels = {}  # start_idx -> [(end_idx, rise, days), ...]

        for i in range(n - min_days):
            for j in range(i + min_days, min(i + max_days + 1, n)):
                rise = (closes[j] - closes[i]) / closes[i]
                if rise >= min_rise:
                    # 确认没有大幅回撤
                    max_dd = 0
                    peak = closes[i]
                    for k in range(i + 1, j + 1):
                        if closes[k] > peak:
                            peak = closes[k]
                        dd = (peak - closes[k]) / peak
                        max_dd = max(max_dd, dd)
                    if max_dd <= 0.15:  # 期间回撤不超过15%
                        if i not in labels:
                            labels[i] = []
                        labels[i].append((j, rise, j - i))
                        break  # 找到最近的一个主升浪即可

        return labels

    def _make_labels(self, closes, start_idx, horizons, thresholds):
        """
        为指定起点生成多阈值标签
        返回: {'5d_5%': 1, '5d_10%': 0, ...}
        """
        label_row = {}
        for h in horizons:
            end_idx = start_idx + h
            if end_idx >= len(closes):
                for t in thresholds:
                    label_row[f'{h}d_{int(t*100)}%'] = 0
                continue
            future_rise = (closes[end_idx] - closes[start_idx]) / closes[start_idx]
            for t in thresholds:
                label_row[f'{h}d_{int(t*100)}%'] = 1 if future_rise >= t else 0
        return label_row

    # ================================================================
    # 特征工程
    # ================================================================

    def _extract_features(self, closes, volumes, moneyflow, idx):
        """
        从日K序列的 idx 位置提取技术特征
        返回: feature_dict
        """
        def ma(arr, n):
            if len(arr) < n:
                return arr[-1] if len(arr) else 0
            return np.mean(arr[-n:])

        def ema(arr, n):
            if len(arr) < 2:
                return arr[-1] if len(arr) else 0
            k = 2.0 / (n + 1)
            result = arr[0]
            for v in arr[1:]:
                result = v * k + result * (1 - k)
            return result

        window = min(idx + 1, 120)
        seg_closes = closes[max(0, idx+1-window):idx+1]
        seg_volumes = volumes[max(0, idx+1-window):idx+1]
        current = seg_closes[-1]

        feats = {}

        # 价格特征
        feats['price'] = current
        for n in [5, 10, 20, 30]:
            mv = ma(seg_closes, n)
            feats[f'ma{n}'] = round(mv, 4)
            feats[f'ma{n}_dist'] = round((current / mv - 1) * 100, 2) if mv > 0 else 0

        # 均线排列
        feats['ma5_over_ma10'] = 1 if ma(seg_closes, 5) > ma(seg_closes, 10) else 0
        feats['ma10_over_ma20'] = 1 if ma(seg_closes, 10) > ma(seg_closes, 20) else 0

        # 涨幅
        for n in [5, 10, 20]:
            if len(seg_closes) > n:
                chg = (seg_closes[-1] - seg_closes[-1-n]) / seg_closes[-1-n] * 100
            else:
                chg = 0
            feats[f'chg_{n}d'] = round(chg, 2)

        # 波动率
        for n in [5, 10, 20]:
            if len(seg_closes) >= n:
                feats[f'volatility_{n}d'] = round(np.std(seg_closes[-n:]) / np.mean(seg_closes[-n:]) * 100, 2)
            else:
                feats[f'volatility_{n}d'] = 0

        # 量能特征
        if len(seg_volumes) >= 37:
            v37 = np.mean(seg_volumes[-37:])
        else:
            v37 = np.mean(seg_volumes) if len(seg_volumes) > 0 else 1
        feats['vol_ratio'] = round(seg_volumes[-1] / v37, 2) if v37 > 0 else 0
        for n in [5, 10, 20]:
            if len(seg_volumes) >= n:
                feats[f'vol_avg_{n}d'] = np.mean(seg_volumes[-n:])
            else:
                feats[f'vol_avg_{n}d'] = 0

        # 量趋势: 5日量 / 前5日量
        if len(seg_volumes) >= 10:
            vol5 = np.mean(seg_volumes[-5:])
            vol5_prev = np.mean(seg_volumes[-10:-5])
            feats['vol_trend'] = round(vol5 / vol5_prev, 2) if vol5_prev > 0 else 1
        else:
            feats['vol_trend'] = 1

        # RSI(6), RSI(14)
        for n in [6, 14]:
            if len(seg_closes) > n:
                deltas = np.diff(seg_closes[-(n+1):])
                gains = np.where(deltas > 0, deltas, 0)
                losses = np.where(deltas < 0, -deltas, 0)
                avg_gain = np.mean(gains)
                avg_loss = np.mean(losses)
                if avg_loss == 0:
                    rsi = 100
                else:
                    rsi = 100 - (100 / (1 + avg_gain / avg_loss))
                feats[f'rsi{n}'] = round(rsi, 1)
            else:
                feats[f'rsi{n}'] = 50

        # MACD
        if len(seg_closes) >= 26:
            ema12 = ema(seg_closes, 12)
            ema26 = ema(seg_closes, 26)
            macd_val = ema12 - ema26
            # 信号线: 近似用前几日的MACD均值
            feats['macd'] = round(macd_val, 4)
        else:
            feats['macd'] = 0

        # 资金特征（如果有）
        net_big = moneyflow.get('net_big', 0)
        feats['net_big'] = net_big

        return feats

    # ================================================================
    # 训练
    # ================================================================

    def train(self, stock_codes=None, sample_size=300):
        """
        训练主升浪识别模型
        stock_codes: 如果为None，从数据库随机选
        """
        print(f"\n{'='*60}")
        print(f"  主升浪模式识别 — 模型训练")
        print(f"{'='*60}")

        # 获取训练股票池
        if stock_codes is None:
            conn = pymysql.connect(**DB_CONFIG)
            c = conn.cursor()
            c.execute("""
                SELECT code FROM daily_info_tbl
                WHERE tradedate > DATE_SUB(CURDATE(), INTERVAL 3 YEAR)
                GROUP BY code HAVING COUNT(*) > 200
                ORDER BY RAND() LIMIT %s
            """, (min(sample_size, 500),))
            stock_codes = [r[0] for r in c.fetchall()]
            c.close()
            conn.close()

        print(f"  训练池: {len(stock_codes)} 只股票")

        # 收集训练样本
        X_list = []
        y_lists = {h: [] for h in PREDICT_HORIZONS}
        y_cols = [f'{h}d_{int(t*100)}%' for h in PREDICT_HORIZONS for t in RISE_THRESHOLDS]

        processed = 0
        for code in stock_codes:
            processed += 1
            if processed % 50 == 0:
                print(f"    进度: {processed}/{len(stock_codes)}")

            try:
                rows = self._fetch_stock_daily(code, 600)
                if len(rows) < 120:
                    continue

                closes = [float(r[4]) * float(r[6] or 1) for r in rows]
                volumes = [float(r[5]) for r in rows]
                dates_first = str(rows[0][0])[:10]

                mf_data = self._fetch_moneyflow(code, dates_first)

                # 标注主升浪
                uptrend_labels = self._label_main_uptrend(closes)
                if not uptrend_labels:
                    continue

                # 遍历每个交易日作为特征点
                for idx in range(60, len(closes) - PREDICT_HORIZONS[-1]):
                    # 从该日提取特征
                    seg_closes = closes[:idx+1]
                    seg_volumes = volumes[:idx+1]

                    mf = {}
                    dates = sorted(mf_data.keys())
                    for d in dates:
                        if rows[idx][0] >= d:
                            mf['net_big'] = mf_data[d][0] + mf_data[d][1]

                    feats = self._extract_features(seg_closes, seg_volumes, mf, len(seg_closes)-1)

                    # 生成标签
                    label_dict = self._make_labels(closes, idx, PREDICT_HORIZONS, RISE_THRESHOLDS)

                    X_list.append(feats)
                    for h in PREDICT_HORIZONS:
                        y_lists[h].append([label_dict[f'{h}d_{int(t*100)}%'] for t in RISE_THRESHOLDS])

            except Exception as e:
                continue

        if len(X_list) < 100:
            print(f"  ⚠️ 训练样本不足: {len(X_list)} < 100")
            return False

        print(f"  训练样本: {len(X_list)} 行 × {len(X_list[0])} 特征")

        # 转为numpy
        self.feature_names = list(X_list[0].keys())
        X = np.array([[row.get(f, 0) for f in self.feature_names] for row in X_list])

        # 标准化
        try:
            from sklearn.preprocessing import StandardScaler
            self.scaler = StandardScaler()
            X = self.scaler.fit_transform(X)
        except ImportError:
            print("  ⚠️ scikit-learn未安装")
            return False

        # 训练各时间窗口模型
        try:
            import xgboost as xgb

            for h in PREDICT_HORIZONS:
                y = np.array(y_lists[h])
                print(f"\n  训练 {h}天窗口模型 (标签: {RISE_THRESHOLDS})")
                print(f"    正样本率: {[f'{t:.0%}:{y[:,i].mean():.1%}' for i, t in enumerate(RISE_THRESHOLDS)]}")

                # 时间序列切分（前80%训练，后20%验证）
                split = int(len(X) * 0.8)
                X_train, X_val = X[:split], X[split:]
                y_train, y_val = y[:split], y[split:]

                model = xgb.XGBClassifier(
                    n_estimators=200, max_depth=6, learning_rate=0.05,
                    subsample=0.8, colsample_bytree=0.8,
                    random_state=42, n_jobs=-1, verbosity=0,
                )
                model.fit(X_train, y_train, eval_set=[(X_val, y_val)], verbose=False)

                # 验证
                y_pred_proba = model.predict_proba(X_val)
                if isinstance(y_pred_proba, list):
                    # multi-output: list of (n_samples, 2) arrays
                    for i, t in enumerate(RISE_THRESHOLDS):
                        acc = (y_pred_proba[i].argmax(axis=1) == y_val[:, i]).mean()
                        print(f"    涨>{t:.0%}: 准确率={acc:.1%}")
                else:
                    acc = (y_pred_proba.argmax(axis=1) == y_val).mean()
                    print(f"    准确率={acc:.1%}")

                self.models[h] = model

                # 保存模型
                os.makedirs(MODEL_DIR, exist_ok=True)
                pickle.dump(model, open(os.path.join(MODEL_DIR, f'uptrend_{h}d.pkl'), 'wb'))

            # 保存基础信息
            pickle.dump(self.scaler, open(os.path.join(MODEL_DIR, 'uptrend_scaler.pkl'), 'wb'))
            meta = {
                'features': self.feature_names,
                'horizons': PREDICT_HORIZONS,
                'thresholds': RISE_THRESHOLDS,
                'trained_at': datetime.datetime.now().isoformat(),
                'samples': len(X_list),
            }
            with open(os.path.join(MODEL_DIR, 'uptrend_meta.json'), 'w') as f:
                json.dump(meta, f, ensure_ascii=False, indent=2)

            print(f"\n  ✅ 模型训练完成，保存至 {MODEL_DIR}/")
            return True

        except ImportError:
            print("  ⚠️ XGBoost未安装")
            return False

    # ================================================================
    # 预测
    # ================================================================

    def predict(self, code):
        """
        对单只股票进行主升浪概率预测
        返回: {horizon: {threshold: probability, ...}, ...}
        """
        if not self.is_loaded():
            return {'error': '模型未加载，请先训练'}

        try:
            rows = self._fetch_stock_daily(code, 200)
            if len(rows) < 60:
                return {'error': '数据不足'}

            closes = [float(r[4]) * float(r[6] or 1) for r in rows]
            volumes = [float(r[5]) for r in rows]

            # 提取特征
            feats = self._extract_features(closes, volumes, {}, len(closes) - 1)

            # 转换为numpy
            X = np.array([[feats.get(f, 0) for f in self.feature_names]])
            if self.scaler:
                X = self.scaler.transform(X)

            # 预测
            result = {}
            for h in PREDICT_HORIZONS:
                if h not in self.models:
                    continue
                model = self.models[h]
                y_proba = model.predict_proba(X)

                probs = {}
                if isinstance(y_proba, list):
                    for i, t in enumerate(RISE_THRESHOLDS):
                        probs[f'{int(t*100)}%'] = round(float(y_proba[i][0, 1]) * 100, 1)
                else:
                    probs[f'{int(RISE_THRESHOLDS[0]*100)}%'] = round(float(y_proba[0, 1]) * 100, 1)

                result[f'{h}天'] = probs

            return result

        except Exception as e:
            return {'error': str(e)}

    def predict_batch(self, codes):
        """批量预测"""
        results = {}
        for code in codes:
            pred = self.predict(code)
            if 'error' not in pred:
                results[code] = pred
        return results

    def print_prediction(self, code, name=''):
        """打印预测结果（人类可读）"""
        pred = self.predict(code)
        if 'error' in pred:
            print(f"  ⚠️ {pred['error']}")
            return

        label = f"股票: {name}({code})" if name else f"股票: {code}"
        print(f"\n{'='*70}")
        print(f"  📈 主升浪概率预测 — {label}")
        print(f"{'='*70}")

        for horizon, probs in pred.items():
            items = ' | '.join([f"涨>{k}: {v}%" for k, v in probs.items()])
            print(f"  {horizon:<10} {items}")

        # 重点提示
        if '10天' in pred:
            p30 = pred['10天'].get('30%', 0)
            if p30 >= 80:
                signal = f'✅ 10天后涨>30%置信度{p30}%，满足≥80%门槛，强买入信号'
            elif p30 >= 60:
                signal = f'⚠️ 10天后涨>30%置信度{p30}%，接近阈值，建议结合基本面判断'
            else:
                signal = f'❌ 10天后涨>30%置信度{p30}%，未达80%门槛'
            print(f"\n  {signal}")
        print(f"{'='*70}\n")


def main():
    import argparse
    parser = argparse.ArgumentParser(description='主升浪模式识别')
    parser.add_argument('--train', action='store_true', help='训练模型')
    parser.add_argument('--predict', type=str, help='预测指定股票')
    parser.add_argument('--predict-batch', type=str, help='批量预测（逗号分隔代码）')
    parser.add_argument('--sample', type=int, default=300, help='训练样本数')
    args = parser.parse_args()

    model = UptrendModel()

    if args.train:
        model.train(sample_size=args.sample)

    elif args.predict:
        # 获取股票名称
        conn = pymysql.connect(**DB_CONFIG)
        c = conn.cursor()
        code_full = args.predict
        if not ('.SH' in code_full or '.SZ' in code_full):
            code_full = (code_full + ('.SH' if code_full.startswith('6') else '.SZ'))
        c.execute("SELECT name FROM stock_basic_info_tbl WHERE code=%s", (code_full,))
        row = c.fetchone()
        name = row[0] if row else ''
        c.close()
        conn.close()

        model.print_prediction(code_full, name)

    elif args.predict_batch:
        codes = [c.strip() for c in args.predict_batch.split(',')]
        for code in codes:
            model.print_prediction(code)

    else:
        parser.print_help()


if __name__ == '__main__':
    main()
