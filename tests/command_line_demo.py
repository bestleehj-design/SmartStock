#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
命令行股票筛选器使用示例和测试脚本
"""

import sys
import os
from screener.command_line_screener import CommandLineScreener
from web_command_line_integration import WebCommandLineIntegration, create_command_line_web_app
from flask import Flask

def test_command_line_screener():
    """测试命令行筛选器"""
    print("🧪 测试命令行筛选器...")
    
    screener = CommandLineScreener()
    
    if not screener.connect_database():
        print("❌ 数据库连接失败")
        return False
    
    try:
        # 测试1: 基础涨幅筛选
        print("\n📊 测试1: 基础涨幅筛选")
        screener.start_index = 0
        screener.predays = 5
        screener.add_condition('a', 1, 3, 0.05, 0.15)  # 1-3天涨幅在5%-15%之间
        
        # 测试单只股票
        test_code = "000001"  # 平安银行
        result = screener.check_stock(test_code)
        status = '✅ 通过' if result else '❌ 不通过'
        print(f"股票 {test_code} 筛选结果: {status}")
        
        # 测试2: 均线粘合筛选
        print("\n📊 测试2: 均线粘合筛选")
        screener.conditions = []  # 清空条件
        screener.add_condition('i', 1, 5)  # 5-10日线粘合
        
        result = screener.check_stock(test_code)
        status = '✅ 通过' if result else '❌ 不通过'
        print(f"股票 {test_code} 均线粘合筛选结果: {status}")
        
        # 测试3: 5上穿10条件
        print("\n📊 测试3: 5上穿10条件")
        screener.conditions = []
        screener.add_condition('v', 1, 3)  # 1-3天满足5上穿10
        
        result = screener.check_stock(test_code)
        status = '✅ 通过' if result else '❌ 不通过'
        print(f"股票 {test_code} 5上穿10筛选结果: {status}")
        
        print("\n✅ 命令行筛选器测试完成")
        return True
        
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        return False
    
    finally:
        screener.close_database()

def test_web_integration():
    """测试Web集成"""
    print("\n🌐 测试Web集成...")
    
    try:
        app = create_command_line_web_app()
        
        # 测试命令行解析
        with app.test_client() as client:
            # 测试预设策略接口
            response = client.get('/api/command-line-presets')
            if response.status_code == 200:
                data = response.get_json()
                print(f"✅ 预设策略接口正常，共 {len(data['presets'])} 个预设")
            else:
                print("❌ 预设策略接口失败")
                return False
            
            # 测试帮助接口
            response = client.get('/api/command-line-help')
            if response.status_code == 200:
                data = response.get_json()
                print(f"✅ 帮助接口正常，共 {len(data['help'])} 个帮助分类")
            else:
                print("❌ 帮助接口失败")
                return False
            
            # 测试命令行筛选接口
            test_command = "-D 0 5 -a 1 3 0.05 0.15"
            response = client.post('/api/command-line-screen', 
                                 json={'command_args': test_command})
            if response.status_code == 200:
                data = response.get_json()
                if data['success']:
                    print(f"✅ 命令行筛选接口正常，找到 {data['result']['count']} 只股票")
                else:
                    print(f"❌ 命令行筛选失败: {data['error']}")
                    return False
            else:
                print("❌ 命令行筛选接口失败")
                return False
        
        print("✅ Web集成测试完成")
        return True
        
    except Exception as e:
        print(f"❌ Web集成测试失败: {e}")
        return False

def demo_command_line_usage():
    """演示命令行使用方法"""
    print("\n📚 命令行使用演示...")
    
    examples = [
        {
            'name': '5上穿10 + 日线粘合 + 放量',
            'command': '-D 0 10 -v 1 0 -a 1 5 0.08 0.3 -d 3 10 1.5 10 -h 1 10 1',
            'description': '寻找均线突破且量能配合的股票'
        },
        {
            'name': '连续多天放量',
            'command': '-D 0 5 -d 3 5 2 10',
            'description': '寻找量能持续放大的股票'
        },
        {
            'name': '多周期粘合 + 5上穿10',
            'command': '-D 0 10 -q 1 10 -r 1 10 -s 1 10 -v 0 0',
            'description': '寻找多周期均线共振的股票'
        },
        {
            'name': '放量 + 涨幅组合',
            'command': '-D 0 10 -q 1 10 -d 5 10 1.5 10 -a 2 10 0.04 0.3',
            'description': '寻找放量上涨的股票'
        },
        {
            'name': '反包企稳模式',
            'command': '-D 0 60 -a 2 20 0.09 0.3',
            'description': '寻找超跌反弹的股票'
        }
    ]
    
    for i, example in enumerate(examples, 1):
        print(f"\n{i}. {example['name']}")
        print(f"   描述: {example['description']}")
        print(f"   命令: {example['command']}")
    
    print("\n💡 使用提示:")
    print("1. 使用 -D 参数设置时间窗口")
    print("2. 多个条件可以组合使用")
    print("3. 条件之间是'与'的关系")
    print("4. 参数范围: a1-a2表示天数范围，r1-r2表示数值范围")

def run_web_app():
    """运行Web应用"""
    print("\n🚀 启动Web应用...")
    print("访问地址: http://localhost:5001/command-line")
    
    app = create_command_line_web_app()
    app.run(debug=True, host='0.0.0.0', port=5001)

def main():
    """主函数"""
    print("🎯 命令行股票筛选器 - 测试和演示")
    print("=" * 50)
    
    if len(sys.argv) > 1:
        command = sys.argv[1]
        
        if command == 'test':
            # 运行测试
            success = test_command_line_screener()
            if success:
                test_web_integration()
        
        elif command == 'demo':
            # 演示使用方法
            demo_command_line_usage()
        
        elif command == 'web':
            # 启动Web应用
            run_web_app()
        
        elif command == 'help':
            # 显示帮助
            print_help()
        
        else:
            print(f"❌ 未知命令: {command}")
            print_help()
    
    else:
        # 默认运行测试
        print("🔍 运行默认测试...")
        success = test_command_line_screener()
        if success:
            test_web_integration()
        
        print("\n📚 使用演示:")
        demo_command_line_usage()
        
        print("\n💻 可用命令:")
        print("  python command_line_demo.py test   - 运行测试")
        print("  python command_line_demo.py demo   - 演示使用方法")
        print("  python command_line_demo.py web    - 启动Web应用")
        print("  python command_line_demo.py help   - 显示帮助")

def print_help():
    """显示帮助信息"""
    print("""
