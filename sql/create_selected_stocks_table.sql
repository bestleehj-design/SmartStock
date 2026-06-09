-- 选股追踪表
-- 用于存储从策略筛选结果中选择的股票

CREATE TABLE IF NOT EXISTS `selected_stocks` (
  `id` INT AUTO_INCREMENT PRIMARY KEY COMMENT '主键ID',
  `code` VARCHAR(10) NOT NULL COMMENT '股票代码',
  `name` VARCHAR(50) DEFAULT NULL COMMENT '股票名称',
  `selected_date` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '选股日期',
  `selected_price` DECIMAL(10, 2) DEFAULT NULL COMMENT '选股时的价格',
  `selected_change_pct` DECIMAL(5, 2) DEFAULT NULL COMMENT '选股时的涨跌幅(%)',
  `current_price` DECIMAL(10, 2) DEFAULT NULL COMMENT '当前价格',
  `current_change_pct` DECIMAL(5, 2) DEFAULT NULL COMMENT '当前涨跌幅(%)',
  `profit_pct` DECIMAL(5, 2) DEFAULT NULL COMMENT '盈亏比例(%)',
  `status` VARCHAR(20) DEFAULT 'tracking' COMMENT '状态: tracking-追踪中, sold-已卖出, removed-已移除',
  `strategy` VARCHAR(50) DEFAULT NULL COMMENT '筛选策略(如: strategy1, strategy2等)',
  `strategy_params` TEXT DEFAULT NULL COMMENT '策略参数(JSON格式)',
  `reason` TEXT DEFAULT NULL COMMENT '选股原因',
  `notes` TEXT DEFAULT NULL COMMENT '备注',
  `updated_at` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  INDEX `idx_code` (`code`),
  INDEX `idx_status` (`status`),
  INDEX `idx_selected_date` (`selected_date`),
  INDEX `idx_strategy` (`strategy`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='选股追踪表';

