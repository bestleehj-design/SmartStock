# 🍎 Mac版股票分析系统

这是原Windows MFC股票分析程序的Mac版本，使用Python Flask + Web技术实现，提供相同的功能但更适合Mac环境。

## ✨ 功能特性

- 📊 **K线图表**：支持K线图和线图切换
- 📈 **技术指标**：MA5、MA10、MA20、MA30、MA60等移动平均线
- 🔍 **智能选股**：基于均线粘合、量价齐升等多维度选股策略
- 📱 **响应式设计**：支持桌面和移动设备
- 🔄 **实时更新**：自动刷新股票数据和连接状态
- 🎨 **现代化界面**：优化的用户体验和视觉设计

## 🚀 快速开始

### 1. 环境准备

确保已安装：
- Python 3.8+
- MySQL数据库（远程或本地）

### 2. 数据采集

首先运行数据采集脚本：

```bash
# 激活虚拟环境
source venv/bin/activate

# 运行数据采集
python new_get_all_stock.py
```

### 3. 启动Web应用

使用启动脚本（推荐）：

```bash
./start_web_app.sh
```

或手动启动：

```bash
# 激活虚拟环境
source venv/bin/activate

# 安装依赖
pip install -r requirements.txt

# 启动应用
cd web/app && python mac_web_app_simple.py
```

### 4. 访问应用

打开浏览器访问：
- 本地访问：http://localhost:5000
- 网络访问：http://0.0.0.0:5000

## 📁 项目结构

```
instock/
├── README_MAC.md             # Mac版使用说明
├── command_line_demo.py      # 命令行演示
├── command_line_screener.py  # 命令行选股器
├── new_get_all_stock.py      # 数据采集脚本
├── newstocklib.py            # 股票数据处理库
├── requirements.txt          # Python依赖
├── start_web_app.sh          # Web应用启动脚本
├── stock_ana_lib.py          # 股票分析库
├── technical_indicators.py   # 技术指标计算
└── web/                      # Web应用目录
    ├── app/
    │   └── mac_web_app_simple.py  # Web应用主程序
    ├── static/
    │   ├── css/              # 样式文件
    │   ├── images/           # 图片资源
    │   └── js/               # JavaScript脚本
    └── templates/
        ├── index.html        # 主页面模板
        └── index_simple.html # 简化页面模板
```

## 🔧 配置说明

### 数据库配置

在 `web/app/mac_web_app_simple.py` 中修改数据库连接配置：

```python
DB_CONFIG = {
    'host': '10.10.65.16',    # 数据库主机
    'port': 3306,              # 端口
    'user': 'root',           # 用户名
    'password': '123456',     # 密码
    'database': 'gp2'         # 数据库名
}
```

### 选股参数

在Web界面中可以设置：
- 最小涨幅：筛选涨幅下限
- 最大涨幅：筛选涨幅上限
- 技术指标：MA5、MA10、MA20等

## 🎯 使用说明

### 1. 查看股票列表
- 左侧显示所有股票
- 点击股票可查看详细信息

### 2. 选股功能
- 设置涨幅范围
- 点击"开始选股"按钮
- 查看符合条件的股票

### 3. 技术分析
- 选择股票后自动显示K线图
- 查看技术指标
- 支持K线图和线图切换

## 🔍 故障排除

### 数据库连接失败
1. 检查MySQL服务是否运行
2. 验证数据库连接配置
3. 确认网络连接正常

### 数据加载失败
1. 确保已执行数据采集脚本
2. 检查数据库表是否存在
3. 查看控制台错误信息

### Web服务启动失败
1. 检查端口5000是否被占用
2. 确认Python依赖已安装
3. 查看错误日志

## 🆚 与Windows版本对比

| 功能 | Windows MFC | Mac Web |
|------|-------------|--------|
| 数据采集 | ✅ | ✅ |
| K线图表 | ✅ | ✅ |
| 技术指标 | ✅ | ✅ (增强版) |
| 选股功能 | ✅ | ✅ |
| 界面美观 | ⭐⭐⭐ | ⭐⭐⭐⭐⭐ |
| 跨平台 | ❌ | ✅ |
| 移动支持 | ❌ | ✅ |
| 部署难度 | 中等 | 简单 |
| 双图表布局 | ❌ | ✅ |
| 均线趋势分析 | ❌ | ✅ |

## 📞 技术支持

如遇到问题，请检查：
1. Python版本是否兼容
2. 数据库连接是否正常
3. 依赖包是否完整安装
4. 防火墙设置是否正确

## 🔄 更新日志

- v2.0.0: 增强版，优化用户体验
  - 实现双区域图表布局（价格图+成交量图）
  - 添加MA5/MA10/MA20/MA30/MA60多均线显示
  - 实现均线趋势智能分析功能
  - 优化界面样式和交互体验
- v1.0.0: 初始版本，实现基本功能
  - 支持K线图表显示
  - 支持技术指标计算
  - 支持选股功能
  - 支持响应式设计
