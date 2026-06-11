# -*- coding: utf-8 -*-
"""
SmartStock 配置文件模板
复制此文件为 config.py 并填入你的实际配置

使用方法:
  cp src/data/config.example.py src/data/config.py
  # 然后修改 config.py 中的密码和Token
"""

# 数据库配置
DB_CONFIG = {
    'host': 'localhost',
    'port': 3306,
    'user': 'root',
    'password': 'your_password_here',   # <<< 改成你的密码
    'database': 'gp2',
    'charset': 'utf8mb4',
    'collation': 'utf8mb4_unicode_ci',
    'autocommit': True
}

# Tushare API Token (从 https://tushare.pro 获取)
TUSHARE_TOKEN = 'your_tushare_token_here'   # <<< 改成你的Token
