-- ============================================================
-- SmartStock 数据库完整建表语句
-- 数据库: gp2
-- 导出日期: 2026-06-11
-- 表数量: 19 张
-- 使用方法: mysql -u root -p < sql/schema.sql
-- ============================================================

CREATE DATABASE IF NOT EXISTS gp2 DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE gp2;

-- ============================================================
-- 1. claude_trades — AI 交易判断记录 (用于 /log /recall)
-- ============================================================
CREATE TABLE IF NOT EXISTS `claude_trades` (
  `id` int NOT NULL AUTO_INCREMENT,
  `analysis_date` date NOT NULL,
  `code` varchar(10) NOT NULL,
  `name` varchar(50) DEFAULT NULL,
  `source` varchar(50) DEFAULT NULL COMMENT '来源命令: /morning /close /bounce /check',
  `action` varchar(20) DEFAULT NULL COMMENT '操作: 买入/卖出/持有/观望/减仓',
  `entry_price` decimal(10,2) DEFAULT NULL,
  `stop_loss` decimal(10,2) DEFAULT NULL,
  `target_price` decimal(10,2) DEFAULT NULL,
  `confidence` varchar(20) DEFAULT NULL COMMENT '置信度: 高/中/低',
  `thesis` text COMMENT '判断逻辑',
  `risks` text COMMENT '风险提示',
  `current_price` decimal(10,2) DEFAULT NULL,
  `ret_1d` decimal(8,4) DEFAULT NULL COMMENT '1日后收益(回填)',
  `ret_3d` decimal(8,4) DEFAULT NULL,
  `ret_5d` decimal(8,4) DEFAULT NULL,
  `ret_10d` decimal(8,4) DEFAULT NULL,
  `ret_20d` decimal(8,4) DEFAULT NULL,
  `hit_target` tinyint DEFAULT NULL COMMENT '是否到达目标价',
  `hit_stop` tinyint DEFAULT NULL COMMENT '是否触发止损',
  `max_ret` decimal(8,4) DEFAULT NULL COMMENT '期间最大收益',
  `accuracy_score` int DEFAULT NULL COMMENT '准确度评分',
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `idx_date` (`analysis_date`),
  KEY `idx_code` (`code`),
  KEY `idx_action` (`action`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- ============================================================
-- 2. daily_info_tbl — 个股日K线 (核心表，888万行)
-- ============================================================
CREATE TABLE IF NOT EXISTS `daily_info_tbl` (
  `code` char(16) NOT NULL DEFAULT '',
  `tradedate` date NOT NULL DEFAULT '1000-01-01',
  `open` double DEFAULT NULL,
  `high` double DEFAULT NULL,
  `low` double DEFAULT NULL,
  `close` double DEFAULT NULL,
  `volume` double DEFAULT NULL COMMENT '成交量(手)',
  `amount` double DEFAULT NULL COMMENT '成交额(元)',
  `adj_factor` double DEFAULT NULL COMMENT '复权因子',
  PRIMARY KEY (`code`,`tradedate`)
) ENGINE=MyISAM DEFAULT CHARSET=latin1;

-- ============================================================
-- 3. daily_basic_tbl — 每日估值/基本面 (560万行)
-- ============================================================
CREATE TABLE IF NOT EXISTS `daily_basic_tbl` (
  `code` char(16) NOT NULL DEFAULT '',
  `tradedate` date NOT NULL DEFAULT '1000-01-01',
  `turnover_rate_f` double DEFAULT NULL COMMENT '换手率(自由流通)',
  `pe` double DEFAULT NULL COMMENT '市盈率',
  `pe_ttm` double DEFAULT NULL COMMENT '市盈率TTM',
  `pb` double DEFAULT NULL COMMENT '市净率',
  `total_share` double DEFAULT NULL COMMENT '总股本',
  `float_share` double DEFAULT NULL COMMENT '流通股本',
  `total_mv` double DEFAULT NULL COMMENT '总市值',
  `circ_mv` double DEFAULT NULL COMMENT '流通市值',
  `free_share` double DEFAULT NULL COMMENT '自由流通股本',
  PRIMARY KEY (`code`,`tradedate`)
) ENGINE=MyISAM DEFAULT CHARSET=latin1;

-- ============================================================
-- 4. daily_moneyflow_tbl — 大单资金流 (536万行)
-- ============================================================
CREATE TABLE IF NOT EXISTS `daily_moneyflow_tbl` (
  `code` char(16) NOT NULL DEFAULT '',
  `tradedate` date NOT NULL DEFAULT '1000-01-01',
  `net_lg_vol` int DEFAULT NULL COMMENT '大单净流入量(手)',
  `net_lg_amount` double DEFAULT NULL COMMENT '大单净流入额(元)',
  `net_elg_vol` int DEFAULT NULL COMMENT '特大单净流入量(手)',
  `net_elg_amount` double DEFAULT NULL COMMENT '特大单净流入额(元)',
  PRIMARY KEY (`code`,`tradedate`)
) ENGINE=MyISAM DEFAULT CHARSET=latin1;

-- ============================================================
-- 5. daily_moneyflow_tbl_2 — 详细资金流拆分 (536万行)
-- ============================================================
CREATE TABLE IF NOT EXISTS `daily_moneyflow_tbl_2` (
  `code` char(16) NOT NULL DEFAULT '',
  `tradedate` date NOT NULL DEFAULT '1000-01-01',
  `buy_sm_vol` int DEFAULT NULL COMMENT '小单买入量',
  `buy_sm_amount` double DEFAULT NULL COMMENT '小单买入额',
  `sell_sm_vol` int DEFAULT NULL COMMENT '小单卖出量',
  `sell_sm_amount` double DEFAULT NULL COMMENT '小单卖出额',
  `buy_md_vol` int DEFAULT NULL COMMENT '中单买入量',
  `buy_md_amount` double DEFAULT NULL COMMENT '中单买入额',
  `sell_md_vol` int DEFAULT NULL COMMENT '中单卖出量',
  `sell_md_amount` double DEFAULT NULL COMMENT '中单卖出额',
  `buy_lg_vol` int DEFAULT NULL COMMENT '大单买入量',
  `buy_lg_amount` double DEFAULT NULL COMMENT '大单买入额',
  `sell_lg_vol` int DEFAULT NULL COMMENT '大单卖出量',
  `sell_lg_amount` double DEFAULT NULL COMMENT '大单卖出额',
  `buy_elg_vol` int DEFAULT NULL COMMENT '特大单买入量',
  `buy_elg_amount` double DEFAULT NULL COMMENT '特大单买入额',
  `sell_elg_vol` int DEFAULT NULL COMMENT '特大单卖出量',
  `sell_elg_amount` double DEFAULT NULL COMMENT '特大单卖出额',
  `net_mf_vol` int DEFAULT NULL COMMENT '净主力资金量',
  `net_mf_amount` double DEFAULT NULL COMMENT '净主力资金额',
  PRIMARY KEY (`code`,`tradedate`)
) ENGINE=MyISAM DEFAULT CHARSET=latin1;

-- ============================================================
-- 6. cyq_perf_tbl — 筹码分布 (570万行)
-- ============================================================
CREATE TABLE IF NOT EXISTS `cyq_perf_tbl` (
  `code` char(16) NOT NULL DEFAULT '',
  `tradedate` date NOT NULL DEFAULT '1000-01-01',
  `his_low` double DEFAULT NULL COMMENT '历史最低',
  `his_high` double DEFAULT NULL COMMENT '历史最高',
  `cost_5pct` double DEFAULT NULL COMMENT '5%成本线',
  `cost_15pct` double DEFAULT NULL COMMENT '15%成本线',
  `cost_50pct` double DEFAULT NULL COMMENT '50%成本线(中位数)',
  `cost_85pct` double DEFAULT NULL COMMENT '85%成本线',
  `cost_95pct` double DEFAULT NULL COMMENT '95%成本线',
  `weight_avg` double DEFAULT NULL COMMENT '加权均价',
  `winner_rate` double DEFAULT NULL COMMENT '获利盘比例',
  PRIMARY KEY (`code`,`tradedate`)
) ENGINE=MyISAM DEFAULT CHARSET=latin1;

-- ============================================================
-- 7. market_index_tbl — 大盘指数日K (用于 /bounce 触发判断)
-- ============================================================
CREATE TABLE IF NOT EXISTS `market_index_tbl` (
  `index_code` varchar(10) NOT NULL COMMENT '指数代码: 000001(上证)/399006(创业板)/000688(科创50)',
  `tradedate` date NOT NULL,
  `open` double DEFAULT NULL,
  `high` double DEFAULT NULL,
  `low` double DEFAULT NULL,
  `close` double DEFAULT NULL,
  `chg_pct` double DEFAULT NULL COMMENT '涨跌幅(%)',
  `volume` double DEFAULT NULL,
  `amount` double DEFAULT NULL,
  PRIMARY KEY (`index_code`,`tradedate`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- ============================================================
-- 8. sox_index_tbl — 费城半导体指数 (8014天, 1994-2026)
-- ============================================================
CREATE TABLE IF NOT EXISTS `sox_index_tbl` (
  `tradedate` date NOT NULL,
  `close` double DEFAULT NULL,
  `chg_pct` double DEFAULT NULL COMMENT '涨跌幅',
  `chg_3m` double DEFAULT NULL COMMENT '3月涨跌幅',
  `chg_6m` double DEFAULT NULL COMMENT '6月涨跌幅',
  `chg_1y` double DEFAULT NULL COMMENT '1年涨跌幅',
  PRIMARY KEY (`tradedate`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- ============================================================
-- 9. fina_info_tbl — 核心财务指标 (26万行)
-- ============================================================
CREATE TABLE IF NOT EXISTS `fina_info_tbl` (
  `code` char(16) NOT NULL DEFAULT '',
  `reportdate` date NOT NULL DEFAULT '1000-01-01',
  `profit_dedt` double DEFAULT NULL COMMENT '扣非净利润',
  `q_dtprofit` double DEFAULT NULL COMMENT '季度利润',
  `netprofit_yoy` double DEFAULT NULL COMMENT '净利润同比(%)',
  `tr_yoy` double DEFAULT NULL COMMENT '营收同比(%)',
  `q_gr_yoy` double DEFAULT NULL COMMENT '季度营收同比(%)',
  `q_profit_yoy` double DEFAULT NULL COMMENT '季度利润同比(%)',
  `q_netprofit_yoy` double DEFAULT NULL COMMENT '季度净利同比(%)',
  PRIMARY KEY (`code`,`reportdate`)
) ENGINE=MyISAM DEFAULT CHARSET=latin1;

-- ============================================================
-- 10. fina_info_detailed_tbl — 完整财务指标 JSON (26万行)
-- ============================================================
CREATE TABLE IF NOT EXISTS `fina_info_detailed_tbl` (
  `code` varchar(10) NOT NULL COMMENT '股票代码',
  `reportdate` date NOT NULL COMMENT '报告期',
  `data` json NOT NULL COMMENT '完整财务指标JSON',
  `created_at` datetime DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`code`,`reportdate`),
  KEY `idx_code` (`code`),
  KEY `idx_reportdate` (`reportdate`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- ============================================================
-- 11. holder_info_tbl — 股东持仓 (116万行)
-- ============================================================
CREATE TABLE IF NOT EXISTS `holder_info_tbl` (
  `code` char(16) NOT NULL DEFAULT '',
  `reportdate` date NOT NULL DEFAULT '1000-01-01',
  `holder_name` varchar(512) NOT NULL DEFAULT '' COMMENT '股东名称',
  `hold_amount` double DEFAULT NULL COMMENT '持仓量',
  PRIMARY KEY (`code`,`reportdate`,`holder_name`(255))
) ENGINE=MyISAM DEFAULT CHARSET=latin1;

-- ============================================================
-- 12. stock_basic_info_tbl — 股票基础信息 (11,552行)
-- ============================================================
CREATE TABLE IF NOT EXISTS `stock_basic_info_tbl` (
  `code` char(16) NOT NULL DEFAULT '',
  `name` varchar(255) DEFAULT NULL,
  `status` int DEFAULT NULL COMMENT '上市状态',
  `type` int DEFAULT NULL COMMENT '股票类型',
  `sw1` varchar(512) DEFAULT NULL COMMENT '申万一级行业',
  `sw2` varchar(512) DEFAULT NULL COMMENT '申万二级行业',
  `sw3` varchar(512) DEFAULT NULL COMMENT '申万三级行业',
  `choice_concept_list` varchar(1024) DEFAULT NULL COMMENT '同花顺概念板块',
  `code_list` varchar(8192) DEFAULT NULL COMMENT '关联代码列表',
  `market` varchar(100) DEFAULT NULL COMMENT '市场: A股/港股',
  PRIMARY KEY (`code`)
) ENGINE=MyISAM DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ============================================================
-- 13. stock_info_tbl — 股票数据状态 (0行，预置)
-- ============================================================
CREATE TABLE IF NOT EXISTS `stock_info_tbl` (
  `code` char(16) NOT NULL DEFAULT '',
  `status` int DEFAULT NULL,
  `first_record_day` date DEFAULT NULL COMMENT '首个数据日',
  `last_update_day` date DEFAULT NULL COMMENT '最后更新日',
  `note` varchar(4096) DEFAULT NULL,
  PRIMARY KEY (`code`)
) ENGINE=MyISAM DEFAULT CHARSET=latin1;

-- ============================================================
-- 14. trade_date_info_tbl — 交易日历 (1,558行)
-- ============================================================
CREATE TABLE IF NOT EXISTS `trade_date_info_tbl` (
  `trade_date` date NOT NULL DEFAULT '1000-01-01',
  PRIMARY KEY (`trade_date`)
) ENGINE=MyISAM DEFAULT CHARSET=latin1;

-- ============================================================
-- 15. data_update_date_info_tbl — 数据更新状态
-- ============================================================
CREATE TABLE IF NOT EXISTS `data_update_date_info_tbl` (
  `update_date` date DEFAULT NULL COMMENT '最后数据更新日期'
) ENGINE=MyISAM DEFAULT CHARSET=latin1;

-- ============================================================
-- 16. stock_news_daily_tbl — 持仓个股新闻舆情
-- ============================================================
CREATE TABLE IF NOT EXISTS `stock_news_daily_tbl` (
  `id` int NOT NULL AUTO_INCREMENT,
  `stock_code` varchar(10) NOT NULL,
  `stock_name` varchar(50) DEFAULT NULL,
  `news_date` date NOT NULL,
  `news_title` varchar(500) NOT NULL,
  `news_source` varchar(100) DEFAULT NULL,
  `sentiment_score` int DEFAULT '0' COMMENT '舆情分: 正=利多, 负=利空',
  `sentiment_label` varchar(20) DEFAULT 'neutral' COMMENT '舆情标签: positive/negative/neutral',
  `matched_keywords` json DEFAULT NULL COMMENT '匹配的关键词',
  `created_at` datetime DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `idx_stock_date` (`stock_code`,`news_date`),
  KEY `idx_news_date` (`news_date`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- ============================================================
-- 17. theme_daily_score_tbl — 主线题材六维评分 (5,983行)
-- ============================================================
CREATE TABLE IF NOT EXISTS `theme_daily_score_tbl` (
  `id` int NOT NULL AUTO_INCREMENT,
  `trade_date` date NOT NULL COMMENT '分析日期',
  `theme_code` varchar(20) NOT NULL COMMENT '板块代码(同花顺概念代码)',
  `theme_name` varchar(100) NOT NULL COMMENT '板块名称',
  `theme_type` varchar(20) DEFAULT 'concept' COMMENT '板块类型: concept/industry',
  `score_zt_ratio` decimal(5,2) DEFAULT '0.00' COMMENT '涨停占比分(0-10)',
  `score_echelon` decimal(5,2) DEFAULT '0.00' COMMENT '涨停梯队分(0-10)',
  `score_sustainability` decimal(5,2) DEFAULT '0.00' COMMENT '持续性分(0-10)',
  `score_capital_flow` decimal(5,2) DEFAULT '0.00' COMMENT '资金流入分(0-10)',
  `score_index_rise` decimal(5,2) DEFAULT '0.00' COMMENT '板块涨幅分(0-10)',
  `score_turnover_ratio` decimal(5,2) DEFAULT '0.00' COMMENT '成交额占比分(0-10)',
  `total_score` decimal(6,2) DEFAULT '0.00' COMMENT '综合总分(0-60)',
  `is_main_theme` tinyint DEFAULT '0' COMMENT '是否主线(1=是)',
  `zt_count` int DEFAULT '0' COMMENT '涨停股数',
  `zt_total` int DEFAULT '0' COMMENT '板块总股数',
  `high_board_count` int DEFAULT '0' COMMENT '高标股数(>=3连板)',
  `first_board_count` int DEFAULT '0' COMMENT '首板股数',
  `net_big_order_amount` double DEFAULT '0' COMMENT '大单净额(万元)',
  `concept_turnover` double DEFAULT '0' COMMENT '板块成交额',
  `avg_rise_5d` decimal(6,2) DEFAULT '0.00' COMMENT '5日平均涨幅(%)',
  `leader_codes` json DEFAULT NULL COMMENT '龙头票代码列表',
  `leader_names` json DEFAULT NULL COMMENT '龙头票名称列表',
  `analysis_detail` json DEFAULT NULL COMMENT '分析详情',
  `created_at` datetime DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_date_code` (`trade_date`,`theme_code`),
  KEY `idx_date` (`trade_date`),
  KEY `idx_main_theme` (`trade_date`,`is_main_theme`),
  KEY `idx_score` (`trade_date`,`total_score`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- ============================================================
-- 18. selected_stocks — 策略选股追踪表
-- ============================================================
CREATE TABLE IF NOT EXISTS `selected_stocks` (
  `id` int NOT NULL AUTO_INCREMENT,
  `code` varchar(10) NOT NULL COMMENT '股票代码',
  `name` varchar(50) DEFAULT NULL,
  `selected_date` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '选股日期',
  `selected_price` decimal(10,2) DEFAULT NULL,
  `selected_change_pct` decimal(5,2) DEFAULT NULL COMMENT '选股时涨跌幅(%)',
  `current_price` decimal(10,2) DEFAULT NULL,
  `current_change_pct` decimal(5,2) DEFAULT NULL,
  `profit_pct` decimal(5,2) DEFAULT NULL COMMENT '盈亏比例(%)',
  `status` varchar(20) DEFAULT 'tracking' COMMENT '状态: tracking/sold/removed',
  `strategy` varchar(50) DEFAULT NULL COMMENT '策略名',
  `strategy_params` text COMMENT '策略参数JSON',
  `reason` text COMMENT '选股原因',
  `notes` text,
  `updated_at` datetime DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  `created_at` datetime DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `idx_code` (`code`),
  KEY `idx_status` (`status`),
  KEY `idx_selected_date` (`selected_date`),
  KEY `idx_strategy` (`strategy`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ============================================================
-- 19. smart_screen_results — Smart Screener 评分结果
-- ============================================================
CREATE TABLE IF NOT EXISTS `smart_screen_results` (
  `id` int NOT NULL AUTO_INCREMENT,
  `screen_date` date NOT NULL,
  `code` varchar(10) NOT NULL,
  `name` varchar(50) DEFAULT NULL,
  `score` int DEFAULT NULL COMMENT '综合评分',
  `sector` varchar(50) DEFAULT NULL COMMENT '板块',
  `is_leader` tinyint DEFAULT '0' COMMENT '是否龙头',
  `price` decimal(10,2) DEFAULT NULL,
  `stop_loss` decimal(10,2) DEFAULT NULL COMMENT '建议止损价',
  `reasons` text COMMENT '评分明细',
  `warnings` text COMMENT '风险提示',
  `ret_1d` decimal(8,4) DEFAULT NULL COMMENT '1日收益(回填)',
  `ret_3d` decimal(8,4) DEFAULT NULL,
  `ret_5d` decimal(8,4) DEFAULT NULL,
  `ret_10d` decimal(8,4) DEFAULT NULL,
  `ret_20d` decimal(8,4) DEFAULT NULL,
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  `sector_index_rise` decimal(5,2) DEFAULT NULL COMMENT '板块涨跌幅',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_screen_date_code` (`screen_date`,`code`),
  KEY `idx_date` (`screen_date`),
  KEY `idx_score` (`screen_date`,`score`),
  KEY `idx_leader` (`screen_date`,`is_leader`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
