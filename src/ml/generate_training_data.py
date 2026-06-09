#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# Ensure src/ directory is in sys.path for package imports
import sys, os
_SRC_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _SRC_DIR not in sys.path:
    sys.path.insert(0, _SRC_DIR)
"""
快速生成AI训练数据脚本
从数据库中批量组合特征和标签数据
"""

import os
import sys
import pymysql
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import json
import time
from typing import Dict, List, Optional, Tuple
from tqdm import tqdm

# 添加项目根目录到Python路径
project_root = os.path.abspath(os.path.dirname(__file__))
sys.path.insert(0, project_root)

# 导入技术指标分析模块
try:
    from data.technical_indicators import TechnicalIndicatorCalculator
    TECHNICAL_INDICATORS_AVAILABLE = True
except ImportError:
    TECHNICAL_INDICATORS_AVAILABLE = False
    print("⚠️ 技术指标分析模块未找到")

# 数据库配置（从主应用读取，或从环境变量读取）
DB_CONFIG = {
    'host': os.getenv('DB_HOST', 'localhost'),
    'port': int(os.getenv('DB_PORT', 3306)),
    'user': os.getenv('DB_USER', 'root'),
    'password': os.getenv('DB_PASSWORD', '12345678'),
    'database': os.getenv('DB_NAME', 'gp2'),
    'charset': 'utf8mb4',
    'autocommit': True
}

def get_db_connection():
    """获取数据库连接"""
    return pymysql.connect(**DB_CONFIG)

def get_all_stock_codes(cursor) -> List[str]:
    """获取所有股票代码"""
    sql = "SELECT DISTINCT code FROM stock_basic_info_tbl WHERE code IS NOT NULL"
    cursor.execute(sql)
    results = cursor.fetchall()
    return [row[0] for row in results]

def get_stock_daily_data_batch(codes: List[str], start_date: int, end_date: int, batch_size: int = 500) -> pd.DataFrame:
    """
    批量获取股票日线数据
    
    Args:
        codes: 股票代码列表
        start_date: 开始日期（YYYYMMDD格式整数）
        end_date: 结束日期（YYYYMMDD格式整数）
        
    Returns:
        DataFrame with columns: code, tradedate, open, high, low, close, volume, amount
    """
    mydb = get_db_connection()
    cursor = mydb.cursor()
    
    # 分批处理，避免SQL语句过长
    all_results = []
    for i in range(0, len(codes), batch_size):
        batch_codes = codes[i:i+batch_size]
        codes_str = "','".join(batch_codes)
        sql = f"""
        SELECT code, tradedate, open, high, low, close, volume, amount
        FROM daily_info_tbl 
        WHERE code IN ('{codes_str}') 
          AND tradedate >= {start_date} 
          AND tradedate <= {end_date}
        ORDER BY code, tradedate ASC
        """
        
        cursor.execute(sql)
        results = cursor.fetchall()
        all_results.extend(results)
    
    mydb.close()
    
    if not all_results:
        return pd.DataFrame()
    
    df = pd.DataFrame(all_results, columns=['code', 'tradedate', 'open', 'high', 'low', 'close', 'volume', 'amount'])
    
    # 处理日期格式：可能是整数（YYYYMMDD）、日期类型或字符串
    def convert_date(date_val):
        if pd.isna(date_val):
            return None
        # 如果已经是日期类型
        if isinstance(date_val, (pd.Timestamp, datetime)):
            return pd.Timestamp(date_val)
        # 如果是整数（YYYYMMDD格式）
        if isinstance(date_val, (int, np.integer)):
            date_str = str(date_val)
            if len(date_str) == 8:
                return pd.to_datetime(date_str, format='%Y%m%d')
        # 如果是字符串，尝试多种格式
        if isinstance(date_val, str):
            # 尝试 YYYYMMDD 格式
            if len(date_val) == 8 and date_val.isdigit():
                return pd.to_datetime(date_val, format='%Y%m%d')
            # 尝试 ISO 格式 (YYYY-MM-DD)
            try:
                return pd.to_datetime(date_val, format='%Y-%m-%d')
            except:
                pass
        # 默认让pandas自动推断
        return pd.to_datetime(date_val, errors='coerce')
    
    df['tradedate'] = df['tradedate'].apply(convert_date)
    
    return df

