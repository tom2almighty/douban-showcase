import os
import json
import sqlite3
import time
import threading
from retrying import retry
from typing import Dict, List, Any, Optional
from datetime import datetime
from utils.logger import get_logger

# 配置日志
logger = get_logger("database")

class Database:
    """处理与SQLite数据库的所有交互"""
    
    # 连接池大小
    MAX_POOL_SIZE = 5
    
    def __init__(self, db_path: str = None):
        """初始化数据库连接
        
        参数:
            db_path: 数据库文件路径，如果为None，则使用环境变量或默认路径
        """
        if db_path is None:
            db_path = os.getenv("SQLITE_DB_PATH", "data/douban.db")
            
        # 确保数据库目录存在
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        
        self.db_path = db_path
        logger.info(f"初始化数据库连接: {self.db_path}")
        
        # 连接池
        self._connection_pool = []
        self._pool_lock = threading.Lock()
        
        # 初始化连接池
        for _ in range(2):  # 预创建两个连接
            try:
                conn = self._create_connection()
                self._return_to_pool(conn)
            except sqlite3.Error as e:
                logger.warning(f"预创建连接失败: {e}")
        
        # 检查并初始化数据库
        self._init_database()
        
    def _create_connection(self) -> sqlite3.Connection:
        """创建一个新的数据库连接"""
        conn = sqlite3.connect(self.db_path, timeout=30)
        conn.row_factory = sqlite3.Row
        # 启用外键约束
        conn.execute("PRAGMA foreign_keys = ON")
        # 优化写入性能
        conn.execute("PRAGMA journal_mode = WAL")
        return conn
    
    def _get_connection_from_pool(self) -> Optional[sqlite3.Connection]:
        """从连接池获取连接"""
        with self._pool_lock:
            if self._connection_pool:
                return self._connection_pool.pop()
        return None
    
    def _return_to_pool(self, conn: sqlite3.Connection) -> None:
        """将连接归还到连接池"""
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
            # 连接已失效，不归还池
            pass
            
        # 如果池已满或连接无效，关闭连接
        try:
            conn.close()
        except:
            pass
        
    @retry(stop_max_attempt_number=5, 
           wait_exponential_multiplier=1000, 
           wait_exponential_max=10000,
           retry_on_exception=lambda e: isinstance(e, sqlite3.OperationalError) and "database is locked" in str(e))
    def _get_connection(self) -> sqlite3.Connection:
        """获取数据库连接，优先从连接池获取，如果失败则创建新连接"""
        conn = self._get_connection_from_pool()
        if conn is not None:
            try:
                # 验证连接有效性
                conn.execute("SELECT 1")
                return conn
            except sqlite3.Error:
                # 连接无效，关闭并创建新连接
                try:
                    conn.close()
                except:
                    pass
        
        # 创建新连接
        for attempt in range(5):  # 尝试5次
            try:
                return self._create_connection()
            except sqlite3.OperationalError as e:
                if "database is locked" in str(e) and attempt < 4:
                    time.sleep(2 ** attempt)  # 指数退避
                    continue
                raise
        
        # 如果达到这里，所有尝试都失败
        raise sqlite3.OperationalError(f"无法创建数据库连接: {self.db_path}")
    
    def execute_query(self, query: str, params: tuple = ()) -> List[Dict[str, Any]]:
        """通用查询执行方法
        
        参数:
            query: SQL查询
            params: 查询参数
            
        返回:
            查询结果的字典列表
        """
        conn = None
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute(query, params)
            
            if query.strip().upper().startswith(("SELECT", "PRAGMA")):
                rows = cursor.fetchall()
                results = []
                for row in rows:
                    item = {}
                    for key in row.keys():
                        item[key] = row[key]
                    results.append(item)
                return results
            else:
                conn.commit()
                return [{"rowcount": cursor.rowcount, "lastrowid": cursor.lastrowid}]
                
        except sqlite3.Error as e:
            if conn:
                try:
                    conn.rollback()
                except:
                    pass
            logger.error(f"执行查询失败: {e}, 查询: {query}")
            raise
        finally:
            if conn:
                self._return_to_pool(conn)
    
    def execute_script(self, script: str) -> bool:
        """执行SQL脚本
        
        参数:
            script: SQL脚本内容
            
        返回:
            执行是否成功
        """
        conn = None
        try:
            conn = self._get_connection()
            conn.executescript(script)
            conn.commit()
            return True
        except sqlite3.Error as e:
            if conn:
                try:
                    conn.rollback()
                except:
                    pass
            logger.error(f"执行脚本失败: {e}")
            return False
        finally:
            if conn:
                self._return_to_pool(conn)
    
    def _init_database(self):
        """确保数据库结构已创建"""
        try:
            # 检查schema_version表是否存在
            result = self.execute_query(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='schema_version'"
            )
            
            if not result:
                logger.info("数据库结构不存在，开始初始化")
                
                # 读取SQL初始化脚本
                project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))  # 到达项目根目录
                script_path = os.path.join(project_root, "src", "scripts", "init_db.sql")
                
                if os.path.exists(script_path):
                    with open(script_path, 'r', encoding='utf-8') as f:
                        sql_script = f.read()
                        
                    # 执行SQL脚本（其中已包含版本插入语句，不要再次插入）
                    if self.execute_script(sql_script):
                        logger.info("数据库结构初始化完成")
                    else:
                        logger.error("执行SQL初始化脚本失败")
                else:
                    logger.error(f"SQL初始化脚本不存在: {script_path}")
            else:
                logger.info("数据库结构已存在")
                    
        except Exception as e:
            logger.error(f"初始化数据库失败: {e}")
            raise
    
    def _ensure_string(self, value):
        """将各种类型安全转换为字符串"""
        if value is None:
            return ""
        if isinstance(value, list):
            if not value:
                return ""
            return str(value[0])
        return str(value)

    def _validate_interest_data(self, data):
        """验证兴趣数据的有效性"""
        required_fields = ["id", "status", "create_time"]
        for field in required_fields:
            if field not in data:
                return False, f"缺少必要字段: {field}"
        
        if "subject" not in data or not isinstance(data["subject"], dict):
            return False, "缺少有效的subject字段"
        
        required_subject_fields = ["title"]
        for field in required_subject_fields:
            if field not in data["subject"]:
                return False, f"subject缺少必要字段: {field}"
            
        required_fields = ["subtype"]
        for field in required_fields:
            if field not in data["subject"]:
                return False, f"subject缺少必要字段: {field}"
            elif not data["subject"][field]:  # 检查是否为空
                return False, f"subject字段 {field} 不能为空"
            
        return True, ""

    def get_interest_count(self, type_: str, status: str) -> int:
        """获取指定类型和状态的条目数量
        
        参数:
            type_: 内容类型 (movie, tv, book 等)
            status: 状态 (mark, doing, done)
            
        返回:
            int: 条目数量
        """
        try:
            result = self.execute_query(
                "SELECT COUNT(*) AS count FROM interests WHERE type = ? AND status = ?",
                (type_, status)
            )
            return result[0]["count"] if result else 0
            
        except Exception as e:
            logger.error(f"获取条目数量失败: {e}")
            return 0

    @retry(stop_max_attempt_number=5, wait_exponential_multiplier=1000, wait_exponential_max=10000)
    def save_interest(self, interest_data: Dict[str, Any]) -> str:
        """保存或更新一条兴趣数据"""
        conn = None
        try:
            # 验证数据
            is_valid, error_msg = self._validate_interest_data(interest_data)
            if not is_valid:
                logger.error(f"无效的兴趣数据: {error_msg}")
                return None
                
            # 提取interest数据中的关键字段
            interest_id = interest_data.get("id")
            if not interest_id:
                logger.error("兴趣数据缺少ID字段")
                return None
                
            # 安全获取subject字段
            subject = interest_data.get("subject", {})
            if not subject:
                logger.error(f"兴趣数据 {interest_id} 缺少subject字段")
                return None
            
            # 直接使用API返回的原始类型
            subject_type = subject.get("type", "")
  
            # 提取基本信息
            title = self._ensure_string(subject.get("title", ""))
            
            url = self._ensure_string(subject.get("url", ""))

            # 直接使用cover_url字段，降级到嵌套的pic字段
            cover_url = subject.get("cover_url", "")
            if not cover_url:
                cover_obj = subject.get("pic", {})
                if isinstance(cover_obj, dict):
                    cover_url = cover_obj.get("large", cover_obj.get("normal", ""))
            
            # 安全处理评分
            douban_score = 0
            if "rating" in subject and subject["rating"]:
                douban_score = subject["rating"].get("value", 0)
                
            genres = json.dumps(subject.get("genres", []),ensure_ascii=False)
            comment = self._ensure_string(interest_data.get("comment", ""))
            status = self._ensure_string(interest_data.get("status", ""))
            create_time = self._ensure_string(interest_data.get("create_time", ""))
            card_subtitle = self._ensure_string(subject.get("card_subtitle", ""))

            my_rating = 0
            if "rating" in interest_data and interest_data["rating"]:
                my_rating = interest_data["rating"].get("value", 0)

            year = 0
            try:
                # 首先尝试从subject.year字段获取（主要适用于movie和tv）
                year_raw = subject.get("year", "")
                if year_raw and isinstance(year_raw, str) and year_raw.isdigit():
                    year = int(year_raw)
                elif year_raw and isinstance(year_raw, int):
                    year = year_raw
                
                # 如果没有获取到年份且有card_subtitle，尝试从中提取
                if year == 0 and card_subtitle:
                    parts = card_subtitle.split(" / ")
                    
                    # 根据不同内容类型采用不同提取策略
                    if subject_type == "movie" or subject_type == "tv":
                        # movie/tv通常以年份开头: "2025 / 中国大陆 / 悬疑 犯罪"
                        if parts and parts[0].strip().isdigit() and len(parts[0].strip()) == 4:
                            year = int(parts[0].strip())
                            
                    elif subject_type == "book":
                        # 书籍通常年份在第二部分: "[美] 作者 / 2025 / 出版社"
                        for part in parts:
                            part = part.strip()
                            if part.isdigit() and len(part) == 4:
                                potential_year = int(part)
                                if 1500 <= potential_year <= 2100:  # 合理的出版年份范围
                                    year = potential_year
                                    break
                                    
                    elif subject_type == "music":
                        # 音乐通常格式为: "张震岳 / 2005" 或中间可能有其他内容
                        for part in parts:
                            part = part.strip()
                            if part.isdigit() and len(part) == 4:
                                potential_year = int(part)
                                if 1900 <= potential_year <= 2100:  # 合理的发行年份范围
                                    year = potential_year
                                    break
                            # 处理可能包含年份的复合部分，如 "2005 其他文本"
                            elif part and len(part) >= 4:
                                year_str = part[:4]
                                if year_str.isdigit():
                                    potential_year = int(year_str)
                                    if 1900 <= potential_year <= 2100:
                                        year = potential_year
                                        break
                                    
                    # 在save_interest方法的年份提取部分，替换游戏类型的处理逻辑为：

                    elif subject_type == "game":
                        # 游戏格式非常多样，需要多种策略
                        
                        # 1. 尝试多级分隔 - 优先按空格斜杠空格分割，如果分割结果少于2部分，再按单斜杠分割
                        game_parts = parts
                        game_parts = card_subtitle.split("/")
                        
                        # 2. 查找日期格式 YYYY-MM-DD 或纯年份
                        year_found = False
                        
                        # 2.1 先检查最后一部分，因为日期通常在最后
                        if game_parts:
                            last_part = game_parts[-1].strip()
                            # 处理 YYYY-MM-DD 格式
                            if "-" in last_part and len(last_part) >= 10:
                                date_parts = last_part.split("-")
                                if len(date_parts) >= 2 and date_parts[0].isdigit() and len(date_parts[0]) == 4:
                                    potential_year = int(date_parts[0])
                                    if 1980 <= potential_year <= 2100:  # 合理的游戏年份范围
                                        year = potential_year
                                        year_found = True
                                        logger.debug(f"从游戏格式1中提取年份: {potential_year}, 源: {last_part}")
                            # 处理纯年份格式
                            elif last_part.isdigit() and len(last_part) == 4:
                                potential_year = int(last_part)
                                if 1980 <= potential_year <= 2100:
                                    year = potential_year
                                    year_found = True
                                    logger.debug(f"从游戏格式2中提取年份: {potential_year}, 源: {last_part}")
                        
                        # 2.2 如果最后一部分没找到，检查所有部分
                        if not year_found:
                            for part in game_parts:
                                part = part.strip()
                                
                                # 处理 YYYY-MM-DD 格式
                                if "-" in part:
                                    date_segment = part.split("-")[0]
                                    if date_segment.isdigit() and len(date_segment) == 4:
                                        potential_year = int(date_segment)
                                        if 1980 <= potential_year <= 2100:
                                            year = potential_year
                                            year_found = True
                                            logger.debug(f"从游戏格式3中提取年份: {potential_year}, 源: {part}")
                                            break
                                            
                                # 处理纯年份格式
                                elif part.isdigit() and len(part) == 4:
                                    potential_year = int(part)
                                    if 1980 <= potential_year <= 2100:
                                        year = potential_year
                                        year_found = True
                                        logger.debug(f"从游戏格式4中提取年份: {potential_year}, 源: {part}")
                                        break
                        
                        # 3. 最后尝试查找嵌入在文本中的年份
                        if not year_found:
                            # 使用正则表达式查找四位数字年份模式
                            import re
                            year_matches = re.findall(r'\b(19\d{2}|20\d{2})\b', card_subtitle)
                            if year_matches:
                                for match in year_matches:
                                    potential_year = int(match)
                                    if 1980 <= potential_year <= 2100:
                                        year = potential_year
                                        year_found = True
                                        logger.debug(f"从游戏格式5中提取年份: {potential_year}, 源: {match}")
                                        break
                                        
                        if year_found:
                            logger.info(f"游戏 '{title}' 成功提取年份: {year}")
                        else:
                            logger.info(f"游戏 '{title}' 无法提取年份，card_subtitle: {card_subtitle}")
                            
            except (ValueError, TypeError) as e:
                logger.warning(f"提取年份时出错: {e}, subtitle: {card_subtitle}")
                year = 0
            
            
            
            # 将整个数据转换为JSON字符串
            raw_json = json.dumps(interest_data, ensure_ascii=False)
            
            conn = self._get_connection()
            
            # 检查记录是否存在
            result = self.execute_query("SELECT id FROM interests WHERE id = ?", (interest_id,))
            exists = len(result) > 0
            
            if exists:
                # 更新现有记录
                self.execute_query("""
                UPDATE interests
                SET type = ?, status = ?, title = ?, url = ?, cover_url = ?, 
                    douban_score = ?, my_rating = ?, comment = ?,
                    year = ?, genres = ?, card_subtitle = ?, create_time = ?, 
                    update_time = CURRENT_TIMESTAMP, raw_json = ?
                WHERE id = ?
                """, (
                    subject_type, status, title, url, cover_url, 
                    douban_score, my_rating, comment,
                    year, genres, card_subtitle, create_time, raw_json,
                    interest_id
                ))
                logger.debug(f"更新记录: {interest_id}, 标题: {title}")
            else:
                # 插入新记录
                self.execute_query("""
                INSERT INTO interests (
                    id, type, status, title, url, cover_url, 
                    douban_score, my_rating, comment,
                    year, genres, card_subtitle, create_time, raw_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    interest_id, subject_type, status, title, url, cover_url, 
                    douban_score, my_rating, comment,
                    year, genres, card_subtitle, create_time, raw_json
                ))
                logger.info(f"新增记录: {interest_id}, 标题: {title}, 类型: {subject_type}")
            
            return interest_id
            
        except Exception as e:
            logger.error(f"保存兴趣数据失败: {e}")
            return None
        finally:
            if conn:
                self._return_to_pool(conn)
       
    def get_interests(self, 
                      type_: Optional[str] = None, 
                      status: Optional[str] = None,
                      year: Optional[int] = None,
                      genre: Optional[str] = None,
                      search_query: Optional[str] = None,
                      sort_by: str = "create_time",
                      sort_order: str = "desc",
                      limit: int = 100,
                      offset: int = 0) -> List[Dict[str, Any]]:
        """获取兴趣列表，支持筛选和排序
        
        参数:
            type_: 类型过滤 (movie, tv, book 等)
            status: 状态过滤 (mark, doing, done)
            year: 年份过滤
            genre: 按标签/类型筛选 (如 "动作", "冒险" 等)
            card_subtitle_query: 在card_subtitle字段中进行模糊匹配
            sort_by: 排序字段
            sort_order: 排序方向 ('asc' 或 'desc')
            limit: 返回数量限制
            offset: 分页偏移量
            
        返回:
            匹配条件的兴趣记录列表
        """
        try:
            # 构建查询
            query = "SELECT * FROM interests WHERE 1=1"
            params = []
            
            if type_:
                query += " AND type = ?"
                params.append(type_)
                
            if status:
                query += " AND status = ?"
                params.append(status)
                
            if year:
                query += " AND year = ?"
                params.append(year)
                
            if genre:
                query += " AND genres LIKE ?"
                params.append(f"%{genre}%")

            if search_query:
                query += " AND (card_subtitle LIKE ? OR title LIKE ?)"
                params.append(f"%{search_query}%")
                params.append(f"%{search_query}%")
            
            # 添加排序
            valid_sort_fields = [
                "create_time", "year", "douban_score", "my_rating", "title"
            ]
            
            if sort_by not in valid_sort_fields:
                sort_by = "create_time"
                
            if sort_order.lower() not in ["asc", "desc"]:
                sort_order = "desc"
                
            query += f" ORDER BY {sort_by} {sort_order}"
            
            # 添加分页
            query += " LIMIT ? OFFSET ?"
            params.extend([limit, offset])
            
            # 执行查询
            results = self.execute_query(query, params)

            # 处理日期字段
            for item in results:
                if 'create_time' in item and item['create_time'] and isinstance(item['create_time'], str):
                    try:
                        # 假设日期格式为 'YYYY-MM-DD HH:MM:SS'
                        item['create_time'] = datetime.strptime(item['create_time'], '%Y-%m-%d %H:%M:%S')
                    except ValueError:
                        # 如果格式不匹配，保留原始字符串
                        pass

            return results
            
        except Exception as e:
            logger.error(f"查询兴趣列表失败: {e}")
            return []
    
    def get_interest_by_id(self, id: str) -> Optional[Dict[str, Any]]:
        """通过ID获取单个兴趣记录
        
        参数:
            id: 记录ID
            
        返回:
            兴趣记录字典，如果不存在则返回None
        """
        try:
            results = self.execute_query("SELECT * FROM interests WHERE id = ?", (id,))
            return results[0] if results else None
            
        except Exception as e:
            logger.error(f"获取兴趣记录失败: {e}")
            return None
    
    def get_latest_timestamps(self, type_: str) -> Dict[str, str]:
        """获取每种状态的最新时间戳
        
        参数:
            type_: 内容类型 (movie, tv, book 等)
            
        返回:
            包含每种状态最新时间戳的字典
        """
        try:
            results = {}
            for status in ["mark", "doing", "done"]:
                query_result = self.execute_query("""
                SELECT MAX(create_time) as latest
                FROM interests
                WHERE type = ? AND status = ?
                """, (type_, status))
                
                if query_result and "latest" in query_result[0]:
                    results[status] = query_result[0]["latest"] or ""
                else:
                    results[status] = ""
                
            return results
            
        except Exception as e:
            logger.error(f"获取最新时间戳失败: {e}")
            return {"mark": "", "doing": "", "done": ""}
    
    def get_items_without_local_image(self) -> List[Dict[str, Any]]:
        """获取所有没有图片缓存的条目
        
        返回:
            没有图片缓存的条目列表
        """
        try:
            results = self.execute_query("""
            SELECT id, type, title, cover_url
            FROM interests
            WHERE cover_url != '' AND local_path IS NULL
            """)
            
            logger.debug(f"找到 {len(results)} 个没有本地图片的条目")
            return results
            
        except Exception as e:
            logger.error(f"查询无图片缓存条目失败: {e}")
            return []

    def update_interest_local_path(self, item_id: str, local_path: str) -> bool:
        """更新兴趣记录的本地图片路径
        
        参数:
            item_id: 条目ID
            local_path: 本地图片相对路径
            
        返回:
            bool: 更新是否成功
        """
        try:
            result = self.execute_query("""
            UPDATE interests
            SET local_path = ?
            WHERE id = ?
            """, (local_path, item_id))
            
            success = result and result[0]["rowcount"] > 0
            
            if success:
                logger.debug(f"更新条目 {item_id} 的本地图片路径: {local_path}")
            else:
                logger.warning(f"未找到条目 {item_id} 进行图片路径更新")
                
            return success
            
        except Exception as e:
            logger.error(f"更新条目图片路径失败: {e}")
            return False

    def get_distinct_types(self):
        """获取数据库中所有不同的条目类型"""
        try:
            types_result = self.execute_query("SELECT DISTINCT type FROM interests ORDER BY type")
            return [row['type'] for row in types_result] if types_result else []
        except Exception as e:
            logger.error(f"获取类型列表失败: {e}")
            return []
            
    def close_all_connections(self):
        """关闭所有连接池中的连接"""
        with self._pool_lock:
            for conn in self._connection_pool:
                try:
                    conn.close()
                except:
                    pass
            self._connection_pool = []
        logger.info("关闭所有数据库连接")