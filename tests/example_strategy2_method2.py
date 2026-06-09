#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
策略2方法2使用示例
从同花顺板块指数行情中识别热门板块和底部企稳快速上升的板块
"""
from data.technical_indicators import HotSectorAnalyzer
from datetime import datetime, timedelta

def example_get_hot_sectors_from_index():
    """示例：获取热门板块（从指数行情分析）"""
    
    # 初始化分析器（启用缓存，默认开启）
    analyzer = HotSectorAnalyzer(enable_cache=True)
    
    # 如果需要禁用缓存，可以这样：
    # analyzer = HotSectorAnalyzer(enable_cache=False)
    
    # 如果需要自定义缓存目录，可以这样：
    # analyzer = HotSectorAnalyzer(enable_cache=True, cache_dir='.my_cache/sector_data')
    
    # 方法1：获取热门概念板块
    print("=" * 60)
    print("📊 分析热门概念板块（从指数行情）")
    print("=" * 60)
    
    result = analyzer.get_hot_sectors_from_index_concept(
        days=30,  # 分析最近30天
        min_rise_pct=5.0,  # 热门板块最小涨幅5%
        bottom_rebound_pct=10.0  # 底部企稳快速上升最小反弹10%
    )
    
    if 'error' in result:
        print(f"❌ 错误: {result['error']}")
        return
    
    # 显示热门板块
    print(f"\n🔥 热门概念板块 (共 {len(result['hot_sectors'])} 个):")
    print("-" * 60)
    for i, sector in enumerate(result['hot_sectors'][:10], 1):  # 显示前10个
        print(f"{i}. {sector['name']} ({sector['code']})")
        print(f"   涨幅: 5日{sector['rise_5d']}% | 10日{sector['rise_10d']}% | 20日{sector['rise_20d']}%")
        print(f"   均线: MA5={sector['ma5']} | MA10={sector['ma10']} | MA30={sector['ma30']}")
        print(f"   均线多头: {'是' if sector['is_bull_ma'] else '否'} | 成交量比: {sector['volume_ratio']}")
        print(f"   综合评分: {sector['score']}")
        print()
    
    # 显示底部企稳快速上升板块
    print(f"\n📈 底部企稳快速上升概念板块 (共 {len(result['bottom_rebound_sectors'])} 个):")
    print("-" * 60)
    for i, sector in enumerate(result['bottom_rebound_sectors'][:10], 1):  # 显示前10个
        print(f"{i}. {sector['name']} ({sector['code']})")
        print(f"   反弹幅度: {sector['rebound_pct']}% | 距底部: {sector['days_from_bottom']}天")
        print(f"   涨幅: 5日{sector['rise_5d']}% | 10日{sector['rise_10d']}%")
        print(f"   均线斜率: MA5={sector['ma5_slope']}% | MA10={sector['ma10_slope']}%")
        print(f"   成交量比: {sector['volume_ratio']} | 综合评分: {sector['score']}")
        print()
    
    # 方法2：获取热门行业板块
    print("\n" + "=" * 60)
    print("📊 分析热门行业板块（从指数行情）")
    print("=" * 60)
    
    result_industry = analyzer.get_hot_sectors_from_index_industry(
        days=30,
        min_rise_pct=5.0,
        bottom_rebound_pct=10.0
    )
    
    if 'error' in result_industry:
        print(f"❌ 错误: {result_industry['error']}")
        return
    
    print(f"\n🔥 热门行业板块 (共 {len(result_industry['hot_sectors'])} 个):")
    print("-" * 60)
    for i, sector in enumerate(result_industry['hot_sectors'][:10], 1):
        print(f"{i}. {sector['name']} ({sector['code']})")
        print(f"   涨幅: 5日{sector['rise_5d']}% | 10日{sector['rise_10d']}%")
        print(f"   综合评分: {sector['score']}")
        print()
    
    print(f"\n📈 底部企稳快速上升行业板块 (共 {len(result_industry['bottom_rebound_sectors'])} 个):")
    print("-" * 60)
    for i, sector in enumerate(result_industry['bottom_rebound_sectors'][:10], 1):
        print(f"{i}. {sector['name']} ({sector['code']})")
        print(f"   反弹幅度: {sector['rebound_pct']}% | 综合评分: {sector['score']}")
        print()


def example_custom_parameters():
    """示例：使用自定义参数"""
    
    analyzer = HotSectorAnalyzer()
    
    # 自定义日期范围
    end_date = datetime.now().strftime('%Y%m%d')
    start_date = (datetime.now() - timedelta(days=60)).strftime('%Y%m%d')
    
    print("=" * 60)
    print("📊 自定义参数分析")
    print("=" * 60)
    print(f"日期范围: {start_date} 至 {end_date}")
    print(f"热门板块最小涨幅: 8%")
    print(f"底部企稳最小反弹: 15%")
    print()
    
    result = analyzer.get_hot_sectors_from_index(
        start_date=start_date,
        end_date=end_date,
        days=60,
        sector_type='concept',
        min_rise_pct=8.0,  # 更严格的涨幅要求
        bottom_rebound_pct=15.0  # 更严格的反弹要求
    )
    
    if 'error' in result:
        print(f"❌ 错误: {result['error']}")
        return
    
    print(f"热门板块: {len(result['hot_sectors'])} 个")
    print(f"底部企稳板块: {len(result['bottom_rebound_sectors'])} 个")
    print(f"总分析板块数: {len(result['all_sectors_analysis'])} 个")


def example_cache_management():
    """示例：缓存管理"""
    from data.technical_indicators import SectorDataCache
    
    # 创建缓存实例
    cache = SectorDataCache()
    
    # 清理板块列表缓存
    print("清理板块列表缓存...")
    cache.clear_cache('sector_list')
    
    # 清理指数数据缓存
    print("清理指数数据缓存...")
    cache.clear_cache('index_data')
    
    # 清理所有缓存
    print("清理所有缓存...")
    cache.clear_cache()


if __name__ == '__main__':
    print("策略2方法2 - 从板块指数行情识别热点板块")
    print("=" * 60)
    print("💡 提示：缓存功能已启用，首次运行会从API获取数据并缓存")
    print("   后续运行会优先使用缓存，大幅减少API调用")
    print("=" * 60)
    print()
    
    # 运行示例
    try:
        example_get_hot_sectors_from_index()
        print("\n")
        example_custom_parameters()
        print("\n")
        # 取消注释以测试缓存管理
        # example_cache_management()
    except Exception as e:
        print(f"❌ 运行出错: {e}")
        import traceback
        traceback.print_exc()

