-- 创建详细财务数据表，用于存储 TuShare fina_indicator_vip 扩展字段
-- 为策略3基本面分析提供数据支撑

CREATE TABLE IF NOT EXISTS fina_info_detailed_tbl (
    code VARCHAR(10) NOT NULL COMMENT '股票代码',
    reportdate DATE NOT NULL COMMENT '报告期',
    data JSON NOT NULL COMMENT '完整财务指标JSON',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    PRIMARY KEY (code, reportdate),
    INDEX idx_code (code),
    INDEX idx_reportdate (reportdate)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
