#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
技术指标分析模块
实现3D交易软件需求中的核心技术指标
"""

import numpy as np
from datetime import datetime, timedelta
import pandas as pd
import os
import json
import hashlib
try:
    import tushare as ts
    TUSHARE_AVAILABLE = True
except ImportError:
    TUSHARE_AVAILABLE = False
    print("警告: tushare未安装，热点板块功能将不可用")


class SectorDataCache:
    """板块数据缓存类 - 使用文件缓存减少API调用"""
    
    def __init__(self, cache_dir='.cache/sector_data'):
        """
        初始化缓存
        
        Args:
            cache_dir: 缓存目录路径
        """
        self.cache_dir = cache_dir
        os.makedirs(cache_dir, exist_ok=True)
        os.makedirs(os.path.join(cache_dir, 'sector_list'), exist_ok=True)
        os.makedirs(os.path.join(cache_dir, 'index_data'), exist_ok=True)
    
    def _get_cache_key(self, *args):
        """生成缓存键（MD5哈希）"""
        key_str = '_'.join(str(arg) for arg in args)
        return hashlib.md5(key_str.encode('utf-8')).hexdigest()
    
    def _get_cache_path(self, cache_type, key):
        """获取缓存文件路径"""
        return os.path.join(self.cache_dir, cache_type, f"{key}.json")
    
    def _is_cache_valid(self, cache_path, expire_hours=None):
        """
        检查缓存是否有效
        
        Args:
            cache_path: 缓存文件路径
            expire_hours: 过期时间（小时），None表示永不过期
            
        Returns:
            bool: 缓存是否有效
        """
        if not os.path.exists(cache_path):
            return False
        
        if expire_hours is None:
            return True  # 永不过期（用于历史数据）
        
        # 检查文件修改时间
        file_time = datetime.fromtimestamp(os.path.getmtime(cache_path))
        expire_time = datetime.now() - timedelta(hours=expire_hours)
        return file_time > expire_time
    
    def get_sector_list(self, sector_type):
        """
        获取板块列表（带缓存）
        
        Args:
            sector_type: 板块类型，'concept'或'industry'
            
        Returns:
            DataFrame或None: 板块列表，如果缓存无效则返回None
        """
        cache_key = self._get_cache_key('sector_list', sector_type)
        cache_path = self._get_cache_path('sector_list', cache_key)
        
        # 板块列表缓存1天
        if self._is_cache_valid(cache_path, expire_hours=24):
            try:
                with open(cache_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    # 检查data是否包含'data'键且不为空
                    if 'data' not in data or not data['data']:
                        print(f"⚠️ 缓存数据为空或格式不正确: {cache_path}", flush=True)
                        return None
                    # 安全地创建DataFrame
                    try:
                        # 检查data['data']是否为空或格式不正确
                        if not data['data'] or (isinstance(data['data'], list) and len(data['data']) == 0):
                            print(f"⚠️ 缓存数据为空: {cache_path}", flush=True)
                            # 删除空缓存文件
                            try:
                                import os
                                if os.path.exists(cache_path):
                                    os.remove(cache_path)
                                    print(f"🗑️ 已删除空缓存文件: {cache_path}", flush=True)
                            except Exception:
                                pass
                            return None
                        
                        # 验证数据格式：确保是字典列表且每个字典都有键
                        if isinstance(data['data'], list) and len(data['data']) > 0:
                            first_item = data['data'][0]
                            if not isinstance(first_item, dict) or len(first_item) == 0:
                                print(f"⚠️ 缓存数据格式无效（非字典或空字典）: {cache_path}", flush=True)
                                try:
                                    import os
                                    if os.path.exists(cache_path):
                                        os.remove(cache_path)
                                        print(f"🗑️ 已删除格式错误的缓存文件: {cache_path}", flush=True)
                                except Exception:
                                    pass
                                return None
                        
                        df = pd.DataFrame(data['data'])
                        # 确保数据不为空且有列
                        if df.empty or len(df.columns) == 0:
                            print(f"⚠️ 缓存数据为空或无有效列: {cache_path}", flush=True)
                            # 删除无效缓存文件
                            try:
                                import os
                                if os.path.exists(cache_path):
                                    os.remove(cache_path)
                                    print(f"🗑️ 已删除无效缓存文件: {cache_path}", flush=True)
                            except Exception:
                                pass
                            return None
                    except (ValueError, pd.errors.EmptyDataError, TypeError) as e:
                        print(f"⚠️ 创建DataFrame失败: {e}, 缓存路径: {cache_path}", flush=True)
                        return None
                    print(f"✅ 从缓存加载板块列表: {sector_type} ({len(df)} 个板块)", flush=True)
                    return df
            except pd.errors.EmptyDataError:
                print(f"⚠️ 缓存数据为空或无有效列: {cache_path}", flush=True)
            except ValueError as e:
                print(f"⚠️ 缓存数据格式错误: {e}", flush=True)
            except Exception as e:
                print(f"⚠️ 读取缓存失败: {e}", flush=True)
        
        return None
    
    def save_sector_list(self, sector_type, df):
        """
        保存板块列表到缓存
        
        Args:
            sector_type: 板块类型
            df: 板块列表DataFrame
        """
        cache_key = self._get_cache_key('sector_list', sector_type)
        cache_path = self._get_cache_path('sector_list', cache_key)
        
        try:
            # DataFrame转JSON
            data = {
                'sector_type': sector_type,
                'cached_time': datetime.now().isoformat(),
                'data': df.to_dict('records')
            }
            with open(cache_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            print(f"💾 板块列表已缓存: {sector_type}", flush=True)
        except Exception as e:
            print(f"⚠️ 保存缓存失败: {e}", flush=True)
    
    def get_index_data(self, sector_code, start_date, end_date):
        """
        获取板块指数数据（带缓存）
        
        Args:
            sector_code: 板块代码
            start_date: 开始日期
            end_date: 结束日期
            
        Returns:
            DataFrame或None: 指数数据，如果缓存无效则返回None
        """
        cache_key = self._get_cache_key('index_data', sector_code, start_date, end_date)
        cache_path = self._get_cache_path('index_data', cache_key)
        
        # 判断是否为历史数据（结束日期不是今天）
        today = datetime.now().strftime('%Y%m%d')
        is_historical = end_date < today
        
        # 历史数据永不过期，最新数据缓存1小时
        expire_hours = None if is_historical else 1
        
        if self._is_cache_valid(cache_path, expire_hours=expire_hours):
            try:
                with open(cache_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    # 检查data是否包含'data'键且不为空
                    if 'data' not in data or not data['data']:
                        print(f"⚠️ 缓存数据为空或格式不正确: {cache_path}", flush=True)
                        return None
                    # 安全地创建DataFrame
                    try:
                        # 检查数据是否为空列表
                        if not data['data'] or len(data['data']) == 0:
                            print(f"⚠️ 缓存数据为空列表: {cache_path}", flush=True)
                            # 删除空缓存文件
                            try:
                                import os
                                if os.path.exists(cache_path):
                                    os.remove(cache_path)
                                    print(f"🗑️ 已删除空缓存文件: {cache_path}", flush=True)
                            except Exception:
                                pass
                            return None
                        
                        # 验证数据格式：确保是字典列表且每个字典都有键
                        if isinstance(data['data'], list):
                            if len(data['data']) > 0:
                                # 检查第一个元素是否是字典且有键
                                first_item = data['data'][0]
                                if not isinstance(first_item, dict) or len(first_item) == 0:
                                    print(f"⚠️ 缓存数据格式无效（非字典或空字典）: {cache_path}", flush=True)
                                    try:
                                        import os
                                        if os.path.exists(cache_path):
                                            os.remove(cache_path)
                                            print(f"🗑️ 已删除格式错误的缓存文件: {cache_path}", flush=True)
                                    except Exception:
                                        pass
                                    return None
                        
                        df = pd.DataFrame(data['data'])
                        # 确保数据不为空且有列
                        if df.empty or len(df.columns) == 0:
                            print(f"⚠️ 缓存数据为空或无有效列: {cache_path}", flush=True)
                            # 删除无效缓存文件
                            try:
                                import os
                                if os.path.exists(cache_path):
                                    os.remove(cache_path)
                                    print(f"🗑️ 已删除无效缓存文件: {cache_path}", flush=True)
                            except Exception:
                                pass
                            return None
                    except (ValueError, pd.errors.EmptyDataError, TypeError, KeyError) as e:
                        print(f"⚠️ 创建DataFrame失败: {e}, 缓存路径: {cache_path}", flush=True)
                        # 删除损坏的缓存文件
                        try:
                            import os
                            if os.path.exists(cache_path):
                                os.remove(cache_path)
                                print(f"🗑️ 已删除损坏的缓存文件: {cache_path}", flush=True)
                        except Exception as del_e:
                            print(f"⚠️ 删除缓存文件失败: {del_e}", flush=True)
                        return None
                    except Exception as e:
                        # 捕获所有其他可能的pandas错误
                        error_str = str(e).lower()
                        if 'no columns' in error_str or 'empty data' in error_str or 'parse from file' in error_str:
                            print(f"⚠️ 缓存数据格式错误（pandas解析失败）: {e}, 缓存路径: {cache_path}", flush=True)
                            # 删除损坏的缓存文件
                            try:
                                import os
                                if os.path.exists(cache_path):
                                    os.remove(cache_path)
                                    print(f"🗑️ 已删除损坏的缓存文件: {cache_path}", flush=True)
                            except Exception as del_e:
                                print(f"⚠️ 删除缓存文件失败: {del_e}", flush=True)
                        else:
                            print(f"⚠️ 创建DataFrame时发生未知错误: {e}, 缓存路径: {cache_path}", flush=True)
                        return None
                    # 确保日期列是字符串格式
                    if 'trade_date' in df.columns:
                        df['trade_date'] = df['trade_date'].astype(str)
                    print(f"✅ 从缓存加载指数数据: {sector_code} ({len(df)} 条记录)", flush=True)
                    return df
            except pd.errors.EmptyDataError as e:
                print(f"⚠️ 缓存数据为空或无有效列: {cache_path}, 错误: {e}", flush=True)
                # 删除损坏的缓存文件
                try:
                    import os
                    if os.path.exists(cache_path):
                        os.remove(cache_path)
                        print(f"🗑️ 已删除损坏的缓存文件: {cache_path}", flush=True)
                except Exception:
                    pass
            except ValueError as e:
                print(f"⚠️ 缓存数据格式错误: {e}, 缓存路径: {cache_path}", flush=True)
                # 删除损坏的缓存文件
                try:
                    import os
                    if os.path.exists(cache_path):
                        os.remove(cache_path)
                        print(f"🗑️ 已删除损坏的缓存文件: {cache_path}", flush=True)
                except Exception:
                    pass
            except json.JSONDecodeError as e:
                print(f"⚠️ JSON解析失败: {e}, 缓存路径: {cache_path}", flush=True)
            except Exception as e:
                print(f"⚠️ 读取缓存失败: {e}, 缓存路径: {cache_path}", flush=True)
                import traceback
                print(f"   详细错误: {traceback.format_exc()}", flush=True)
        
        return None
    
    def save_index_data(self, sector_code, start_date, end_date, df):
        """
        保存板块指数数据到缓存
        
        Args:
            sector_code: 板块代码
            start_date: 开始日期
            end_date: 结束日期
            df: 指数数据DataFrame
        """
        cache_key = self._get_cache_key('index_data', sector_code, start_date, end_date)
        cache_path = self._get_cache_path('index_data', cache_key)
        
        try:
            # DataFrame转JSON
            data = {
                'sector_code': sector_code,
                'start_date': start_date,
                'end_date': end_date,
                'cached_time': datetime.now().isoformat(),
                'data': df.to_dict('records')
            }
            with open(cache_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"⚠️ 保存缓存失败: {e}", flush=True)
    
    def clear_cache(self, cache_type=None):
        """
        清理缓存
        
        Args:
            cache_type: 缓存类型，'sector_list'或'index_data'，None表示清理所有
        """
        if cache_type:
            cache_path = os.path.join(self.cache_dir, cache_type)
            if os.path.exists(cache_path):
                for file in os.listdir(cache_path):
                    os.remove(os.path.join(cache_path, file))
                print(f"🗑️ 已清理缓存: {cache_type}", flush=True)
        else:
            # 清理所有缓存
            for cache_type in ['sector_list', 'index_data']:
                cache_path = os.path.join(self.cache_dir, cache_type)
                if os.path.exists(cache_path):
                    for file in os.listdir(cache_path):
                        os.remove(os.path.join(cache_path, file))
            print("🗑️ 已清理所有缓存", flush=True)


class MAConvergenceAnalyzer:
    """均线粘合分析器"""
    
    def __init__(self, convergence_threshold=0.04):
        """
        初始化均线粘合分析器
        
        Args:
            convergence_threshold: 粘合阈值，默认4%
        """
        self.convergence_threshold = convergence_threshold
    
    def calculate_ma(self, prices, period):
        """
        计算移动平均线
        
        Args:
            prices: 价格序列
            period: 周期
            
        Returns:
            MA值列表
        """
        if len(prices) < period:
            return []
        
        ma_values = []
        for i in range(period - 1, len(prices)):
            ma = sum(prices[i - period + 1:i + 1]) / period
            ma_values.append(ma)
        return ma_values
    
    def calculate_convergence_ratio(self, ma_values):
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
    
    def is_convergent(self, ma_values):
        """
        判断均线是否粘合
        
        Args:
            ma_values: 均线值列表
            
        Returns:
            是否粘合
        """
        convergence_ratio = self.calculate_convergence_ratio(ma_values)
        return convergence_ratio < self.convergence_threshold
    
    def get_convergence_combinations(self, closes):
        """
        获取各种均线粘合组合
        
        Args:
            closes: 收盘价序列
            
        Returns:
            各种均线组合的粘合分析结果
        """
        results = {}
        
        # 日线均线粘合：5日、10日、30日
        ma5 = self.calculate_ma(closes, 5)
        ma10 = self.calculate_ma(closes, 10)
        ma30 = self.calculate_ma(closes, 30)
        
        if len(ma5) > 0 and len(ma10) > 0 and len(ma30) > 0:
            # 取最新的值
            latest_ma5 = ma5[-1]
            latest_ma10 = ma10[-1]
            latest_ma30 = ma30[-1]
            
            results['daily_5_10_30'] = {
                'ma_values': [latest_ma5, latest_ma10, latest_ma30],
                'convergence_ratio': self.calculate_convergence_ratio([latest_ma5, latest_ma10, latest_ma30]),
                'is_convergent': self.is_convergent([latest_ma5, latest_ma10, latest_ma30]),
                'description': '日线均线粘合：5日、10日、30日'
            }
        
        # 周线均线粘合：25日、50日、150日（5周、10周、30周）
        ma25 = self.calculate_ma(closes, 25)
        ma50 = self.calculate_ma(closes, 50)
        ma150 = self.calculate_ma(closes, 150)
        
        if len(ma25) > 0 and len(ma50) > 0 and len(ma150) > 0:
            latest_ma25 = ma25[-1]
            latest_ma50 = ma50[-1]
            latest_ma150 = ma150[-1]
            
            results['weekly_25_50_150'] = {
                'ma_values': [latest_ma25, latest_ma50, latest_ma150],
                'convergence_ratio': self.calculate_convergence_ratio([latest_ma25, latest_ma50, latest_ma150]),
                'is_convergent': self.is_convergent([latest_ma25, latest_ma50, latest_ma150]),
                'description': '周线均线粘合：25日、50日、150日（5周、10周、30周）'
            }
        
        # 月线均线粘合：100日、200日、600日（5月、10月、30月）
        ma100 = self.calculate_ma(closes, 100)
        ma200 = self.calculate_ma(closes, 200)
        ma600 = self.calculate_ma(closes, 600)
        
        if len(ma100) > 0 and len(ma200) > 0 and len(ma600) > 0:
            latest_ma100 = ma100[-1]
            latest_ma200 = ma200[-1]
            latest_ma600 = ma600[-1]
            
            results['monthly_100_200_600'] = {
                'ma_values': [latest_ma100, latest_ma200, latest_ma600],
                'convergence_ratio': self.calculate_convergence_ratio([latest_ma100, latest_ma200, latest_ma600]),
                'is_convergent': self.is_convergent([latest_ma100, latest_ma200, latest_ma600]),
                'description': '月线均线粘合：100日、200日、600日（5月、10月、30月）'
            }
        
        # 其他均线粘合组合
        other_combinations = [
            ([5, 10], '5/10日'),
            ([5, 10, 20], '5/10/20日'),
            ([5, 10, 20, 30], '5/10/20/30日'),
            ([5, 10, 20, 30, 60], '5/10/20/30/60日'),
            ([10, 20, 30, 60, 120], '10/20/30/60/120日'),
            ([10, 20, 30, 60, 120, 250], '10/20/30/60/120/250日'),
            ([20, 30, 60, 120, 250, 500], '20/30/60/120/250/500日')
        ]
        
        for periods, description in other_combinations:
            ma_values = []
            valid = True
            
            for period in periods:
                ma = self.calculate_ma(closes, period)
                if len(ma) > 0:
                    ma_values.append(ma[-1])
                else:
                    valid = False
                    break
            
            if valid and len(ma_values) == len(periods):
                key = f"other_{'_'.join(map(str, periods))}"
                results[key] = {
                    'ma_values': ma_values,
                    'convergence_ratio': self.calculate_convergence_ratio(ma_values),
                    'is_convergent': self.is_convergent(ma_values),
                    'description': description
                }
        
        return results
    
    def get_convergence_duration(self, closes, periods, days=20):
        """
        获取均线粘合持续时间
        
        Args:
            closes: 收盘价序列
            periods: 均线周期列表
            days: 检查天数
            
        Returns:
            粘合持续天数
        """
        if len(closes) < max(periods) + days:
            return 0
        
        convergence_days = 0
        
        for i in range(len(closes) - days, len(closes)):
            ma_values = []
            valid = True
            
            for period in periods:
                if i >= period - 1:
                    ma = sum(closes[i - period + 1:i + 1]) / period
                    ma_values.append(ma)
                else:
                    valid = False
                    break
            
            if valid and self.is_convergent(ma_values):
                convergence_days += 1
            else:
                break
        
        return convergence_days


class VolumeAnalyzer:
    """成交量分析器"""
    
    def __init__(self, surge_threshold=1.2, shrink_threshold=0.7):
        """
        初始化成交量分析器
        
        Args:
            surge_threshold: 放量阈值，默认1.2
            shrink_threshold: 缩量阈值，默认0.7
        """
        self.surge_threshold = surge_threshold
        self.shrink_threshold = shrink_threshold
    
    def calculate_v37(self, volumes):
        """
        计算37天平均成交量
        
        Args:
            volumes: 成交量序列
            
        Returns:
            V37值
        """
        if len(volumes) < 37:
            return 0.0
        
        return sum(volumes[-37:]) / 37
    
    def is_volume_surge(self, current_volume, v37):
        """
        判断是否放量
        
        Args:
            current_volume: 当前成交量
            v37: 37天平均成交量
            
        Returns:
            是否放量
        """
        if v37 <= 0:
            return False
        
        return current_volume / v37 >= self.surge_threshold
    
    def is_volume_shrink(self, current_volume, v37):
        """
        判断是否缩量
        
        Args:
            current_volume: 当前成交量
            v37: 37天平均成交量
            
        Returns:
            是否缩量
        """
        if v37 <= 0:
            return False
        
        return current_volume / v37 < self.shrink_threshold
    
    def get_volume_ratio(self, current_volume, v37):
        """
        获取量比
        
        Args:
            current_volume: 当前成交量
            v37: 37天平均成交量
            
        Returns:
            量比
        """
        if v37 <= 0:
            return 0.0
        
        return current_volume / v37
    
    def analyze_volume_pattern(self, volumes, closes):
        """
        分析成交量模式
        
        Args:
            volumes: 成交量序列
            closes: 收盘价序列
            
        Returns:
            成交量分析结果
        """
        if len(volumes) < 37 or len(closes) < 2:
            return {
                'v37': 0.0,
                'current_volume': 0,
                'volume_ratio': 0.0,
                'is_surge': False,
                'is_shrink': False,
                'volume_pattern': 'unknown'
            }
        
        v37 = self.calculate_v37(volumes)
        current_volume = volumes[-1]
        volume_ratio = self.get_volume_ratio(current_volume, v37)
        
        is_surge = self.is_volume_surge(current_volume, v37)
        is_shrink = self.is_volume_shrink(current_volume, v37)
        
        # 判断成交量模式
        volume_pattern = 'normal'
        if is_surge:
            volume_pattern = 'surge'
        elif is_shrink:
            volume_pattern = 'shrink'
        
        return {
            'v37': v37,
            'current_volume': current_volume,
            'volume_ratio': volume_ratio,
            'is_surge': is_surge,
            'is_shrink': is_shrink,
            'volume_pattern': volume_pattern
        }


class Strategy1Analyzer:
    """策略1分析器：5/10/30日线粘合 + 量价齐升"""
    
    def __init__(self, surge_threshold=1.5, min_change_pct=3.0, uptrend_config=None):
        self.ma_analyzer = MAConvergenceAnalyzer()
        self.volume_analyzer = VolumeAnalyzer(surge_threshold=surge_threshold)
        self.min_change_pct = min_change_pct
        self.surge_threshold = surge_threshold  # 存储放量阈值，便于引用
        
        # 上涨vs反弹判断的默认配置（优化版）
        self.uptrend_config = uptrend_config or {
            # 粘合检查
            'convergence_check_days': 20,  # 检查最近N天
            'min_convergence_days': 10,    # 至少N天粘合
            'convergence_std_threshold': 2.0,  # 粘合期间价格波动标准差阈值（%）
            
            # 放量但涨幅不大
            'volume_surge_threshold': 1.5,  # 放量阈值
            'max_rise_pct': 3.0,            # 最大涨幅（%）
            'min_small_rise_days': 4,        # 至少N次（从3增加到4）
            
            # 持续小幅度上涨
            'max_small_rise_pct': 2.0,      # 小幅度上涨阈值（%）
            'min_continuous_days': 7,       # 至少连续N天（从5增加到7）
            
            # 量价配合
            'up_volume_threshold': 1.2,     # 上涨放量阈值
            'down_volume_threshold': 0.8,   # 下跌缩量阈值
            'min_up_volume_days': 3,        # 至少N次上涨放量（从2增加到3）
            'min_down_volume_days': 2,      # 至少N次下跌缩量（从1增加到2）
            
            # 反弹特征检查（优化：更严格的触发条件）
            'sudden_surge_threshold': 7.0,   # 单日大涨阈值从5%提高到7%
            'sudden_surge_check_days': 5,    # 检查最近N天
            'volume_surge_ratio': 4.0,       # 成交量突然放大倍数从3倍提高到4倍
            'volume_surge_max_count': 2,     # 突然放大最多N次
            'volume_surge_stable_days': 3,   # 放量后需站稳N天
            'volume_surge_stable_threshold': 2.0,  # 放量后跌幅不超过N%
            'divergence_check_days': 7,      # 量价背离检查天数从5天延长到7天
            'min_divergence_count': 3,       # 至少N次量价背离（从2增加到3）
            'quick_rebound_pct': 15.0,       # 快速反弹阈值从10%提高到15%
            'quick_rebound_days': 30,        # 快速反弹时间窗口从20天延长到30天
            
            # 评分权重（优化：降低扣分，提高加分）
            'weights': {
                'convergence': 3,           # 粘合持续时间权重从2提高到3
                'volume_accumulation': 3,    # 放量但涨幅不大权重从2提高到3
                'continuous_rise': 3,       # 持续小幅度上涨权重从2提高到3
                'volume_price_match': 3,     # 量价配合权重从2提高到3
                'ma_slope': 2,              # 均线斜率权重从1提高到2
                'ma_cross': 2,              # 均线金叉（新增）
                'break_resistance': 2,      # 突破关键阻力（新增）
                'sudden_surge': -1,         # 单日大涨扣分从-2调整为-1
                'volume_surge': -1,         # 成交量突然放大扣分从-2调整为-1
                'quick_rebound': -2,        # 快速反弹扣分从-3调整为-2
                'divergence': -1,           # 量价背离扣分从-2调整为-1
                'bear_trend': -1            # 空头排列扣分保持不变
            },
            
            # 判断阈值（优化：降低上涨门槛，提高反弹门槛）
            'min_uptrend_score': 2,         # 至少N分才算上涨（从3调整为2）
            'max_rebound_score': -1         # 低于N分算反弹（从0调整为-1）
        }
        
        # 趋势分析器延迟初始化（避免循环依赖）
        self._trend_analyzer = None
    
    def check_ma_convergence_5_10_30(self, closes):
        """
        检查5/10/30日线粘合
        
        Args:
            closes: 收盘价序列
            
        Returns:
            是否粘合
        """
        combinations = self.ma_analyzer.get_convergence_combinations(closes)
        daily_convergence = combinations.get('daily_5_10_30', {})
        return daily_convergence.get('is_convergent', False)
    
    def check_ma_convergence_today_or_yesterday(self, closes):
        """
        检查当天或前一天5/10/30日线粘合
        
        Args:
            closes: 收盘价序列
            
        Returns:
            (当天是否粘合, 前一天是否粘合, 是否满足条件)
        """
        if len(closes) < 31:
            return (False, False, False)
        
        # 检查当天粘合
        today_convergent = self.check_ma_convergence_5_10_30(closes)
        
        # 检查前一天粘合（去掉最后一天的数据）
        yesterday_closes = closes[:-1]
        yesterday_convergent = False
        if len(yesterday_closes) >= 30:
            yesterday_convergent = self.check_ma_convergence_5_10_30(yesterday_closes)
        
        # 只要当天或前一天任一满足即可
        is_ok = today_convergent or yesterday_convergent
        
        return (today_convergent, yesterday_convergent, is_ok)
    
    def check_uptrend_vs_rebound(self, closes, volumes):
        """
        判断是真正的上涨、反弹还是中性趋势（基于策略3的条件）
        
        根据需求文档，真正的上涨特征：
        1. 粘合时间长（≥10天）
        2. 近期多个放量但涨幅不大
        3. 近期多个小幅度持续上涨
        4. 上涨放量、下跌缩量
        
        反弹特征：
        1. 单日大涨（>5%）
        2. 成交量突然放大但不可持续
        3. 量价背离（上涨时缩量，下跌时放量）
        4. 空头排列下的上涨
        5. 从底部快速反弹
        
        Args:
            closes: 收盘价序列
            volumes: 成交量序列
            
        Returns:
            {
                'is_uptrend': bool,  # 是否真正的上涨
                'is_rebound': bool,  # 是否反弹
                'is_neutral': bool,  # 是否中性趋势
                'confidence': float,  # 置信度 0-1
                'score': int,  # 评分
                'reasons': list,  # 原因列表
                'indicators': dict  # 详细指标数据
            }
        """
        config = self.uptrend_config
        weights = config['weights']
        
        if len(closes) < 20 or len(volumes) < 37:
            return {
                'is_uptrend': False,
                'is_rebound': False,
                'is_neutral': True,
                'confidence': 0.0,
                'score': 0,
                'reasons': ['数据不足'],
                'indicators': {}
            }
        
        score = 0
        reasons = []
        indicators = {}
        
        # 计算均线
        ma5 = self.ma_analyzer.calculate_ma(closes, 5)
        ma10 = self.ma_analyzer.calculate_ma(closes, 10)
        ma30 = self.ma_analyzer.calculate_ma(closes, 30)
        
        if len(ma5) == 0 or len(ma10) == 0 or len(ma30) == 0:
            return {
                'is_uptrend': False,
                'is_rebound': False,
                'is_neutral': True,
                'confidence': 0.0,
                'score': 0,
                'reasons': ['无法计算均线'],
                'indicators': {}
            }
        
        v37 = self.volume_analyzer.calculate_v37(volumes)
        
        # 1. 检查粘合持续时间（优化：要求粘合期间价格波动较小）
        convergence_days = 0
        check_days = min(config['convergence_check_days'], len(ma5), len(ma10), len(ma30))
        convergence_prices = []  # 记录粘合期间的价格
        if check_days >= config['min_convergence_days']:
            for i in range(-check_days, 0):
                idx = len(ma5) + i
                if idx >= 0 and idx < len(ma5) and idx < len(ma10) and idx < len(ma30):
                    ma_vals = [ma5[idx], ma10[idx], ma30[idx]]
                    if self.ma_analyzer.is_convergent(ma_vals):
                        convergence_days += 1
                        if idx < len(closes):
                            convergence_prices.append(closes[idx])
        
        indicators['convergence_days'] = convergence_days
        if convergence_days >= config['min_convergence_days']:
            # 检查粘合期间价格波动
            price_std_ok = True
            if convergence_prices and len(convergence_prices) > 1:
                import numpy as np
                price_std = np.std(convergence_prices) / np.mean(convergence_prices) * 100
                price_std_ok = price_std < config.get('convergence_std_threshold', 2.0)
            
            if price_std_ok:
                score += weights['convergence']
                reasons.append(f'粘合持续{convergence_days}天（波动小）')
            else:
                # 波动较大，只给一半分
                score += weights['convergence'] // 2
                reasons.append(f'粘合持续{convergence_days}天（波动较大）')
        
        # 2. 检查近期多个放量但涨幅不大（优化：要求至少4次）
        small_rise_surge_days = 0
        check_days = min(10, len(closes) - 1, len(volumes) - 1)
        if check_days > 0:
            for i in range(-check_days, 0):
                idx = len(closes) + i
                if idx > 0 and idx < len(closes) and idx < len(volumes):
                    prev_idx = idx - 1
                    if prev_idx >= 0 and prev_idx < len(closes) and closes[prev_idx] > 0:
                        vol_ratio = volumes[idx] / v37 if v37 > 0 else 0
                        if vol_ratio >= config['volume_surge_threshold']:  # 放量
                            change_pct = ((closes[idx] - closes[prev_idx]) / closes[prev_idx] * 100)
                            if 0 < change_pct < config['max_rise_pct']:  # 上涨但涨幅不大
                                small_rise_surge_days += 1
        
        indicators['small_rise_surge_days'] = small_rise_surge_days
        if small_rise_surge_days >= config['min_small_rise_days']:
            score += weights['volume_accumulation']
            reasons.append(f'{small_rise_surge_days}次放量但涨幅不大')
        
        # 3. 检查近期多个小幅度持续上涨（优化：要求连续7天）
        max_continuous_days = 0
        continuous_days = 0
        check_days = min(10, len(closes) - 1)
        if check_days > 0:
            for i in range(-check_days, 0):
                idx = len(closes) + i
                if idx > 0 and idx < len(closes):
                    prev_idx = idx - 1
                    if prev_idx >= 0 and prev_idx < len(closes) and closes[prev_idx] > 0:
                        change_pct = ((closes[idx] - closes[prev_idx]) / closes[prev_idx] * 100)
                        if 0 < change_pct < config['max_small_rise_pct']:  # 小幅度上涨
                            continuous_days += 1
                            max_continuous_days = max(max_continuous_days, continuous_days)
                        else:
                            continuous_days = 0  # 中断则重置
        
        indicators['max_continuous_days'] = max_continuous_days
        if max_continuous_days >= config['min_continuous_days']:
            score += weights['continuous_rise']
            reasons.append(f'连续{max_continuous_days}天小幅上涨')
        
        # 4. 检查上涨放量、下跌缩量
        up_volume_ok = 0
        down_volume_ok = 0
        check_days = min(config['divergence_check_days'], len(closes) - 1, len(volumes) - 1)
        if check_days > 0:
            for i in range(-check_days, 0):
                idx = len(closes) + i
                if idx > 0 and idx < len(closes) and idx < len(volumes):
                    prev_idx = idx - 1
                    if prev_idx >= 0 and prev_idx < len(closes) and closes[prev_idx] > 0:
                        vol_ratio = volumes[idx] / v37 if v37 > 0 else 0
                        change_pct = ((closes[idx] - closes[prev_idx]) / closes[prev_idx] * 100)
                        
                        if change_pct > 0:  # 上涨
                            if vol_ratio >= config['up_volume_threshold']:  # 放量
                                up_volume_ok += 1
                        elif change_pct < 0:  # 下跌
                            if vol_ratio < config['down_volume_threshold']:  # 缩量
                                down_volume_ok += 1
        
        indicators['up_volume_ok'] = up_volume_ok
        indicators['down_volume_ok'] = down_volume_ok
        if up_volume_ok >= config['min_up_volume_days'] and down_volume_ok >= config['min_down_volume_days']:
            score += weights['volume_price_match']
            reasons.append(f'上涨放量{up_volume_ok}次，下跌缩量{down_volume_ok}次')
        
        # 5. 检查均线斜率（趋势方向）（优化：检查5日和10日均线同时向上）
        ma5_slope = 0
        ma10_slope = 0
        if len(ma5) >= 5:
            ma5_slope = ((ma5[-1] - ma5[-5]) / ma5[-5] * 100) if ma5[-5] > 0 else 0
        if len(ma10) >= 5:
            ma10_slope = ((ma10[-1] - ma10[-5]) / ma10[-5] * 100) if ma10[-5] > 0 else 0
        
        if ma5_slope > 0 and ma10_slope > 0:
            score += weights['ma_slope']
            reasons.append('5日和10日均线同时向上')
        elif ma5_slope > 0:
            # 只有5日均线向上，给一半分
            score += weights['ma_slope'] // 2
            reasons.append('5日均线向上')
        
        indicators['ma5_slope'] = ma5_slope
        indicators['ma10_slope'] = ma10_slope
        
        # 5.1 检查均线金叉（新增加分项）
        has_ma_cross = False
        if len(ma5) >= 2 and len(ma10) >= 2:
            # 检查5日均线是否上穿10日均线
            if ma5[-2] <= ma10[-2] and ma5[-1] > ma10[-1]:
                has_ma_cross = True
                score += weights.get('ma_cross', 0)
                reasons.append('5日均线上穿10日均线（金叉）')
        
        indicators['has_ma_cross'] = has_ma_cross
        
        # 5.2 检查突破关键阻力（新增加分项）
        has_break_resistance = False
        if len(closes) >= 30:
            # 检查是否突破30日内高点
            recent_high = max(closes[-30:])
            if closes[-1] >= recent_high * 0.98:  # 接近或突破高点（允许2%误差）
                has_break_resistance = True
                score += weights.get('break_resistance', 0)
                reasons.append('突破30日内高点')
        
        indicators['has_break_resistance'] = has_break_resistance
        
        # 6. 检查单日大涨（反弹特征）
        has_sudden_surge = False
        check_days = min(config['sudden_surge_check_days'], len(closes) - 1)
        if check_days > 0:
            for i in range(-check_days, 0):
                idx = len(closes) + i
                if idx > 0 and idx < len(closes):
                    prev_idx = idx - 1
                    if prev_idx >= 0 and prev_idx < len(closes) and closes[prev_idx] > 0:
                        change_pct = ((closes[idx] - closes[prev_idx]) / closes[prev_idx] * 100)
                        if change_pct > config['sudden_surge_threshold']:  # 单日涨幅>阈值
                            has_sudden_surge = True
                            break
        
        indicators['has_sudden_surge'] = has_sudden_surge
        if has_sudden_surge:
            score += weights['sudden_surge']
            reasons.append(f'出现单日大涨（>{config["sudden_surge_threshold"]}%）')
        
        # 7. 检查成交量突然放大但不可持续（反弹特征）（优化：要求放量后价格持续站稳）
        has_volume_surge = False
        if len(volumes) >= 10:
            recent_volumes = volumes[-10:]
            avg_volume = sum(recent_volumes) / len(recent_volumes) if recent_volumes else 0
            if avg_volume > 0:
                max_volume = max(recent_volumes)
                max_volume_ratio = max_volume / avg_volume
                
                # 如果最大成交量是平均的N倍以上，且只出现1-2次，可能是突然放大
                if max_volume_ratio >= config['volume_surge_ratio']:
                    surge_count = sum(1 for v in recent_volumes if v / avg_volume >= config['volume_surge_ratio'] * 0.83)
                    if surge_count <= config['volume_surge_max_count']:  # 只有1-2次大幅放量
                        # 检查放量后价格是否持续站稳
                        max_volume_idx = recent_volumes.index(max_volume)
                        stable_days = config.get('volume_surge_stable_days', 3)
                        stable_threshold = config.get('volume_surge_stable_threshold', 2.0)
                        
                        # 检查放量后N天内跌幅是否超过阈值
                        if len(closes) >= len(recent_volumes):
                            # 找到放量当天的价格
                            surge_price_idx = len(closes) - (len(recent_volumes) - max_volume_idx)
                            if surge_price_idx >= 0 and surge_price_idx < len(closes):
                                surge_price = closes[surge_price_idx]
                                # 检查放量后stable_days天内的最低价
                                end_idx = min(surge_price_idx + stable_days, len(closes))
                                if end_idx > surge_price_idx:
                                    prices_after = closes[surge_price_idx:end_idx]
                                    if prices_after:
                                        min_price_after = min(prices_after)
                                        if surge_price > 0:
                                            drop_pct = ((surge_price - min_price_after) / surge_price * 100) if min_price_after < surge_price else 0
                                            # 如果放量后跌幅超过阈值，判定为不可持续
                                            if drop_pct > stable_threshold:
                                                has_volume_surge = True
                        else:
                            # 数据不足，保守判断
                            has_volume_surge = True
        
        indicators['has_volume_surge'] = has_volume_surge
        if has_volume_surge:
            score += weights['volume_surge']
            reasons.append('成交量突然放大但不可持续')
        
        # 8. 检查量价背离（反弹特征）
        divergence_count = 0
        check_days = min(config['divergence_check_days'], len(closes) - 1, len(volumes) - 1)
        if check_days > 0:
            for i in range(-check_days, 0):
                idx = len(closes) + i
                if idx > 0 and idx < len(closes) and idx < len(volumes):
                    prev_idx = idx - 1
                    if prev_idx >= 0 and prev_idx < len(closes) and closes[prev_idx] > 0:
                        vol_ratio = volumes[idx] / v37 if v37 > 0 else 0
                        change_pct = ((closes[idx] - closes[prev_idx]) / closes[prev_idx] * 100)
                        
                        # 上涨时缩量或下跌时放量
                        if (change_pct > 0 and vol_ratio < 0.8) or (change_pct < 0 and vol_ratio >= 1.5):
                            divergence_count += 1
        
        indicators['divergence_count'] = divergence_count
        if divergence_count >= config['min_divergence_count']:
            score += weights['divergence']
            reasons.append(f'{divergence_count}次量价背离')
        
        # 9. 检查空头排列（反弹特征）（优化：如果5日均线已上穿10日均线，则不扣分）
        is_bear_trend = False
        try:
            # 延迟初始化趋势分析器（避免循环依赖）
            if self._trend_analyzer is None:
                # 在方法内部初始化，避免在__init__时TrendAnalyzer还未定义
                self._trend_analyzer = TrendAnalyzer()
            
            # 检查短均多头：5>10>20>30日
            is_bull = self._trend_analyzer.check_bull_trend(closes, [5, 10, 20, 30], is_true_bull=False)
            is_bear_trend = not is_bull
            
            # 例外条件：如果5日均线已上穿10日均线，则不扣分
            if is_bear_trend and len(ma5) >= 2 and len(ma10) >= 2:
                if ma5[-1] > ma10[-1]:  # 5日均线在10日均线上方
                    is_bear_trend = False
        except (NameError, AttributeError):
            # 如果TrendAnalyzer还未定义或检查失败，跳过
            pass
        
        indicators['is_bear_trend'] = is_bear_trend
        if is_bear_trend:
            score += weights['bear_trend']
            reasons.append('空头排列下的上涨')
        
        # 10. 检查是否从底部快速反弹（扣分项）（优化：提高阈值和时间窗口）
        is_quick_rebound = False
        rebound_days = config['quick_rebound_days']
        if len(closes) >= rebound_days:
            recent_closes = closes[-rebound_days:]
            min_price = min(recent_closes)
            min_price_index_in_recent = recent_closes.index(min_price)
            min_price_index = len(closes) - rebound_days + min_price_index_in_recent
            days_from_bottom = len(closes) - min_price_index - 1
            
            rebound_pct = ((closes[-1] - min_price) / min_price * 100) if min_price > 0 else 0
            
            # 如果从底部反弹超过阈值，且底部在最近N天内，可能是反弹
            if rebound_pct >= config['quick_rebound_pct'] and days_from_bottom <= rebound_days:
                is_quick_rebound = True
                score += weights['quick_rebound']
                reasons.append(f'从底部快速反弹{rebound_pct:.1f}%（{days_from_bottom}天）')
        
        indicators['is_quick_rebound'] = is_quick_rebound
        
        # 判断结果（优化：调整阈值）
        is_uptrend = score >= config['min_uptrend_score']  # 至少N分才算真正的上涨
        is_rebound = score <= config['max_rebound_score'] or is_quick_rebound
        is_neutral = not is_uptrend and not is_rebound  # 既不是上涨也不是反弹则为中性

        # 改进的置信度计算（优化：更平滑的映射）
        max_possible_score = sum(w for w in weights.values() if w > 0)  # 所有正权重的和
        min_uptrend_score = config['min_uptrend_score']
        max_rebound_score = config['max_rebound_score']
        
        if score <= max_rebound_score:
            # 得分≤-1，肯定是反弹
            confidence = 0.0
        elif score < min_uptrend_score:
            # 得分在-1到2之间，线性映射到0.0~0.5
            score_range = min_uptrend_score - max_rebound_score
            normalized_score = (score - max_rebound_score) / score_range if score_range > 0 else 0
            confidence = normalized_score * 0.5  # 0.0~0.5之间
        else:
            # 得分≥2，真正的上涨，线性映射到0.5~1.0
            score_range = max_possible_score - min_uptrend_score
            normalized_score = (score - min_uptrend_score) / score_range if score_range > 0 else 0
            confidence = 0.5 + normalized_score * 0.5  # 0.5~1.0之间
        
        confidence = min(1.0, max(0.0, confidence))  # 确保在0-1范围内

        return {
            'is_uptrend': is_uptrend,
            'is_rebound': is_rebound,
            'is_neutral': is_neutral,
            'confidence': confidence,
            'score': score,
            'reasons': reasons,
            'indicators': indicators
        }
    
    def check_volume_price_rise(self, volumes, closes, min_change_pct=None, surge_threshold=None):
        """
        检查量价齐升（当天）
        
        Args:
            volumes: 成交量序列
            closes: 收盘价序列
            min_change_pct: 最小涨幅百分比，如果为None则使用初始化时的值
            surge_threshold: 放量阈值，如果为None则使用初始化时的值
            
        Returns:
            是否量价齐升
        """
        if len(closes) < 2 or len(volumes) < 37:
            return False
        
        # 使用传入的阈值或默认阈值
        threshold = min_change_pct if min_change_pct is not None else self.min_change_pct
        
        # 检查涨幅
        current_price = closes[-1]
        prev_price = closes[-2]
        change_pct = ((current_price - prev_price) / prev_price) * 100
        
        if change_pct < threshold:
            return False
        
        # 检查放量 - 使用指定的surge_threshold或默认的
        if surge_threshold is not None:
            volume_analyzer = VolumeAnalyzer(surge_threshold=surge_threshold)
        else:
            volume_analyzer = self.volume_analyzer
        
        volume_analysis = volume_analyzer.analyze_volume_pattern(volumes, closes)
        return volume_analysis['is_surge']
    
    def check_method1(self, volumes, closes, min_change_pct=4.0, surge_threshold=1.5):
        """
        方法1：当天或前一天5/10/30日线粘合，且当天量价齐升
        
        Args:
            volumes: 成交量序列
            closes: 收盘价序列
            min_change_pct: 最小涨幅百分比，默认4%
            surge_threshold: 放量阈值，默认1.5
            
        Returns:
            是否满足方法1条件
        """
        # 检查当天或前一天粘合
        today_ok, yesterday_ok, ma_ok = self.check_ma_convergence_today_or_yesterday(closes)
        
        if not ma_ok:
            return False
        
        # 检查当天量价齐升
        volume_price_ok = self.check_volume_price_rise(volumes, closes, min_change_pct, surge_threshold)
        
        return volume_price_ok
    
    def check_method2(self, volumes, closes, surge_threshold=1.5, 
                      recent_days=10, min_surge_days=5, min_change_pct=3.0):
        """
        方法2：当天或前一天5/10/30日线粘合，且最近若干天放量上涨，有一天涨幅超过3%
        
        Args:
            volumes: 成交量序列
            closes: 收盘价序列
            surge_threshold: 放量阈值，默认1.5
            recent_days: 检查最近天数，默认10天
            min_surge_days: 最少放量天数，默认5天
            min_change_pct: 最小涨幅百分比，默认3%
            
        Returns:
            是否满足方法2条件
        """
        # 检查当天或前一天粘合
        today_ok, yesterday_ok, ma_ok = self.check_ma_convergence_today_or_yesterday(closes)
        
        if not ma_ok:
            return False
        
        # 需要足够的数据
        if len(closes) < max(37, recent_days + 1) or len(volumes) < max(37, recent_days + 1):
            return False
        
        # 计算V37（37天平均成交量）
        v37 = self.volume_analyzer.calculate_v37(volumes)
        if v37 <= 0:
            return False
        
        # 检查最近recent_days天（包括当天）
        recent_volumes = volumes[-recent_days:]
        recent_closes = closes[-recent_days:]
        
        # 统计放量天数
        surge_days = 0
        has_big_change = False  # 是否有涨幅超过min_change_pct的
        
        # 从第二天开始检查（因为需要前一天的价格计算涨幅）
        for i in range(1, len(recent_closes)):
            # 检查是否放量（当天成交量/V37 >= 阈值）
            if recent_volumes[i] / v37 >= surge_threshold:
                surge_days += 1
            
            # 检查涨幅（当天相对于前一天的涨幅）
            change_pct = ((recent_closes[i] - recent_closes[i-1]) / recent_closes[i-1]) * 100
            if change_pct >= min_change_pct:
                has_big_change = True
        
        # 条件：至少min_surge_days天放量，且有一天涨幅超过min_change_pct
        return surge_days >= min_surge_days and has_big_change
    
    def analyze_strategy1(self, stock_data, surge_threshold=None, min_change_pct=None, 
                         method='both', recent_days=10, min_surge_days=5):
        """
        分析策略1条件（方法1和方法2是"或"的关系，只要满足一个即可）
        
        Args:
            stock_data: 股票数据字典
            surge_threshold: 放量阈值，如果为None则使用初始化时的值（默认1.5）
            min_change_pct: 最小涨幅百分比，如果为None则使用方法默认值（方法1默认4%，方法2默认3%）
            method: 使用方法，'method1'、'method2' 或 'both'（同时检查两个方法，任一满足即可），默认'both'
            recent_days: 方法2参数：检查最近天数，默认10天
            min_surge_days: 方法2参数：最少放量天数，默认5天
            
        Returns:
            策略1分析结果
        """
        closes = stock_data.get('closes', [])
        volumes = stock_data.get('volumes', [])
        
        # 检查当天或前一天粘合
        today_ok, yesterday_ok, ma_convergence = self.check_ma_convergence_today_or_yesterday(closes)
        
        if not ma_convergence:
            # 数据不足或未粘合
            if len(closes) < 31 or len(volumes) < 37:
                return {
                    'is_candidate': False,
                    'ma_convergence': False,
                    'volume_price_rise': False,
                    'method1_ok': False,
                    'method2_ok': False,
                    'method': method,
                    'reason': '数据不足'
                }
            else:
                return {
                    'is_candidate': False,
                    'ma_convergence': False,
                    'volume_price_rise': False,
                    'method1_ok': False,
                    'method2_ok': False,
                    'method': method,
                    'reason': '当天或前一天5/10/30日线未粘合'
                }
        
        # 方法1参数：当天量价齐升
        method1_min_change = min_change_pct if min_change_pct is not None else 4.0
        method1_surge_threshold = surge_threshold if surge_threshold is not None else 1.5
        
        # 方法2参数：最近若干天放量上涨
        method2_min_change = min_change_pct if min_change_pct is not None else 3.0
        method2_surge_threshold = surge_threshold if surge_threshold is not None else 1.5
        
        # 检查方法1和方法2
        method1_ok = False
        method2_ok = False
        volume_price_rise = False
        
        if method in ('method1', 'both'):
            # 检查方法1：当天或前一天粘合，且当天量价齐升
            method1_ok = self.check_method1(volumes, closes, method1_min_change, method1_surge_threshold)
            if method1_ok:
                volume_price_rise = self.check_volume_price_rise(volumes, closes, method1_min_change, method1_surge_threshold)
        
        if method in ('method2', 'both'):
            # 检查方法2：当天或前一天粘合，且最近若干天放量上涨，有一天涨幅超过3%
            method2_ok = self.check_method2(volumes, closes, method2_surge_threshold, 
                                           recent_days, min_surge_days, method2_min_change)
        
        # 方法1和方法2是"或"的关系，只要满足一个即可
        if method == 'both':
            is_candidate = method1_ok or method2_ok
        elif method == 'method1':
            is_candidate = method1_ok
        else:  # method == 'method2'
            is_candidate = method2_ok
        
        # 🆕 如果满足策略1基本条件，检查是否是真正的上涨还是反弹
        trend_analysis = None
        if is_candidate and len(closes) >= 20 and len(volumes) >= 37:
            trend_analysis = self.check_uptrend_vs_rebound(closes, volumes)
            
            # 如果是反弹，降低优先级（不直接过滤，但标记出来）
            if trend_analysis['is_rebound']:
                # 可以在这里选择是否过滤掉反弹股票
                # 目前保留，但会在reason中标记
                pass
        
        # 获取成交量分析结果（用于返回）
        if surge_threshold is not None:
            temp_volume_analyzer = VolumeAnalyzer(surge_threshold=surge_threshold)
            volume_analysis = temp_volume_analyzer.analyze_volume_pattern(volumes, closes)
        else:
            volume_analysis = self.volume_analyzer.analyze_volume_pattern(volumes, closes)
        
        # 计算涨幅信息用于返回
        if len(closes) >= 2:
            current_price = closes[-1]
            prev_price = closes[-2]
            change_pct = ((current_price - prev_price) / prev_price) * 100
        else:
            change_pct = 0.0
        
        # 构建原因说明
        reason = []
        satisfied_methods = []
        
        if method1_ok:
            satisfied_methods.append('方法1')
        if method2_ok:
            satisfied_methods.append('方法2')
        
        if not ma_convergence:
            reason.append('当天或前一天5/10/30日线未粘合')
        elif not is_candidate:
            if method in ('method1', 'both') and not method1_ok:
                reason.append(f'方法1：当天未量价齐升（涨幅需>={method1_min_change}%，放量需>={method1_surge_threshold}倍）')
            if method in ('method2', 'both') and not method2_ok:
                reason.append(f'方法2：最近{recent_days}天放量天数不足{min_surge_days}天或涨幅不足{method2_min_change}%')
        
        # 构建方法描述
        if method == 'both':
            if satisfied_methods:
                method_desc = f"满足条件：{', '.join(satisfied_methods)}"
            else:
                method_desc = "方法1或方法2（均未满足）"
        elif method == 'method1':
            method_desc = '方法1：当天或前一天粘合+当天量价齐升'
        else:
            method_desc = f'方法2：当天或前一天粘合+最近{recent_days}天有{min_surge_days}天放量+有涨幅>={method2_min_change}%'
        
        # 🆕 添加趋势分析信息到reason
        trend_info = ""
        if trend_analysis:
            if trend_analysis['is_rebound']:
                trend_info = f" ⚠️可能是反弹（评分{trend_analysis['score']}分）"
            elif trend_analysis['is_uptrend']:
                trend_info = f" ✅真正的上涨（置信度{trend_analysis['confidence']:.0%}，评分{trend_analysis['score']}分）"
            elif trend_analysis.get('is_neutral'):
                trend_info = f" ⚪中性趋势（评分{trend_analysis['score']}分）"
            if trend_analysis['reasons']:
                trend_info += f": {', '.join(trend_analysis['reasons'])}"
        
        base_reason = '; '.join(reason) if reason else f'符合策略1条件（{method_desc}）'
        final_reason = base_reason + trend_info
        
        result = {
            'is_candidate': is_candidate,
            'ma_convergence': ma_convergence,
            'ma_convergence_today': today_ok,
            'ma_convergence_yesterday': yesterday_ok,
            'volume_price_rise': volume_price_rise,
            'method1_ok': method1_ok,
            'method2_ok': method2_ok,
            'change_pct': change_pct,
            'method': method,
            'method_desc': method_desc,
            'satisfied_methods': satisfied_methods,
            'reason': final_reason,
            'ma_convergence_ratio': self.ma_analyzer.get_convergence_combinations(closes).get('daily_5_10_30', {}).get('convergence_ratio', 0.0),
            'volume_analysis': volume_analysis,
            'config': {
                'surge_threshold': surge_threshold if surge_threshold is not None else self.volume_analyzer.surge_threshold,
                'min_change_pct': min_change_pct,
                'method': method,
                'method1_min_change_pct': method1_min_change,
                'method2_min_change_pct': method2_min_change,
                'recent_days': recent_days,
                'min_surge_days': min_surge_days
            }
        }
        
        # 🆕 添加趋势分析结果
        if trend_analysis:
            result['trend_analysis'] = trend_analysis
        
        return result


class HotSectorAnalyzer:
    """热点板块分析器 - 从tushare获取同花顺热榜数据"""
    
    def __init__(self, tushare_token='a054107022932e4f13f532718167561fd11765012b25472b351a81d7', 
                 enable_cache=True, cache_dir='.cache/sector_data'):
        """
        初始化热点板块分析器
        
        Args:
            tushare_token: tushare token，如果为None则尝试从环境变量获取
            enable_cache: 是否启用缓存，默认True
            cache_dir: 缓存目录，默认'.cache/sector_data'
        """
        self.tushare_available = TUSHARE_AVAILABLE
        if self.tushare_available:
            if tushare_token:
                ts.set_token(tushare_token)
            self.pro = ts.pro_api()
        else:
            self.pro = None
        
        # 初始化缓存
        self.enable_cache = enable_cache
        if self.enable_cache:
            self.cache = SectorDataCache(cache_dir=cache_dir)
        else:
            self.cache = None
    
    def get_hot_stocks_from_ths(self, start_date=None, end_date=None, weeks=2):
        """
        从同花顺热榜获取热点股票
        
        Args:
            start_date: 开始日期，格式'YYYYMMDD'，如果为None则自动计算
            end_date: 结束日期，格式'YYYYMMDD'，如果为None则使用今天
            weeks: 获取周数，默认2周
            
        Returns:
            dict: {code: score}，score越小越热点
        """
        if not self.tushare_available or not self.pro:
            return {}
        
        try:
            # 计算日期范围
            if end_date is None:
                end_date = datetime.now().strftime('%Y%m%d')
            
            if start_date is None:
                end_dt = datetime.strptime(end_date, '%Y%m%d')
                start_dt = end_dt - timedelta(days=weeks * 7)
                start_date = start_dt.strftime('%Y%m%d')
            
            # 获取交易日的数据
            hot_stocks = {}
            current_date = datetime.strptime(start_date, '%Y%m%d')
            end_dt = datetime.strptime(end_date, '%Y%m%d')
            
            while current_date <= end_dt:
                date_str = current_date.strftime('%Y%m%d')
                
                try:
                    # 调用tushare API获取同花顺热榜数据
                    df = self.pro.ths_hot(
                        start_date=date_str,
                        end_date=date_str
                    )
                    
                    if df is not None and not df.empty:
                        # 处理股票数据（排除板块）
                        for index, row in df.iterrows():
                            code = row.get('code') or row.get('ts_code', '')
                            rank = row.get('rank', 100)
                            
                            if code and not code.endswith(('BK0000', 'BK0001')):  # 排除板块代码
                                if code not in hot_stocks:
                                    hot_stocks[code] = []
                                hot_stocks[code].append(101 - rank)  # rank越小越热点，转换为分数
                
                except Exception as e:
                    print(f"❌ 获取 {date_str} 同花顺热榜数据失败: {e}")
                
                current_date += timedelta(days=1)
            
            # 计算平均分数
            result = {}
            for code, scores in hot_stocks.items():
                result[code] = sum(scores) / len(scores)
            
            # 按分数降序排序
            sorted_result = {k: v for k, v in sorted(result.items(), key=lambda item: item[1], reverse=True)}
            
            return sorted_result
            
        except Exception as e:
            print(f"❌ 获取同花顺热榜热点股票失败: {e}")
            return {}
    
    def get_max_increase_stocks(self, days=30, threshold=20.0):
        """
        获取指定天数内最大涨幅超过阈值的股票
        
        Args:
            days: 统计天数，默认30天
            threshold: 涨幅阈值（百分比），默认20%
            
        Returns:
            dict: {code: increase_pct}，涨幅百分比
        """
        if not self.tushare_available or not self.pro:
            return {}
        
        try:
            # 计算日期
            end_date = datetime.now().strftime('%Y%m%d')
            start_date = (datetime.now() - timedelta(days=days)).strftime('%Y%m%d')
            
            # 获取所有股票基本信息
            stocks_df = self.pro.stock_basic(market='', exchange='', list_status='L')
            
            # 获取股票行情数据
            max_increase_stocks = {}
            
            # 分批获取（tushare API有调用限制）
            for i in range(0, len(stocks_df), 500):
                batch_codes = stocks_df.iloc[i:i+500]['ts_code'].tolist()
                
                try:
                    # 获取K线数据
                    df = self.pro.daily(
                        ts_code=','.join(batch_codes),
                        start_date=start_date,
                        end_date=end_date
                    )
                    
                    if df is not None and not df.empty:
                        # 计算每只股票的最大涨幅
                        for code in batch_codes:
                            code_df = df[df['ts_code'] == code]
                            if len(code_df) > 0:
                                # 计算期间内的最大涨幅
                                max_close = code_df['close'].max()
                                min_close = code_df['close'].min()
                                increase_pct = (max_close - min_close) / min_close * 100
                                
                                if increase_pct >= threshold:
                                    max_increase_stocks[code] = increase_pct
                
                except Exception as e:
                    print(f"❌ 批量获取K线数据失败: {e}")
            
            # 按涨幅降序排序
            sorted_result = {k: v for k, v in sorted(max_increase_stocks.items(), key=lambda item: item[1], reverse=True)}
            
            return sorted_result
            
        except Exception as e:
            print(f"❌ 获取最大涨幅股票失败: {e}")
            return {}
    
    @staticmethod
    def generate_rank_by_single_day(df):
        """
        对某一天的排名数据进行处理，将重复的code的rank取平均值
        
        Args:
            df: 某一天的DataFrame，包含ts_code和rank列
            
        Returns:
            dict: {code: 平均rank}
        """
        code_to_rank = {}
        result = {}
        
        for index, row in df.iterrows():
            code = row['ts_code']
            rank = row['rank']
            
            if code not in code_to_rank:
                code_to_rank[code] = (rank, 1)
            else:
                total_rank_count = code_to_rank[code][1] + 1
                total_rank = code_to_rank[code][0] + rank
                code_to_rank[code] = (total_rank, total_rank_count)
        
        for code in code_to_rank:
            result[code] = code_to_rank[code][0] / code_to_rank[code][1]
        
        return result
    
    @staticmethod
    def gen_code_to_all_days_rank(hot_info):
        """
        生成所有code在所有日期的排名数据
        对于某些天查询不到的，设置为100
        
        Args:
            hot_info: dict，格式为 {datestr: DataFrame}
            
        Returns:
            dict: {code: {datestr: rank}}
        """
        code_to_all_days_rank = {}
        
        # 先处理有数据的天
        for datestr in hot_info:
            df = hot_info[datestr]
            code_to_rank = HotSectorAnalyzer.generate_rank_by_single_day(df)
            
            for code in code_to_rank:
                rank = code_to_rank[code]
                if code not in code_to_all_days_rank:
                    code_to_all_days_rank[code] = {}
                if datestr not in code_to_all_days_rank[code]:
                    code_to_all_days_rank[code][datestr] = rank
        
        # 对于所有code，补齐缺失的日期（设置为100）
        all_dates = set(hot_info.keys())
        for code in code_to_all_days_rank:
            for datestr in all_dates:
                if datestr not in code_to_all_days_rank[code]:
                    code_to_all_days_rank[code][datestr] = 100
        
        return code_to_all_days_rank
    
    def get_hot_sectors_from_tushare(self, start_date=None, end_date=None, weeks=2, 
                                     sector_type='industry'):
        """
        从tushare获取热点板块数据（行业板块或概念板块）
        
        Args:
            start_date: 开始日期，格式'YYYYMMDD'，如果为None则自动计算
            end_date: 结束日期，格式'YYYYMMDD'，如果为None则使用今天
            weeks: 获取周数，默认2周
            sector_type: 板块类型，'industry'（行业板块）或'concept'（概念板块）
            
        Returns:
            dict: {
                'hot_info': {datestr: DataFrame},  # 原始数据
                'code_to_all_days_rank': {code: {datestr: rank}},  # 处理后的排名数据
                'latest_ranks': {code: rank},  # 最后一天的排名
                'avg_ranks_3days': {code: avg_rank},  # 最近3天平均排名
                'top_sectors': [code],  # 排名靠前的板块（按最后一天排名）
            }
        """
        if not self.tushare_available or not self.pro:
            return {
                'error': 'tushare不可用，请检查tushare是否安装并配置token',
                'hot_info': {},
                'code_to_all_days_rank': {},
                'latest_ranks': {},
                'avg_ranks_3days': {},
                'top_sectors': []
            }
        
        try:
            # 计算日期范围
            if end_date is None:
                end_date = datetime.now().strftime('%Y%m%d')
            
            if start_date is None:
                # 计算2周前的日期（约14个交易日）
                end_dt = datetime.strptime(end_date, '%Y%m%d')
                start_dt = end_dt - timedelta(days=weeks * 7)
                start_date = start_dt.strftime('%Y%m%d')
            
            # 获取交易日列表（简化处理，实际应该获取交易日历）
            # 这里假设每天都是交易日，实际应该使用tushare的交易日历
            hot_info = {}
            current_date = datetime.strptime(start_date, '%Y%m%d')
            end_dt = datetime.strptime(end_date, '%Y%m%d')
            
            print(f"📊 开始获取同花顺热榜数据: {start_date} 至 {end_date} ({sector_type})", flush=True)
            
            # 获取每一天的数据
            while current_date <= end_dt:
                date_str = current_date.strftime('%Y%m%d')
                
                try:
                    # 调用tushare API获取同花顺热榜数据
                    # ths_hot API参数：start_date, end_date (格式YYYYMMDD)
                    # 注意：可能需要根据实际API文档调整参数名
                    df = self.pro.ths_hot(
                        start_date=date_str,
                        end_date=date_str
                    )
                    
                    if df is not None and not df.empty:
                        # 根据sector_type过滤数据（如果API返回的数据包含type字段）
                        # 如果API不支持type参数，可能需要通过其他方式区分行业和概念
                        if 'type' in df.columns:
                            df = df[df['type'] == sector_type]
                        
                        if not df.empty:
                            hot_info[date_str] = df
                            print(f"✅ 获取 {date_str} 数据: {len(df)} 条记录", flush=True)
                        else:
                            print(f"⚠️ {date_str} 无{sector_type}类型数据", flush=True)
                    else:
                        print(f"⚠️ {date_str} 无数据", flush=True)
                
                except Exception as e:
                    print(f"❌ 获取 {date_str} 数据失败: {e}", flush=True)
                
                # 移动到下一天
                current_date += timedelta(days=1)
            
            if not hot_info:
                return {
                    'error': '未获取到任何数据',
                    'hot_info': {},
                    'code_to_all_days_rank': {},
                    'latest_ranks': {},
                    'avg_ranks_3days': {},
                    'top_sectors': []
                }
            
            # 处理排名数据
            code_to_all_days_rank = self.gen_code_to_all_days_rank(hot_info)
            
            # 获取最后一天的排名
            latest_date = max(hot_info.keys())
            latest_ranks = {}
            if latest_date in hot_info:
                latest_df = hot_info[latest_date]
                latest_code_to_rank = self.generate_rank_by_single_day(latest_df)
                latest_ranks = latest_code_to_rank
            
            # 计算最近3天平均排名
            sorted_dates = sorted(hot_info.keys())
            recent_3_dates = sorted_dates[-3:] if len(sorted_dates) >= 3 else sorted_dates
            avg_ranks_3days = {}
            
            for code in code_to_all_days_rank:
                ranks = [code_to_all_days_rank[code].get(d, 100) for d in recent_3_dates]
                avg_ranks_3days[code] = sum(ranks) / len(ranks)
            
            # 获取排名靠前的板块（按最后一天排名，排名越小越靠前）
            sorted_sectors = sorted(latest_ranks.items(), key=lambda x: x[1])
            top_sectors = [code for code, rank in sorted_sectors[:20]]  # 取前20名
            
            # 获取板块代码到名称的映射
            code_to_name = {}
            try:
                # 获取同花顺板块指数列表以获取板块名称
                index_type = 'I' if sector_type == 'industry' else 'N'
                sector_list = self.pro.ths_index(exchange='A', type=index_type, 
                                                 fields='ts_code,name,type')
                if sector_list is not None and not sector_list.empty:
                    for _, row in sector_list.iterrows():
                        code_to_name[row['ts_code']] = row['name']
                    print(f"✅ 获取到 {len(code_to_name)} 个板块名称映射", flush=True)
            except Exception as e:
                print(f"⚠️ 获取板块名称映射失败: {e}，将只返回板块代码", flush=True)
            
            # 构建top_sectors_with_names，包含代码和名称
            top_sectors_with_names = []
            for code in top_sectors:
                sector_info = {
                    'code': code,
                    'name': code_to_name.get(code, code),  # 如果没有名称，使用代码
                    'rank': latest_ranks.get(code, 100),
                    'avg_rank_3days': avg_ranks_3days.get(code, 100)
                }
                top_sectors_with_names.append(sector_info)
            
            return {
                'hot_info': hot_info,
                'code_to_all_days_rank': code_to_all_days_rank,
                'latest_ranks': latest_ranks,
                'avg_ranks_3days': avg_ranks_3days,
                'top_sectors': top_sectors,  # 保持向后兼容，只返回代码列表
                'top_sectors_with_names': top_sectors_with_names,  # 新增：包含代码和名称的列表
                'code_to_name': code_to_name,  # 新增：代码到名称的映射
                'start_date': start_date,
                'end_date': end_date
            }
        
        except Exception as e:
            print(f"❌ 获取热点板块数据失败: {e}", flush=True)
            import traceback
            traceback.print_exc()
            return {
                'error': f'获取热点板块数据失败: {str(e)}',
                'hot_info': {},
                'code_to_all_days_rank': {},
                'latest_ranks': {},
                'avg_ranks_3days': {},
                'top_sectors': []
            }
    
    def get_hot_industry_sectors(self, start_date=None, end_date=None, weeks=2):
        """
        获取热点行业板块
        
        Args:
            start_date: 开始日期
            end_date: 结束日期
            weeks: 周数
            
        Returns:
            dict: 热点行业板块数据
        """
        return self.get_hot_sectors_from_tushare(start_date, end_date, weeks, 'industry')
    
    def get_hot_concept_sectors(self, start_date=None, end_date=None, weeks=2):
        """
        获取热点概念板块
        
        Args:
            start_date: 开始日期
            end_date: 结束日期
            weeks: 周数
            
        Returns:
            dict: 热点概念板块数据
        """
        return self.get_hot_sectors_from_tushare(start_date, end_date, weeks, 'concept')
    
    def get_hot_sectors_from_index(self, start_date=None, end_date=None, days=30,
                                    sector_type='concept', min_rise_pct=5.0, 
                                    bottom_rebound_pct=10.0):
        """
        策略2方法2：从同花顺板块指数行情中识别热门板块和底部企稳快速上升的板块
        
        根据指数的涨幅和均线等，确定当前的热门概念和行业，或者底部企稳并快速上升的概念和行业
        
        Args:
            start_date: 开始日期，格式'YYYYMMDD'，如果为None则自动计算
            end_date: 结束日期，格式'YYYYMMDD'，如果为None则使用今天
            days: 分析天数，默认30天
            sector_type: 板块类型，'concept'（概念板块）或'industry'（行业板块）
            min_rise_pct: 热门板块最小涨幅阈值（%），默认5%
            bottom_rebound_pct: 底部企稳快速上升的最小反弹幅度（%），默认10%
            
        Returns:
            dict: {
                'hot_sectors': [{'code': str, 'name': str, 'rise_pct': float, ...}],  # 热门板块
                'bottom_rebound_sectors': [{'code': str, 'name': str, ...}],  # 底部企稳快速上升板块
                'all_sectors_analysis': {code: analysis_dict},  # 所有板块的详细分析
                'error': str  # 错误信息（如果有）
            }
        """
        if not self.tushare_available or not self.pro:
            return {
                'error': 'tushare不可用，请检查tushare是否安装并配置token',
                'hot_sectors': [],
                'bottom_rebound_sectors': [],
                'all_sectors_analysis': {}
            }
        
        try:
            # 计算日期范围
            if end_date is None:
                end_date = datetime.now().strftime('%Y%m%d')
            
            if start_date is None:
                end_dt = datetime.strptime(end_date, '%Y%m%d')
                start_dt = end_dt - timedelta(days=days + 10)  # 多取10天用于计算均线
                start_date = start_dt.strftime('%Y%m%d')
            
            print(f"📊 开始从板块指数行情分析热点板块: {start_date} 至 {end_date} ({sector_type})", flush=True)
            
            # 1. 获取板块列表（优先从缓存）
            try:
                # 获取同花顺板块指数列表
                # type: 'N'概念板块, 'I'行业板块
                index_type = 'I' if sector_type == 'industry' else 'N'
                
                # 尝试从缓存获取
                sector_list = None
                if self.enable_cache and self.cache:
                    sector_list = self.cache.get_sector_list(sector_type)
                
                # 如果缓存没有，从API获取
                if sector_list is None or sector_list.empty:
                    sector_list = self.pro.ths_index(exchange='A', type=index_type, 
                                                     fields='ts_code,name,type')
                    
                    # 保存到缓存
                    if self.enable_cache and self.cache and sector_list is not None and not sector_list.empty:
                        self.cache.save_sector_list(sector_type, sector_list)
                
                if sector_list is None or sector_list.empty:
                    return {
                        'error': f'未获取到{sector_type}板块列表',
                        'hot_sectors': [],
                        'bottom_rebound_sectors': [],
                        'all_sectors_analysis': {}
                    }
                
                print(f"✅ 获取到 {len(sector_list)} 个{sector_type}板块", flush=True)
                
            except Exception as e:
                return {
                    'error': f'获取板块列表失败: {str(e)}',
                    'hot_sectors': [],
                    'bottom_rebound_sectors': [],
                    'all_sectors_analysis': {}
                }
            
            # 2. 获取每个板块的指数行情数据
            all_sectors_analysis = {}
            hot_sectors = []
            bottom_rebound_sectors = []
            
            ma_analyzer = MAConvergenceAnalyzer()
            
            for idx, row in sector_list.iterrows():
                sector_code = row['ts_code']
                sector_name = row['name']
                
                try:
                    # 获取板块指数日线数据（优先从缓存）
                    df = None
                    from_api = False  # 标记是否从API获取
                    
                    if self.enable_cache and self.cache:
                        df = self.cache.get_index_data(sector_code, start_date, end_date)
                    
                    # 如果缓存没有，从API获取
                    if df is None or df.empty:
                        df = self.pro.ths_daily(
                            ts_code=sector_code,
                            start_date=start_date,
                            end_date=end_date,
                            fields='trade_date,close,open,high,low,vol,amount'
                        )
                        from_api = True
                        
                        # 保存到缓存
                        if self.enable_cache and self.cache and df is not None and not df.empty:
                            self.cache.save_index_data(sector_code, start_date, end_date, df)
                    
                    if df is None or df.empty:
                        continue
                    
                    # 控制API调用频率（仅在从API获取数据时延迟）
                    if from_api:
                        import time
                        time.sleep(0.2)  # 避免API限流
                    
                    # 按日期排序
                    df = df.sort_values('trade_date')
                    df = df.reset_index(drop=True)
                    
                    if len(df) < 30:  # 数据不足30天，跳过
                        continue
                    
                    # 提取价格和成交量数据
                    closes = df['close'].tolist()
                    opens = df['open'].tolist()
                    highs = df['high'].tolist()
                    lows = df['low'].tolist()
                    volumes = df['vol'].tolist()
                    dates = df['trade_date'].tolist()
                    
                    # 计算技术指标
                    # 3. 计算涨幅
                    current_price = closes[-1]
                    price_5days_ago = closes[-6] if len(closes) >= 6 else closes[0]
                    price_10days_ago = closes[-11] if len(closes) >= 11 else closes[0]
                    price_20days_ago = closes[-21] if len(closes) >= 21 else closes[0]
                    
                    rise_5d = ((current_price - price_5days_ago) / price_5days_ago * 100) if price_5days_ago > 0 else 0
                    rise_10d = ((current_price - price_10days_ago) / price_10days_ago * 100) if price_10days_ago > 0 else 0
                    rise_20d = ((current_price - price_20days_ago) / price_20days_ago * 100) if price_20days_ago > 0 else 0
                    
                    # 4. 计算均线
                    ma5 = ma_analyzer.calculate_ma(closes, 5)
                    ma10 = ma_analyzer.calculate_ma(closes, 10)
                    ma30 = ma_analyzer.calculate_ma(closes, 30)
                    
                    # 均线值（最新）
                    ma5_latest = ma5[-1] if ma5 else None
                    ma10_latest = ma10[-1] if ma10 else None
                    ma30_latest = ma30[-1] if ma30 else None
                    
                    # 5. 判断均线多头排列（5日>10日>30日）
                    is_bull_ma = False
                    if ma5_latest and ma10_latest and ma30_latest:
                        is_bull_ma = ma5_latest > ma10_latest > ma30_latest
                    
                    # 6. 计算均线斜率（判断趋势）
                    ma5_slope = 0
                    ma10_slope = 0
                    if len(ma5) >= 5:
                        ma5_slope = ((ma5[-1] - ma5[-5]) / ma5[-5] * 100) if ma5[-5] > 0 else 0
                    if len(ma10) >= 5:
                        ma10_slope = ((ma10[-1] - ma10[-5]) / ma10[-5] * 100) if ma10[-5] > 0 else 0
                    
                    # 7. 计算成交量变化
                    avg_volume_20d = sum(volumes[-20:]) / 20 if len(volumes) >= 20 else volumes[-1]
                    volume_ratio = volumes[-1] / avg_volume_20d if avg_volume_20d > 0 else 1.0
                    
                    # 8. 计算最低点和反弹幅度（用于判断底部企稳）
                    if len(closes) >= 30:
                        recent_closes = closes[-30:]
                        min_price_30d = min(recent_closes)
                        min_price_index_in_recent = recent_closes.index(min_price_30d)
                        min_price_index = len(closes) - 30 + min_price_index_in_recent
                    else:
                        min_price_30d = min(closes)
                        min_price_index = closes.index(min_price_30d)
                    days_from_bottom = len(closes) - min_price_index - 1
                    
                    rebound_pct = ((current_price - min_price_30d) / min_price_30d * 100) if min_price_30d > 0 else 0
                    
                    # 9. 判断底部企稳快速上升的条件
                    # - 从最低点反弹超过阈值
                    # - 均线开始向上（斜率>0）
                    # - 成交量放大
                    is_bottom_rebound = (
                        rebound_pct >= bottom_rebound_pct and
                        days_from_bottom <= 20 and  # 底部在最近20天内
                        ma5_slope > 0 and  # 5日均线向上
                        volume_ratio >= 1.2  # 成交量放大
                    )
                    
                    # 10. 判断热门板块的条件
                    # - 涨幅大
                    # - 均线多头排列
                    # - 成交量放大
                    is_hot = (
                        (rise_5d >= min_rise_pct or rise_10d >= min_rise_pct * 1.5) and
                        is_bull_ma and
                        volume_ratio >= 1.2
                    )
                    
                    # 构建分析结果
                    analysis = {
                        'code': sector_code,
                        'name': sector_name,
                        'current_price': current_price,
                        'rise_5d': round(rise_5d, 2),
                        'rise_10d': round(rise_10d, 2),
                        'rise_20d': round(rise_20d, 2),
                        'ma5': round(ma5_latest, 2) if ma5_latest else None,
                        'ma10': round(ma10_latest, 2) if ma10_latest else None,
                        'ma30': round(ma30_latest, 2) if ma30_latest else None,
                        'is_bull_ma': is_bull_ma,
                        'ma5_slope': round(ma5_slope, 2),
                        'ma10_slope': round(ma10_slope, 2),
                        'volume_ratio': round(volume_ratio, 2),
                        'rebound_pct': round(rebound_pct, 2),
                        'days_from_bottom': days_from_bottom,
                        'is_hot': is_hot,
                        'is_bottom_rebound': is_bottom_rebound,
                        'score': 0  # 综合评分
                    }
                    
                    # 计算综合评分（用于排序）
                    score = 0
                    if is_hot:
                        score += rise_5d * 2 + rise_10d + (ma5_slope * 10) + (volume_ratio * 5)
                    if is_bottom_rebound:
                        score += rebound_pct * 1.5 + (ma5_slope * 10) + (volume_ratio * 5)
                    
                    analysis['score'] = round(score, 2)
                    all_sectors_analysis[sector_code] = analysis
                    
                    if is_hot:
                        hot_sectors.append(analysis)
                    
                    if is_bottom_rebound:
                        bottom_rebound_sectors.append(analysis)
                    
                except Exception as e:
                    print(f"⚠️ 分析板块 {sector_code}({sector_name}) 失败: {e}", flush=True)
                    continue
            
            # 按评分排序
            hot_sectors.sort(key=lambda x: x['score'], reverse=True)
            bottom_rebound_sectors.sort(key=lambda x: x['score'], reverse=True)
            
            print(f"✅ 分析完成: 热门板块 {len(hot_sectors)} 个, 底部企稳板块 {len(bottom_rebound_sectors)} 个", flush=True)
            
            return {
                'hot_sectors': hot_sectors,
                'bottom_rebound_sectors': bottom_rebound_sectors,
                'all_sectors_analysis': all_sectors_analysis,
                'start_date': start_date,
                'end_date': end_date
            }
            
        except Exception as e:
            print(f"❌ 从板块指数行情分析热点板块失败: {e}", flush=True)
            import traceback
            traceback.print_exc()
            return {
                'error': f'分析失败: {str(e)}',
                'hot_sectors': [],
                'bottom_rebound_sectors': [],
                'all_sectors_analysis': {}
            }
    
    def get_hot_sectors_from_index_concept(self, start_date=None, end_date=None, days=30,
                                           min_rise_pct=5.0, bottom_rebound_pct=10.0):
        """
        获取热门概念板块（从指数行情分析）
        
        Args:
            start_date: 开始日期
            end_date: 结束日期
            days: 分析天数
            min_rise_pct: 热门板块最小涨幅阈值
            bottom_rebound_pct: 底部企稳快速上升的最小反弹幅度
            
        Returns:
            dict: 热点概念板块数据
        """
        return self.get_hot_sectors_from_index(start_date, end_date, days, 'concept', 
                                               min_rise_pct, bottom_rebound_pct)
    
    def get_hot_sectors_from_index_industry(self, start_date=None, end_date=None, days=30,
                                            min_rise_pct=5.0, bottom_rebound_pct=10.0):
        """
        获取热门行业板块（从指数行情分析）
        
        Args:
            start_date: 开始日期
            end_date: 结束日期
            days: 分析天数
            min_rise_pct: 热门板块最小涨幅阈值
            bottom_rebound_pct: 底部企稳快速上升的最小反弹幅度
            
        Returns:
            dict: 热点行业板块数据
        """
        return self.get_hot_sectors_from_index(start_date, end_date, days, 'industry', 
                                               min_rise_pct, bottom_rebound_pct)


class Strategy2Analyzer:
    """策略2分析器 - 跟随热点板块"""
    
    def __init__(self, surge_threshold=1.5, ma_period=5):
        self.volume_analyzer = VolumeAnalyzer(surge_threshold=surge_threshold)
        self.surge_threshold = surge_threshold
        self.ma_period = ma_period
        self.hot_sector_analyzer = HotSectorAnalyzer()  # 热点板块分析器
    
    def analyze_strategy2(self, stock_data):
        """
        策略2分析：跟随热点板块
        1. 股票今日涨幅大于3%
        2. 成交量放大于1.5倍
        3. 短期均线向上发散
        
        Args:
            stock_data: 股票数据字典
            
        Returns:
            策略分析结果
        """
        closes = stock_data.get('closes', [])
        volumes = stock_data.get('volumes', [])
        
        if len(closes) < self.ma_period + 1 or len(volumes) < 37:
            return {
                'is_valid': False,
                'reason': '数据不足'
            }
        
        # 检查涨幅
        current_change_pct = ((closes[-1] - closes[-2]) / closes[-2]) * 100
        is_rise = current_change_pct > 3
        
        # 检查成交量
        v37 = self.volume_analyzer.calculate_v37(volumes)
        is_volume_surge = self.volume_analyzer.is_volume_surge(volumes[-1], v37)
        
        # 计算短期均线
        ma_values = []
        for i in range(len(closes) - self.ma_period + 1):
            ma = sum(closes[i:i+self.ma_period]) / self.ma_period
            ma_values.append(ma)
        
        # 检查均线向上发散
        is_ma_ascending = False
        if len(ma_values) >= 5:  # 至少需要5天的均线数据
            is_ma_ascending = all(ma_values[i] > ma_values[i-1] for i in range(-3, 0))
        
        # 策略满足条件
        is_valid = is_rise and is_volume_surge and is_ma_ascending
        
        return {
            'is_valid': is_valid,
            'current_change_pct': current_change_pct,
            'is_rise': is_rise,
            'is_volume_surge': is_volume_surge,
            'is_ma_ascending': is_ma_ascending,
            'reason': '满足策略2条件' if is_valid else '不满足策略2条件'
        }
    
    def get_hot_sectors_combined(self, start_date=None, end_date=None, weeks=2, days=30,
                                 min_rise_pct=5.0, bottom_rebound_pct=10.0):
        """
        策略2：综合获取热点板块（方法1 + 方法2）
        
        方法1：从同花顺热榜获取热点板块
        方法2：从板块指数行情分析热门板块和底部企稳快速上升板块
        
        Args:
            start_date: 开始日期
            end_date: 结束日期
            weeks: 方法1的周数
            days: 方法2的分析天数
            min_rise_pct: 方法2的热门板块最小涨幅阈值
            bottom_rebound_pct: 方法2的底部企稳快速上升最小反弹幅度
            
        Returns:
            dict: {
                'method1_concept': {...},  # 方法1概念板块
                'method1_industry': {...},  # 方法1行业板块
                'method2_concept': {...},  # 方法2概念板块
                'method2_industry': {...},  # 方法2行业板块
                'combined_hot_concepts': [code],  # 综合热门概念（两种方法都识别到的）
                'combined_hot_industries': [code],  # 综合热门行业
            }
        """
        result = {
            'method1_concept': {},
            'method1_industry': {},
            'method2_concept': {},
            'method2_industry': {},
            'combined_hot_concepts': [],
            'combined_hot_industries': []
        }
        
        # 方法1：从热榜获取
        try:
            result['method1_concept'] = self.hot_sector_analyzer.get_hot_concept_sectors(
                start_date, end_date, weeks
            )
            result['method1_industry'] = self.hot_sector_analyzer.get_hot_industry_sectors(
                start_date, end_date, weeks
            )
        except Exception as e:
            print(f"⚠️ 方法1获取失败: {e}", flush=True)
        
        # 方法2：从指数行情分析
        try:
            result['method2_concept'] = self.hot_sector_analyzer.get_hot_sectors_from_index_concept(
                start_date, end_date, days, min_rise_pct, bottom_rebound_pct
            )
            result['method2_industry'] = self.hot_sector_analyzer.get_hot_sectors_from_index_industry(
                start_date, end_date, days, min_rise_pct, bottom_rebound_pct
            )
        except Exception as e:
            print(f"⚠️ 方法2获取失败: {e}", flush=True)
        
        # 综合两种方法的结果（找出两种方法都识别到的板块）
        # 概念板块
        method1_concept_codes = set()
        if 'top_sectors' in result['method1_concept']:
            method1_concept_codes = set(result['method1_concept']['top_sectors'])
        
        method2_concept_codes = set()
        if 'hot_sectors' in result['method2_concept']:
            method2_concept_codes = {s['code'] for s in result['method2_concept']['hot_sectors']}
        
        result['combined_hot_concepts'] = list(method1_concept_codes & method2_concept_codes)
        
        # 行业板块
        method1_industry_codes = set()
        if 'top_sectors' in result['method1_industry']:
            method1_industry_codes = set(result['method1_industry']['top_sectors'])
        
        method2_industry_codes = set()
        if 'hot_sectors' in result['method2_industry']:
            method2_industry_codes = {s['code'] for s in result['method2_industry']['hot_sectors']}
        
        result['combined_hot_industries'] = list(method1_industry_codes & method2_industry_codes)
        
        return result

class Strategy3Analyzer:
    """策略3分析器 - 综合多维度筛选（技术面+资金面）"""
    
    def __init__(self):
        self.trend_analyzer = TrendAnalyzer()
        self.ma_analyzer = MAConvergenceAnalyzer()
        self.volume_analyzer = VolumeAnalyzer(surge_threshold=1.5)
        self.technical_indicator_analyzer = TechnicalIndicatorAnalyzer()
        self.chip_analyzer = ChipDistributionAnalyzer()
    
    def analyze_strategy3(self, stock_data, money_flow_data=None, fina_data=None):
        """
        策略3分析：综合多维度筛选（技术面+资金面+基本面）

        检查项（满足越多越佳）：
        技术面：
        1. 如果日线、周线、月线多头，更佳
        2. 如果周线、月线粘合，更佳
        3. 如果粘合时间长，比如10天、20天都是粘合，更佳
        4. 如果近期多个放量，但涨幅不大，更佳
        5. 如果近期多个小幅度持续上涨，更佳
        6. 如果上涨放量、下跌缩量，更佳
        7. MACD金叉且红柱放大
        8. KDJ低位金叉
        9. RSI在50以上且向上
        10. 筹码集中，上方套牢盘较少

        资金面：
        11. 大单净流入，特别是主力资金连续流入

        基本面：
        12. 基本面综合评分（盈利能力、成长能力、财务健康、估值、盈利质量）

        Args:
            stock_data: 股票数据字典，包含closes, volumes, opens, highs, lows等
            money_flow_data: 资金流数据字典（可选），包含today_net, continuous_days, total_net等
            fina_data: 财务数据字典（可选），包含roe, roa, 毛利率, 净利率等

        Returns:
            策略分析结果（包含评分和详细分析）
        """
        closes = stock_data.get('closes', [])
        volumes = stock_data.get('volumes', [])
        opens = stock_data.get('opens', closes)  # 如果没有开盘价，使用收盘价
        highs = stock_data.get('highs', closes)
        lows = stock_data.get('lows', closes)
        
        # 数据要求：至少30天用于基本分析，更多数据可以计算更多指标
        if len(closes) < 30 or len(volumes) < 37:
            return {
                'is_valid': False,
                'score': 0,
                'reason': '数据不足（需要至少30天数据）',
                'details': {}
            }
        
        score = 0
        reasons = []
        details = {}
        
        # 1. 检查日线、周线、月线多头（根据数据可用性）
        bull_trend_results = self.trend_analyzer.analyze_all_bull_trends(closes)
        
        # 日线多头：5>10>20>30日（需要至少30天数据）
        daily_bull = bull_trend_results.get('short_term_bull', {}).get('is_bull', False)
        if daily_bull:
            score += 2
            reasons.append('日线多头')
            details['daily_bull'] = True
        
        # 周线多头：25>50>100>150日（对应5>10>20>30周，需要至少150天数据）
        if len(closes) >= 150:
            weekly_bull = bull_trend_results.get('mid_term_bull', {}).get('is_bull', False)
            if weekly_bull:
                score += 2
                reasons.append('周线多头')
                details['weekly_bull'] = True
        else:
            weekly_bull = False
        
        # 月线多头：100>200>400>600日（对应5>10>20>30月，需要至少600天数据）
        if len(closes) >= 600:
            monthly_bull = bull_trend_results.get('long_term_bull', {}).get('is_bull', False)
            if monthly_bull:
                score += 2
                reasons.append('月线多头')
                details['monthly_bull'] = True
        else:
            monthly_bull = False
        
        # 2. 检查周线、月线粘合（根据数据可用性）
        ma_combinations = self.ma_analyzer.get_convergence_combinations(closes)
        
        # 周线粘合：25>50>150日（需要至少150天数据）
        weekly_convergence = False
        if len(closes) >= 150:
            weekly_convergence = ma_combinations.get('weekly_25_50_150', {}).get('is_convergent', False)
            if weekly_convergence:
                score += 2
                reasons.append('周线粘合')
                details['weekly_convergence'] = True
        
        # 月线粘合：100>200>600日（需要至少600天数据）
        monthly_convergence = False
        if len(closes) >= 600:
            monthly_convergence = ma_combinations.get('monthly_100_200_600', {}).get('is_convergent', False)
            if monthly_convergence:
                score += 2
                reasons.append('月线粘合')
                details['monthly_convergence'] = True
        
        # 3. 检查粘合持续时间（检查最近20天）
        convergence_days = 0
        if len(closes) >= 20:
            # 检查日线粘合持续时间
            daily_ma5 = self.ma_analyzer.calculate_ma(closes, 5)
            daily_ma10 = self.ma_analyzer.calculate_ma(closes, 10)
            daily_ma30 = self.ma_analyzer.calculate_ma(closes, 30)
            
            # 检查最近20天的粘合状态
            check_days = min(20, len(daily_ma5), len(daily_ma10), len(daily_ma30))
            if check_days >= 10:
                for i in range(-check_days, 0):
                    idx = len(daily_ma5) + i
                    # 确保所有索引都有效
                    if idx >= 0 and idx < len(daily_ma5) and idx < len(daily_ma10) and idx < len(daily_ma30):
                        ma_vals = [daily_ma5[idx], daily_ma10[idx], daily_ma30[idx]]
                        if self.ma_analyzer.is_convergent(ma_vals):
                            convergence_days += 1
        
        if convergence_days >= 20:
            score += 3
            reasons.append(f'粘合持续≥20天')
            details['convergence_days'] = convergence_days
        elif convergence_days >= 10:
            score += 2
            reasons.append(f'粘合持续≥10天')
            details['convergence_days'] = convergence_days
        
        # 4. 检查近期多个放量，但涨幅不大（最近10天）
        v37 = self.volume_analyzer.calculate_v37(volumes)
        surge_days = 0
        small_rise_days = 0
        
        if len(closes) >= 10 and len(volumes) >= 10:
            check_days = min(10, len(closes) - 1, len(volumes) - 1)  # 确保有前一天数据
            if check_days > 0:
                for i in range(-check_days, 0):
                    idx = len(closes) + i
                    # 确保索引有效且有前一天数据
                    if idx > 0 and idx < len(closes) and idx < len(volumes):
                        prev_idx = idx - 1
                        if prev_idx >= 0 and prev_idx < len(closes):
                            # 检查是否放量
                            vol_ratio = volumes[idx] / v37 if v37 > 0 else 0
                            if vol_ratio >= 1.5:
                                surge_days += 1
                                
                                # 检查涨幅是否不大（<3%）
                                if closes[prev_idx] > 0:
                                    change_pct = ((closes[idx] - closes[prev_idx]) / closes[prev_idx] * 100)
                                    if 0 < change_pct < 3:  # 上涨但涨幅不大
                                        small_rise_days += 1
        
        if small_rise_days >= 3:  # 至少3天放量但涨幅不大
            score += 3
            reasons.append(f'近期{small_rise_days}次放量但涨幅不大')
            details['small_rise_surge_days'] = small_rise_days
        
        # 5. 检查近期多个小幅度持续上涨（最近10天）
        continuous_small_rise_days = 0
        max_continuous_days = 0
        if len(closes) >= 10:
            check_days = min(10, len(closes) - 1)  # 确保有前一天数据
            if check_days > 0:
                for i in range(-check_days, 0):
                    idx = len(closes) + i
                    # 确保索引有效且有前一天数据
                    if idx > 0 and idx < len(closes):
                        prev_idx = idx - 1
                        if prev_idx >= 0 and prev_idx < len(closes) and closes[prev_idx] > 0:
                            change_pct = ((closes[idx] - closes[prev_idx]) / closes[prev_idx] * 100)
                            if 0 < change_pct < 2:  # 小幅度上涨（<2%）
                                continuous_small_rise_days += 1
                                max_continuous_days = max(max_continuous_days, continuous_small_rise_days)
                            else:
                                continuous_small_rise_days = 0  # 中断则重置
                continuous_small_rise_days = max_continuous_days
        
        if continuous_small_rise_days >= 5:  # 至少连续5天小幅上涨
            score += 3
            reasons.append(f'近期{continuous_small_rise_days}天小幅持续上涨')
            details['continuous_small_rise_days'] = continuous_small_rise_days
        
        # 6. 检查上涨放量、下跌缩量（最近5天）
        up_volume_ok = 0
        down_volume_ok = 0
        
        if len(closes) >= 5 and len(volumes) >= 5:
            check_days = min(5, len(closes) - 1, len(volumes) - 1)  # 确保有前一天数据
            if check_days > 0:
                for i in range(-check_days, 0):
                    idx = len(closes) + i
                    # 确保索引有效且有前一天数据
                    if idx > 0 and idx < len(closes) and idx < len(volumes):
                        prev_idx = idx - 1
                        if prev_idx >= 0 and prev_idx < len(closes) and closes[prev_idx] > 0:
                            vol_ratio = volumes[idx] / v37 if v37 > 0 else 0
                            change_pct = ((closes[idx] - closes[prev_idx]) / closes[prev_idx] * 100)
                            
                            if change_pct > 0:  # 上涨
                                if vol_ratio >= 1.2:  # 放量
                                    up_volume_ok += 1
                            elif change_pct < 0:  # 下跌
                                if vol_ratio < 0.8:  # 缩量
                                    down_volume_ok += 1
        
        if up_volume_ok >= 2 and down_volume_ok >= 1:  # 至少2次上涨放量，1次下跌缩量
            score += 3
            reasons.append('上涨放量下跌缩量')
            details['up_volume_ok'] = up_volume_ok
            details['down_volume_ok'] = down_volume_ok
        
        # 7. 检查MACD金叉且红柱放大（技术面分析）
        try:
            macd_result = self.technical_indicator_analyzer.calculate_macd(closes)
            if macd_result['is_golden_cross']:
                score += 2
                reasons.append('MACD金叉')
                details['macd_golden_cross'] = True
            if macd_result['is_red_bar_expanding']:
                score += 1
                reasons.append('MACD红柱放大')
                details['macd_red_bar_expanding'] = True
            details['macd'] = {
                'dif': macd_result['dif'][-1] if macd_result['dif'] else 0,
                'dea': macd_result['dea'][-1] if macd_result['dea'] else 0,
                'macd': macd_result['macd'][-1] if macd_result['macd'] else 0
            }
        except Exception as e:
            details['macd'] = None
        
        # 8. 检查KDJ低位金叉（技术面分析）
        try:
            if len(highs) > 0 and len(lows) > 0:
                kdj_result = self.technical_indicator_analyzer.calculate_kdj(closes, highs, lows)
                if kdj_result['is_low_golden_cross']:
                    score += 2
                    reasons.append('KDJ低位金叉')
                    details['kdj_low_golden_cross'] = True
                details['kdj'] = {
                    'k': kdj_result['k'][-1] if kdj_result['k'] else 0,
                    'd': kdj_result['d'][-1] if kdj_result['d'] else 0,
                    'j': kdj_result['j'][-1] if kdj_result['j'] else 0
                }
        except Exception as e:
            details['kdj'] = None
        
        # 9. 检查RSI在50以上且向上（技术面分析）
        try:
            rsi_result = self.technical_indicator_analyzer.calculate_rsi(closes)
            if rsi_result['is_above_50'] and rsi_result['is_upward']:
                score += 2
                reasons.append('RSI在50以上且向上')
                details['rsi_strong'] = True
            elif rsi_result['is_above_50']:
                score += 1
                reasons.append('RSI在50以上')
            details['rsi'] = rsi_result['rsi'][-1] if rsi_result['rsi'] else 0
        except Exception as e:
            details['rsi'] = None
        
        # 10. 检查筹码分布：筹码集中，上方套牢盘较少（技术面分析）
        try:
            chip_result = self.chip_analyzer.calculate_chip_concentration(closes, volumes)
            if chip_result['is_concentrated']:
                score += 2
                reasons.append('筹码集中，上方套牢盘少')
                details['chip_concentrated'] = True
            elif chip_result['concentration_ratio'] > 0.6:
                score += 1
                reasons.append('筹码较集中')
            details['chip_analysis'] = {
                'concentration_ratio': chip_result['concentration_ratio'],
                'upper_pressure_ratio': chip_result['upper_pressure_ratio'],
                'cost_center': chip_result['cost_center']
            }
        except Exception as e:
            details['chip_analysis'] = None
        
        # 11. 检查资金面：大单净流入，特别是主力资金连续流入（资金面分析）
        if money_flow_data:
            today_net = money_flow_data.get('today_net', 0)
            continuous_days = money_flow_data.get('continuous_days', 0)
            total_net = money_flow_data.get('total_net', 0)
            
            # 今日大单净流入
            if today_net > 0:
                score += 2
                reasons.append(f'今日主力净流入{today_net:.0f}万元')
                details['money_flow_today'] = today_net
            
            # 连续流入天数
            if continuous_days >= 3:
                score += 3
                reasons.append(f'主力资金连续流入{continuous_days}天')
                details['money_flow_continuous_days'] = continuous_days
            elif continuous_days >= 2:
                score += 1
                reasons.append(f'主力资金连续流入{continuous_days}天')
                details['money_flow_continuous_days'] = continuous_days
            
            # 累计净流入
            if total_net > 0:
                details['money_flow_total'] = total_net
        else:
            details['money_flow'] = '数据不可用'

        # 12. 基本面分析
        if fina_data:
            try:
                from fundamental_analyzer import FundamentalAnalyzer
                fundamental_analyzer = FundamentalAnalyzer()
                fa_result = fundamental_analyzer.analyze_from_data(fina_data)
                fundamental_score = fa_result['score']
                fundamental_rating = fa_result['rating_label']
                details['fundamental_score'] = fundamental_score
                details['fundamental_rating'] = fundamental_rating
                details['fundamental_details'] = fa_result.get('details', {})

                if fundamental_score >= 80:
                    score += 7
                    reasons.append(f'基本面优秀(评分{fundamental_score})')
                elif fundamental_score >= 60:
                    score += 5
                    reasons.append(f'基本面良好(评分{fundamental_score})')
                elif fundamental_score >= 40:
                    score += 3
                    reasons.append(f'基本面一般(评分{fundamental_score})')
                else:
                    reasons.append(f'基本面较差(评分{fundamental_score})')
            except Exception as e:
                details['fundamental_score'] = None
                details['fundamental_error'] = str(e)
        else:
            details['fundamental_score'] = None

        # 风险检测：突破历史最高位（基于突破质量智能判断）
        is_break_historical_high = False
        distance_to_historical_high_pct = 0
        historical_high = 0

        if len(closes) >= 60:  # 至少需要60天数据来判断历史最高位
            historical_high = max(closes)
            current_price = closes[-1]

            if historical_high > 0:
                distance_to_historical_high_pct = ((current_price - historical_high) / historical_high) * 100

                # 计算辅助指标：成交量、收盘强度
                avg_vol_20 = sum(volumes[-21:-1]) / 20 if len(volumes) >= 21 else sum(volumes[:-1]) / max(len(volumes[:-1]), 1)
                vol_ratio = volumes[-1] / avg_vol_20 if avg_vol_20 > 0 else 1
                day_range = highs[-1] - lows[-1]
                close_position = (closes[-1] - lows[-1]) / day_range if day_range > 0 else 0.5

                if current_price > historical_high * 1.005:
                    # === 突破历史新高：基于突破质量判断 ===
                    is_break_historical_high = True

                    # 多周期趋势共振：日线多头 + 周线或月线多头
                    multi_tf_bull = daily_bull and (weekly_bull or monthly_bull)

                    # 三个质量维度
                    strong_volume = vol_ratio >= 1.5
                    strong_close = close_position >= 0.5
                    strong_trend = multi_tf_bull

                    quality_score = sum([strong_volume, strong_close, strong_trend])

                    # 质量描述
                    quality_parts = []
                    if strong_volume:
                        quality_parts.append(f'放量({vol_ratio:.1f}x)')
                    if strong_close:
                        quality_parts.append(f'收盘强势({close_position:.0%})')
                    if strong_trend:
                        tf_parts = ['日线多头']
                        if weekly_bull:
                            tf_parts.append('周线')
                        if monthly_bull:
                            tf_parts.append('月线')
                        quality_parts.append('+'.join(tf_parts) + '共振')
                    quality_desc = ', '.join(quality_parts) if quality_parts else '突破信号弱'

                    if quality_score >= 3:
                        # 高质量突破：放量+强势收盘+多周期共振 → 加分
                        score += 2
                        reasons.append(f'✅放量强势突破历史新高({quality_desc})')
                    elif quality_score == 2:
                        # 中等质量突破：不扣分不加分
                        reasons.append(f'📈突破历史新高({quality_desc})')
                    elif quality_score == 1:
                        # 弱势突破：警惕假突破
                        score = max(0, score - 2)
                        reasons.append(f'⚠️弱势突破历史新高({quality_desc}，警惕假突破)')
                    else:
                        # 极弱突破：缩量+弱势收盘+趋势不配合
                        score = max(0, score - 4)
                        reasons.append(f'⚠️缩量弱势突破历史新高({quality_desc}，假突破风险高)')

                    details['break_historical_high'] = True
                    details['historical_high'] = historical_high
                    details['distance_to_historical_high_pct'] = distance_to_historical_high_pct
                    details['break_quality'] = {
                        'quality_score': quality_score,
                        'vol_ratio': round(vol_ratio, 2),
                        'close_position': round(close_position, 2),
                        'multi_tf_bull': multi_tf_bull,
                        'details': quality_desc
                    }

                elif current_price >= historical_high * 0.995:
                    # === 接近历史高位但未突破 ===
                    if vol_ratio >= 1.5 and close_position >= 0.5:
                        # 放量强势接近：蓄力蓄势，小幅提示
                        score = max(0, score - 1)
                        reasons.append(f'📊放量蓄力接近历史新高(距{abs(distance_to_historical_high_pct):.2f}%)')
                    else:
                        # 弱势接近：动能不足
                        score = max(0, score - 2)
                        reasons.append(f'⚠️接近历史高位但动能不足(距{abs(distance_to_historical_high_pct):.2f}%)')

                    details['break_historical_high'] = False
                    details['near_historical_high'] = True
                    details['historical_high'] = historical_high
                    details['distance_to_historical_high_pct'] = distance_to_historical_high_pct

                else:
                    details['break_historical_high'] = False
                    details['near_historical_high'] = False
                    details['historical_high'] = historical_high
                    details['distance_to_historical_high_pct'] = distance_to_historical_high_pct
        
        # 判断是否满足策略3条件（评分>=5分）
        is_valid = score >= 5
        
        # 🆕 分析买入时机
        buy_timing_result = None
        try:
            buy_timing_analyzer = BuyTimingAnalyzer()
            buy_timing_result = buy_timing_analyzer.analyze_buy_timing(stock_data, intraday_data=None)
            details['buy_timing'] = buy_timing_result
        except Exception as e:
            details['buy_timing'] = {'error': str(e)}
        
        return {
            'is_valid': is_valid,
            'score': score,
            'reasons': reasons,
            'details': details,
            'daily_bull': daily_bull,
            'weekly_bull': weekly_bull,
            'monthly_bull': monthly_bull,
            'weekly_convergence': weekly_convergence,
            'monthly_convergence': monthly_convergence,
            'convergence_days': convergence_days,
            'bull_trend_details': bull_trend_results,
            'ma_combinations': ma_combinations,
            'buy_timing': buy_timing_result,  # 🆕 买入时机分析结果
            'break_historical_high': is_break_historical_high,  # 🆕 是否突破历史最高位
            'distance_to_historical_high_pct': distance_to_historical_high_pct,  # 🆕 距离历史最高位百分比
            'historical_high': historical_high,  # 🆕 历史最高价
            'reason': f'策略3评分: {score}分 ({", ".join(reasons)})' if reasons else '不满足策略3条件'
        }

class BuyTimingAnalyzer:
    """买入时机分析器"""
    
    def __init__(self):
        self.ma_analyzer = MAConvergenceAnalyzer()
        self.volume_analyzer = VolumeAnalyzer(surge_threshold=1.5)
    
    def analyze_buy_timing(self, stock_data, intraday_data=None):
        """
        分析买入时机
        
        Args:
            stock_data: 股票数据字典，包含closes, volumes, opens, highs, lows等
            intraday_data: 分时数据（可选），包含分时价格和分时均线
            
        Returns:
            {
                'day_line_signals': dict,  # 日线买入信号
                'intraday_signals': dict,  # 分时买入信号
                'buy_score': int,  # 买入评分
                'buy_recommendation': str,  # 买入建议
                'warnings': list  # 警告信息
            }
        """
        closes = stock_data.get('closes', [])
        volumes = stock_data.get('volumes', [])
        opens = stock_data.get('opens', closes)
        highs = stock_data.get('highs', closes)
        lows = stock_data.get('lows', closes)
        
        day_line_signals = {}
        intraday_signals = {}
        buy_score = 0
        buy_recommendation = '观望'
        warnings = []
        
        if len(closes) < 30:
            return {
                'day_line_signals': {},
                'intraday_signals': {},
                'buy_score': 0,
                'buy_recommendation': '数据不足',
                'warnings': ['数据不足，无法判断买入时机']
            }
        
        # 4.2 日线买入点分析
        
        # 4.2.1 突破关键阻力位并确认有效（连续两天站上）
        if len(closes) >= 30:
            # 计算30日内高点作为关键阻力位
            resistance_level = max(closes[-30:])
            current_price = closes[-1]
            
            # 检查是否连续两天站上阻力位
            if len(closes) >= 2:
                day1_above = closes[-1] >= resistance_level * 0.98  # 允许2%误差
                day2_above = closes[-2] >= resistance_level * 0.98
                
                if day1_above and day2_above:
                    day_line_signals['break_resistance'] = True
                    buy_score += 3
                    buy_recommendation = '突破关键阻力位，可考虑买入'
                elif day1_above:
                    day_line_signals['break_resistance'] = 'pending'  # 待确认
                    buy_score += 1
            else:
                day_line_signals['break_resistance'] = False
        
        # 4.2.2 均线粘合后首次大幅放量上涨
        if len(closes) >= 30:
            ma5 = self.ma_analyzer.calculate_ma(closes, 5)
            ma10 = self.ma_analyzer.calculate_ma(closes, 10)
            ma30 = self.ma_analyzer.calculate_ma(closes, 30)
            
            if len(ma5) >= 2 and len(ma10) >= 2 and len(ma30) >= 2:
                # 检查前一天是否粘合
                prev_ma_vals = [ma5[-2], ma10[-2], ma30[-2]]
                was_convergent = self.ma_analyzer.is_convergent(prev_ma_vals)
                
                # 检查今天是否大幅放量上涨
                v37 = self.volume_analyzer.calculate_v37(volumes)
                current_volume_ratio = volumes[-1] / v37 if v37 > 0 else 0
                current_change_pct = ((closes[-1] - closes[-2]) / closes[-2] * 100) if closes[-2] > 0 else 0
                
                if was_convergent and current_volume_ratio >= 2.0 and current_change_pct >= 3.0:
                    day_line_signals['convergence_surge'] = True
                    buy_score += 3
                    if buy_recommendation == '观望':
                        buy_recommendation = '均线粘合后首次大幅放量上涨，可考虑买入'
                else:
                    day_line_signals['convergence_surge'] = False
        
        # 4.1 分时买入点分析（如果有分时数据）
        if intraday_data:
            intraday_prices = intraday_data.get('prices', [])
            intraday_ma = intraday_data.get('ma', [])
            
            if len(intraday_prices) >= 2 and len(intraday_ma) >= 2:
                # 检查分时线是否回踩均线并再次向上
                current_price = intraday_prices[-1]
                current_ma = intraday_ma[-1]
                prev_price = intraday_prices[-2]
                prev_ma = intraday_ma[-2]
                
                # 回踩均线：价格曾低于均线，现在高于均线
                if prev_price <= prev_ma and current_price > current_ma:
                    intraday_signals['ma_rebound'] = True
                    buy_score += 2
                    if buy_recommendation == '观望':
                        buy_recommendation = '分时线回踩均线后向上，可考虑买入'
                else:
                    intraday_signals['ma_rebound'] = False
        else:
            intraday_signals['ma_rebound'] = None
        
        # 4.1.2 避免追高：开盘冲高7-8个点以上不追
        if len(opens) > 0 and len(closes) > 0:
            open_price = opens[-1] if opens else closes[-1]
            prev_close = closes[-2] if len(closes) >= 2 else open_price
            
            if prev_close > 0:
                open_change_pct = ((open_price - prev_close) / prev_close * 100)
                
                if open_change_pct >= 7.0:
                    warnings.append(f'开盘冲高{open_change_pct:.1f}%，不建议追高')
                    buy_score -= 2  # 扣分
                elif open_change_pct >= 5.0:
                    warnings.append(f'开盘冲高{open_change_pct:.1f}%，谨慎追高')
                    buy_score -= 1
        
        # 综合买入建议
        if buy_score >= 5:
            buy_recommendation = '强烈推荐买入'
        elif buy_score >= 3:
            buy_recommendation = '可考虑买入'
        elif buy_score >= 1:
            buy_recommendation = '谨慎买入'
        elif buy_score < 0:
            buy_recommendation = '不建议买入'
        
        return {
            'day_line_signals': day_line_signals,
            'intraday_signals': intraday_signals,
            'buy_score': buy_score,
            'buy_recommendation': buy_recommendation,
            'warnings': warnings
        }
    
    def analyze_intraday_buy_timing(self, intraday_data):
        """
        分析分时买入时机（需要分时数据）
        
        Args:
            intraday_data: 分时数据字典，包含time, price, volume, ma等
            
        Returns:
            {
                'is_good_timing': bool,  # 是否好的买入时机
                'buy_signals': list,     # 买入信号列表
                'buy_reason': str        # 买入理由
            }
        """
        # 注意：分时数据需要从实时行情获取，这里提供接口框架
        # 实际实现需要接入分时数据源
        
        return {
            'is_good_timing': False,
            'buy_signals': ['分时数据不可用'],
            'buy_reason': '分时数据不可用，无法判断分时买入时机'
        }


class SellStrategyAnalyzer:
    """卖出策略分析器"""
    
    def __init__(self):
        self.volume_analyzer = VolumeAnalyzer()
    
    def analyze_sell_strategy(self, stock_data, purchase_price, holding_days):
        """
        卖出策略分析
        1. 止损条件：跌破10日均线且成交量放大
        2. 止盈条件：短期涨幅过大（>15%）或者均线死叉
        3. 趋势变化：多头趋势转为空头趋势
        
        Args:
            stock_data: 股票数据字典
            purchase_price: 买入价格
            holding_days: 持股天数
            
        Returns:
            卖出建议结果
        """
        closes = stock_data.get('closes', [])
        volumes = stock_data.get('volumes', [])
        
        if len(closes) < 10 or not purchase_price:
            return {
                'sell': False,
                'reason': '数据不足或买入价格未知',
                'signal_type': 'unknown'
            }
        
        # 计算收益率
        current_price = closes[-1]
        profit_ratio = (current_price - purchase_price) / purchase_price * 100
        
        # 止损条件：跌破10日均线且成交量放大
        ma10 = sum(closes[-10:]) / 10 if len(closes) >= 10 else 0
        is_below_ma10 = current_price < ma10
        v37 = self.volume_analyzer.calculate_v37(volumes)
        volume_ratio = self.volume_analyzer.get_volume_ratio(volumes[-1], v37) if v37 > 0 else 0
        is_volume_surge = volume_ratio > 1.5
        
        stop_loss_condition = is_below_ma10 and is_volume_surge
        
        # 止盈条件：短期涨幅过大（>15%）
        stop_profit_condition = profit_ratio > 15
        
        # 止盈条件：连续下跌
        is_continuous_fall = False
        if len(closes) >= 4:
            is_continuous_fall = all(closes[i] < closes[i-1] for i in range(-3, 0))
        
        # 生成卖出建议
        sell_reason = ""
        signal_type = "none"
        
        if stop_loss_condition:
            sell = True
            sell_reason = "止损：跌破10日均线且成交量放大"
            signal_type = "stop_loss"
        elif stop_profit_condition:
            sell = True
            sell_reason = f"止盈：收益达到{profit_ratio:.2f}%"
            signal_type = "stop_profit"
        elif is_continuous_fall:
            sell = True
            sell_reason = "连续下跌3天"
            signal_type = "continuous_fall"
        else:
            sell = False
            sell_reason = "持有"
            signal_type = "hold"
        
        return {
            'sell': sell,
            'reason': sell_reason,
            'signal_type': signal_type,
            'profit_ratio': profit_ratio,
            'current_price': current_price,
            'holding_days': holding_days
        }

class TrendAnalyzer:
    """趋势分析器 - 判断多头/空头状态"""
    
    def __init__(self):
        self.ma_analyzer = MAConvergenceAnalyzer()
    
    def is_ma_ascending(self, ma_values):
        """判断均线是否呈现多头排列（从大到小，短期均线在长期均线之上）"""
        if len(ma_values) < 2:
            return False
        
        for i in range(1, len(ma_values)):
            if ma_values[i] >= ma_values[i-1]:
                return False
        return True
    
    def check_bull_trend(self, closes, ma_periods, is_true_bull=True):
        """检查多头趋势
        
        Args:
            closes: 收盘价序列
            ma_periods: 均线周期列表（按从小到大顺序）
            is_true_bull: 是否检查真多头（收盘价在最小均线上方）
            
        Returns:
            是否多头趋势
        """
        try:
            if not closes or len(closes) < max(ma_periods):
                return False
            
            # 计算各周期均线
            ma_values = []
            for period in ma_periods:
                try:
                    ma = self.ma_analyzer.calculate_ma(closes, period)
                    if ma and len(ma) > 0:  # 如果有计算结果
                        ma_values.append(ma[-1])
                    else:
                        return False
                except Exception as e:
                    # 如果计算均线失败，返回False
                    error_str = str(e).lower()
                    if 'no columns' in error_str or 'parse from file' in error_str or 'empty data' in error_str:
                        # pandas相关错误，静默处理
                        pass
                    return False
            
            if len(ma_values) != len(ma_periods):
                return False
            
            # 检查多头排列
            is_bull = self.is_ma_ascending(ma_values)
            
            # 如果是真多头，还需检查收盘价是否在最小均线上方
            if is_bull and is_true_bull:
                return closes[-1] > ma_values[0]
            
            return is_bull
        except Exception as e:
            # 捕获所有异常，包括pandas相关的错误
            error_str = str(e).lower()
            if 'no columns' in error_str or 'parse from file' in error_str or 'empty data' in error_str:
                # pandas相关错误，可能是缓存文件问题，不影响整体功能
                pass
            return False
    
    def analyze_all_bull_trends(self, closes):
        """分析所有多头趋势类型"""
        results = {}
        
        # 数据验证
        if not closes or len(closes) < 5:
            # 返回空结果，避免后续计算失败
            return {
                'short_term_bull': {'is_bull': False, 'is_true_bull': False, 'is_false_bull': False, 'description': '短均多头'},
                'mid_term_bull': {'is_bull': False, 'is_true_bull': False, 'is_false_bull': False, 'description': '中均多头'},
                'long_term_bull': {'is_bull': False, 'is_true_bull': False, 'is_false_bull': False, 'description': '长均多头'},
                'five_line_bull': {'is_bull': False, 'is_true_bull': False, 'is_false_bull': False, 'description': '5线开花'}
            }
        
        try:
            # 短均多头：5>10>20>30日
            short_bull_true = self.check_bull_trend(closes, [5, 10, 20, 30], is_true_bull=True)
            short_bull_false = self.check_bull_trend(closes, [5, 10, 20, 30], is_true_bull=False)
            results['short_term_bull'] = {
                'is_bull': short_bull_true or short_bull_false,
                'is_true_bull': short_bull_true,
                'is_false_bull': short_bull_false and not short_bull_true,
                'description': '短均多头'
            }
        except Exception as e:
            # 捕获所有异常，包括pandas相关的错误
            error_str = str(e).lower()
            if 'no columns' in error_str or 'parse from file' in error_str or 'empty data' in error_str:
                # pandas相关错误，可能是缓存文件问题，不影响整体功能
                pass
            results['short_term_bull'] = {'is_bull': False, 'is_true_bull': False, 'is_false_bull': False, 'description': '短均多头'}
        
        try:
            # 中均多头：25>50>100>150日（对应5>10>20>30周）
            if len(closes) >= 150:
                mid_bull_true = self.check_bull_trend(closes, [25, 50, 100, 150], is_true_bull=True)
                mid_bull_false = self.check_bull_trend(closes, [25, 50, 100, 150], is_true_bull=False)
                results['mid_term_bull'] = {
                    'is_bull': mid_bull_true or mid_bull_false,
                    'is_true_bull': mid_bull_true,
                    'is_false_bull': mid_bull_false and not mid_bull_true,
                    'description': '中均多头'
                }
            else:
                results['mid_term_bull'] = {'is_bull': False, 'is_true_bull': False, 'is_false_bull': False, 'description': '中均多头'}
        except Exception as e:
            # 捕获所有异常，包括pandas相关的错误
            error_str = str(e).lower()
            if 'no columns' in error_str or 'parse from file' in error_str or 'empty data' in error_str:
                # pandas相关错误，可能是缓存文件问题，不影响整体功能
                pass
            results['mid_term_bull'] = {'is_bull': False, 'is_true_bull': False, 'is_false_bull': False, 'description': '中均多头'}
        
        try:
            # 长均多头：100>200>400>600日（对应5>10>20>30月）
            if len(closes) >= 600:
                long_bull_true = self.check_bull_trend(closes, [100, 200, 400, 600], is_true_bull=True)
                long_bull_false = self.check_bull_trend(closes, [100, 200, 400, 600], is_true_bull=False)
                results['long_term_bull'] = {
                    'is_bull': long_bull_true or long_bull_false,
                    'is_true_bull': long_bull_true,
                    'is_false_bull': long_bull_false and not long_bull_true,
                    'description': '长均多头'
                }
            else:
                results['long_term_bull'] = {'is_bull': False, 'is_true_bull': False, 'is_false_bull': False, 'description': '长均多头'}
        except Exception as e:
            # 捕获所有异常，包括pandas相关的错误
            error_str = str(e).lower()
            if 'no columns' in error_str or 'parse from file' in error_str or 'empty data' in error_str:
                # pandas相关错误，可能是缓存文件问题，不影响整体功能
                pass
            results['long_term_bull'] = {'is_bull': False, 'is_true_bull': False, 'is_false_bull': False, 'description': '长均多头'}
        
        try:
            # 5线开花：5>10>30>120>250日
            if len(closes) >= 250:
                five_line_bull_true = self.check_bull_trend(closes, [5, 10, 30, 120, 250], is_true_bull=True)
                five_line_bull_false = self.check_bull_trend(closes, [5, 10, 30, 120, 250], is_true_bull=False)
                results['five_line_bull'] = {
                    'is_bull': five_line_bull_true or five_line_bull_false,
                    'is_true_bull': five_line_bull_true,
                    'is_false_bull': five_line_bull_false and not five_line_bull_true,
                    'description': '5线开花'
                }
            else:
                results['five_line_bull'] = {'is_bull': False, 'is_true_bull': False, 'is_false_bull': False, 'description': '5线开花'}
        except Exception as e:
            # 捕获所有异常，包括pandas相关的错误
            error_str = str(e).lower()
            if 'no columns' in error_str or 'parse from file' in error_str or 'empty data' in error_str:
                # pandas相关错误，可能是缓存文件问题，不影响整体功能
                pass
            results['five_line_bull'] = {'is_bull': False, 'is_true_bull': False, 'is_false_bull': False, 'description': '5线开花'}
        
        return results

class PriceVolumeAnalyzer:
    """量价关系分析器"""
    
    def __init__(self):
        self.volume_analyzer = VolumeAnalyzer(surge_threshold=1.5)  # 按需求设置为1.5倍
    
    def analyze_ma_crossover(self, closes, ma_short=5, ma_long=10):
        """分析均线交叉
        
        Args:
            closes: 收盘价序列
            ma_short: 短期均线周期
            ma_long: 长期均线周期
            
        Returns:
            交叉分析结果
        """
        if len(closes) < ma_long + 1:
            return {'signal': 'none', 'description': '数据不足'}
        
        # 计算均线
        ma_short_values = []
        ma_long_values = []
        
        for i in range(len(closes) - ma_long + 1):
            ma_short_val = sum(closes[i:i+ma_short]) / ma_short if i + ma_short <= len(closes) else 0
            ma_long_val = sum(closes[i:i+ma_long]) / ma_long
            ma_short_values.append(ma_short_val)
            ma_long_values.append(ma_long_val)
        
        # 判断交叉信号
        if len(ma_short_values) >= 2:
            # 金叉：短期均线上穿长期均线
            if ma_short_values[-1] > ma_long_values[-1] and ma_short_values[-2] <= ma_long_values[-2]:
                return {'signal': 'golden_cross', 'description': '5穿10金叉'}
            # 死叉：短期均线下穿长期均线
            elif ma_short_values[-1] < ma_long_values[-1] and ma_short_values[-2] >= ma_long_values[-2]:
                return {'signal': 'death_cross', 'description': '5穿10死叉'}
        
        return {'signal': 'none', 'description': '无交叉信号'}
    
    def analyze_volume_color(self, current_volume, v37, close_price, open_price, turnover_rate=0):
        """分析成交量颜色标记
        
        Args:
            current_volume: 当前成交量
            v37: 37天平均成交量
            close_price: 收盘价
            open_price: 开盘价
            turnover_rate: 换手率
            
        Returns:
            成交量颜色标记信息
        """
        volume_ratio = current_volume / v37 if v37 > 0 else 0
        is_up = close_price > open_price
        
        # 基于量比的颜色标记
        color_type = 'normal'
        color_desc = '普通'
        
        if is_up:
            if 3 < volume_ratio <= 4.5:
                color_type = 'yellow'
                color_desc = '黄色实心柱'
            elif 4.5 < volume_ratio <= 6:
                color_type = 'green'
                color_desc = '绿色实心柱'
            elif volume_ratio > 6:
                color_type = 'white'
                color_desc = '白色实心柱'
            else:
                color_type = 'red'
                color_desc = '红色实心柱'
        
        # 基于换手率的颜色标记（如果换手率大于10%）
        if turnover_rate >= 10:
            if 10 <= turnover_rate < 20:
                color_type = 'red'
                color_desc = '红色柱（换手率10-20%）'
            elif 20 <= turnover_rate < 30:
                color_type = 'green'
                color_desc = '绿色柱（换手率20-30%）'
            elif 30 <= turnover_rate < 40:
                color_type = 'yellow'
                color_desc = '黄色柱（换手率30-40%）'
            elif turnover_rate >= 40:
                color_type = 'white'
                color_desc = '白色柱（换手率>=40%）'
        
        return {
            'color_type': color_type,
            'description': color_desc,
            'volume_ratio': volume_ratio,
            'turnover_rate': turnover_rate
        }

class TechnicalIndicatorAnalyzer:
    """技术指标分析器 - MACD、KDJ、RSI等"""
    
    def calculate_macd(self, closes, fast_period=12, slow_period=26, signal_period=9):
        """
        计算MACD指标
        
        Args:
            closes: 收盘价序列
            fast_period: 快线周期，默认12
            slow_period: 慢线周期，默认26
            signal_period: 信号线周期，默认9
            
        Returns:
            {
                'dif': list,      # DIF线（快线-慢线）
                'dea': list,      # DEA线（信号线）
                'macd': list,     # MACD柱（DIF-DEA）*2
                'is_golden_cross': bool,  # 是否金叉
                'is_red_bar_expanding': bool  # 红柱是否放大
            }
        """
        if len(closes) < slow_period + signal_period:
            return {
                'dif': [],
                'dea': [],
                'macd': [],
                'is_golden_cross': False,
                'is_red_bar_expanding': False
            }
        
        # 计算EMA
        def calculate_ema(prices, period):
            ema = []
            multiplier = 2.0 / (period + 1)
            for i, price in enumerate(prices):
                if i == 0:
                    ema.append(price)
                else:
                    ema.append((price - ema[-1]) * multiplier + ema[-1])
            return ema
        
        # 计算快线和慢线EMA
        ema_fast = calculate_ema(closes, fast_period)
        ema_slow = calculate_ema(closes, slow_period)
        
        # 计算DIF（快线-慢线）
        dif = [ema_fast[i] - ema_slow[i] for i in range(len(ema_fast))]
        
        # 计算DEA（DIF的EMA，即信号线）
        dea = calculate_ema(dif, signal_period)
        
        # 计算MACD柱（DIF-DEA）*2
        macd = [(dif[i] - dea[i]) * 2 for i in range(len(dea))]
        
        # 判断是否金叉（DIF上穿DEA）
        is_golden_cross = False
        if len(dif) >= 2 and len(dea) >= 2:
            if dif[-2] <= dea[-2] and dif[-1] > dea[-1]:
                is_golden_cross = True
        
        # 判断红柱是否放大（MACD柱为正且增大）
        is_red_bar_expanding = False
        if len(macd) >= 2:
            if macd[-1] > 0 and macd[-1] > macd[-2]:
                is_red_bar_expanding = True
        
        return {
            'dif': dif,
            'dea': dea,
            'macd': macd,
            'is_golden_cross': is_golden_cross,
            'is_red_bar_expanding': is_red_bar_expanding
        }
    
    def calculate_kdj(self, closes, highs, lows, period=9, k_period=3, d_period=3):
        """
        计算KDJ指标
        
        Args:
            closes: 收盘价序列
            highs: 最高价序列
            lows: 最低价序列
            period: RSV周期，默认9
            k_period: K值平滑周期，默认3
            d_period: D值平滑周期，默认3
            
        Returns:
            {
                'k': list,      # K值
                'd': list,      # D值
                'j': list,      # J值
                'is_low_golden_cross': bool  # 是否低位金叉（K上穿D且K<30）
            }
        """
        if len(closes) < period or len(highs) < period or len(lows) < period:
            return {
                'k': [],
                'd': [],
                'j': [],
                'is_low_golden_cross': False
            }
        
        # 计算RSV
        rsv = []
        for i in range(period - 1, len(closes)):
            period_high = max(highs[i - period + 1:i + 1])
            period_low = min(lows[i - period + 1:i + 1])
            if period_high != period_low:
                rsv_value = ((closes[i] - period_low) / (period_high - period_low)) * 100
            else:
                rsv_value = 50
            rsv.append(rsv_value)
        
        # 计算K、D值（使用EMA平滑）
        k = []
        d = []
        for i, rsv_value in enumerate(rsv):
            if i == 0:
                k.append(50)  # 初始值
                d.append(50)
            else:
                k_value = (2 * k[-1] + rsv_value) / 3
                d_value = (2 * d[-1] + k_value) / 3
                k.append(k_value)
                d.append(d_value)
        
        # 计算J值（J = 3K - 2D）
        j = [3 * k[i] - 2 * d[i] for i in range(len(k))]
        
        # 判断是否低位金叉（K上穿D且K<30）
        is_low_golden_cross = False
        if len(k) >= 2 and len(d) >= 2:
            if k[-2] <= d[-2] and k[-1] > d[-1] and k[-1] < 30:
                is_low_golden_cross = True
        
        return {
            'k': k,
            'd': d,
            'j': j,
            'is_low_golden_cross': is_low_golden_cross
        }
    
    def calculate_rsi(self, closes, period=14):
        """
        计算RSI指标
        
        Args:
            closes: 收盘价序列
            period: RSI周期，默认14
            
        Returns:
            {
                'rsi': list,      # RSI值
                'is_above_50': bool,  # 是否在50以上
                'is_upward': bool     # 是否向上
            }
        """
        if len(closes) < period + 1:
            return {
                'rsi': [],
                'is_above_50': False,
                'is_upward': False
            }
        
        # 计算涨跌幅
        changes = []
        for i in range(1, len(closes)):
            change = closes[i] - closes[i - 1]
            changes.append(change)
        
        # 计算RSI
        rsi = []
        for i in range(period - 1, len(changes)):
            period_changes = changes[i - period + 1:i + 1]
            gains = [c for c in period_changes if c > 0]
            losses = [-c for c in period_changes if c < 0]
            
            avg_gain = sum(gains) / period if gains else 0
            avg_loss = sum(losses) / period if losses else 0
            
            if avg_loss == 0:
                rsi_value = 100
            else:
                rs = avg_gain / avg_loss
                rsi_value = 100 - (100 / (1 + rs))
            
            rsi.append(rsi_value)
        
        # 判断是否在50以上且向上
        is_above_50 = False
        is_upward = False
        if len(rsi) >= 2:
            is_above_50 = rsi[-1] > 50
            is_upward = rsi[-1] > rsi[-2]
        
        return {
            'rsi': rsi,
            'is_above_50': is_above_50,
            'is_upward': is_upward
        }


class ChipDistributionAnalyzer:
    """筹码分布分析器"""
    
    def calculate_chip_concentration(self, closes, volumes=None, period=60):
        """
        计算筹码集中度
        
        Args:
            closes: 收盘价序列
            volumes: 成交量序列（可选）
            period: 分析周期，默认60天
            
        Returns:
            {
                'concentration_ratio': float,  # 筹码集中度（0-1，越高越集中）
                'upper_pressure_ratio': float,  # 上方套牢盘比例（0-1）
                'cost_center': float,  # 成本重心
                'is_concentrated': bool  # 是否筹码集中
            }
        """
        if not closes or len(closes) < period:
            return {
                'concentration_ratio': 0.0,
                'upper_pressure_ratio': 1.0,
                'cost_center': 0.0,
                'is_concentrated': False
            }
        
        recent_closes = closes[-period:]
        current_price = closes[-1]
        
        # 计算成本重心（加权平均价格）
        if volumes and len(volumes) >= period:
            recent_volumes = volumes[-period:]
            total_value = sum(recent_closes[i] * recent_volumes[i] for i in range(len(recent_closes)))
            total_volume = sum(recent_volumes)
            cost_center = total_value / total_volume if total_volume > 0 else sum(recent_closes) / len(recent_closes)
        else:
            cost_center = sum(recent_closes) / len(recent_closes)
        
        # 计算筹码集中度（价格在成本重心附近的集中程度）
        price_std = np.std(recent_closes) if len(recent_closes) > 1 else 0
        price_mean = np.mean(recent_closes)
        concentration_ratio = 1.0 - min(1.0, price_std / price_mean) if price_mean > 0 else 0.0
        
        # 计算上方套牢盘比例（当前价格上方的筹码比例）
        upper_pressure = sum(1 for price in recent_closes if price > current_price)
        upper_pressure_ratio = upper_pressure / len(recent_closes) if recent_closes else 1.0
        
        # 判断是否筹码集中（集中度>0.7且上方套牢盘<0.3）
        is_concentrated = concentration_ratio > 0.7 and upper_pressure_ratio < 0.3
        
        return {
            'concentration_ratio': concentration_ratio,
            'upper_pressure_ratio': upper_pressure_ratio,
            'cost_center': cost_center,
            'is_concentrated': is_concentrated
        }
    
    def calculate_chip_levels(self, price_data, volumes=None):
        """计算筹码分位线
        
        Args:
            price_data: 价格数据（收盘价或最高价最低价平均）
            volumes: 成交量数据（可选，用于加权计算）
            
        Returns:
            筹码分位线字典
        """
        if not price_data:
            return {
                'cost5': 0,
                'cost15': 0,
                'cost50': 0,
                'cost85': 0,
                'cost95': 0
            }
        
        # 使用pandas计算分位数
        prices_series = pd.Series(price_data)
        
        # 如果提供了成交量，使用成交量加权计算
        if volumes and len(volumes) == len(price_data):
            # 创建DataFrame
            df = pd.DataFrame({
                'price': prices_series,
                'volume': volumes
            })
            
            # 排序
            df_sorted = df.sort_values('price')
            
            # 计算累计成交量权重
            df_sorted['cum_volume'] = df_sorted['volume'].cumsum()
            total_volume = df_sorted['volume'].sum()
            df_sorted['weight'] = df_sorted['cum_volume'] / total_volume
            
            # 计算分位线
            cost5 = df_sorted[df_sorted['weight'] >= 0.05]['price'].iloc[0] if len(df_sorted[df_sorted['weight'] >= 0.05]) > 0 else 0
            cost15 = df_sorted[df_sorted['weight'] >= 0.15]['price'].iloc[0] if len(df_sorted[df_sorted['weight'] >= 0.15]) > 0 else 0
            cost50 = df_sorted[df_sorted['weight'] >= 0.5]['price'].iloc[0] if len(df_sorted[df_sorted['weight'] >= 0.5]) > 0 else 0
            cost85 = df_sorted[df_sorted['weight'] >= 0.85]['price'].iloc[0] if len(df_sorted[df_sorted['weight'] >= 0.85]) > 0 else 0
            cost95 = df_sorted[df_sorted['weight'] >= 0.95]['price'].iloc[0] if len(df_sorted[df_sorted['weight'] >= 0.95]) > 0 else 0
        else:
            # 简单分位数计算
            cost5 = prices_series.quantile(0.05) if len(prices_series) > 0 else 0
            cost15 = prices_series.quantile(0.15) if len(prices_series) > 0 else 0
            cost50 = prices_series.quantile(0.5) if len(prices_series) > 0 else 0
            cost85 = prices_series.quantile(0.85) if len(prices_series) > 0 else 0
            cost95 = prices_series.quantile(0.95) if len(prices_series) > 0 else 0
        
        return {
            'cost5': float(cost5),
            'cost15': float(cost15),
            'cost50': float(cost50),
            'cost85': float(cost85),
            'cost95': float(cost95)
        }


class LimitUpPredictor:
    """涨停预测分析器：分析股票的涨停潜力"""
    
    def __init__(self, config=None):
        """
        初始化涨停预测分析器
        
        Args:
            config: 配置字典，包含各种阈值参数
        """
        self.config = config or {
            # 涨幅相关
            'min_change_pct': 3.0,      # 最低涨幅（%），有上涨空间
            'max_change_pct': 8.0,      # 最高涨幅（%），未涨停
            'ideal_change_pct': (4.0, 7.0),  # 理想涨幅区间
            
            # 量价相关
            'min_volume_ratio': 1.5,    # 最低量比
            'ideal_volume_ratio': (2.0, 5.0),  # 理想量比区间
            
            # 换手率相关（需要从数据库获取）
            'min_turnover_rate': 2.0,   # 最低换手率（%）
            'max_turnover_rate': 10.0,  # 最高换手率（%）
            'ideal_turnover_rate': (3.0, 8.0),  # 理想换手率区间
            
            # 市值相关（需要从数据库获取，单位：亿元）
            'min_market_cap': 10.0,     # 最低流通市值
            'max_market_cap': 100.0,    # 最高流通市值
            'ideal_market_cap': (20.0, 80.0),  # 理想市值区间
            
            # 技术形态
            'min_ma_slope': 0.1,        # 均线斜率最小值（%）
            'require_ma_bull': True,    # 是否要求多头排列
            
            # 涨停历史
            'check_limit_up_history': True,  # 是否检查涨停历史
            'limit_up_history_days': 30,     # 检查最近N天
            'min_limit_up_count': 1,         # 至少N次涨停
            
            # 评分权重
            'weights': {
                'change_pct': 3,        # 涨幅权重
                'volume_ratio': 3,      # 量比权重
                'turnover_rate': 2,     # 换手率权重
                'market_cap': 2,        # 市值权重
                'ma_trend': 2,          # 均线趋势权重
                'limit_up_history': 2,  # 涨停历史权重
                'volume_price_match': 2 # 量价配合权重
            },
            
            # 判断阈值
            'min_total_score': 8        # 最低总分（满分约20分）
        }
    
    def predict_limit_up_potential(self, closes, volumes, opens=None, highs=None, 
                                   change_pct=None, turnover_rate=None, 
                                   market_cap=None, limit_up_history=None):
        """
        预测股票的涨停潜力
        
        Args:
            closes: 收盘价序列
            volumes: 成交量序列
            opens: 开盘价序列（可选）
            highs: 最高价序列（可选）
            change_pct: 当前涨幅（%），如果为None则从closes计算
            turnover_rate: 换手率（%），如果为None则无法评分
            market_cap: 流通市值（亿元），如果为None则无法评分
            limit_up_history: 涨停历史信息，格式：{'count': int, 'recent_days': int}
            
        Returns:
            {
                'potential_score': float,  # 涨停潜力评分（0-100）
                'total_score': float,      # 总分
                'max_score': float,        # 满分
                'confidence': float,       # 置信度（0-1）
                'is_high_potential': bool, # 是否高潜力
                'reasons': list,           # 原因列表
                'indicators': dict,        # 详细指标
                'suggestions': list        # 建议列表
            }
        """
        if len(closes) < 30 or len(volumes) < 30:
            return {
                'potential_score': 0,
                'total_score': 0,
                'max_score': 0,
                'confidence': 0,
                'is_high_potential': False,
                'reasons': ['数据不足'],
                'indicators': {},
                'suggestions': []
            }
        
        config = self.config
        weights = config['weights']
        score = 0
        max_score = 0
        reasons = []
        indicators = {}
        suggestions = []
        
        # 1. 涨幅评分
        if change_pct is None and len(closes) >= 2:
            change_pct = ((closes[-1] - closes[-2]) / closes[-2]) * 100
        
        if change_pct is not None:
            max_score += weights['change_pct'] * 10
            if config['ideal_change_pct'][0] <= change_pct <= config['ideal_change_pct'][1]:
                score += weights['change_pct'] * 10
                reasons.append(f"涨幅适中({change_pct:.2f}%)，有上涨空间")
            elif config['min_change_pct'] <= change_pct < config['ideal_change_pct'][0]:
                score += weights['change_pct'] * 7
                reasons.append(f"涨幅偏低({change_pct:.2f}%)，但仍有空间")
            elif config['ideal_change_pct'][1] < change_pct <= config['max_change_pct']:
                score += weights['change_pct'] * 8
                reasons.append(f"涨幅较高({change_pct:.2f}%)，接近涨停")
            elif change_pct < config['min_change_pct']:
                score += weights['change_pct'] * 3
                reasons.append(f"涨幅偏低({change_pct:.2f}%)")
                suggestions.append("涨幅偏低，可能上涨动力不足")
            else:
                reasons.append(f"涨幅过高({change_pct:.2f}%)，可能已接近涨停")
                suggestions.append("涨幅已较高，注意风险")
            
            indicators['change_pct'] = change_pct
        
        # 2. 量比评分
        if len(volumes) >= 37:
            # 计算37天平均成交量
            avg_volume_37 = sum(volumes[-37:-1]) / 36 if len(volumes) > 1 else volumes[-1]
            volume_ratio = volumes[-1] / avg_volume_37 if avg_volume_37 > 0 else 1.0
            
            max_score += weights['volume_ratio'] * 10
            if config['ideal_volume_ratio'][0] <= volume_ratio <= config['ideal_volume_ratio'][1]:
                score += weights['volume_ratio'] * 10
                reasons.append(f"量比理想({volume_ratio:.2f}倍)，资金关注度高")
            elif volume_ratio >= config['min_volume_ratio']:
                if volume_ratio < config['ideal_volume_ratio'][0]:
                    score += weights['volume_ratio'] * 7
                    reasons.append(f"量比适中({volume_ratio:.2f}倍)")
                else:
                    score += weights['volume_ratio'] * 8
                    reasons.append(f"量比较高({volume_ratio:.2f}倍)，资金活跃")
            else:
                score += weights['volume_ratio'] * 3
                reasons.append(f"量比偏低({volume_ratio:.2f}倍)")
                suggestions.append("量比偏低，可能资金关注度不够")
            
            indicators['volume_ratio'] = volume_ratio
        
        # 3. 换手率评分（需要外部提供）
        if turnover_rate is not None:
            max_score += weights['turnover_rate'] * 10
            if config['ideal_turnover_rate'][0] <= turnover_rate <= config['ideal_turnover_rate'][1]:
                score += weights['turnover_rate'] * 10
                reasons.append(f"换手率理想({turnover_rate:.2f}%)，流动性好")
            elif config['min_turnover_rate'] <= turnover_rate < config['ideal_turnover_rate'][0]:
                score += weights['turnover_rate'] * 7
                reasons.append(f"换手率适中({turnover_rate:.2f}%)")
            elif config['ideal_turnover_rate'][1] < turnover_rate <= config['max_turnover_rate']:
                score += weights['turnover_rate'] * 8
                reasons.append(f"换手率较高({turnover_rate:.2f}%)，交易活跃")
            elif turnover_rate < config['min_turnover_rate']:
                score += weights['turnover_rate'] * 3
                reasons.append(f"换手率偏低({turnover_rate:.2f}%)")
                suggestions.append("换手率偏低，可能关注度不够")
            else:
                score += weights['turnover_rate'] * 2
                reasons.append(f"换手率过高({turnover_rate:.2f}%)，注意风险")
                suggestions.append("换手率过高，可能存在出货风险")
            
            indicators['turnover_rate'] = turnover_rate
        else:
            max_score += weights['turnover_rate'] * 10
            suggestions.append("缺少换手率数据，无法完整评估")
        
        # 4. 市值评分（需要外部提供）
        if market_cap is not None:
            max_score += weights['market_cap'] * 10
            if config['ideal_market_cap'][0] <= market_cap <= config['ideal_market_cap'][1]:
                score += weights['market_cap'] * 10
                reasons.append(f"市值适中({market_cap:.2f}亿元)，易于拉升")
            elif config['min_market_cap'] <= market_cap < config['ideal_market_cap'][0]:
                score += weights['market_cap'] * 8
                reasons.append(f"市值较小({market_cap:.2f}亿元)，易于拉升")
            elif config['ideal_market_cap'][1] < market_cap <= config['max_market_cap']:
                score += weights['market_cap'] * 7
                reasons.append(f"市值较大({market_cap:.2f}亿元)，需要更多资金")
            else:
                score += weights['market_cap'] * 3
                if market_cap < config['min_market_cap']:
                    reasons.append(f"市值过小({market_cap:.2f}亿元)，可能流动性差")
                else:
                    reasons.append(f"市值过大({market_cap:.2f}亿元)，不易涨停")
                suggestions.append("市值不在理想区间，涨停难度较大")
            
            indicators['market_cap'] = market_cap
        else:
            max_score += weights['market_cap'] * 10
            suggestions.append("缺少市值数据，无法完整评估")
        
        # 5. 均线趋势评分
        if len(closes) >= 30:
            # 计算均线
            ma5 = sum(closes[-5:]) / 5
            ma10 = sum(closes[-10:]) / 10
            ma20 = sum(closes[-20:]) / 20 if len(closes) >= 20 else ma10
            ma30 = sum(closes[-30:]) / 30
            
            # 检查多头排列
            is_bull = ma5 > ma10 > ma20 > ma30
            # 计算均线斜率
            ma5_slope = ((ma5 - sum(closes[-6:-1]) / 5) / (sum(closes[-6:-1]) / 5)) * 100 if len(closes) >= 6 else 0
            
            max_score += weights['ma_trend'] * 10
            if is_bull and ma5_slope > config['min_ma_slope']:
                score += weights['ma_trend'] * 10
                reasons.append("多头排列，均线向上，技术形态好")
            elif is_bull:
                score += weights['ma_trend'] * 7
                reasons.append("多头排列，但均线斜率较小")
            elif ma5 > ma10:
                score += weights['ma_trend'] * 5
                reasons.append("短期均线向上，但未形成多头排列")
            else:
                score += weights['ma_trend'] * 2
                reasons.append("均线形态不佳")
                suggestions.append("均线形态不佳，可能影响涨停概率")
            
            indicators['ma_trend'] = {
                'is_bull': is_bull,
                'ma5_slope': ma5_slope,
                'ma5': ma5,
                'ma10': ma10,
                'ma20': ma20,
                'ma30': ma30
            }
        
        # 6. 涨停历史评分
        if limit_up_history and limit_up_history.get('count', 0) > 0:
            max_score += weights['limit_up_history'] * 10
            count = limit_up_history['count']
            if count >= 3:
                score += weights['limit_up_history'] * 10
                reasons.append(f"近期有{count}次涨停，股性活跃")
            elif count >= 2:
                score += weights['limit_up_history'] * 8
                reasons.append(f"近期有{count}次涨停，股性较活跃")
            else:
                score += weights['limit_up_history'] * 6
                reasons.append(f"近期有{count}次涨停")
            
            indicators['limit_up_history'] = limit_up_history
        else:
            max_score += weights['limit_up_history'] * 10
            if config['check_limit_up_history']:
                suggestions.append("近期无涨停历史，股性可能不够活跃")
        
        # 7. 量价配合评分
        if opens is not None and len(opens) >= 5 and len(closes) >= 5:
            # 检查最近5天的量价配合
            up_volume_days = 0
            down_volume_days = 0
            
            for i in range(-5, 0):
                if i >= -len(closes) + 1:
                    idx = len(closes) + i
                    prev_idx = idx - 1
                    if prev_idx >= 0:
                        price_change = closes[idx] - closes[prev_idx]
                        volume_change = volumes[idx] - volumes[prev_idx] if idx < len(volumes) else 0
                        
                        if price_change > 0 and volume_change > 0:
                            up_volume_days += 1
                        elif price_change < 0 and volume_change < 0:
                            down_volume_days += 1
            
            max_score += weights['volume_price_match'] * 10
            if up_volume_days >= 3:
                score += weights['volume_price_match'] * 10
                reasons.append(f"量价配合好，{up_volume_days}天上涨放量")
            elif up_volume_days >= 2:
                score += weights['volume_price_match'] * 7
                reasons.append(f"量价配合较好，{up_volume_days}天上涨放量")
            else:
                score += weights['volume_price_match'] * 4
                reasons.append("量价配合一般")
                suggestions.append("量价配合不够理想，可能影响涨停概率")
            
            indicators['volume_price_match'] = {
                'up_volume_days': up_volume_days,
                'down_volume_days': down_volume_days
            }
        
        # 计算潜力评分和置信度
        potential_score = (score / max_score * 100) if max_score > 0 else 0
        confidence = min(score / config['min_total_score'], 1.0) if config['min_total_score'] > 0 else 0
        is_high_potential = score >= config['min_total_score']
        
        return {
            'potential_score': potential_score,
            'total_score': score,
            'max_score': max_score,
            'confidence': confidence,
            'is_high_potential': is_high_potential,
            'reasons': reasons,
            'indicators': indicators,
            'suggestions': suggestions
        }
    
    def calculate_chip_levels(self, price_data, volumes=None):
        """计算筹码分位线
        
        Args:
            price_data: 价格数据（收盘价或最高价最低价平均）
            volumes: 成交量数据（可选，用于加权计算）
            
        Returns:
            筹码分位线字典
        """
        if not price_data:
            return {
                'cost5': 0,
                'cost15': 0,
                'cost50': 0,
                'cost85': 0,
                'cost95': 0
            }
        
        # 使用pandas计算分位数
        prices_series = pd.Series(price_data)
        
        # 如果提供了成交量，使用成交量加权计算
        if volumes and len(volumes) == len(price_data):
            # 创建DataFrame
            df = pd.DataFrame({
                'price': prices_series,
                'volume': volumes
            })
            
            # 排序
            df_sorted = df.sort_values('price')
            
            # 计算累计成交量权重
            df_sorted['cum_volume'] = df_sorted['volume'].cumsum()
            total_volume = df_sorted['volume'].sum()
            df_sorted['weight'] = df_sorted['cum_volume'] / total_volume
            
            # 计算分位线
            cost5 = df_sorted[df_sorted['weight'] >= 0.05]['price'].iloc[0] if len(df_sorted[df_sorted['weight'] >= 0.05]) > 0 else 0
            cost15 = df_sorted[df_sorted['weight'] >= 0.15]['price'].iloc[0] if len(df_sorted[df_sorted['weight'] >= 0.15]) > 0 else 0
            cost50 = df_sorted[df_sorted['weight'] >= 0.5]['price'].iloc[0] if len(df_sorted[df_sorted['weight'] >= 0.5]) > 0 else 0
            cost85 = df_sorted[df_sorted['weight'] >= 0.85]['price'].iloc[0] if len(df_sorted[df_sorted['weight'] >= 0.85]) > 0 else 0
            cost95 = df_sorted[df_sorted['weight'] >= 0.95]['price'].iloc[0] if len(df_sorted[df_sorted['weight'] >= 0.95]) > 0 else 0
        else:
            # 简单分位数计算
            cost5 = prices_series.quantile(0.05) if len(prices_series) > 0 else 0
            cost15 = prices_series.quantile(0.15) if len(prices_series) > 0 else 0
            cost50 = prices_series.quantile(0.5) if len(prices_series) > 0 else 0
            cost85 = prices_series.quantile(0.85) if len(prices_series) > 0 else 0
            cost95 = prices_series.quantile(0.95) if len(prices_series) > 0 else 0
        
        return {
            'cost5': float(cost5),
            'cost15': float(cost15),
            'cost50': float(cost50),
            'cost85': float(cost85),
            'cost95': float(cost95)
        }

class TechnicalIndicatorCalculator:
    """技术指标计算器 - 统一入口"""
    
    def __init__(self):
        self.ma_analyzer = MAConvergenceAnalyzer()
        self.volume_analyzer = VolumeAnalyzer(surge_threshold=1.5)  # 按需求设置为1.5倍
        self.strategy1_analyzer = Strategy1Analyzer(surge_threshold=1.5)
        self.strategy2_analyzer = Strategy2Analyzer(surge_threshold=1.5)
        self.strategy3_analyzer = Strategy3Analyzer()
        self.sell_strategy_analyzer = SellStrategyAnalyzer()
        self.buy_timing_analyzer = BuyTimingAnalyzer()
        self.trend_analyzer = TrendAnalyzer()
        self.price_volume_analyzer = PriceVolumeAnalyzer()
        self.chip_analyzer = ChipDistributionAnalyzer()
        self.technical_indicator_analyzer = TechnicalIndicatorAnalyzer()
    
    def calculate_all_indicators(self, stock_data):
        """
        计算所有技术指标
        
        Args:
            stock_data: 股票数据字典，包含closes, volumes, opens, highs, lows等
            
        Returns:
            所有技术指标结果
        """
        closes = stock_data.get('closes', [])
        volumes = stock_data.get('volumes', [])
        opens = stock_data.get('opens', [])
        highs = stock_data.get('highs', [])
        lows = stock_data.get('lows', [])
        
        if len(closes) < 30 or len(volumes) < 37:
            return {
                'error': '数据不足，需要至少30天价格数据和37天成交量数据'
            }
        
        # 均线粘合分析
        ma_convergence = self.ma_analyzer.get_convergence_combinations(closes)
        
        # 成交量分析
        volume_analysis = self.volume_analyzer.analyze_volume_pattern(volumes, closes)
        
        # 趋势分析 - 多头状态
        bull_trend_analysis = self.trend_analyzer.analyze_all_bull_trends(closes)
        
        # 均线交叉分析
        ma_crossover_analysis = self.price_volume_analyzer.analyze_ma_crossover(closes)
        
        # 量价颜色分析
        if len(opens) > 0 and len(closes) > 0:
            v37 = self.volume_analyzer.calculate_v37(volumes)
            volume_color_analysis = self.price_volume_analyzer.analyze_volume_color(
                volumes[-1] if volumes else 0, 
                v37, 
                closes[-1], 
                opens[-1]
            )
        else:
            volume_color_analysis = {'color_type': 'unknown', 'description': '数据不足'}
        
        # 筹码分布分析（使用最近一段时间的数据）
        recent_period = min(60, len(closes))  # 使用最近60天数据或全部数据
        chip_levels = self.chip_analyzer.calculate_chip_levels(
            closes[-recent_period:], 
            volumes[-recent_period:] if len(volumes) >= recent_period else None
        )
        
        # 🆕 筹码集中度分析
        chip_concentration = self.chip_analyzer.calculate_chip_concentration(
            closes, 
            volumes, 
            period=recent_period
        )
        
        # 🆕 技术指标分析（MACD、KDJ、RSI）
        macd_analysis = self.technical_indicator_analyzer.calculate_macd(closes)
        kdj_analysis = None
        rsi_analysis = None
        if len(highs) > 0 and len(lows) > 0:
            kdj_analysis = self.technical_indicator_analyzer.calculate_kdj(closes, highs, lows)
        rsi_analysis = self.technical_indicator_analyzer.calculate_rsi(closes)
        
        # 策略1分析
        strategy1_analysis = self.strategy1_analyzer.analyze_strategy1(stock_data)
        
        # 策略2分析
        strategy2_analysis = self.strategy2_analyzer.analyze_strategy2(stock_data)
        
        # 🆕 买入时机分析
        buy_timing_analyzer = BuyTimingAnalyzer()
        buy_timing_analysis = buy_timing_analyzer.analyze_buy_timing(stock_data, intraday_data=None)
        
        # 策略3分析
        strategy3_analysis = self.strategy3_analyzer.analyze_strategy3(stock_data)
        
        # 计算涨幅图标记
        if len(closes) > 1:
            current_change_pct = ((closes[-1] - closes[-2]) / closes[-2]) * 100
            rise_marks = self._calculate_rise_marks(current_change_pct)
        else:
            rise_marks = {'lines': 0, 'description': '数据不足'}
        
        return {
            'ma_convergence': ma_convergence,
            'volume_analysis': volume_analysis,
            'bull_trend_analysis': bull_trend_analysis,
            'ma_crossover_analysis': ma_crossover_analysis,
            'volume_color_analysis': volume_color_analysis,
            'chip_levels': chip_levels,
            'chip_concentration': chip_concentration,  # 🆕 筹码集中度分析
            'macd_analysis': macd_analysis,  # 🆕 MACD分析
            'kdj_analysis': kdj_analysis,  # 🆕 KDJ分析
            'rsi_analysis': rsi_analysis,  # 🆕 RSI分析
            'buy_timing_analysis': buy_timing_analysis,  # 🆕 买入时机分析
            'rise_marks': rise_marks,
            'strategy1_analysis': strategy1_analysis,
            'strategy2_analysis': strategy2_analysis,
            'strategy3_analysis': strategy3_analysis,
            'timestamp': datetime.now().isoformat()
        }
    
    def _calculate_rise_marks(self, change_pct):
        """计算涨幅图标记线数量"""
        lines = 0
        description = ''
        
        if 5 < change_pct < 10:
            lines = 1
            description = '一根红线（5%-10%）'
        elif 10 <= change_pct < 20:
            lines = 2
            description = '两根红线（10%-20%）'
        elif 20 <= change_pct < 30:
            lines = 3
            description = '三根红线（20%-30%）'
        elif change_pct >= 30:
            lines = 4
            description = '四根红线（>=30%）'
        else:
            lines = 0
            description = '无标记线（<=5%）'
        
        return {'lines': lines, 'description': description}


# 测试函数
def test_technical_indicators():
    """测试技术指标计算"""
    # 模拟数据
    closes = [10.0 + i * 0.1 for i in range(100)]
    volumes = [1000000 + i * 10000 for i in range(100)]
    
    calculator = TechnicalIndicatorCalculator()
    stock_data = {
        'closes': closes,
        'volumes': volumes
    }
    
    results = calculator.calculate_all_indicators(stock_data)
    
    print("技术指标测试结果:")
    print(f"均线粘合分析: {results.get('ma_convergence', {})}")
    print(f"成交量分析: {results.get('volume_analysis', {})}")
    print(f"策略1分析: {results.get('strategy1_analysis', {})}")


if __name__ == "__main__":
    test_technical_indicators()