🎯 命令行股票筛选器使用帮助

📋 基本用法:
  python command_line_demo.py [command]

🔧 可用命令:
  test    - 运行功能测试
  demo    - 演示使用方法
  web     - 启动Web应用
  help    - 显示此帮助信息

🌐 Web应用:
  启动后访问: http://localhost:5001/command-line
  提供图形化界面进行命令行筛选

📚 命令行参数说明:
  -D start_index predays  - 设置时间窗口
  -a a1 a2 r1 r2         - 涨幅条件
  -b r1 r2               - 价格区间条件
  -c c1 c2 r1 r2         - 换手率条件
  -d d1 d2 r1 r2         - 相对换手率条件
  -e a1 a2 a3            - 短线多头条件
  -f a1 a2 a3            - 中线多头条件
  -g a1 a2 a3            - 长线多头条件
  -h a1 a2 a3            - 5线开花条件
  -i a1 a2               - 5-10日线粘合
  -j a1 a2               - 5-10-20日线粘合
  -k a1 a2               - 5-10-20-30日线粘合
  -m a1 a2               - 5-10-20-30-60日线粘合
  -n a1 a2               - 10-20-30-60-120日线粘合
  -o a1 a2               - 10-20-30-60-120-250日线粘合
  -p a1 a2               - 10-20-30-60-120-250-500日线粘合
  -q a1 a2               - 日线粘合5-10-30
  -r a1 a2               - 周线粘合25-50-150
  -s a1 a2               - 月线粘合100-200-600
  -t a1 a2 r1 r2         - 创新低条件
  -u r1 r2               - 量能对比条件
  -v a1 a2               - 5上穿10条件
  -w a1 a2 a3            - 收盘价在均线之上条件

💡 示例:
  -D 0 10 -v 1 0 -a 1 5 0.08 0.3 -d 3 10 1.5 10 -h 1 10 1
  -D 0 5 -d 3 5 2 10
  -D 0 10 -q 1 10 -r 1 10 -s 1 10 -v 0 0
""")

if __name__ == '__main__':
    main()