def get_stock_basic_info_batch(codes: List[str], batch_size: int = 500) -> pd.DataFrame:
    """批量获取股票基本信息"""
    mydb = get_db_connection()
    cursor = mydb.cursor()
    
    # 分批处理
    all_results = []
    for i in range(0, len(codes), batch_size):
        batch_codes = codes[i:i+batch_size]
        codes_str = "','".join(batch_codes)
        sql = f"""
        SELECT code, name, sw1, sw2, sw3, market
        FROM stock_basic_info_tbl 
        WHERE code IN ('{codes_str}')
        """
        
        cursor.execute(sql)
        results = cursor.fetchall()
        all_results.extend(results)
    
    mydb.close()
    
    if not all_results:
        return pd.DataFrame()
    
    df = pd.DataFrame(all_results, columns=['code', 'name', 'sw1', 'sw2', 'sw3', 'market'])
    return df

def get_money_flow_batch(codes: List[str], start_date: int, end_date: int) -> pd.DataFrame:
    """批量获取资金流数据"""
    mydb = get_db_connection()
    cursor = mydb.cursor()
    
    codes_str = "','".join(codes)
    
    # 尝试从daily_moneyflow_tbl_2获取
    sql = f"""
    SELECT code, tradedate,
           COALESCE(buy_lg_amount, 0) - COALESCE(sell_lg_amount, 0) as net_lg_amount,
           COALESCE(buy_elg_amount, 0) - COALESCE(sell_elg_amount, 0) as net_elg_amount
    FROM daily_moneyflow_tbl_2 
    WHERE code IN ('{codes_str}') 
      AND tradedate >= {start_date} 
      AND tradedate <= {end_date}
    ORDER BY code, tradedate ASC
    """
    
    try:
        cursor.execute(sql)
        results = cursor.fetchall()
    except:
        # 如果表2不存在，尝试表1
        sql = f"""
        SELECT code, tradedate, net_lg_amount, net_elg_amount
        FROM daily_moneyflow_tbl 
        WHERE code IN ('{codes_str}') 
          AND tradedate >= {start_date} 
          AND tradedate <= {end_date}
        ORDER BY code, tradedate ASC
        """
        cursor.execute(sql)
        results = cursor.fetchall()
    
    mydb.close()
    
    if not results:
        return pd.DataFrame()
    
    df = pd.DataFrame(results, columns=['code', 'tradedate', 'net_lg_amount', 'net_elg_amount'])
    
    # 处理日期格式（同上面的逻辑）
    def convert_date(date_val):
        if pd.isna(date_val):
            return None
        if isinstance(date_val, (pd.Timestamp, datetime)):
            return pd.Timestamp(date_val)
        if isinstance(date_val, (int, np.integer)):
            date_str = str(date_val)
            if len(date_str) == 8:
                return pd.to_datetime(date_str, format='%Y%m%d')
        if isinstance(date_val, str):
            if len(date_val) == 8 and date_val.isdigit():
                return pd.to_datetime(date_val, format='%Y%m%d')
            try:
                return pd.to_datetime(date_val, format='%Y-%m-%d')
            except:
                pass
        return pd.to_datetime(date_val, errors='coerce')
    
    df['tradedate'] = df['tradedate'].apply(convert_date)
    df['net_inflow'] = df['net_lg_amount'] + df['net_elg_amount']  # 主力净流入
    
    return df

