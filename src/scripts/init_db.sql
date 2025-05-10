-- 版本控制表
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER PRIMARY KEY,
    applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    description TEXT
);

-- 插入初始版本记录
INSERT OR IGNORE INTO schema_version (version, description) VALUES (1, '初始数据库结构');

-- 主数据表（统一内容类型存储）
CREATE TABLE IF NOT EXISTS interests (
    id TEXT PRIMARY KEY,
    type TEXT NOT NULL,                     -- 内容类型 (movie,tv,book等)
    status TEXT NOT NULL CHECK(status IN ('done', 'doing', 'mark')), -- 状态修改为标准值
    title TEXT NOT NULL,
    url TEXT NOT NULL,
    cover_url TEXT,
    douban_score REAL,                      -- 豆瓣评分
    my_rating INTEGER,                      -- 个人评分
    comment TEXT,                           -- 评论
    year INTEGER,                           -- 年份
    genres TEXT,                            -- JSON格式的分类列表
    card_subtitle TEXT,                     -- 保留card_subtitle作为统一存储字段，包含分类/创作者等信息
    create_time TEXT NOT NULL,              -- 豆瓣原始时间戳
    update_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    local_path TEXT,                        -- 本地图片路径
    raw_json TEXT,                          -- 原始API数据
    metadata TEXT                           -- 新增:存储元数据的JSON字段，如地区、语言等
);

-- 创建常用查询的索引
-- 1. 类型和状态组合索引，常用于列表筛选
CREATE INDEX IF NOT EXISTS idx_interests_type_status ON interests(type, status);

-- 2. 年份索引，用于年份统计和筛选
CREATE INDEX IF NOT EXISTS idx_interests_year ON interests(year);

-- 3. 创建时间索引，用于排序和时间线查询
CREATE INDEX IF NOT EXISTS idx_interests_create_time ON interests(create_time);

-- 4. 评分索引，用于评分统计和排序
CREATE INDEX IF NOT EXISTS idx_interests_douban_score ON interests(douban_score);
CREATE INDEX IF NOT EXISTS idx_interests_my_rating ON interests(my_rating);

-- 5. 标题索引，用于搜索
CREATE INDEX IF NOT EXISTS idx_interests_title ON interests(title COLLATE NOCASE);

-- 6. 单独类型索引，用于特定类型列表
CREATE INDEX IF NOT EXISTS idx_interests_type ON interests(type);

-- 7. 组合索引，用于最常见的查询组合
CREATE INDEX IF NOT EXISTS idx_interests_type_year ON interests(type, year);
CREATE INDEX IF NOT EXISTS idx_interests_type_score ON interests(type, douban_score);

-- 创建触发器，自动更新update_time字段
CREATE TRIGGER IF NOT EXISTS update_interests_timestamp 
AFTER UPDATE ON interests
BEGIN
    UPDATE interests SET update_time = CURRENT_TIMESTAMP WHERE id = NEW.id;
END;

-- 创建辅助视图，简化统计查询
CREATE VIEW IF NOT EXISTS v_interests_stats AS
SELECT 
    type,
    status,
    COUNT(*) as count,
    AVG(CASE WHEN douban_score > 0 THEN douban_score ELSE NULL END) as avg_score,
    strftime('%Y', create_time) as year_created
FROM interests
GROUP BY type, status, year_created;

-- 创建缓存表，用于存储频繁计算的统计结果
CREATE TABLE IF NOT EXISTS stats_cache (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,  -- 存储JSON格式的统计结果
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP,
    version INTEGER DEFAULT 1
);

-- 为缓存表创建过期索引
CREATE INDEX IF NOT EXISTS idx_stats_cache_expires ON stats_cache(expires_at);

