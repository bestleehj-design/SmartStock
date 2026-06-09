#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试策略2的tushare热点板块获取功能
"""

import sys
import os

# 添加项目根目录到Python路径
project_root = os.path.abspath(os.path.dirname(__file__))
sys.path.insert(0, project_root)

try:
    from data.technical_indicators import HotSectorAnalyzer, Strategy2Analyzer
    print("✅ 成功导入技术指标模块")
except ImportError as e:
    print(f"❌ 导入失败: {e}")
    sys.exit(1)

def test_tushare_connection():
    """测试tushare连接"""
    print("\n" + "="*60)
    print("测试1: Tushare连接")
    print("="*60)
    
    try:
        analyzer = HotSectorAnalyzer()
        
        if not analyzer.tushare_available:
            print("❌ Tushare不可用，请检查tushare是否安装")
            return False
        
        if analyzer.pro is None:
            print("❌ Tushare API未初始化")
            return False
        
        print("✅ Tushare已安装并初始化")
        print(f"✅ 缓存功能: {'启用' if analyzer.enable_cache else '禁用'}")
        return True
        
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_ths_hot_api():
    """测试同花顺热榜API (方法1)"""
    print("\n" + "="*60)
    print("测试2: 同花顺热榜API (ths_hot) - 方法1")
    print("="*60)
    
    try:
        analyzer = HotSectorAnalyzer()
        
        if not analyzer.tushare_available or not analyzer.pro:
            print("❌ Tushare不可用")
            return False
        
        # 测试获取最近一天的数据
        from datetime import datetime, timedelta
        today = datetime.now()
        yesterday = today - timedelta(days=1)
        date_str = yesterday.strftime('%Y%m%d')
        
        print(f"📅 测试日期: {date_str}")
        print("📡 调用 ths_hot API...")
        
        df = analyzer.pro.ths_hot(
            start_date=date_str,
            end_date=date_str
        )
        
        if df is None:
            print("⚠️ API返回None（可能是非交易日）")
            # 尝试更早的日期
            for days_ago in range(2, 8):
                test_date = today - timedelta(days=days_ago)
                date_str = test_date.strftime('%Y%m%d')
                print(f"📅 尝试日期: {date_str}")
                df = analyzer.pro.ths_hot(start_date=date_str, end_date=date_str)
                if df is not None and not df.empty:
                    break
        
        if df is None:
            print("❌ 无法获取数据（可能所有测试日期都是非交易日）")
            return False
        
        if df.empty:
            print("⚠️ API返回空DataFrame")
            return False
        
        print(f"✅ 成功获取数据: {len(df)} 条记录")
        print(f"📊 数据列: {list(df.columns)}")
        print(f"📋 前5条数据:")
        print(df.head().to_string())
        
        # 检查是否有type列用于区分行业和概念
        if 'type' in df.columns:
            print(f"✅ 数据包含type列，可以区分行业和概念")
            print(f"   类型分布: {df['type'].value_counts().to_dict()}")
        else:
            print("⚠️ 数据不包含type列，可能需要其他方式区分行业和概念")
        
        return True
        
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_get_hot_sectors_from_tushare():
    """测试从tushare获取热点板块（方法1完整流程）"""
    print("\n" + "="*60)
    print("测试3: 从tushare获取热点板块（方法1完整流程）")
    print("="*60)
    
    try:
        analyzer = HotSectorAnalyzer()
        
        if not analyzer.tushare_available or not analyzer.pro:
            print("❌ Tushare不可用")
            return False
        
        print("📡 获取热点概念板块...")
        result_concept = analyzer.get_hot_concept_sectors(weeks=1)
        
        if 'error' in result_concept:
            print(f"❌ 获取概念板块失败: {result_concept['error']}")
        else:
            print(f"✅ 成功获取概念板块数据")
            print(f"   获取日期范围: {result_concept.get('start_date')} 至 {result_concept.get('end_date')}")
            print(f"   数据天数: {len(result_concept.get('hot_info', {}))}")
            print(f"   板块数量: {len(result_concept.get('latest_ranks', {}))}")
            top_concepts = result_concept.get('top_sectors', [])[:10]
            if top_concepts:
                print(f"   Top 10概念板块: {top_concepts}")
        
        print("\n📡 获取热点行业板块...")
        result_industry = analyzer.get_hot_industry_sectors(weeks=1)
        
        if 'error' in result_industry:
            print(f"❌ 获取行业板块失败: {result_industry['error']}")
        else:
            print(f"✅ 成功获取行业板块数据")
            print(f"   获取日期范围: {result_industry.get('start_date')} 至 {result_industry.get('end_date')}")
            print(f"   数据天数: {len(result_industry.get('hot_info', {}))}")
            print(f"   板块数量: {len(result_industry.get('latest_ranks', {}))}")
            top_industries = result_industry.get('top_sectors', [])[:10]
            if top_industries:
                print(f"   Top 10行业板块: {top_industries}")
        
        return 'error' not in result_concept or 'error' not in result_industry
        
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_ths_index_api():
    """测试同花顺板块指数列表API"""
    print("\n" + "="*60)
    print("测试4: 同花顺板块指数列表API (ths_index)")
    print("="*60)
    
    try:
        analyzer = HotSectorAnalyzer()
        
        if not analyzer.tushare_available or not analyzer.pro:
            print("❌ Tushare不可用")
            return False
        
        print("📡 获取概念板块列表...")
        concept_list = analyzer.pro.ths_index(exchange='A', type='N', fields='ts_code,name')
        
        if concept_list is None or concept_list.empty:
            print("❌ 无法获取概念板块列表")
            return False
        
        print(f"✅ 成功获取概念板块列表: {len(concept_list)} 个板块")
        print(f"📋 前5个板块:")
        print(concept_list.head().to_string())
        
        print("\n📡 获取行业板块列表...")
        industry_list = analyzer.pro.ths_index(exchange='A', type='I', fields='ts_code,name')
        
        if industry_list is None or industry_list.empty:
            print("❌ 无法获取行业板块列表")
            return False
        
        print(f"✅ 成功获取行业板块列表: {len(industry_list)} 个板块")
        print(f"📋 前5个板块:")
        print(industry_list.head().to_string())
        
        return True
        
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_ths_daily_api():
    """测试同花顺板块指数行情API (方法2)"""
    print("\n" + "="*60)
    print("测试5: 同花顺板块指数行情API (ths_daily) - 方法2")
    print("="*60)
    
    try:
        analyzer = HotSectorAnalyzer()
        
        if not analyzer.tushare_available or not analyzer.pro:
            print("❌ Tushare不可用")
            return False
        
        # 先获取一个板块代码
        print("📡 获取板块列表...")
        concept_list = analyzer.pro.ths_index(exchange='A', type='N', fields='ts_code,name')
        
        if concept_list is None or concept_list.empty:
            print("❌ 无法获取板块列表")
            return False
        
        test_code = concept_list.iloc[0]['ts_code']
        test_name = concept_list.iloc[0]['name']
        print(f"📊 测试板块: {test_code} ({test_name})")
        
        # 获取最近30天的数据
        from datetime import datetime, timedelta
        end_date = datetime.now().strftime('%Y%m%d')
        start_date = (datetime.now() - timedelta(days=60)).strftime('%Y%m%d')
        
        print(f"📅 日期范围: {start_date} 至 {end_date}")
        print("📡 调用 ths_daily API...")
        
        df = analyzer.pro.ths_daily(
            ts_code=test_code,
            start_date=start_date,
            end_date=end_date,
            fields='trade_date,close,open,high,low,vol,amount'
        )
        
        if df is None:
            print("❌ API返回None")
            return False
        
        if df.empty:
            print("⚠️ API返回空DataFrame")
            return False
        
        print(f"✅ 成功获取数据: {len(df)} 条记录")
        print(f"📊 数据列: {list(df.columns)}")
        print(f"📋 最新5条数据:")
        print(df.tail().to_string())
        
        return True
        
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_get_hot_sectors_from_index():
    """测试从指数行情获取热点板块（方法2完整流程）"""
    print("\n" + "="*60)
    print("测试6: 从指数行情获取热点板块（方法2完整流程）")
    print("="*60)
    
    try:
        analyzer = HotSectorAnalyzer()
        
        if not analyzer.tushare_available or not analyzer.pro:
            print("❌ Tushare不可用")
            return False
        
        print("📡 获取热门概念板块（从指数分析）...")
        result_concept = analyzer.get_hot_sectors_from_index_concept(days=30)
        
        if 'error' in result_concept:
            print(f"❌ 获取概念板块失败: {result_concept['error']}")
        else:
            hot_concepts = result_concept.get('hot_sectors', [])
            bottom_concepts = result_concept.get('bottom_rebound_sectors', [])
            print(f"✅ 成功分析概念板块")
            print(f"   热门板块数量: {len(hot_concepts)}")
            if hot_concepts:
                print(f"   热门板块示例: {hot_concepts[:3]}")
            print(f"   底部反弹板块数量: {len(bottom_concepts)}")
            if bottom_concepts:
                print(f"   底部反弹板块示例: {bottom_concepts[:3]}")
        
        print("\n📡 获取热门行业板块（从指数分析）...")
        result_industry = analyzer.get_hot_sectors_from_index_industry(days=30)
        
        if 'error' in result_industry:
            print(f"❌ 获取行业板块失败: {result_industry['error']}")
        else:
            hot_industries = result_industry.get('hot_sectors', [])
            bottom_industries = result_industry.get('bottom_rebound_sectors', [])
            print(f"✅ 成功分析行业板块")
            print(f"   热门板块数量: {len(hot_industries)}")
            if hot_industries:
                print(f"   热门板块示例: {hot_industries[:3]}")
            print(f"   底部反弹板块数量: {len(bottom_industries)}")
            if bottom_industries:
                print(f"   底部反弹板块示例: {bottom_industries[:3]}")
        
        return 'error' not in result_concept or 'error' not in result_industry
        
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_strategy2_combined():
    """测试策略2综合方法"""
    print("\n" + "="*60)
    print("测试7: 策略2综合方法（方法1 + 方法2）")
    print("="*60)
    
    try:
        analyzer = Strategy2Analyzer()
        
        print("📡 获取综合热点板块...")
        result = analyzer.get_hot_sectors_combined(weeks=1, days=30)
        
        print(f"✅ 策略2综合结果:")
        print(f"   方法1概念板块: {len(result.get('method1_concept', {}).get('top_sectors', []))} 个")
        print(f"   方法1行业板块: {len(result.get('method1_industry', {}).get('top_sectors', []))} 个")
        print(f"   方法2概念板块: {len(result.get('method2_concept', {}).get('hot_sectors', []))} 个热门, "
              f"{len(result.get('method2_concept', {}).get('bottom_rebound_sectors', []))} 个底部反弹")
        print(f"   方法2行业板块: {len(result.get('method2_industry', {}).get('hot_sectors', []))} 个热门, "
              f"{len(result.get('method2_industry', {}).get('bottom_rebound_sectors', []))} 个底部反弹")
        print(f"   综合热门概念: {len(result.get('combined_hot_concepts', []))} 个")
        print(f"   综合热门行业: {len(result.get('combined_hot_industries', []))} 个")
        
        if result.get('combined_hot_concepts'):
            print(f"   综合热门概念示例: {result['combined_hot_concepts'][:5]}")
        if result.get('combined_hot_industries'):
            print(f"   综合热门行业示例: {result['combined_hot_industries'][:5]}")
        
        return True
        
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """主测试函数"""
    print("="*60)
    print("策略2 Tushare热点板块获取功能测试")
    print("="*60)
    
    results = []
    
    # 运行所有测试
    results.append(("Tushare连接", test_tushare_connection()))
    results.append(("同花顺热榜API", test_ths_hot_api()))
    results.append(("获取热点板块（方法1）", test_get_hot_sectors_from_tushare()))
    results.append(("板块指数列表API", test_ths_index_api()))
    results.append(("板块指数行情API", test_ths_daily_api()))
    results.append(("获取热点板块（方法2）", test_get_hot_sectors_from_index()))
    results.append(("策略2综合方法", test_strategy2_combined()))
    
    # 输出总结
    print("\n" + "="*60)
    print("测试总结")
    print("="*60)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for name, result in results:
        status = "✅ 通过" if result else "❌ 失败"
        print(f"{status}: {name}")
    
    print(f"\n总计: {passed}/{total} 个测试通过")
    
    if passed == total:
        print("\n🎉 所有测试通过！策略2可以使用tushare获取热点板块。")
    else:
        print(f"\n⚠️ 有 {total - passed} 个测试失败，请检查上述错误信息。")

if __name__ == '__main__':
    main()