def get_daily_basic_batch(codes: List[str], start_date: int, end_date: int) -> pd.DataFrame:
    """批量获取每日基本面数据"""
    mydb = get_db_connection()
    cursor = mydb.cursor()
    
    codes_str = "','".join(codes)
    sql = f"""
    SELECT code, tradedate, turnover_rate_f, circ_mv
    FROM daily_basic_tbl 
    WHERE code IN ('{codes_str}') 
      AND tradedate >= {start_date} 
      AND tradedate <= {end_date}
    ORDER BY code, tradedate ASC
    """
    
    try:
        cursor.execute(sql)
        results = cursor.fetchall()
        mydb.close()
        
        if not results:
            return pd.DataFrame()
        
        df = pd.DataFrame(results, columns=['code', 'tradedate', 'turnover_rate', 'circ_mv'])
        
        # 处理日期格式（同上面的逻辑）
        def convert_date(date_val):
            if pd.isna(date_val):
                return None
            if isinstance(date_val, (pd.Timestamp, datetime)):
                return pd.Timestamp(date_val)
            if isinstance(date_val, (int, np.integer)):
                date_str = str(date_val)
                if len(date_str) == 8:
                    return pd.to_datetime(date_str, format='%Y%m%d')
            if isinstance(date_val, str):
                if len(date_val) == 8 and date_val.isdigit():
                    return pd.to_datetime(date_val, format='%Y%m%d')
                try:
                    return pd.to_datetime(date_val, format='%Y-%m-%d')
                except:
                    pass
            return pd.to_datetime(date_val, errors='coerce')
        
        df['tradedate'] = df['tradedate'].apply(convert_date)
        df['circ_mv'] = df['circ_mv'] / 10000  # 转换为亿元
        
        return df
    except:
        mydb.close()
        return pd.DataFrame()

