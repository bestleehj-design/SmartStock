# -*- coding: utf-8 -*-
"""
数据库和API配置文件
统一管理数据库连接配置和第三方API密钥

使用说明：
1. 此配置文件被以下模块使用：
   - newstocklib.py: 数据库连接初始化
   - new_get_all_stock.py: 数据库连接和tushare token
   - web/app/mac_web_app_simple.py: 数据库连接

2. 如果web应用需要不同的数据库host（如localhost），可以在mac_web_app_simple.py中覆盖：
   DB_CONFIG['host'] = 'localhost'

3. 建议将此文件添加到.gitignore中，避免将敏感信息提交到版本控制系统
"""

# 数据库配置
# 注意：根据实际环境修改以下配置
DB_CONFIG = {
    'host': 'localhost',      # 数据库主机地址
    'port': 3306,                # 数据库端口
    'user': 'root',              # 数据库用户名
    'password': '12345678',        # 数据库密码
    'database': 'gp2',           # 数据库名
    'charset': 'utf8mb4',        # 字符集
    'collation': 'utf8mb4_unicode_ci',  # 排序规则
    'autocommit': True           # 自动提交
}

# Tushare API配置
TUSHARE_TOKEN = 'a054107022932e4f13f532718167561fd11765012b25472b351a81d7'

