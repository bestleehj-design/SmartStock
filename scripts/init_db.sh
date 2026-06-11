#!/bin/bash
# ============================================================
# SmartStock 数据库初始化脚本
# 功能: 创建数据库 + 建表 (不包含数据拉取)
# 用法: bash scripts/init_db.sh
# ============================================================

set -e

echo "=============================================="
echo "  SmartStock 数据库初始化"
echo "=============================================="

# 1. 检查 MySQL 是否运行
if ! command -v mysql &> /dev/null; then
    echo "❌ 未找到 mysql 命令，请先安装 MySQL"
    exit 1
fi

if ! mysqladmin ping -u root --silent 2>/dev/null; then
    echo "⚠️  MySQL 可能未运行，尝试连接..."
fi

# 2. 读取密码
read -sp "请输入 MySQL root 密码: " MYSQL_PWD
echo ""

# 3. 测试连接
if ! mysql -u root -p"$MYSQL_PWD" -e "SELECT 1" --silent 2>/dev/null; then
    echo "❌ MySQL 连接失败，请检查密码"
    exit 1
fi
echo "✅ MySQL 连接成功"

# 4. 创建数据库
echo "📦 创建数据库 gp2..."
mysql -u root -p"$MYSQL_PWD" -e "CREATE DATABASE IF NOT EXISTS gp2 DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"

# 5. 导入建表语句
echo "📋 导入表结构 (sql/schema.sql)..."
mysql -u root -p"$MYSQL_PWD" gp2 < sql/schema.sql
echo "✅ 19 张表创建完成"

# 6. 检查配置文件
if [ ! -f "src/data/config.py" ]; then
    echo ""
    echo "⚠️  未找到 src/data/config.py"
    echo "   请复制模板并填入你的配置:"
    echo "   cp src/data/config.example.py src/data/config.py"
fi

echo ""
echo "=============================================="
echo "  ✅ 数据库初始化完成!"
echo "=============================================="
echo ""
echo "  下一步:"
echo "  1. 确保 src/data/config.py 中密码正确"
echo "  2. 运行数据更新: /update 或 python3 src/data/new_get_all_stock.py"
echo "  3. 运行盘前分析: /morning"
echo ""
