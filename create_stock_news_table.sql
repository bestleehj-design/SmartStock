-- 持仓新闻舆情分析系统 - 新闻表 DDL
-- 创建日期: 2026-06-01
-- 使用方法: mysql -u root -p gp2 < create_stock_news_table.sql

CREATE TABLE IF NOT EXISTS stock_news_daily_tbl (
  id INT AUTO_INCREMENT PRIMARY KEY,
  stock_code VARCHAR(10) NOT NULL,
  stock_name VARCHAR(50),
  news_date DATE NOT NULL,
  news_title VARCHAR(500) NOT NULL,
  news_source VARCHAR(100),
  sentiment_score INT DEFAULT 0,
  sentiment_label VARCHAR(20) DEFAULT 'neutral',
  matched_keywords JSON,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  INDEX idx_stock_date (stock_code, news_date),
  INDEX idx_news_date (news_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