def calculate_technical_features(stock_data: Dict, calculator: TechnicalIndicatorCalculator) -> Dict:
    """
    计算技术指标特征
    
    Args:
        stock_data: 股票数据字典，包含closes, volumes, opens, highs, lows
        calculator: 技术指标计算器
        
    Returns:
        特征字典
    """
    features = {}
    
    try:
        closes = stock_data.get('closes', [])
        volumes = stock_data.get('volumes', [])
        opens = stock_data.get('opens', closes)
        highs = stock_data.get('highs', closes)
        lows = stock_data.get('lows', closes)
        
        if len(closes) < 30:
            return features
        
        # 1. 策略1分析
        strategy1_result = calculator.strategy1_analyzer.analyze_strategy1(stock_data)
        features['strategy1_score'] = strategy1_result.get('score', 0)
        features['ma_convergence_ratio'] = strategy1_result.get('ma_convergence_ratio', 0)
        features['volume_ratio'] = strategy1_result.get('volume_analysis', {}).get('volume_ratio', 0)
        
        # 2. 趋势分析
        trend_analysis = calculator.strategy1_analyzer.check_uptrend_vs_rebound(closes, volumes)
        features['trend_type'] = 'uptrend' if trend_analysis['is_uptrend'] else ('rebound' if trend_analysis['is_rebound'] else 'neutral')
        features['trend_confidence'] = trend_analysis.get('confidence', 0)
        features['trend_score'] = trend_analysis.get('score', 0)
        
        # 3. 策略3分析
        strategy3_result = calculator.strategy3_analyzer.analyze_strategy3(stock_data)
        features['strategy3_score'] = strategy3_result.get('score', 0)
        
        # 4. MACD
        macd_result = calculator.technical_indicator_analyzer.calculate_macd(closes)
        features['macd_dif'] = macd_result['dif'][-1] if macd_result['dif'] else 0
        features['macd_dea'] = macd_result['dea'][-1] if macd_result['dea'] else 0
        features['macd_bar'] = macd_result['macd'][-1] if macd_result['macd'] else 0
        features['macd_golden_cross'] = 1 if macd_result.get('is_golden_cross', False) else 0
        features['macd_red_bar_expanding'] = 1 if macd_result.get('is_red_bar_expanding', False) else 0
        
        # 5. KDJ
        if len(highs) > 0 and len(lows) > 0:
            kdj_result = calculator.technical_indicator_analyzer.calculate_kdj(closes, highs, lows)
            features['kdj_k'] = kdj_result['k'][-1] if kdj_result['k'] else 0
            features['kdj_d'] = kdj_result['d'][-1] if kdj_result['d'] else 0
            features['kdj_j'] = kdj_result['j'][-1] if kdj_result['j'] else 0
            features['kdj_low_golden_cross'] = 1 if kdj_result.get('is_low_golden_cross', False) else 0
        
        # 6. RSI
        rsi_result = calculator.technical_indicator_analyzer.calculate_rsi(closes)
        features['rsi_value'] = rsi_result['rsi'][-1] if rsi_result['rsi'] else 0
        features['rsi_above_50'] = 1 if rsi_result.get('is_above_50', False) else 0
        features['rsi_upward'] = 1 if rsi_result.get('is_upward', False) else 0
        
        # 7. 筹码分布
        chip_result = calculator.chip_analyzer.calculate_chip_concentration(closes, volumes)
        features['chip_concentration_ratio'] = chip_result.get('concentration_ratio', 0)
        features['upper_pressure_ratio'] = chip_result.get('upper_pressure_ratio', 0)
        
        # 8. 均线特征
        ma5 = calculator.ma_analyzer.calculate_ma(closes, 5)
        ma10 = calculator.ma_analyzer.calculate_ma(closes, 10)
        ma30 = calculator.ma_analyzer.calculate_ma(closes, 30)
        
        if len(ma5) > 0 and len(ma10) > 0:
            features['ma5'] = ma5[-1]
            features['ma10'] = ma10[-1]
            features['ma30'] = ma30[-1] if len(ma30) > 0 else 0
            features['ma5_ma10_ratio'] = ma5[-1] / ma10[-1] if ma10[-1] > 0 else 0
        
        # 9. 价格特征
        features['current_price'] = closes[-1]
        features['change_pct'] = ((closes[-1] - closes[-2]) / closes[-2] * 100) if len(closes) >= 2 and closes[-2] > 0 else 0
        features['price_volatility'] = np.std(closes[-20:]) / np.mean(closes[-20:]) * 100 if len(closes) >= 20 else 0
        
        # 10. 成交量特征
        v37 = calculator.volume_analyzer.calculate_v37(volumes)
        features['volume_ratio'] = volumes[-1] / v37 if v37 > 0 else 0
        
        # ========== 新增特征：买入时机和风险预警 ==========
        
        # 11. 买入时机特征
        try:
            buy_timing_analyzer = calculator.buy_timing_analyzer if hasattr(calculator, 'buy_timing_analyzer') else None
            if buy_timing_analyzer is None:
                # 如果没有buy_timing_analyzer，尝试从strategy3中获取
                buy_timing_result = strategy3_result.get('buy_timing', {})
            else:
                buy_timing_result = buy_timing_analyzer.analyze_buy_timing(stock_data)
            
            # 突破确认
            day_line_signals = buy_timing_result.get('day_line_signals', {})
            features['break_resistance_confirmed'] = 1 if day_line_signals.get('break_resistance') == True else 0
            features['break_resistance_pending'] = 1 if day_line_signals.get('break_resistance') == 'pending' else 0
            
            # 回调买入信号（新增计算逻辑）
            # 回调买入：价格从高点回调到均线附近，且成交量萎缩，然后开始放量上涨
            if len(closes) >= 10 and len(volumes) >= 10:
                ma5 = calculator.ma_analyzer.calculate_ma(closes, 5)
                ma10 = calculator.ma_analyzer.calculate_ma(closes, 10)
                
                if len(ma5) >= 3 and len(ma10) >= 3:
                    # 最近3天的价格和均线
                    current_price = closes[-1]
                    ma5_current = ma5[-1]
                    ma10_current = ma10[-1]
                    
                    # 检查是否在均线附近（±2%）
                    near_ma5 = abs(current_price - ma5_current) / ma5_current < 0.02 if ma5_current > 0 else False
                    near_ma10 = abs(current_price - ma10_current) / ma10_current < 0.02 if ma10_current > 0 else False
                    
                    # 检查是否从高点回调（最近5天内有高点，然后回调）
                    high_5d = max(closes[-5:])
                    is_pullback = (high_5d > closes[-1]) and (high_5d - closes[-1]) / high_5d > 0.02  # 从高点回调超过2%
                    
                    # 检查成交量：回调时缩量，现在开始放量
                    volume_5d_avg = np.mean(volumes[-5:])
                    volume_prev_5d_avg = np.mean(volumes[-10:-5]) if len(volumes) >= 10 else volume_5d_avg
                    volume_surge = volumes[-1] > volume_prev_5d_avg * 1.2  # 当前成交量比前5天平均大20%
                    
                    # 检查是否上涨
                    is_rising = closes[-1] > closes[-2] if len(closes) >= 2 else False
                    
                    # 回调买入信号：从高点回调到均线附近，且开始放量上涨
                    features['pullback_buy_signal'] = 1 if (is_pullback and (near_ma5 or near_ma10) and volume_surge and is_rising) else 0
                else:
                    features['pullback_buy_signal'] = 0
            else:
                features['pullback_buy_signal'] = 0
            
            # 买入评分
            features['buy_timing_score'] = buy_timing_result.get('buy_score', 0)
        except Exception as e:
            features['break_resistance_confirmed'] = 0
            features['break_resistance_pending'] = 0
            features['pullback_buy_signal'] = 0
            features['buy_timing_score'] = 0
        
        # 12. 风险预警特征
        # 12.1 高位风险（接近历史高点）
        if len(closes) >= 60:
            recent_high = max(closes[-60:])  # 60日最高价
            current_price = closes[-1]
            distance_to_high = (current_price - recent_high) / recent_high * 100 if recent_high > 0 else 0
            features['is_near_high'] = 1 if distance_to_high >= -5 else 0  # 距离高点5%以内
            features['distance_to_high_pct'] = distance_to_high
        else:
            features['is_near_high'] = 0
            features['distance_to_high_pct'] = 0
        
        # 12.2 放量滞涨风险
        if len(closes) >= 5 and len(volumes) >= 5:
            # 最近5天的价格变化
            price_change_5d = (closes[-1] - closes[-5]) / closes[-5] * 100 if closes[-5] > 0 else 0
            # 最近5天的平均成交量
            avg_volume_5d = np.mean(volumes[-5:])
            # 前5天的平均成交量
            avg_volume_prev_5d = np.mean(volumes[-10:-5]) if len(volumes) >= 10 else avg_volume_5d
            volume_increase = (avg_volume_5d - avg_volume_prev_5d) / avg_volume_prev_5d * 100 if avg_volume_prev_5d > 0 else 0
            
            # 放量但涨幅小（放量滞涨）
            features['volume_price_stagnation'] = 1 if volume_increase > 50 and abs(price_change_5d) < 2 else 0
            features['volume_increase_pct'] = volume_increase
        else:
            features['volume_price_stagnation'] = 0
            features['volume_increase_pct'] = 0
        
        # 12.3 技术指标背离风险
        # MACD背离：价格创新高但MACD未创新高，或价格创新低但MACD未创新低
        if len(closes) >= 20 and len(macd_result.get('macd', [])) >= 20:
            macd_values = macd_result['macd'][-20:]
            price_high_10d = max(closes[-10:])
            price_high_prev_10d = max(closes[-20:-10])
            macd_high_10d = max(macd_values[-10:])
            macd_high_prev_10d = max(macd_values[-20:-10]) if len(macd_values) >= 20 else macd_high_10d
            
            # 顶背离：价格创新高但MACD未创新高
            top_divergence = 1 if price_high_10d > price_high_prev_10d and macd_high_10d < macd_high_prev_10d else 0
            # 底背离：价格创新低但MACD未创新低（这里只检查顶背离作为风险）
            features['macd_top_divergence'] = top_divergence
        else:
            features['macd_top_divergence'] = 0
        
        # RSI背离
        if len(closes) >= 20 and len(rsi_result.get('rsi', [])) >= 20:
            rsi_values = rsi_result['rsi'][-20:]
            price_high_10d = max(closes[-10:])
            price_high_prev_10d = max(closes[-20:-10])
            rsi_high_10d = max(rsi_values[-10:])
            rsi_high_prev_10d = max(rsi_values[-20:-10]) if len(rsi_values) >= 20 else rsi_high_10d
            
            rsi_top_divergence = 1 if price_high_10d > price_high_prev_10d and rsi_high_10d < rsi_high_prev_10d else 0
            features['rsi_top_divergence'] = rsi_top_divergence
        else:
            features['rsi_top_divergence'] = 0
        
        # 综合背离风险
        features['technical_divergence_risk'] = features.get('macd_top_divergence', 0) + features.get('rsi_top_divergence', 0)
        
    except Exception as e:
        print(f"⚠️ 计算技术特征失败: {e}")
    
    return features

