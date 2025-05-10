import os
import sqlite3
import time
import threading
from typing import Dict, List, Any, Optional
from utils.logger import get_logger

# 配置日志
logger = get_logger("data_provider")

class StatisticsDataProvider:
    """统计数据提供者，负责执行所有统计相关的数据库查询
    
    此类专注于数据获取，不包含任何业务逻辑处理
    """
    
    # 连接池配置
    MAX_POOL_SIZE = 3
    QUERY_TIMEOUT = 30  # 查询超时时间（秒）
    
    def __init__(self, db_instance=None):
        """初始化数据提供者
        
        参数:
            db_instance: 数据库实例，如果提供则使用其连接池
        """
        self.db = db_instance
        
        # 如果没有提供数据库实例，则创建自己的连接池
        if not self.db:
            self._connection_pool = []
            self._pool_lock = threading.Lock()
            self.db_path = os.getenv("SQLITE_DB_PATH", "data/douban.db")
            logger.info(f"数据提供者使用独立连接池，数据库路径: {self.db_path}")
        else:
            logger.info("数据提供者使用外部数据库实例")
            
        # 初始化查询计数器和计时器
        self.query_count = 0
        self.total_query_time = 0
        self.slow_query_count = 0  # 慢查询计数 (>1秒)
        
    def _get_connection(self) -> sqlite3.Connection:
        """获取数据库连接（从连接池或数据库实例）"""
        if self.db:
            # 从外部数据库实例获取连接
            return self.db._get_connection()
            
        # 使用自己的连接池
        with self._pool_lock:
            if self._connection_pool:
                return self._connection_pool.pop()
                
        # 如果池为空，创建新连接
        conn = self._create_connection()
        return conn
        
    def _create_connection(self) -> sqlite3.Connection:
        """创建新的数据库连接"""
        conn = sqlite3.connect(self.db_path, timeout=self.QUERY_TIMEOUT)
        conn.row_factory = sqlite3.Row
        # 优化查询
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA temp_store = MEMORY")
        conn.execute("PRAGMA cache_size = 10000")
        return conn
        
    def _return_connection(self, conn: sqlite3.Connection) -> None:
        """将连接返回连接池"""
        if self.db:
            # 使用外部数据库实例归还连接
            if hasattr(self.db, "_return_to_pool"):
                self.db._return_to_pool(conn)
            else:
                conn.close()
            return
            
        # 使用自己的连接池
        if conn is None:
            return
            
        try:
            # 检查连接是否有效
            conn.execute("SELECT 1")
            
            with self._pool_lock:
                if len(self._connection_pool) < self.MAX_POOL_SIZE:
                    self._connection_pool.append(conn)
                    return
                    
        except sqlite3.Error:
            # 连接无效，不归还
            pass
            
        # 如果池已满或连接无效，关闭连接
        try:
            conn.close()
        except:
            pass
            
    def _execute_query(self, query: str, params: tuple = ()) -> List[Dict[str, Any]]:
        """执行SQL查询并返回结果
        
        参数:
            query: SQL查询语句
            params: 查询参数
            
        返回:
            查询结果列表，每项为字典
        """
        conn = None
        start_time = time.time()
        self.query_count += 1
        
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            
            cursor.execute(query, params)
            rows = cursor.fetchall()
            
            # 将 sqlite3.Row 对象转换为普通字典
            results = []
            for row in rows:
                item = {}
                for key in row.keys():
                    item[key] = row[key]
                results.append(item)
                
            # 记录查询时间
            query_time = time.time() - start_time
            self.total_query_time += query_time
            
            # 记录慢查询
            if query_time > 1.0:
                self.slow_query_count += 1
                truncated_query = query.replace('\n', ' ')[:100] + ('...' if len(query) > 100 else '')
                logger.warning(f"慢查询 ({query_time:.2f}秒): {truncated_query}")
                
            return results
            
        except sqlite3.Error as e:
            logger.error(f"查询执行失败: {e}, 查询: {query[:100]}...")
            return []
            
        finally:
            if conn:
                self._return_connection(conn)
            
    def _execute_single_result_query(self, query: str, params: tuple = (), 
                                    default: Any = None) -> Any:
        """执行单一结果查询
        
        参数:
            query: SQL查询语句
            params: 查询参数
            default: 如果没有结果时返回的默认值
            
        返回:
            查询结果，如无结果则返回默认值
        """
        results = self._execute_query(query, params)
        if results and len(results) > 0:
            # 获取第一行第一个字段的值
            first_row = results[0]
            if first_row:
                keys = list(first_row.keys())
                if keys:
                    return first_row[keys[0]]
                    
        return default
        
    def _safe_int(self, value, default=0) -> int:
        """安全转换为整数"""
        try:
            if value is None:
                return default
            return int(value)
        except (ValueError, TypeError):
            return default
            
    def _safe_float(self, value, default=0.0, round_digits=None) -> float:
        """安全转换为浮点数"""
        try:
            if value is None:
                return default
            result = float(value)
            if round_digits is not None:
                result = round(result, round_digits)
            return result
        except (ValueError, TypeError):
            return default
            
    def _safe_str(self, value, default="") -> str:
        """安全转换为字符串"""
        if value is None:
            return default
        try:
            return str(value)
        except:
            return default
            
    # ------------------------------------------------------------
    # 基本统计查询
    # ------------------------------------------------------------
    
    def get_total_count(self) -> int:
        """获取兴趣条目总数"""
        query = "SELECT COUNT(*) as total FROM interests"
        return self._safe_int(self._execute_single_result_query(query))
        
    def get_type_counts(self) -> Dict[str, int]:
        """获取各类型条目数量"""
        query = """
            SELECT type, COUNT(*) as count
            FROM interests
            GROUP BY type
            ORDER BY count DESC
        """
        results = self._execute_query(query)
        
        type_counts = {}
        for row in results:
            type_counts[row["type"]] = self._safe_int(row["count"])
            
        return type_counts
        
    def get_status_counts(self) -> Dict[str, int]:
        """获取各状态条目数量"""
        query = """
            SELECT status, COUNT(*) as count
            FROM interests
            GROUP BY status
        """
        results = self._execute_query(query)
        
        status_counts = {"done": 0, "doing": 0, "wish": 0}
        for row in results:
            status = row["status"]
            # 将 'mark' 映射为 'wish'（保持与前端一致）
            if status == "mark":
                status = "wish"
            if status in status_counts:
                status_counts[status] = self._safe_int(row["count"])
                
        return status_counts
        
    def get_status_counts_by_type(self, type_: str) -> Dict[str, int]:
        """获取指定类型的各状态条目数量"""
        query = """
            SELECT status, COUNT(*) as count
            FROM interests
            WHERE type = ?
            GROUP BY status
        """
        
        results = self._execute_query(query, (type_,))
        
        status_stats = {}
        for row in results:
            status_key = row["status"]
            # 将 'mark' 映射为 'wish'（保持与前端一致）
            if status_key == "mark":
                status_key = "wish"
            status_stats[status_key] = self._safe_int(row["count"])
        
        # 确保所有状态键都存在
        for status in ["done", "doing", "wish"]:
            if status not in status_stats:
                status_stats[status] = 0
                
        return status_stats
        
    def get_year_stats_by_type(self, type_: str) -> Dict[str, int]:
        """获取指定类型的年份统计"""
        query = """
            SELECT year, COUNT(*) as count
            FROM interests
            WHERE type = ? AND year > 0
            GROUP BY year
            ORDER BY year
        """
        
        results = self._execute_query(query, (type_,))
        
        year_stats = {}
        for row in results:
            year = self._safe_str(row["year"])
            if year:
                year_stats[year] = self._safe_int(row["count"])
                
        return year_stats
        
    def get_genres_by_type(self, type_: str, limit: int = 20) -> Dict[str, int]:
        """获取指定类型的标签/分类统计"""
        query = """
            SELECT value as genre, COUNT(*) as count
            FROM interests
            JOIN json_each(interests.genres) ON json_valid(interests.genres)
            WHERE interests.type = ? AND interests.genres IS NOT NULL AND interests.genres != ''
            GROUP BY genre
            ORDER BY count DESC
            LIMIT ?
        """
        
        results = self._execute_query(query, (type_, limit))
        
        genres_stats = {}
        for row in results:
            genre = row["genre"]
            if genre:
                genres_stats[genre] = self._safe_int(row["count"])
                
        return genres_stats
        
    def get_rating_groups_by_type(self, type_: str) -> Dict[str, int]:
        """获取指定类型的评分分布"""
        query = """
            SELECT 
                CASE 
                    WHEN douban_score = 0 THEN '未评分'
                    WHEN douban_score >= 1 AND douban_score <= 2 THEN '1-2星'
                    WHEN douban_score >= 3 AND douban_score <= 5 THEN '3-5星'
                    WHEN douban_score >= 6 AND douban_score <= 7 THEN '6-7星'
                    WHEN douban_score >= 8 AND douban_score <= 10 THEN '8-10星'
                END as rating_group,
                COUNT(*) as count
            FROM interests
            WHERE type = ?
            GROUP BY rating_group
        """
        
        results = self._execute_query(query, (type_,))
        
        rating_stats = {}
        for row in results:
            rating_stats[row["rating_group"]] = self._safe_int(row["count"])
            
        return rating_stats
        
    def get_card_subtitles_by_type(self, type_: str) -> List[Dict[str, Any]]:
        """获取指定类型的所有card_subtitle值及其计数"""
        query = """
            SELECT card_subtitle, COUNT(*) as count
            FROM interests
            WHERE type = ? AND card_subtitle IS NOT NULL AND card_subtitle != ''
            GROUP BY card_subtitle
        """
        
        return self._execute_query(query, (type_,))
        
    # ------------------------------------------------------------
    # 评分统计查询
    # ------------------------------------------------------------
    
    def get_rating_stats(self, type_: Optional[str] = None) -> Dict[str, Any]:
        """获取评分统计数据"""
        # 构建基本查询条件
        where_clause = "WHERE douban_score IS NOT NULL AND douban_score > 0"
        params = []
        
        # 添加类型过滤
        if type_:
            where_clause += " AND type = ?"
            params.append(type_)
        
        # 获取基本统计数据
        stats_query = f"""
            SELECT AVG(douban_score) as average, MAX(douban_score) as max, 
                MIN(douban_score) as min, COUNT(douban_score) as count
            FROM interests
            {where_clause}
        """
        
        stats_result = self._execute_query(stats_query, params)
        stats_row = stats_result[0] if stats_result else {}
        
        # 安全处理和类型转换
        stats = {
            'average': self._safe_float(stats_row.get('average'), round_digits=1),
            'max': self._safe_float(stats_row.get('max')),
            'min': self._safe_float(stats_row.get('min')),
            'count': self._safe_int(stats_row.get('count'))
        }
        
        # 获取评分分布
        dist_query = f"""
            SELECT CAST(douban_score AS INTEGER) as rating_floor, COUNT(*) as count
            FROM interests
            {where_clause}
            GROUP BY rating_floor
            ORDER BY rating_floor
        """
        
        dist_rows = self._execute_query(dist_query, params)
        
        # 初始化分布数组 (1-10分)
        distribution = [0] * 10
        
        # 填充分布数据
        for row in dist_rows:
            floor = self._safe_int(row.get('rating_floor'))
            if 1 <= floor <= 10:
                distribution[floor - 1] = self._safe_int(row.get('count'))
                
        return {
            'stats': stats,
            'distribution': distribution
        }
        
    def get_year_distribution(self, type_: Optional[str] = None) -> Dict[str, List]:
        """获取年份分布统计"""
        # 构建查询条件
        where_clause = "WHERE year IS NOT NULL AND year > 0"
        params = []
        
        # 添加类型过滤
        if type_:
            where_clause += " AND type = ?"
            params.append(type_)
        
        query = f"""
            SELECT year, COUNT(*) as count
            FROM interests
            {where_clause}
            GROUP BY year
            ORDER BY year
        """
        
        results = self._execute_query(query, params)
        
        # 安全处理和类型转换
        years = []
        counts = []
        for row in results:
            try:
                year = self._safe_int(row.get('year'))
                count = self._safe_int(row.get('count'))
                
                # 筛选有效年份 (避免异常值)
                if 1800 <= year <= 2100:
                    years.append(str(year))
                    counts.append(count)
            except:
                continue  # 跳过无效数据
                
        return {
            'labels': years,
            'all': counts
        }
        
    def get_genre_distribution(self, type_: Optional[str] = None, limit: int = 20) -> List[Dict[str, Any]]:
        """获取标签分布统计"""
        # 构建基本查询条件
        where_clause = """
            json_valid(genres) 
            AND genres != '[]'
            AND genres != ''
            AND json_extract(genres, '$[' || num || ']') IS NOT NULL
        """
        params = []
        
        # 添加类型过滤
        if type_:
            where_clause += " AND type = ?"
            params.append(type_)
        
        # 使用JSON数组展开查询标签
        query = f"""
        SELECT DISTINCT 
            TRIM(json_extract(genres, '$[' || num || ']')) as genre_name,
            COUNT(*) as count
        FROM 
            interests,
            (SELECT 0 as num UNION SELECT 1 UNION SELECT 2 UNION SELECT 3 UNION SELECT 4 
            UNION SELECT 5 UNION SELECT 6 UNION SELECT 7 UNION SELECT 8 UNION SELECT 9)
        WHERE 
            {where_clause}
        GROUP BY genre_name
        HAVING genre_name != ''
        ORDER BY count DESC
        LIMIT ?
        """
        
        # 添加limit参数
        params.append(limit)
        
        results = self._execute_query(query, params)
        
        genres = []
        for row in results:
            if row.get('genre_name'):
                try:
                    # 去除JSON字符串可能带有的引号
                    name = self._safe_str(row.get('genre_name')).strip('"\'')
                    count = self._safe_int(row.get('count'))
                    
                    if name:  # 确保名称非空
                        genres.append({
                            'name': name, 
                            'count': count
                        })
                except:
                    continue
                    
        return genres
        
    def get_collection_trend(self, period: str = 'month', months: int = 12, 
                          type_: Optional[str] = None) -> Dict[str, List]:
        """获取收藏趋势数据"""
        # 构建WHERE子句及参数
        where_clause = "WHERE create_time IS NOT NULL"
        params = []
        
        # 添加类型过滤
        if type_:
            where_clause += " AND type = ?"
            params.append(type_)
        
        # 根据period选择不同的查询
        if period.lower() == 'month':
            # 避免SQLite注入，安全处理months参数
            months = self._safe_int(months, 12)
            months = max(1, min(months, 120))  # 限制范围1-120个月
            
            query = f"""
                SELECT strftime('%Y-%m', create_time) as period, COUNT(*) as count
                FROM interests
                {where_clause}
                GROUP BY period
                ORDER BY period DESC
                LIMIT ?
            """
            params.append(months)
            
        elif period.lower() == 'year':
            query = f"""
                SELECT strftime('%Y', create_time) as period, COUNT(*) as count
                FROM interests
                {where_clause}
                GROUP BY period
                ORDER BY period DESC
                LIMIT 10
            """
        else:
            # 无效的周期，默认使用月
            logger.warning(f"无效的周期参数: {period}，使用默认值'month'")
            query = f"""
                SELECT strftime('%Y-%m', create_time) as period, COUNT(*) as count
                FROM interests
                {where_clause}
                GROUP BY period
                ORDER BY period DESC
                LIMIT ?
            """
            params.append(months)
        
        results = self._execute_query(query, params)
        
        # 将结果处理为键值对
        return {row.get('period'): self._safe_int(row.get('count')) for row in results}
        
    # ------------------------------------------------------------
    # 电影特定统计查询
    # ------------------------------------------------------------
    
    def get_movie_decades(self) -> Dict[str, int]:
        """获取电影/电视剧年代分布"""
        query = """
        SELECT 
            CAST((year / 10) * 10 AS TEXT) || '年代' as decade, 
            COUNT(*) as count
        FROM interests
        WHERE (type = 'movie' OR type = 'tv') AND year > 0
        GROUP BY decade
        ORDER BY year
        """
        
        results = self._execute_query(query)
        
        return {row.get('decade'): self._safe_int(row.get('count')) for row in results}
        
    def get_top_movie_genres(self) -> List[Dict[str, Any]]:
        """获取评分最高的电影/电视剧标签"""
        query = """
        SELECT 
            c.value as region,
            AVG(i.douban_score) as avg_score,
            COUNT(*) as count
        FROM 
            interests i,
            json_each(i.genres) c
        WHERE 
            (i.type = 'movie' OR i.type = 'tv')
            AND i.douban_score > 0
            AND json_valid(i.genres)
        GROUP BY region
        HAVING count >= 5
        ORDER BY avg_score DESC
        LIMIT 10
        """
        
        results = self._execute_query(query)
        
        top_genres = []
        for row in results:
            top_genres.append({
                'name': self._safe_str(row.get('region')),
                'score': self._safe_float(row.get('avg_score'), round_digits=1),
                'count': self._safe_int(row.get('count'))
            })
            
        return top_genres
        
    # ------------------------------------------------------------
    # 图书特定统计查询
    # ------------------------------------------------------------
    
    def get_book_reading_trend(self) -> Dict[str, List]:
        """获取图书阅读趋势"""
        query = """
        SELECT strftime('%Y', create_time) as year, COUNT(*) as count
        FROM interests
        WHERE type = 'book' AND status = 'done'
        GROUP BY year
        ORDER BY year
        """
        
        results = self._execute_query(query)
        
        labels = []
        values = []
        for row in results:
            labels.append(row.get('year'))
            values.append(self._safe_int(row.get('count')))
            
        return {
            'labels': labels,
            'values': values
        }
        
    # ------------------------------------------------------------
    # 游戏特定统计查询
    # ------------------------------------------------------------
    
    def get_game_year_stats(self) -> Dict[str, List]:
        """获取游戏年份评分统计"""
        query = """
        SELECT year, AVG(douban_score) as avg_score, COUNT(*) as count
        FROM interests
        WHERE type = 'game' AND year > 0
        GROUP BY year
        ORDER BY year
        """
        
        results = self._execute_query(query)
        
        labels = []
        scores = []
        counts = []
        
        for row in results:
            year = self._safe_int(row.get('year'))
            if 1980 <= year <= 2100:  # 确保年份有效
                labels.append(str(year))
                scores.append(self._safe_float(row.get('avg_score'), round_digits=1))
                counts.append(self._safe_int(row.get('count')))
                
        return {
            'labels': labels,
            'scores': scores,
            'counts': counts
        }
        
    # ------------------------------------------------------------
    # 数据修复查询
    # ------------------------------------------------------------
    
    def find_invalid_genres(self) -> List[Dict[str, Any]]:
        """查找无效的genres JSON数据"""
        query = """
        SELECT id, genres FROM interests 
        WHERE genres IS NOT NULL AND genres != '' AND NOT json_valid(genres)
        """
        return self._execute_query(query)
        
    def fix_invalid_genres(self, item_id: str) -> bool:
        """修复无效的genres JSON数据"""
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute("UPDATE interests SET genres = '[]' WHERE id = ?", (item_id,))
            conn.commit()
            self._return_connection(conn)
            return True
        except sqlite3.Error as e:
            logger.error(f"修复无效的genres JSON数据失败: {e}")
            return False
            
    def fix_null_card_subtitles(self) -> int:
        """修复空的card_subtitle字段"""
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute("UPDATE interests SET card_subtitle = '' WHERE card_subtitle IS NULL")
            rowcount = cursor.rowcount
            conn.commit()
            self._return_connection(conn)
            return rowcount
        except sqlite3.Error as e:
            logger.error(f"修复空的card_subtitle字段失败: {e}")
            return 0
            
    def find_invalid_dates(self) -> List[Dict[str, Any]]:
        """查找无效的create_time日期格式"""
        query = """
        SELECT id, create_time FROM interests
        WHERE create_time IS NOT NULL AND 
            create_time != '' AND
            strftime('%Y-%m-%d', create_time) IS NULL
        """
        return self._execute_query(query)
        
    def fix_invalid_date(self, item_id: str) -> bool:
        """修复指定条目的无效日期"""
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute("UPDATE interests SET create_time = CURRENT_TIMESTAMP WHERE id = ?", (item_id,))
            conn.commit()
            self._return_connection(conn)
            return True
        except sqlite3.Error as e:
            logger.error(f"修复无效日期失败: {e}")
            return False
            
    def get_stats(self) -> Dict[str, Any]:
        """获取数据提供者的运行状态"""
        avg_query_time = 0
        if self.query_count > 0:
            avg_query_time = self.total_query_time / self.query_count
            
        return {
            'query_count': self.query_count,
            'total_query_time': round(self.total_query_time, 2),
            'avg_query_time': round(avg_query_time, 4),
            'slow_query_count': self.slow_query_count
        }