#!/bin/bash
# ============================================================
# SmartStock 数据库增量迁移脚本
#
# 对比 sql/migrations/ 目录下的 SQL 文件与数据库中 schema_migrations 表，
# 只执行尚未应用的迁移，按编号顺序执行。
#
# 用法:
#   bash scripts/migrate_db.sh                   # 交互式输入密码
#   bash scripts/migrate_db.sh -p 12345678       # 命令行指定密码
# ============================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
MIGRATIONS_DIR="$PROJECT_DIR/sql/migrations"

# 读取密码
if [ "$1" = "-p" ] && [ -n "$2" ]; then
    MYSQL_PWD="$2"
else
    read -sp "请输入 MySQL root 密码: " MYSQL_PWD
    echo ""
fi

# 测试连接
if ! mysql -u root -p"$MYSQL_PWD" gp2 -e "SELECT 1" --silent 2>/dev/null; then
    echo "❌ MySQL 连接失败"
    exit 1
fi

# 确保迁移追踪表存在
echo "📋 检查迁移状态..."
mysql -u root -p"$MYSQL_PWD" gp2 -e "
    CREATE TABLE IF NOT EXISTS schema_migrations (
        migration_id varchar(20) NOT NULL,
        applied_at datetime DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (migration_id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
" 2>/dev/null

# 获取已执行的迁移列表
APPLIED=$(mysql -u root -p"$MYSQL_PWD" gp2 -N -e "SELECT migration_id FROM schema_migrations ORDER BY migration_id" 2>/dev/null)
APPLIED_LIST=$(echo "$APPLIED" | tr '\n' '|')

# 遍历迁移文件
PENDING=0
APPLIED_COUNT=0

for sql_file in "$MIGRATIONS_DIR"/*.sql; do
    [ -f "$sql_file" ] || continue

    filename=$(basename "$sql_file")
    migration_id="${filename%%.sql}"
    migration_id="${migration_id%%_*}"  # 取编号部分

    # 检查是否已执行
    if echo "$APPLIED" | grep -q "^${migration_id}$" 2>/dev/null; then
        APPLIED_COUNT=$((APPLIED_COUNT + 1))
        continue
    fi

    # 执行迁移
    echo "🔄 执行迁移: $filename"
    if mysql -u root -p"$MYSQL_PWD" gp2 < "$sql_file" 2>/tmp/migrate_err.txt; then
        # 记录执行
        mysql -u root -p"$MYSQL_PWD" gp2 -e "INSERT INTO schema_migrations (migration_id) VALUES ('$migration_id')" 2>/dev/null
        echo "   ✅ 完成"
        PENDING=$((PENDING + 1))
    else
        echo "   ❌ 失败: $(cat /tmp/migrate_err.txt 2>/dev/null)"
        exit 1
    fi
done

if [ $PENDING -eq 0 ]; then
    echo "✅ 已是最新 ($APPLIED_COUNT 个迁移已执行, 0 个待执行)"
else
    echo "✅ 完成: 执行了 $PENDING 个新迁移"
fi
