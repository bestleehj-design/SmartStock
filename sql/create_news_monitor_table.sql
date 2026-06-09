-- 持仓新闻监控表
-- 用于存储持仓股票的新闻/消息及情感分析结果

CREATE TABLE IF NOT EXISTS `news_monitor_tbl` (
  `id` INT AUTO_INCREMENT PRIMARY KEY,
  `code` VARCHAR(10) NOT NULL COMMENT '股票代码',
  `name` VARCHAR(50) COMMENT '股票名称',
  `news_title` VARCHAR(500) NOT NULL COMMENT '新闻标题',
  `news_summary` TEXT COMMENT '新闻摘要',
  `news_url` VARCHAR(500) COMMENT '新闻链接',
  `news_date` DATETIME COMMENT '新闻发布时间',
  `source` VARCHAR(50) COMMENT '来源',
  `negative_score` INT DEFAULT 0 COMMENT '负面分数',
  `positive_score` INT DEFAULT 0 COMMENT '正面分数',
  `sentiment` VARCHAR(20) COMMENT '情感: negative/neutral/positive',
  `is_alert` TINYINT DEFAULT 0 COMMENT '是否需要预警 1=是',
  `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP,
  INDEX `idx_code` (`code`),
  INDEX `idx_trade_date` (`news_date`),
  INDEX `idx_sentiment` (`sentiment`),
  INDEX `idx_is_alert` (`is_alert`),
  UNIQUE KEY `uk_code_title_url` (`code`, `news_title`(200), `news_url`(200))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='持仓新闻监控表';