def calculate_labels(df: pd.DataFrame, code: str, date: pd.Timestamp, future_days: List[int] = [1, 3, 5, 10]) -> Dict:
    """
    计算标签数据（未来收益率等）
    
    Args:
        df: 股票日线数据DataFrame
        code: 股票代码
        date: 当前日期
        future_days: 未来天数列表
        
    Returns:
        标签字典
    """
    labels = {}
    
    try:
        stock_df = df[df['code'] == code].sort_values('tradedate').reset_index(drop=True)
        
        # 找到当前日期在DataFrame中的位置索引
        current_pos = stock_df[stock_df['tradedate'] == date].index
        
        if len(current_pos) == 0:
            return labels
        
        current_pos = current_pos[0]
        current_price = stock_df.iloc[current_pos]['close']
        
        if current_price <= 0:
            return labels
        
        # 计算未来N天收益率
        for days in future_days:
            future_pos = current_pos + days
            if future_pos < len(stock_df):
                future_price = stock_df.iloc[future_pos]['close']
                return_pct = (future_price - current_price) / current_price * 100
                labels[f'return_{days}d'] = return_pct
                labels[f'is_rising_{days}d'] = 1 if return_pct > 0 else 0
                labels[f'is_limit_up_{days}d'] = 1 if return_pct >= 9.8 else 0  # 涨停阈值
                
                # 计算最大回撤（从当前价格或未来峰值到最低点的最大跌幅）
                future_prices = stock_df.iloc[current_pos+1:future_pos+1]['close'].values
                if len(future_prices) > 0:
                    # 构建完整的价格序列（包含当前价格）
                    price_sequence = np.concatenate([[current_price], future_prices])
                    # 计算累积最高价（从当前价格开始）
                    cumulative_max = np.maximum.accumulate(price_sequence)
                    # 计算每个时点的回撤（从峰值到当前价格的跌幅）
                    drawdowns = (cumulative_max - price_sequence) / cumulative_max * 100
                    # 最大回撤（排除第一个，因为第一个是当前价格，回撤为0）
                    max_drawdown = np.max(drawdowns[1:]) if len(drawdowns) > 1 else 0
                    labels[f'max_drawdown_{days}d'] = max_drawdown
            else:
                labels[f'return_{days}d'] = None
                labels[f'is_rising_{days}d'] = None
                labels[f'is_limit_up_{days}d'] = None
                labels[f'max_drawdown_{days}d'] = None
    
    except Exception as e:
        print(f"⚠️ 计算标签失败 {code} {date}: {e}")
    
    return labels

