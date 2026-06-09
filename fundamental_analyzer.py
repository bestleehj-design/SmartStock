# -*- coding: utf-8 -*-
"""
基本面分析器 - 为策略3提供AI辅助基本面分析维度

评分维度 (总分0-100):
  盈利能力 (0-25): ROE, ROA, 毛利率, 净利率
  成长能力 (0-25): 营收增速YoY, 利润增速YoY, 近4季度趋势
  财务健康 (0-20): 资产负债率, 流动比率
  估值合理性 (0-15): PE分位, PB
  盈利质量 (0-15): 经营现金流/营收, 现金流增速
"""

from newstocklib import createMySQLCon, closeMySQL


class FundamentalAnalyzer:
    """基本面分析器 - 基于财务指标进行综合评分"""

    def __init__(self):
        self.mydb, self.dbcursor = createMySQLCon()

    def analyze(self, stock_code):
        """分析指定股票的基本面，返回评分和详细结果"""
        fina_data = self._load_fina_data(stock_code)
        if not fina_data:
            return {
                'score': 0,
                'rating': 'D',
                'rating_label': '数据不足',
                'details': {},
                'summary': '无可用财务数据'
            }
        return self.analyze_from_data(fina_data)

    def analyze_from_data(self, fina_data):
        """基于已加载的财务数据字典进行分析"""
        if not fina_data:
            return 0

        profitability = self._score_profitability(fina_data)
        growth = self._score_growth(fina_data)
        health = self._score_health(fina_data)
        valuation = self._score_valuation(fina_data)
        quality = self._score_quality(fina_data)

        total_score = profitability + growth + health + valuation + quality
        total_score = min(100, max(0, total_score))

        # 评级
        if total_score >= 80:
            rating = 'A'
            rating_label = '优秀'
        elif total_score >= 60:
            rating = 'B'
            rating_label = '良好'
        elif total_score >= 40:
            rating = 'C'
            rating_label = '一般'
        else:
            rating = 'D'
            rating_label = '较差'

        details = {
            'profitability': profitability,
            'profitability_max': 25,
            'growth': growth,
            'growth_max': 25,
            'health': health,
            'health_max': 20,
            'valuation': valuation,
            'valuation_max': 15,
            'quality': quality,
            'quality_max': 15,
            'total_score': total_score,
            'rating': rating,
            'rating_label': rating_label,
            'roe': fina_data.get('roe'),
            'roa': fina_data.get('roa'),
            'grossprofit_margin': fina_data.get('grossprofit_margin'),
            'netprofit_margin': fina_data.get('netprofit_margin'),
            'tr_yoy': fina_data.get('tr_yoy'),
            'netprofit_yoy': fina_data.get('netprofit_yoy'),
            'debt_to_assets': fina_data.get('debt_to_assets'),
            'current_ratio': fina_data.get('current_ratio'),
            'pe': fina_data.get('pe'),
            'pb': fina_data.get('pb'),
            'q_profit_yoy': fina_data.get('q_profit_yoy'),
            'q_gr_yoy': fina_data.get('q_gr_yoy'),
        }

        summary = f'基本面评分: {total_score}/100 ({rating_label})'
        if total_score >= 80:
            summary += ' - 盈利能力强，成长性好，财务健康'
        elif total_score >= 60:
            summary += ' - 基本面良好，具备投资价值'
        elif total_score >= 40:
            summary += ' - 基本面一般，需关注风险'
        else:
            summary += ' - 基本面较差，投资需谨慎'

        return {
            'score': total_score,
            'rating': rating,
            'rating_label': rating_label,
            'details': details,
            'summary': summary
        }

    def _load_fina_data(self, code):
        """从 fina_info_detailed_tbl 加载最新期财务数据"""
        try:
            sql = (
                'SELECT reportdate, data FROM fina_info_detailed_tbl '
                'WHERE code=%s ORDER BY reportdate DESC LIMIT 1'
            )
            self.dbcursor.execute(sql, (code,))
            result = self.dbcursor.fetchone()

            if result is None:
                return None

            import json
            reportdate, data_json = result
            if isinstance(data_json, str):
                data = json.loads(data_json)
            else:
                data = data_json

            data['reportdate'] = str(reportdate)
            return data
        except Exception as e:
            print(f"加载财务数据失败 {code}: {e}")
            return None

    # ========== 盈利能力评分 (0-25) ==========
    def _score_profitability(self, data):
        score = 0.0

        # ROE (0-8分)
        roe = self._safe_float(data.get('roe'))
        if roe is not None:
            if roe >= 20:
                score += 8
            elif roe >= 15:
                score += 6
            elif roe >= 10:
                score += 4
            elif roe >= 5:
                score += 2
            elif roe > 0:
                score += 1

        # ROA (0-6分)
        roa = self._safe_float(data.get('roa'))
        if roa is not None:
            if roa >= 10:
                score += 6
            elif roa >= 6:
                score += 4.5
            elif roa >= 3:
                score += 3
            elif roa >= 1:
                score += 1.5

        # 毛利率 (0-6分)
        gm = self._safe_float(data.get('grossprofit_margin'))
        if gm is not None:
            if gm >= 60:
                score += 6
            elif gm >= 40:
                score += 4.5
            elif gm >= 20:
                score += 3
            elif gm >= 10:
                score += 1.5

        # 净利率 (0-5分)
        npm = self._safe_float(data.get('netprofit_margin'))
        if npm is not None:
            if npm >= 20:
                score += 5
            elif npm >= 10:
                score += 3.5
            elif npm >= 5:
                score += 2
            elif npm > 0:
                score += 1

        return round(min(25, score), 1)

    # ========== 成长能力评分 (0-25) ==========
    def _score_growth(self, data):
        score = 0.0

        # 营收增速YoY (0-10分)
        tr_yoy = self._safe_float(data.get('tr_yoy'))
        if tr_yoy is not None:
            if tr_yoy >= 30:
                score += 10
            elif tr_yoy >= 20:
                score += 7.5
            elif tr_yoy >= 10:
                score += 5
            elif tr_yoy >= 5:
                score += 2.5
            elif tr_yoy > 0:
                score += 1

        # 利润增速YoY (0-10分)
        netprofit_yoy = self._safe_float(data.get('netprofit_yoy'))
        if netprofit_yoy is not None:
            if netprofit_yoy >= 30:
                score += 10
            elif netprofit_yoy >= 20:
                score += 7.5
            elif netprofit_yoy >= 10:
                score += 5
            elif netprofit_yoy >= 0:
                score += 2.5

        # 近4季度趋势 (0-5分) - roe_trend / revenue_growth_trend
        trend_score = 0
        roe_trend = data.get('roe_trend')
        if roe_trend and isinstance(roe_trend, list) and len(roe_trend) >= 3:
            increasing = all(
                self._safe_float(roe_trend[i]) is not None
                and self._safe_float(roe_trend[i + 1]) is not None
                and self._safe_float(roe_trend[i]) < self._safe_float(roe_trend[i + 1])
                for i in range(len(roe_trend) - 1)
            )
            if increasing:
                trend_score += 3
            elif (
                self._safe_float(roe_trend[0]) is not None
                and self._safe_float(roe_trend[-1]) is not None
                and self._safe_float(roe_trend[-1]) > self._safe_float(roe_trend[0])
            ):
                trend_score += 1.5

        rev_trend = data.get('revenue_growth_trend')
        if rev_trend and isinstance(rev_trend, list) and len(rev_trend) >= 3:
            increasing = all(
                self._safe_float(rev_trend[i]) is not None
                and self._safe_float(rev_trend[i + 1]) is not None
                and self._safe_float(rev_trend[i]) < self._safe_float(rev_trend[i + 1])
                for i in range(len(rev_trend) - 1)
            )
            if increasing:
                trend_score += 2
            elif (
                self._safe_float(rev_trend[0]) is not None
                and self._safe_float(rev_trend[-1]) is not None
                and self._safe_float(rev_trend[-1]) > self._safe_float(rev_trend[0])
            ):
                trend_score += 1

        score += min(5, trend_score)

        return round(min(25, score), 1)

    # ========== 财务健康评分 (0-20) ==========
    def _score_health(self, data):
        score = 0.0

        # 资产负债率 (0-12分) - 越低越好，但也不是越低越健康
        debt = self._safe_float(data.get('debt_to_assets'))
        if debt is not None:
            if 30 <= debt <= 50:
                score += 12
            elif 20 <= debt < 30 or 50 < debt <= 60:
                score += 9
            elif 10 <= debt < 20 or 60 < debt <= 70:
                score += 6
            elif debt < 10 or 70 < debt <= 80:
                score += 3
            elif debt > 80:
                score += 1  # 极高负债率仍有底线分以避免完全零分

        # 流动比率 (0-8分)
        cr = self._safe_float(data.get('current_ratio'))
        if cr is not None:
            if 1.5 <= cr <= 3.0:
                score += 8
            elif 1.0 <= cr < 1.5 or 3.0 < cr <= 5.0:
                score += 5
            elif cr < 1.0:
                score += 2  # 存在短期偿债压力
            elif cr > 5.0:
                score += 3  # 过高，资产利用效率低

        return round(min(20, score), 1)

    # ========== 估值评分 (0-15) ==========
    def _score_valuation(self, data):
        score = 0.0

        # PE (0-10分) - 越低估值越合理
        pe = self._safe_float(data.get('pe'))
        if pe is not None:
            if pe < 0:
                score += 0  # 亏损
            elif pe <= 15:
                score += 10
            elif pe <= 25:
                score += 7.5
            elif pe <= 50:
                score += 5
            elif pe <= 80:
                score += 2.5

        # PB (0-5分)
        pb = self._safe_float(data.get('pb'))
        if pb is not None:
            if pb < 0:
                score += 0
            elif pb <= 1.5:
                score += 5
            elif pb <= 3:
                score += 3.5
            elif pb <= 5:
                score += 2
            elif pb <= 8:
                score += 1

        return round(min(15, score), 1)

    # ========== 盈利质量评分 (0-15) ==========
    def _score_quality(self, data):
        score = 0.0

        # 经营现金流/营收 (0-10分)
        cf_sales = self._safe_float(data.get('cf_sales'))
        if cf_sales is not None:
            if cf_sales >= 0.2:
                score += 10
            elif cf_sales >= 0.1:
                score += 7.5
            elif cf_sales >= 0.05:
                score += 5
            elif cf_sales > 0:
                score += 2.5

        # 现金流增速 (0-5分)
        ocf_yoy = self._safe_float(data.get('ocf_yoy'))
        if ocf_yoy is not None:
            if ocf_yoy >= 30:
                score += 5
            elif ocf_yoy >= 15:
                score += 3.5
            elif ocf_yoy >= 0:
                score += 2
            else:
                score += 0  # 现金流下降

        return round(min(15, score), 1)

    def _safe_float(self, val):
        """安全转换为float，处理None和NaN"""
        if val is None:
            return None
        try:
            result = float(val)
            import math
            if math.isnan(result) or math.isinf(result):
                return None
            return result
        except (ValueError, TypeError):
            return None
