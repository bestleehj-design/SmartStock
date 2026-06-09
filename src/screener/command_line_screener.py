#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
命令行股票筛选器
基于命令行手册实现的技术分析筛选系统
"""

import pymysql
import os
import argparse
import sys
from typing import List, Dict, Optional, Tuple
from datetime import datetime, timedelta
import json

# 设置环境变量
os.environ['TMPDIR'] = os.path.expanduser('~/mysql_temp')

class CommandLineScreener:
    """命令行股票筛选器"""
    
    def __init__(self):
        self.connection = None
        self.cursor = None
        self.stock_data_cache = {}
        
        # 默认参数
        self.start_index = 0
        self.predays = 5
        self.inc_or_exc = 0  # 0=include, 1=exclude
        
        # 筛选条件
        self.conditions = []
        
    def connect_database(self):
        """连接数据库"""
        try:
            self.connection = pymysql.connect(
                host='localhost',
                port=3306,
                user='root',
                password='12345678',
                database='gp2',
                charset='utf8mb4',
                autocommit=True
            )
            self.cursor = self.connection.cursor()
            print("✅ 数据库连接成功")
            return True
        except Exception as e:
            print(f"❌ 数据库连接失败: {e}")
            return False
    
    def close_database(self):
        """关闭数据库连接"""
        if self.cursor:
            self.cursor.close()
        if self.connection:
            self.connection.close()
    
    def calculate_ma(self, prices: List[float], period: int) -> List[float]:
        """计算移动平均线"""
        if len(prices) < period:
            return []
        
        ma_values = []
        for i in range(period - 1, len(prices)):
            ma = sum(prices[i - period + 1:i + 1]) / period
            ma_values.append(ma)
        return ma_values
    
    def get_stock_data(self, code: str, days: int = 100) -> Optional[Dict]:
        """获取股票数据"""
        try:
            sql = """
            SELECT tradedate, open, high, low, close, volume, amount
            FROM daily_info_tbl 
            WHERE code = %s 
            ORDER BY tradedate DESC 
            LIMIT %s
            """
            
            self.cursor.execute(sql, (code, days))
            result = self.cursor.fetchall()
            
            if not result:
                return None
            
            dates = [row[0] for row in result]
            opens = [float(row[1]) for row in result]
            highs = [float(row[2]) for row in result]
            lows = [float(row[3]) for row in result]
            closes = [float(row[4]) for row in result]
            volumes = [int(row[5]) for row in result]
            amounts = [float(row[6]) for row in result]
            
            return {
                'dates': dates,
                'opens': opens,
                'highs': highs,
                'lows': lows,
                'closes': closes,
                'volumes': volumes,
                'amounts': amounts
            }
        except Exception as e:
            print(f"❌ 获取股票数据失败 {code}: {e}")
            return None
    
    def check_condition_a(self, stock_data: Dict, a1: int, a2: int, r1: float, r2: float) -> bool:
        """检查涨幅条件 -a a1 a2 r1 r2"""
        closes = stock_data['closes']
        if len(closes) < self.predays:
            return False
        
        count = 0
        for i in range(self.start_index, min(self.start_index + self.predays, len(closes) - 1)):
            if i + 1 < len(closes):
                change_rate = (closes[i] - closes[i + 1]) / closes[i + 1]
                # 将百分比转换为小数进行比较
                change_rate_pct = change_rate * 100
                if r1 <= change_rate_pct <= r2:
                    count += 1
        
        return a1 <= count <= a2
    
    def check_condition_b(self, stock_data: Dict, r1: float, r2: float) -> bool:
        """检查价格区间条件 -b r1 r2"""
        closes = stock_data['closes']
        if len(closes) < self.predays:
            return False
        
        data_range = closes[self.start_index:self.start_index + self.predays]
        if not data_range:
            return False
        
        min_price = min(data_range)
        max_price = max(data_range)
        change_rate = (max_price - min_price) / min_price
        
        return r1 <= change_rate <= r2
    
    def check_condition_c(self, stock_data: Dict, c1: int, c2: int, r1: float, r2: float) -> bool:
        """检查换手率条件 -c c1 c2 r1 r2"""
        # 这里需要换手率数据，暂时用成交量代替
        volumes = stock_data['volumes']
        if len(volumes) < self.predays:
            return False
        
        count = 0
        avg_volume = sum(volumes) / len(volumes)
        
        for i in range(self.start_index, min(self.start_index + self.predays, len(volumes))):
            volume_ratio = volumes[i] / avg_volume if avg_volume > 0 else 0
            if r1 <= volume_ratio <= r2:
                count += 1
        
        return c1 <= count <= c2
    
    def check_condition_d(self, stock_data: Dict, d1: int, d2: int, r1: float, r2: float) -> bool:
        """检查相对换手率条件 -d d1 d2 r1 r2"""
        volumes = stock_data['volumes']
        if len(volumes) < self.predays:
            return False
        
        count = 0
        # 使用v37作为基准（这里简化为37天平均成交量）
        v37 = sum(volumes[:37]) / 37 if len(volumes) >= 37 else sum(volumes) / len(volumes)
        
        for i in range(self.start_index, min(self.start_index + self.predays, len(volumes))):
            ratio = volumes[i] / v37 if v37 > 0 else 0
            if r1 <= ratio <= r2:
                count += 1
        
        return d1 <= count <= d2
    
    def check_condition_e(self, stock_data: Dict, a1: int, a2: int, a3: int) -> bool:
        """检查短线多头条件 -e a1 a2 a3"""
        closes = stock_data['closes']
        if len(closes) < 30:  # 需要足够数据计算均线
            return False
        
        count = 0
        for i in range(self.start_index, min(self.start_index + self.predays, len(closes) - 30)):
            # 计算MA5, MA10, MA20, MA30
            ma5 = sum(closes[i:i+5]) / 5
            ma10 = sum(closes[i:i+10]) / 10
            ma20 = sum(closes[i:i+20]) / 20
            ma30 = sum(closes[i:i+30]) / 30
            
            # 检查多头排列
            is_bullish = ma5 > ma10 > ma20 > ma30
            
            if a3 == 1:  # 真多头，收盘价要在均线之上
                is_bullish = is_bullish and closes[i] > ma5
            elif a3 == 0:  # 假多头，不要求收盘价位置
                pass
            
            if is_bullish:
                count += 1
        
        return a1 <= count <= a2
    
    def check_condition_f(self, stock_data: Dict, a1: int, a2: int, a3: int) -> bool:
        """检查中线多头条件 -f a1 a2 a3"""
        closes = stock_data['closes']
        if len(closes) < 150:  # 需要足够数据计算周线
            return False
        
        count = 0
        for i in range(self.start_index, min(self.start_index + self.predays, len(closes) - 150)):
            # 计算周线均线 (5周=25天, 10周=50天, 20周=100天, 30周=150天)
            ma25 = sum(closes[i:i+25]) / 25
            ma50 = sum(closes[i:i+50]) / 50
            ma100 = sum(closes[i:i+100]) / 100
            ma150 = sum(closes[i:i+150]) / 150
            
            # 检查多头排列
            is_bullish = ma25 > ma50 > ma100 > ma150
            
            if a3 == 1:  # 真多头
                is_bullish = is_bullish and closes[i] > ma25
            elif a3 == 0:  # 假多头
                pass
            
            if is_bullish:
                count += 1
        
        return a1 <= count <= a2
    
    def check_condition_g(self, stock_data: Dict, a1: int, a2: int, a3: int) -> bool:
        """检查长线多头条件 -g a1 a2 a3"""
        closes = stock_data['closes']
        if len(closes) < 600:  # 需要足够数据计算月线
            return False
        
        count = 0
        for i in range(self.start_index, min(self.start_index + self.predays, len(closes) - 600)):
            # 计算月线均线 (5月=100天, 10月=200天, 20月=400天, 30月=600天)
            ma100 = sum(closes[i:i+100]) / 100
            ma200 = sum(closes[i:i+200]) / 200
            ma400 = sum(closes[i:i+400]) / 400
            ma600 = sum(closes[i:i+600]) / 600
            
            # 检查多头排列
            is_bullish = ma100 > ma200 > ma400 > ma600
            
            if a3 == 1:  # 真多头
                is_bullish = is_bullish and closes[i] > ma100
            elif a3 == 0:  # 假多头
                pass
            
            if is_bullish:
                count += 1
        
        return a1 <= count <= a2
    
    def check_condition_h(self, stock_data: Dict, a1: int, a2: int, a3: int) -> bool:
        """检查5线开花条件 -h a1 a2 a3"""
        closes = stock_data['closes']
        if len(closes) < 250:  # 需要足够数据计算所有均线
            return False
        
        count = 0
        for i in range(self.start_index, min(self.start_index + self.predays, len(closes) - 250)):
            # 计算5条均线
            ma5 = sum(closes[i:i+5]) / 5
            ma10 = sum(closes[i:i+10]) / 10
            ma30 = sum(closes[i:i+30]) / 30
            ma120 = sum(closes[i:i+120]) / 120
            ma250 = sum(closes[i:i+250]) / 250
            
            # 检查5线开花（多头排列）
            is_bullish = ma5 > ma10 > ma30 > ma120 > ma250
            
            if a3 == 1:  # 真多头
                is_bullish = is_bullish and closes[i] > ma5
            elif a3 == 0:  # 假多头
                pass
            
            if is_bullish:
                count += 1
        
        return a1 <= count <= a2
    
    def check_ma_convergence(self, stock_data: Dict, periods: List[int], a1: int, a2: int) -> bool:
        """检查均线粘合条件"""
        closes = stock_data['closes']
        max_period = max(periods)
        
        if len(closes) < max_period:
            return False
        
        count = 0
        for i in range(self.start_index, min(self.start_index + self.predays, len(closes) - max_period)):
            # 计算指定周期的均线
            ma_values = []
            for period in periods:
                ma = sum(closes[i:i+period]) / period
                ma_values.append(ma)
            
            # 检查粘合度（最大值与最小值的比值）
            max_ma = max(ma_values)
            min_ma = min(ma_values)
            convergence_rate = (max_ma - min_ma) / min_ma
            
            # 粘合度阈值设为4%
            if convergence_rate <= 0.04:
                count += 1
        
        return a1 <= count <= a2
    
    def check_condition_i(self, stock_data: Dict, a1: int, a2: int) -> bool:
        """检查5-10粘合条件 -i a1 a2"""
        return self.check_ma_convergence(stock_data, [5, 10], a1, a2)
    
    def check_condition_j(self, stock_data: Dict, a1: int, a2: int) -> bool:
        """检查5-10-20粘合条件 -j a1 a2"""
        return self.check_ma_convergence(stock_data, [5, 10, 20], a1, a2)
    
    def check_condition_k(self, stock_data: Dict, a1: int, a2: int) -> bool:
        """检查5-10-20-30粘合条件 -k a1 a2"""
        return self.check_ma_convergence(stock_data, [5, 10, 20, 30], a1, a2)
    
    def check_condition_m(self, stock_data: Dict, a1: int, a2: int) -> bool:
        """检查5-10-20-30-60粘合条件 -m a1 a2"""
        return self.check_ma_convergence(stock_data, [5, 10, 20, 30, 60], a1, a2)
    
    def check_condition_n(self, stock_data: Dict, a1: int, a2: int) -> bool:
        """检查10-20-30-60-120粘合条件 -n a1 a2"""
        return self.check_ma_convergence(stock_data, [10, 20, 30, 60, 120], a1, a2)
    
    def check_condition_o(self, stock_data: Dict, a1: int, a2: int) -> bool:
        """检查10-20-30-60-120-250粘合条件 -o a1 a2"""
        return self.check_ma_convergence(stock_data, [10, 20, 30, 60, 120, 250], a1, a2)
    
    def check_condition_p(self, stock_data: Dict, a1: int, a2: int) -> bool:
        """检查10-20-30-60-120-250-500粘合条件 -p a1 a2"""
        return self.check_ma_convergence(stock_data, [10, 20, 30, 60, 120, 250, 500], a1, a2)
    
    def check_condition_q(self, stock_data: Dict, a1: int, a2: int) -> bool:
        """检查日线粘合5-10-30条件 -q a1 a2"""
        return self.check_ma_convergence(stock_data, [5, 10, 30], a1, a2)
    
    def check_condition_r(self, stock_data: Dict, a1: int, a2: int) -> bool:
        """检查周线粘合25-50-150条件 -r a1 a2"""
        return self.check_ma_convergence(stock_data, [25, 50, 150], a1, a2)
    
    def check_condition_s(self, stock_data: Dict, a1: int, a2: int) -> bool:
        """检查月线粘合100-200-600条件 -s a1 a2"""
        return self.check_ma_convergence(stock_data, [100, 200, 600], a1, a2)
    
    def check_condition_t(self, stock_data: Dict, a1: int, a2: int, r1: float, r2: float) -> bool:
        """检查创新低条件 -t a1 a2 r1 r2"""
        closes = stock_data['closes']
        if len(closes) < self.predays + 10:  # 需要更多数据
            return False
        
        count = 0
        for i in range(self.start_index, min(self.start_index + self.predays, len(closes) - 10)):
            # 检查前面是否有r1-r2的涨幅
            has_gain = False
            for j in range(i + 1, min(i + 10, len(closes) - 1)):
                gain_rate = (closes[j] - closes[j + 1]) / closes[j + 1]
                if r1 <= gain_rate <= r2:
                    has_gain = True
                    break
            
            if has_gain:
                # 检查是否没有创新低
                current_price = closes[i]
                min_price = min(closes[i:i+5])  # 最近5天最低价
                if current_price >= min_price:
                    count += 1
        
        return a1 <= count <= a2
    
    def check_condition_u(self, stock_data: Dict, r1: float, r2: float) -> bool:
        """检查量能对比条件 -u r1 r2"""
        closes = stock_data['closes']
        volumes = stock_data['volumes']
        
        if len(closes) < self.predays:
            return False
        
        # 计算阳线和阴线的平均量能
        yang_volumes = []
        yin_volumes = []
        
        for i in range(self.start_index, min(self.start_index + self.predays, len(closes) - 1)):
            if closes[i] > closes[i + 1]:  # 阳线
                yang_volumes.append(volumes[i])
            else:  # 阴线
                yin_volumes.append(volumes[i])
        
        if not yang_volumes or not yin_volumes:
            return False
        
        avg_yang = sum(yang_volumes) / len(yang_volumes)
        avg_yin = sum(yin_volumes) / len(yin_volumes)
        
        ratio = avg_yang / avg_yin if avg_yin > 0 else 0
        
        return r1 <= ratio <= r2
    
    def check_condition_v(self, stock_data: Dict, a1: int, a2: int) -> bool:
        """检查5上穿10条件 -v a1 a2"""
        closes = stock_data['closes']
        if len(closes) < 20:
            return False
        
        count = 0
        for i in range(self.start_index, min(self.start_index + self.predays, len(closes) - 10)):
            # 计算MA5和MA10
            ma5_current = sum(closes[i:i+5]) / 5
            ma10_current = sum(closes[i:i+10]) / 10
            
            if i + 1 < len(closes) - 10:
                ma5_prev = sum(closes[i+1:i+6]) / 5
                ma10_prev = sum(closes[i+1:i+11]) / 10
                
                # 检查5日线上穿10日线
                if ma5_prev <= ma10_prev and ma5_current > ma10_current:
                    count += 1
        
        return a1 <= count <= a2
    
    def check_condition_w(self, stock_data: Dict, a1: int, a2: int, a3: int) -> bool:
        """检查收盘价在均线之上条件 -w a1 a2 a3"""
        closes = stock_data['closes']
        if len(closes) < a3:
            return False
        
        count = 0
        for i in range(self.start_index, min(self.start_index + self.predays, len(closes) - a3)):
            ma = sum(closes[i:i+a3]) / a3
            if closes[i] > ma:
                count += 1
        
        return a1 <= count <= a2
    
    def add_condition(self, condition_type: str, *args):
        """添加筛选条件"""
        self.conditions.append((condition_type, args))
    
    def check_stock(self, code: str) -> bool:
        """检查单只股票是否满足所有条件"""
        stock_data = self.get_stock_data(code)
        if not stock_data:
            return False
        
        for condition_type, args in self.conditions:
            try:
                if condition_type == 'a':
                    if not self.check_condition_a(stock_data, *args):
                        return False
                elif condition_type == 'b':
                    if not self.check_condition_b(stock_data, *args):
                        return False
                elif condition_type == 'c':
                    if not self.check_condition_c(stock_data, *args):
                        return False
                elif condition_type == 'd':
                    if not self.check_condition_d(stock_data, *args):
                        return False
                elif condition_type == 'e':
                    if not self.check_condition_e(stock_data, *args):
                        return False
                elif condition_type == 'f':
                    if not self.check_condition_f(stock_data, *args):
                        return False
                elif condition_type == 'g':
                    if not self.check_condition_g(stock_data, *args):
                        return False
                elif condition_type == 'h':
                    if not self.check_condition_h(stock_data, *args):
                        return False
                elif condition_type == 'i':
                    if not self.check_condition_i(stock_data, *args):
                        return False
                elif condition_type == 'j':
                    if not self.check_condition_j(stock_data, *args):
                        return False
                elif condition_type == 'k':
                    if not self.check_condition_k(stock_data, *args):
                        return False
                elif condition_type == 'm':
                    if not self.check_condition_m(stock_data, *args):
                        return False
                elif condition_type == 'n':
                    if not self.check_condition_n(stock_data, *args):
                        return False
                elif condition_type == 'o':
                    if not self.check_condition_o(stock_data, *args):
                        return False
                elif condition_type == 'p':
                    if not self.check_condition_p(stock_data, *args):
                        return False
                elif condition_type == 'q':
                    if not self.check_condition_q(stock_data, *args):
                        return False
                elif condition_type == 'r':
                    if not self.check_condition_r(stock_data, *args):
                        return False
                elif condition_type == 's':
                    if not self.check_condition_s(stock_data, *args):
                        return False
                elif condition_type == 't':
                    if not self.check_condition_t(stock_data, *args):
                        return False
                elif condition_type == 'u':
                    if not self.check_condition_u(stock_data, *args):
                        return False
                elif condition_type == 'v':
                    if not self.check_condition_v(stock_data, *args):
                        return False
                elif condition_type == 'w':
                    if not self.check_condition_w(stock_data, *args):
                        return False
            except Exception as e:
                print(f"❌ 检查条件 {condition_type} 时出错: {e}")
                return False
        
        return True
    
    def get_all_stock_codes(self) -> List[str]:
        """获取所有股票代码"""
        try:
            sql = "SELECT DISTINCT code FROM daily_info_tbl WHERE code LIKE '00%' OR code LIKE '30%' OR code LIKE '60%'"
            self.cursor.execute(sql)
            result = self.cursor.fetchall()
            return [row[0] for row in result]
        except Exception as e:
            print(f"❌ 获取股票代码失败: {e}")
            return []
    
    def screen_stocks(self) -> List[str]:
        """执行股票筛选"""
        print(f"🔍 开始筛选股票...")
        print(f"📊 筛选条件: {len(self.conditions)} 个")
        print(f"📅 时间窗口: start_index={self.start_index}, predays={self.predays}")
        
        all_codes = self.get_all_stock_codes()
        print(f"📈 总股票数量: {len(all_codes)}")
        
        candidates = []
        processed = 0
        
        for code in all_codes:
            processed += 1
            if processed % 100 == 0:
                print(f"⏳ 已处理: {processed}/{len(all_codes)} ({processed/len(all_codes)*100:.1f}%)")
            
            if self.check_stock(code):
                candidates.append(code)
                print(f"✅ 找到候选股票: {code}")
        
        print(f"🎯 筛选完成! 找到 {len(candidates)} 只符合条件的股票")
        return candidates


def parse_command_line():
    """解析命令行参数"""
    parser = argparse.ArgumentParser(description='股票技术分析筛选器')
    
    # 基础参数
    parser.add_argument('-D', '--time-window', nargs=2, type=int, metavar=('START_INDEX', 'PREDAYS'),
                       help='设置时间窗口: start_index predays (默认: 0 5)')
    
    parser.add_argument('-I', '--include-exclude', type=int, choices=[0, 1],
                       help='包含/排除模式: 0=include, 1=exclude')
    
    # 价格相关条件
    parser.add_argument('-a', '--gain-range', nargs=4, type=float, metavar=('A1', 'A2', 'R1', 'R2'),
                       help='涨幅条件: a1 a2 r1 r2 (天数范围 涨幅范围)')
    
    parser.add_argument('-b', '--price-range', nargs=2, type=float, metavar=('R1', 'R2'),
                       help='价格区间条件: r1 r2 (最低到最高涨幅范围)')
    
    # 成交量条件
    parser.add_argument('-c', '--turnover-range', nargs=4, type=float, metavar=('C1', 'C2', 'R1', 'R2'),
                       help='换手率条件: c1 c2 r1 r2')
    
    parser.add_argument('-d', '--volume-ratio', nargs=4, type=float, metavar=('D1', 'D2', 'R1', 'R2'),
                       help='相对换手率条件: d1 d2 r1 r2')
    
    parser.add_argument('-u', '--volume-compare', nargs=2, type=float, metavar=('R1', 'R2'),
                       help='量能对比条件: r1 r2 (阳线/阴线量能比)')
    
    # 多头条件
    parser.add_argument('-e', '--short-bull', nargs=3, type=int, metavar=('A1', 'A2', 'A3'),
                       help='短线多头: a1 a2 a3 (a3: 1=真多头, 0=假多头)')
    
    parser.add_argument('-f', '--medium-bull', nargs=3, type=int, metavar=('A1', 'A2', 'A3'),
                       help='中线多头: a1 a2 a3')
    
    parser.add_argument('-g', '--long-bull', nargs=3, type=int, metavar=('A1', 'A2', 'A3'),
                       help='长线多头: a1 a2 a3')
    
    parser.add_argument('-H', '--five-line-flower', nargs=3, type=int, metavar=('A1', 'A2', 'A3'),
                       help='5线开花: a1 a2 a3')
    
    # 均线粘合条件
    parser.add_argument('-i', '--ma5-10-convergence', nargs=2, type=int, metavar=('A1', 'A2'),
                       help='5-10粘合: a1 a2')
    
    parser.add_argument('-j', '--ma5-10-20-convergence', nargs=2, type=int, metavar=('A1', 'A2'),
                       help='5-10-20粘合: a1 a2')
    
    parser.add_argument('-k', '--ma5-10-20-30-convergence', nargs=2, type=int, metavar=('A1', 'A2'),
                       help='5-10-20-30粘合: a1 a2')
    
    parser.add_argument('-m', '--ma5-10-20-30-60-convergence', nargs=2, type=int, metavar=('A1', 'A2'),
                       help='5-10-20-30-60粘合: a1 a2')
    
    parser.add_argument('-n', '--ma10-20-30-60-120-convergence', nargs=2, type=int, metavar=('A1', 'A2'),
                       help='10-20-30-60-120粘合: a1 a2')
    
    parser.add_argument('-O', '--ma10-20-30-60-120-250-convergence', nargs=2, type=int, metavar=('A1', 'A2'),
                       help='10-20-30-60-120-250粘合: a1 a2')
    
    parser.add_argument('-p', '--ma10-20-30-60-120-250-500-convergence', nargs=2, type=int, metavar=('A1', 'A2'),
                       help='10-20-30-60-120-250-500粘合: a1 a2')
    
    # 多周期粘合
    parser.add_argument('-q', '--daily-convergence', nargs=2, type=int, metavar=('A1', 'A2'),
                       help='日线粘合5-10-30: a1 a2')
    
    parser.add_argument('-r', '--weekly-convergence', nargs=2, type=int, metavar=('A1', 'A2'),
                       help='周线粘合25-50-150: a1 a2')
    
    parser.add_argument('-s', '--monthly-convergence', nargs=2, type=int, metavar=('A1', 'A2'),
                       help='月线粘合100-200-600: a1 a2')
    
    # 特殊条件
    parser.add_argument('-t', '--new-low', nargs=4, type=float, metavar=('A1', 'A2', 'R1', 'R2'),
                       help='创新低条件: a1 a2 r1 r2')
    
    parser.add_argument('-V', '--ma5-cross-ma10', nargs=2, type=int, metavar=('A1', 'A2'),
                       help='5上穿10条件: a1 a2')
    
    parser.add_argument('-w', '--above-ma', nargs=3, type=int, metavar=('A1', 'A2', 'A3'),
                       help='收盘价在均线之上: a1 a2 a3 (a3=均线天数)')
    
    # 输出选项
    parser.add_argument('--output', '-o', type=str, help='输出文件路径')
    parser.add_argument('--json', action='store_true', help='输出JSON格式')
    parser.add_argument('--verbose', '-v', action='store_true', help='详细输出')
    
    return parser.parse_args()


def main():
    """主函数"""
    args = parse_command_line()
    
    # 创建筛选器
    screener = CommandLineScreener()
    
    if not screener.connect_database():
        return 1
    
    try:
        # 设置时间窗口
        if args.time_window:
            screener.start_index, screener.predays = args.time_window
        
        if args.include_exclude is not None:
            screener.inc_or_exc = args.include_exclude
        
        # 添加筛选条件
        if args.gain_range:
            screener.add_condition('a', *[int(x) if i < 2 else x for i, x in enumerate(args.gain_range)])
        
        if args.price_range:
            screener.add_condition('b', *args.price_range)
        
        if args.turnover_range:
            screener.add_condition('c', *[int(x) if i < 2 else x for i, x in enumerate(args.turnover_range)])
        
        if args.volume_ratio:
            screener.add_condition('d', *[int(x) if i < 2 else x for i, x in enumerate(args.volume_ratio)])
        
        if args.volume_compare:
            screener.add_condition('u', *args.volume_compare)
        
        if args.short_bull:
            screener.add_condition('e', *args.short_bull)
        
        if args.medium_bull:
            screener.add_condition('f', *args.medium_bull)
        
        if args.long_bull:
            screener.add_condition('g', *args.long_bull)
        
        if args.five_line_flower:
            screener.add_condition('h', *args.five_line_flower)
        
        if args.ma5_10_convergence:
            screener.add_condition('i', *args.ma5_10_convergence)
        
        if args.ma5_10_20_convergence:
            screener.add_condition('j', *args.ma5_10_20_convergence)
        
        if args.ma5_10_20_30_convergence:
            screener.add_condition('k', *args.ma5_10_20_30_convergence)
        
        if args.ma5_10_20_30_60_convergence:
            screener.add_condition('m', *args.ma5_10_20_30_60_convergence)
        
        if args.ma10_20_30_60_120_convergence:
            screener.add_condition('n', *args.ma10_20_30_60_120_convergence)
        
        if args.ma10_20_30_60_120_250_convergence:
            screener.add_condition('o', *args.ma10_20_30_60_120_250_convergence)
        
        if args.ma10_20_30_60_120_250_500_convergence:
            screener.add_condition('p', *args.ma10_20_30_60_120_250_500_convergence)
        
        if args.daily_convergence:
            screener.add_condition('q', *args.daily_convergence)
        
        if args.weekly_convergence:
            screener.add_condition('r', *args.weekly_convergence)
        
        if args.monthly_convergence:
            screener.add_condition('s', *args.monthly_convergence)
        
        if args.new_low:
            screener.add_condition('t', *[int(x) if i < 2 else x for i, x in enumerate(args.new_low)])
        
        if args.ma5_cross_ma10:
            screener.add_condition('v', *args.ma5_cross_ma10)
        
        if args.above_ma:
            screener.add_condition('w', *args.above_ma)
        
        # 执行筛选
        candidates = screener.screen_stocks()
        
        # 输出结果
        if args.json:
            result = {
                'timestamp': datetime.now().isoformat(),
                'conditions': screener.conditions,
                'time_window': {'start_index': screener.start_index, 'predays': screener.predays},
                'candidates': candidates,
                'count': len(candidates)
            }
            output = json.dumps(result, ensure_ascii=False, indent=2)
        else:
            output = '\n'.join(candidates)
        
        if args.output:
            with open(args.output, 'w', encoding='utf-8') as f:
                f.write(output)
            print(f"📄 结果已保存到: {args.output}")
        else:
            print("\n" + "="*50)
            print("🎯 筛选结果:")
            print("="*50)
            print(output)
        
        return 0
        
    except Exception as e:
        print(f"❌ 程序执行出错: {e}")
        if args.verbose:
            import traceback
            traceback.print_exc()
        return 1
    
    finally:
        screener.close_database()


if __name__ == '__main__':
    sys.exit(main())


