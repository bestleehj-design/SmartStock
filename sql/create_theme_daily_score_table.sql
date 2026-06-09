-- 每日主线题材分析表
-- 存储每个交易日各题材板块的多维度评分结果

CREATE TABLE IF NOT EXISTS theme_daily_score_tbl (
    id INT AUTO_INCREMENT PRIMARY KEY COMMENT '主键ID',
    trade_date DATE NOT NULL COMMENT '分析日期',
    theme_code VARCHAR(20) NOT NULL COMMENT '板块代码(同花顺概念代码)',
    theme_name VARCHAR(100) NOT NULL COMMENT '板块名称',
    theme_type VARCHAR(20) DEFAULT 'concept' COMMENT '板块类型: concept/industry',
    -- 六维评分
    score_zt_ratio DECIMAL(5,2) DEFAULT 0 COMMENT '涨停占比分数(0-10)',
    score_echelon DECIMAL(5,2) DEFAULT 0 COMMENT '涨停梯队分数(0-10)',
    score_sustainability DECIMAL(5,2) DEFAULT 0 COMMENT '持续性分数(0-10)',
    score_capital_flow DECIMAL(5,2) DEFAULT 0 COMMENT '资金流入分数(0-10)',
    score_index_rise DECIMAL(5,2) DEFAULT 0 COMMENT '板块指数涨幅分数(0-10)',
    score_turnover_ratio DECIMAL(5,2) DEFAULT 0 COMMENT '成交额占比分数(0-10)',
    total_score DECIMAL(6,2) DEFAULT 0 COMMENT '综合总分(0-60)',
    is_main_theme TINYINT DEFAULT 0 COMMENT '是否主线题材(1=是)',
    -- 统计字段
    zt_count INT DEFAULT 0 COMMENT '板块涨停股数',
    zt_total INT DEFAULT 0 COMMENT '板块总股数',
    high_board_count INT DEFAULT 0 COMMENT '高标股数(3连板及以上)',
    first_board_count INT DEFAULT 0 COMMENT '首板股数',
    net_big_order_amount DOUBLE DEFAULT 0 COMMENT '板块大单净额(万元)',
    concept_turnover DOUBLE DEFAULT 0 COMMENT '板块成交额',
    avg_rise_5d DECIMAL(6,2) DEFAULT 0 COMMENT '板块5日平均涨幅(%)',
    -- 龙头信息
    leader_codes JSON COMMENT '龙头票代码列表',
    leader_names JSON COMMENT '龙头票名称列表',
    -- 分析详情
    analysis_detail JSON COMMENT '分析详情(JSON)',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    UNIQUE KEY uk_date_code (trade_date, theme_code),
    INDEX idx_date (trade_date),
    INDEX idx_main_theme (trade_date, is_main_theme),
    INDEX idx_score (trade_date, total_score)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='每日主线题材分析表';
