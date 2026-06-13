#!/bin/bash
# ============================================================
# SmartStock 数据导出脚本
#
# 导出全量数据给其他人使用。分两种模式：
#   bash scripts/export_data.sh minimal   → 最小包 (~900MB) 仅日K+基础
#   bash scripts/export_data.sh full      → 完整包 (~3.5GB) 所有表
#
# 导出文件: exports/gp2_minimal_YYYYMMDD.sql.gz
#           exports/gp2_full_YYYYMMDD.sql.gz
# ============================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
EXPORT_DIR="$PROJECT_DIR/exports"
DATE_TAG=$(date +%Y%m%d)

mkdir -p "$EXPORT_DIR"

# 读取密码
read -sp "请输入 MySQL root 密码: " MYSQL_PWD
echo ""

# 测试连接
if ! mysql -u root -p"$MYSQL_PWD" gp2 -e "SELECT 1" --silent 2>/dev/null; then
    echo "❌ MySQL 连接失败"
    exit 1
fi

MODE="${1:-minimal}"
DUMP_CMD="mysqldump -u root -p$MYSQL_PWD --single-transaction --quick gp2"

# === 最小包：核心数据 ===
MINIMAL_TABLES=(
    daily_info_tbl          # 个股日K (812MB)
    stock_basic_info_tbl    # 股票基础信息 (7MB)
    market_index_tbl        # 大盘指数
    sox_index_tbl           # 费城半导体 (2MB)
    trade_date_info_tbl     # 交易日历
    fina_info_tbl           # 财务指标 (23MB)
)

# === 扩展包：资金流 + 筹码 ===
EXTRA_TABLES=(
    daily_basic_tbl         # 每日估值 (604MB)
    daily_moneyflow_tbl     # 大单资金流 (327MB)
    daily_moneyflow_tbl_2   # 详细资金流 (767MB)
    cyq_perf_tbl            # 筹码分布 (614MB)
    fina_info_detailed_tbl  # 财务详情JSON (245MB)
    holder_info_tbl         # 股东持仓 (106MB)
)

# === 不导出的表（个人数据） ===
# claude_trades, selected_stocks, smart_screen_results,
# stock_news_daily_tbl, theme_daily_score_tbl

if [ "$MODE" = "minimal" ]; then
    OUTPUT="$EXPORT_DIR/gp2_minimal_${DATE_TAG}.sql.gz"
    echo "📦 导出最小数据包 (~900MB 压缩后约 200MB)..."
    $DUMP_CMD --no-create-info "${MINIMAL_TABLES[@]}" | gzip > "$OUTPUT"
    SIZE=$(du -h "$OUTPUT" | cut -f1)
    echo "✅ 已导出: $OUTPUT ($SIZE)"
    echo ""
    echo "   包含: 个股日K + 股票信息 + 大盘指数 + SOX + 交易日历 + 财务指标"
    echo "   不包含: 资金流 / 筹码 / 股东 / 个人交易记录"

elif [ "$MODE" = "full" ]; then
    OUTPUT="$EXPORT_DIR/gp2_full_${DATE_TAG}.sql.gz"
    echo "📦 导出完整数据包 (~3.5GB 压缩后约 800MB)..."
    ALL_TABLES=("${MINIMAL_TABLES[@]}" "${EXTRA_TABLES[@]}")
    $DUMP_CMD --no-create-info "${ALL_TABLES[@]}" | gzip > "$OUTPUT"
    SIZE=$(du -h "$OUTPUT" | cut -f1)
    echo "✅ 已导出: $OUTPUT ($SIZE)"
    echo ""
    echo "   包含: 全部行情 + 资金流 + 筹码 + 财务 + 股东"

else
    echo "用法: bash scripts/export_data.sh [minimal|full]"
    exit 1
fi

echo ""
echo "📤 分享方式:"
echo "   直接发送 $OUTPUT 文件给对方"
echo ""
echo "📥 对方导入方法:"
echo "   gunzip < $OUTPUT | mysql -u root -p gp2"
