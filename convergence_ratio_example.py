#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
均线粘合度计算示例
演示 calculate_convergence_ratio 函数的具体计算过程
"""

def calculate_convergence_ratio(ma_values):
    """
    计算均线粘合度
    
    Args:
        ma_values: 均线值列表
        
    Returns:
        粘合度比例 (max-min)/min
    """
    if not ma_values or len(ma_values) < 2:
        return 0.0
    
    max_ma = max(ma_values)
    min_ma = min(ma_values)
    
    if min_ma <= 0:
        return 0.0
    
    return (max_ma - min_ma) / min_ma


print("=" * 60)
print("均线粘合度计算示例")
print("=" * 60)

# 示例1: 高度粘合的情况（均线非常接近）
print("\n【示例1】高度粘合 - 均线非常接近")
ma_values_1 = [10.00, 10.05, 10.02, 10.08, 10.03]
print(f"均线值: {ma_values_1}")
print(f"最大值: {max(ma_values_1):.2f}")
print(f"最小值: {min(ma_values_1):.2f}")
ratio_1 = calculate_convergence_ratio(ma_values_1)
print(f"粘合度 = (最大值 - 最小值) / 最小值")
print(f"粘合度 = ({max(ma_values_1):.2f} - {min(ma_values_1):.2f}) / {min(ma_values_1):.2f}")
print(f"粘合度 = {ratio_1:.4f} = {ratio_1*100:.2f}%")
print(f"结论: {'高度粘合' if ratio_1 < 0.04 else '未粘合'} (阈值4%)")

# 示例2: 中度粘合的情况
print("\n【示例2】中度粘合 - 均线有一定距离")
ma_values_2 = [10.00, 10.15, 10.08, 10.20, 10.12]
print(f"均线值: {ma_values_2}")
print(f"最大值: {max(ma_values_2):.2f}")
print(f"最小值: {min(ma_values_2):.2f}")
ratio_2 = calculate_convergence_ratio(ma_values_2)
print(f"粘合度 = ({max(ma_values_2):.2f} - {min(ma_values_2):.2f}) / {min(ma_values_2):.2f}")
print(f"粘合度 = {ratio_2:.4f} = {ratio_2*100:.2f}%")
print(f"结论: {'粘合' if ratio_2 < 0.04 else '未粘合'} (阈值4%)")

# 示例3: 未粘合的情况（均线分散）
print("\n【示例3】未粘合 - 均线分散")
ma_values_3 = [10.00, 10.50, 10.30, 11.00, 10.80]
print(f"均线值: {ma_values_3}")
print(f"最大值: {max(ma_values_3):.2f}")
print(f"最小值: {min(ma_values_3):.2f}")
ratio_3 = calculate_convergence_ratio(ma_values_3)
print(f"粘合度 = ({max(ma_values_3):.2f} - {min(ma_values_3):.2f}) / {min(ma_values_3):.2f}")
print(f"粘合度 = {ratio_3:.4f} = {ratio_3*100:.2f}%")
print(f"结论: {'粘合' if ratio_3 < 0.04 else '未粘合'} (阈值4%)")

# 示例4: 实际股票场景 - 5日、10日、30日均线
print("\n【示例4】实际场景 - 5日、10日、30日均线粘合")
ma5 = 12.50
ma10 = 12.45
ma30 = 12.48
ma_values_4 = [ma5, ma10, ma30]
print(f"5日均线: {ma5:.2f}")
print(f"10日均线: {ma10:.2f}")
print(f"30日均线: {ma30:.2f}")
print(f"均线值: {ma_values_4}")
ratio_4 = calculate_convergence_ratio(ma_values_4)
print(f"粘合度 = ({max(ma_values_4):.2f} - {min(ma_values_4):.2f}) / {min(ma_values_4):.2f}")
print(f"粘合度 = {ratio_4:.4f} = {ratio_4*100:.2f}%")
print(f"结论: {'均线粘合，可能酝酿突破' if ratio_4 < 0.04 else '均线未粘合，趋势明确'}")

# 示例5: 边界情况 - 空列表
print("\n【示例5】边界情况 - 空列表")
ma_values_5 = []
ratio_5 = calculate_convergence_ratio(ma_values_5)
print(f"均线值: {ma_values_5}")
print(f"粘合度: {ratio_5}")
print(f"结论: 数据不足，返回0.0")

# 示例6: 边界情况 - 只有一条均线
print("\n【示例6】边界情况 - 只有一条均线")
ma_values_6 = [10.00]
ratio_6 = calculate_convergence_ratio(ma_values_6)
print(f"均线值: {ma_values_6}")
print(f"粘合度: {ratio_6}")
print(f"结论: 至少需要2条均线才能计算粘合度")

# 示例7: 边界情况 - 最小值为0或负数
print("\n【示例7】边界情况 - 最小值为0")
ma_values_7 = [0.0, 0.5, 1.0]
ratio_7 = calculate_convergence_ratio(ma_values_7)
print(f"均线值: {ma_values_7}")
print(f"粘合度: {ratio_7}")
print(f"结论: 最小值为0时，避免除零错误，返回0.0")

print("\n" + "=" * 60)
print("总结:")
print("=" * 60)
print("1. 粘合度 = (最大值 - 最小值) / 最小值")
print("2. 粘合度越小，表示均线越接近（粘合度越高）")
print("3. 通常粘合度 < 4% 被认为是均线粘合")
print("4. 均线粘合通常表示价格整理，可能酝酿突破")
print("=" * 60)





