def generate_training_data(
    start_date: str = '20230101',
    end_date: str = None,
    max_stocks: int = None,
    batch_size: int = 100,
    output_file: str = 'training_data.csv',
    min_data_days: int = 60
):
    """
    生成训练数据
    
    Args:
        start_date: 开始日期（YYYYMMDD格式）
        end_date: 结束日期（YYYYMMDD格式），None表示今天
        max_stocks: 最大股票数量，None表示全部
        batch_size: 批量处理大小
        output_file: 输出文件名
        min_data_days: 最少需要的数据天数
    """
    print("🚀 开始生成训练数据...")
    
    if not TECHNICAL_INDICATORS_AVAILABLE:
        print("❌ 技术指标模块不可用，无法生成训练数据")
        return
    
    # 初始化
    if end_date is None:
        end_date = datetime.now().strftime('%Y%m%d')
    
    start_date_int = int(start_date)
    end_date_int = int(end_date)
    
    mydb = get_db_connection()
    cursor = mydb.cursor()
    
    # 获取所有股票代码
    print("📊 获取股票列表...")
    all_codes = get_all_stock_codes(cursor)
    if max_stocks:
        all_codes = all_codes[:max_stocks]
    print(f"✅ 共 {len(all_codes)} 只股票")
    
    mydb.close()
    
    # 批量获取数据
    print("📥 批量获取股票数据...")
    daily_df = get_stock_daily_data_batch(all_codes, start_date_int, end_date_int, batch_size=batch_size)
    print(f"✅ 获取 {len(daily_df)} 条日线数据")
    
    basic_df = get_stock_basic_info_batch(all_codes)
    print(f"✅ 获取 {len(basic_df)} 条基本信息")
    
    money_flow_df = get_money_flow_batch(all_codes, start_date_int, end_date_int)
    print(f"✅ 获取 {len(money_flow_df)} 条资金流数据")
    
    daily_basic_df = get_daily_basic_batch(all_codes, start_date_int, end_date_int)
    print(f"✅ 获取 {len(daily_basic_df)} 条基本面数据")
    
    # 初始化技术指标计算器
    calculator = TechnicalIndicatorCalculator()
    
    # 生成训练样本
    print("🔄 生成训练样本...")
    training_samples = []
    
    # 按股票分组处理
    for code in tqdm(all_codes, desc="处理股票"):
        try:
            stock_daily = daily_df[daily_df['code'] == code].sort_values('tradedate')
            
            if len(stock_daily) < min_data_days:
                continue
            
            # 获取该股票的所有交易日期
            trade_dates = stock_daily['tradedate'].unique()
            
            # 对每个交易日期生成一个样本（需要保证有未来数据）
            for i, date in enumerate(trade_dates[:-10]):  # 最后10天不生成样本（需要未来数据）
                try:
                    # 获取到当前日期为止的数据
                    current_data = stock_daily[stock_daily['tradedate'] <= date].tail(min_data_days)
                    
                    if len(current_data) < min_data_days:
                        continue
                    
                    # 准备股票数据
                    stock_data = {
                        'closes': current_data['close'].values.tolist(),
                        'volumes': current_data['volume'].values.tolist(),
                        'opens': current_data['open'].values.tolist(),
                        'highs': current_data['high'].values.tolist(),
                        'lows': current_data['low'].values.tolist()
                    }
                    
                    # 计算技术特征
                    features = calculate_technical_features(stock_data, calculator)
                    
                    # 获取资金流数据（增强版）
                    money_flow = money_flow_df[(money_flow_df['code'] == code) & 
                                               (money_flow_df['tradedate'] == date)]
                    if len(money_flow) > 0:
                        today_mf = money_flow.iloc[0]
                        features['today_net_inflow'] = today_mf['net_inflow']
                        
                        # 计算连续流入天数
                        recent_mf = money_flow_df[(money_flow_df['code'] == code) & 
                                                 (money_flow_df['tradedate'] <= date)].tail(10)
                        continuous_days = 0
                        for _, row in recent_mf.iterrows():
                            if row['net_inflow'] > 0:
                                continuous_days += 1
                            else:
                                break
                        features['continuous_inflow_days'] = continuous_days
                        features['total_net_inflow'] = recent_mf['net_inflow'].sum()
                        
                        # ========== 新增：资金流入强度（大单占比）==========
                        # 大单占比 = (大单净流入 + 特大单净流入) / 总成交额
                        # 这里用净流入金额的绝对值作为近似
                        net_lg = today_mf.get('net_lg_amount', 0)  # 大单净流入
                        net_elg = today_mf.get('net_elg_amount', 0)  # 特大单净流入
                        large_order_inflow = abs(net_lg) + abs(net_elg)
                        total_inflow_abs = abs(net_lg) + abs(net_elg) + abs(today_mf['net_inflow'] - net_lg - net_elg)
                        
                        # 获取当日成交额（从daily_df）
                        daily_data = daily_df[(daily_df['code'] == code) & 
                                             (daily_df['tradedate'] == date)]
                        if len(daily_data) > 0:
                            daily_amount = daily_data.iloc[0]['amount']  # 成交额（万元）
                            if daily_amount > 0:
                                # 大单占比 = 大单净流入绝对值 / 总成交额
                                features['large_order_ratio'] = large_order_inflow / daily_amount if daily_amount > 0 else 0
                            else:
                                features['large_order_ratio'] = 0
                        else:
                            features['large_order_ratio'] = 0
                        
                        # ========== 新增：资金流入的稳定性（波动率）==========
                        # 计算最近10天资金流的波动率（标准差/均值）
                        if len(recent_mf) >= 5:
                            inflow_values = recent_mf['net_inflow'].values
                            inflow_mean = np.mean(inflow_values)
                            inflow_std = np.std(inflow_values)
                            # 波动率 = 标准差 / 均值（如果均值为0，使用标准差）
                            if abs(inflow_mean) > 0.01:
                                features['inflow_stability'] = inflow_std / abs(inflow_mean)
                            else:
                                features['inflow_stability'] = inflow_std if inflow_std > 0 else 0
                        else:
                            features['inflow_stability'] = 0
                    else:
                        features['today_net_inflow'] = 0
                        features['continuous_inflow_days'] = 0
                        features['total_net_inflow'] = 0
                        features['large_order_ratio'] = 0
                        features['inflow_stability'] = 0
                    
                    # 获取基本面数据
                    basic = daily_basic_df[(daily_basic_df['code'] == code) & 
                                          (daily_basic_df['tradedate'] == date)]
                    if len(basic) > 0:
                        features['turnover_rate'] = basic.iloc[0]['turnover_rate'] if pd.notna(basic.iloc[0]['turnover_rate']) else 0
                        features['circ_mv'] = basic.iloc[0]['circ_mv'] if pd.notna(basic.iloc[0]['circ_mv']) else 0
                    else:
                        # 如果当天数据不存在，尝试使用最近的数据
                        recent_basic = daily_basic_df[(daily_basic_df['code'] == code) & 
                                                     (daily_basic_df['tradedate'] <= date)].tail(1)
                        if len(recent_basic) > 0:
                            features['turnover_rate'] = recent_basic.iloc[0]['turnover_rate'] if pd.notna(recent_basic.iloc[0]['turnover_rate']) else 0
                            features['circ_mv'] = recent_basic.iloc[0]['circ_mv'] if pd.notna(recent_basic.iloc[0]['circ_mv']) else 0
                        else:
                            features['turnover_rate'] = 0
                            features['circ_mv'] = 0
                    
                    # 获取基本信息
                    stock_info = basic_df[basic_df['code'] == code]
                    if len(stock_info) > 0:
                        features['industry'] = stock_info.iloc[0]['sw1'] if pd.notna(stock_info.iloc[0]['sw1']) else ''
                        features['name'] = stock_info.iloc[0]['name'] if pd.notna(stock_info.iloc[0]['name']) else ''
                    else:
                        features['industry'] = ''
                        features['name'] = ''
                    
                    # 计算标签
                    labels = calculate_labels(daily_df, code, date)
                    
                    # 检查标签是否完整（所有标签都应该有值，不能为None）
                    future_days = [1, 3, 5, 10]
                    labels_complete = True
                    for days in future_days:
                        if labels.get(f'return_{days}d') is None:
                            labels_complete = False
                            break
                    
                    # 只有当标签完整时才添加样本
                    if not labels_complete:
                        continue
                    
                    # 合并特征和标签
                    sample = {
                        'code': code,
                        'date': date.strftime('%Y%m%d'),
                        **features,
                        **labels
                    }
                    
                    training_samples.append(sample)
                    
                except Exception as e:
                    continue
        
        except Exception as e:
            print(f"⚠️ 处理股票 {code} 失败: {e}")
            continue
    
    # 保存为CSV
    if training_samples:
        print(f"💾 保存训练数据到 {output_file}...")
        df = pd.DataFrame(training_samples)
        df.to_csv(output_file, index=False, encoding='utf-8-sig')
        print(f"✅ 共生成 {len(training_samples)} 个训练样本")
        print(f"📊 特征数量: {len([c for c in df.columns if c not in ['code', 'date', 'name', 'industry'] and not c.startswith('return_') and not c.startswith('is_') and not c.startswith('max_drawdown_')])}")
        print(f"📊 标签数量: {len([c for c in df.columns if c.startswith('return_') or c.startswith('is_') or c.startswith('max_drawdown_')])}")
    else:
        print("❌ 未生成任何训练样本")

if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(description='生成AI训练数据')
    parser.add_argument('--start_date', type=str, default='20230101', help='开始日期（YYYYMMDD）')
    parser.add_argument('--end_date', type=str, default=None, help='结束日期（YYYYMMDD），默认今天')
    parser.add_argument('--max_stocks', type=int, default=None, help='最大股票数量，默认全部')
    parser.add_argument('--batch_size', type=int, default=100, help='批量处理大小')
    parser.add_argument('--output', type=str, default='training_data.csv', help='输出文件名')
    parser.add_argument('--min_data_days', type=int, default=60, help='最少需要的数据天数')
    
    args = parser.parse_args()
    
    generate_training_data(
        start_date=args.start_date,
        end_date=args.end_date,
        max_stocks=args.max_stocks,
        batch_size=args.batch_size,
        output_file=args.output,
        min_data_days=args.min_data_days
    )

