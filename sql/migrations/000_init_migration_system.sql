# ============================================================
# SmartStock 数据库迁移系统 - 用于增量更新已有数据库
#
# 使用方式:
#   新建: mysql -u root -p < sql/schema.sql          (建库 + 19张表)
#   更新: bash scripts/migrate_db.sh                  (只执行未跑的迁移)
#   迁移: 在 sql/migrations/ 下新建 .sql 文件，编号递增
# ============================================================

-- Migration 000: 迁移追踪表（系统自用）
CREATE TABLE IF NOT EXISTS `schema_migrations` (
  `migration_id` varchar(20) NOT NULL COMMENT '迁移编号',
  `applied_at` datetime DEFAULT CURRENT_TIMESTAMP COMMENT '执行时间',
  PRIMARY KEY (`migration_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
