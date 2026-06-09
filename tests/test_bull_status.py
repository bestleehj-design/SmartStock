#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
测试多头状态计算算法
"""

import sys
import os
from data.technical_indicators import TrendAnalyzer


def test_bull_status_calculation():
    """
    测试多头状态计算
    """
    print("开始测试多头状态计算算法...\n")
    
    analyzer = TrendAnalyzer()
    
    # 测试场景1: 明确的多头排列 (短期均线在长期均线之上)
    print("===== 测试场景1: 明确的多头排列 =====")
    # 模拟价格数据，形成多头排列（价格逐渐上升）
    bullish_prices = [10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30, 31, 32, 33, 34, 35, 36, 37, 38, 39, 40]
    
    # 手动计算不同周期的均线值（最后一个值）
    ma5 = sum(bullish_prices[-5:]) / 5
    ma10 = sum(bullish_prices[-10:]) / 10
    ma20 = sum(bullish_prices[-20:]) / 20
    ma30 = sum(bullish_prices[-30:]) / 30
    
    print(f"价格序列: {bullish_prices[-10:]}")
    print(f"MA5: {ma5:.2f}, MA10: {ma10:.2f}, MA20: {ma20:.2f}, MA30: {ma30:.2f}")
    print(f"预期: 多头排列 (MA5 > MA10 > MA20 > MA30)")
    
    # 测试is_ma_ascending方法
    ma_values = [ma5, ma10, ma20, ma30]  # 按周期从小到大排列
    result = analyzer.is_ma_ascending(ma_values)
    print(f"is_ma_ascending([MA5, MA10, MA20, MA30]) = {result}")
    print(f"预期: True (短期均线在长期均线之上)\n")
    
    # 测试完整的多头趋势分析
    bull_trend = analyzer.analyze_all_bull_trends(bullish_prices)
    print(f"短均多头: {bull_trend['short_term_bull']}")
    print(f"中均多头: {bull_trend['mid_term_bull']}")
    print(f"长均多头: {bull_trend['long_term_bull']}")
    print(f"5线开花: {bull_trend['five_line_bull']}\n")
    
    # 测试场景2: 明确的空头排列 (长期均线在短期均线之上)
    print("===== 测试场景2: 明确的空头排列 =====")
    # 模拟价格数据，形成空头排列（价格逐渐下降）
    bearish_prices = list(reversed(bullish_prices))  # 反转多头排列，形成空头排列
    
    # 手动计算不同周期的均线值（最后一个值）
    ma5_bear = sum(bearish_prices[-5:]) / 5
    ma10_bear = sum(bearish_prices[-10:]) / 10
    ma20_bear = sum(bearish_prices[-20:]) / 20
    ma30_bear = sum(bearish_prices[-30:]) / 30
    
    print(f"价格序列: {bearish_prices[-10:]}")
    print(f"MA5: {ma5_bear:.2f}, MA10: {ma10_bear:.2f}, MA20: {ma20_bear:.2f}, MA30: {ma30_bear:.2f}")
    print(f"预期: 空头排列 (MA5 < MA10 < MA20 < MA30)")
    
    # 测试is_ma_ascending方法
    ma_values_bear = [ma5_bear, ma10_bear, ma20_bear, ma30_bear]  # 按周期从小到大排列
    result_bear = analyzer.is_ma_ascending(ma_values_bear)
    print(f"is_ma_ascending([MA5, MA10, MA20, MA30]) = {result_bear}")
    print(f"预期: False (长期均线在短期均线之上)\n")
    
    # 测试完整的多头趋势分析
    bear_trend = analyzer.analyze_all_bull_trends(bearish_prices)
    print(f"短均多头: {bear_trend['short_term_bull']}")
    print(f"中均多头: {bear_trend['mid_term_bull']}")
    print(f"长均多头: {bear_trend['long_term_bull']}")
    print(f"5线开花: {bear_trend['five_line_bull']}\n")
    
    # 测试场景3: 不规则排列
    print("===== 测试场景3: 不规则排列 =====")
    # 模拟价格数据，形成不规则排列
    mixed_prices = [10, 11, 10, 11, 10, 11, 10, 11, 10, 11, 10, 11, 10, 11, 10, 11, 10, 11, 10, 11, 10, 11, 10, 11, 10, 11, 10, 11, 10, 11, 10]
    
    # 测试完整的多头趋势分析
    mixed_trend = analyzer.analyze_all_bull_trends(mixed_prices)
    print(f"短均多头: {mixed_trend['short_term_bull']}")
    print(f"中均多头: {mixed_trend['mid_term_bull']}")
    print(f"长均多头: {mixed_trend['long_term_bull']}")
    print(f"5线开花: {mixed_trend['five_line_bull']}\n")
    
    print("测试完成!")


if __name__ == "__main__":
    test_bull_status_calculation()