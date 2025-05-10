import re
import time
from typing import Dict, List, Any, Optional
from datetime import datetime
from utils.logger import get_logger
from services.analytics.data_provider import StatisticsDataProvider

# 配置日志
logger = get_logger("analyzer")

class DataAnalyzer:
    """数据分析器，专注于数据转换和业务逻辑处理
    
    负责从原始数据中提取、转换、分析出有意义的统计结果
    """
    
    # 缓存配置
    CACHE_TTL = 300  # 缓存有效期（秒）
    
    def __init__(self, data_provider=None, db_instance=None):
        """初始化数据分析器
        
        参数:
            data_provider: 数据提供者实例，如果为None则创建新实例
            db_instance: 数据库实例，用于创建数据提供者
        """
        # 初始化数据提供者
        self.provider = data_provider or StatisticsDataProvider(db_instance)
        
        # 缓存
        self._cache = {}
        self._cache_times = {}
        
        logger.info("数据分析器初始化完成")
        
    def _get_cached_or_fetch(self, key: str, fetch_func, *args, **kwargs):
        """从缓存获取数据，如果缓存不存在或已过期则重新获取
        
        参数:
            key: 缓存键
            fetch_func: 获取数据的函数
            args, kwargs: 传递给fetch_func的参数
            
        返回:
            获取或计算的结果
        """
        now = time.time()
        
        # 检查缓存是否有效
        if (key in self._cache and key in self._cache_times and 
            now - self._cache_times[key] < self.CACHE_TTL):
            logger.debug(f"从缓存获取数据: {key}")
            return self._cache[key]
            
        # 缓存不存在或已过期，重新获取数据
        logger.debug(f"重新获取数据: {key}")
        result = fetch_func(*args, **kwargs)
        
        # 更新缓存
        self._cache[key] = result
        self._cache_times[key] = now
        
        return result
        
    def clear_cache(self):
        """清除所有缓存"""
        self._cache.clear()
        self._cache_times.clear()
        logger.info("已清除所有分析缓存")
        
    def _extract_metadata(self, content_type: str, card_subtitle: str) -> Dict[str, Any]:
        """从card_subtitle提取元数据
        
        参数:
            content_type: 内容类型 (movie, tv, book 等)
            card_subtitle: 卡片副标题文本
            
        返回:
            Dict: 包含提取的元数据的字典
        """
        # 类型检查和空值处理
        if not isinstance(content_type, str):
            content_type = str(content_type) if content_type is not None else ""
        if not isinstance(card_subtitle, str):
            card_subtitle = str(card_subtitle) if card_subtitle is not None else ""
            
        # 早期返回：如果subtitle为空，直接返回空字典    
        if not card_subtitle.strip():
            return {}
            
        metadata = {}
        
        # 安全分割，处理可能的异常字符
        try:
            parts = card_subtitle.split(" / ")
            # 过滤空部分
            parts = [p.strip() for p in parts if p.strip()]
        except Exception as e:
            logger.warning(f"分割副标题失败: {card_subtitle}, 错误: {e}")
            return {}
        
        # 根据内容类型使用不同的提取策略
        if isinstance(content_type, str) and content_type.lower() in ["movie", "tv"]:
            # 电影/电视剧格式："2025 / 中国大陆 美国 / 悬疑 犯罪 / 导演"
            if len(parts) >= 2:
                # 处理多地区情况，空格分隔
                region_text = parts[1].strip()
                regions = []
                if region_text:
                    regions = [r.strip() for r in region_text.split() if r.strip()]
                metadata["regions"] = regions
                
                # 提取年份（通常在第一部分）
                if len(parts) >= 1:
                    year_text = parts[0].strip()
                    if year_text and year_text.isdigit():
                        try:
                            year = int(year_text)
                            # 合理性检查：年份应在合理范围内
                            if 1800 <= year <= 2100:
                                metadata["year"] = year
                        except ValueError:
                            # 忽略无法转换的年份
                            pass
                    
        elif isinstance(content_type, str) and content_type.lower() == "book":
            # 图书格式："[美] 作者名 / 2025 / 出版社"
            if len(parts) >= 1:
                # 提取作者信息（第一部分）
                author_raw = parts[0].strip()
                
                # 使用正则表达式分离国籍和作者名
                try:
                    author_match = re.match(r'(?:\[([^\]]+)\])?\s*(.*)', author_raw)
                    if author_match:
                        nationality, name = author_match.groups()
                        # 安全处理可能的None值
                        nationality = nationality.strip() if nationality else ""
                        name = name.strip() if name else author_raw.strip()
                        
                        if name:  # 确保名称非空
                            metadata["author"] = {
                                "nationality": nationality,
                                "name": name
                            }
                except Exception as e:
                    logger.debug(f"解析作者信息失败: {author_raw}, 错误: {e}")
                    # 如果解析失败，仍保存原始文本
                    metadata["author"] = {
                        "nationality": "",
                        "name": author_raw
                    }
                
                # 提取出版社（通常在第三部分）
                if len(parts) >= 3:
                    publisher = parts[2].strip()
                    if publisher:
                        metadata["publisher"] = publisher
                    
                # 提取年份（通常在第二部分）
                if len(parts) >= 2:
                    year_text = parts[1].strip()
                    try:
                        if year_text and year_text.isdigit():
                            year = int(year_text)
                            # 合理性检查
                            if 1800 <= year <= 2100:
                                metadata["year"] = year
                    except ValueError:
                        # 忽略无法转换的年份
                        pass
                    
        elif isinstance(content_type, str) and content_type.lower() == "game":
            # 游戏格式多变，尝试提取开发商和年份
            if len(parts) >= 1:
                developer = parts[0].strip()
                if developer:
                    metadata["developer"] = developer
                
            # 尝试从任何部分提取年份
            for part in parts:
                if not isinstance(part, str):
                    continue
                    
                try:
                    # 使用更严格的年份匹配模式
                    year_match = re.search(r'\b(19\d{2}|20\d{2})\b', part)
                    if year_match:
                        year = int(year_match.group(1))
                        # 合理性检查
                        if 1970 <= year <= 2100:  # 游戏年份通常不早于1970年
                            metadata["year"] = year
                            break
                except (ValueError, TypeError, AttributeError) as e:
                    logger.debug(f"从部分 '{part}' 提取年份失败: {e}")
                    continue
        
        return metadata
    
    def get_basic_statistics(self, type_: Optional[str] = None) -> Dict[str, Any]:
        """获取基本统计信息
        
        参数:
            type_: 可选，内容类型(movie, tv, book 等)，如不提供则返回所有类型的统计
            
        返回:
            包含统计数据的字典
        """
        # 验证type_参数
        if type_ is not None:
            if not isinstance(type_, str):
                logger.warning(f"type_参数类型错误: {type(type_)}，尝试转换为字符串")
                try:
                    type_ = str(type_)
                except:
                    logger.warning("无法将type_转换为字符串，使用None")
                    type_ = None
            elif type_.strip() == '':
                logger.debug("type_为空字符串，视为None")
                type_ = None
                
        cache_key = f"basic_stats_{type_ or 'all'}"
        
        return self._get_cached_or_fetch(cache_key, self._compute_basic_statistics, type_)

        
    def _compute_basic_statistics(self, type_: Optional[str] = None) -> Dict[str, Any]:
        """计算基本统计信息
        
        参数:
            type_: 内容类型过滤
            
        返回:
            基本统计信息
        """
        try:
            if type_:
                # 如果指定了类型，则获取该类型的详细统计
                return self.get_content_type_statistics(type_)
            else:
                # 否则获取所有类型的概览统计
                # 获取总数
                total_count = self.provider.get_total_count()
                
                # 按类型统计
                type_counts = self.provider.get_type_counts()
                
                # 按状态统计
                status_counts = self.provider.get_status_counts()
                
                return {
                    "total_count": total_count,
                    "type_counts": type_counts,
                    "status_counts": status_counts
                }
                
        except Exception as e:
            logger.error(f"获取基本统计信息失败: {e}")
            return {
                "total_count": 0,
                "type_counts": {},
                "status_counts": {"done": 0, "doing": 0, "wish": 0}
            }

    def get_content_type_statistics(self, type_: str) -> Dict[str, Any]:
        """获取特定内容类型的统计信息
        
        参数:
            type_: 内容类型 (movie, tv, book 等)
            
        返回:
            包含该类型详细统计信息的字典
        """
        # 验证必要参数
        if type_ is None:
            logger.error("未提供type_参数")
            return {
                "status": {},
                "years": {},
                "genres": {},
                "ratings": {},
                "total": 0,
                "error": "未提供内容类型参数"
            }
            
        # 类型转换
        if not isinstance(type_, str):
            logger.warning(f"type_参数类型错误: {type(type_)}，尝试转换为字符串")
            try:
                type_ = str(type_)
            except:
                logger.error("type_参数转换失败")
                return {
                    "status": {},
                    "years": {},
                    "genres": {},
                    "ratings": {},
                    "total": 0,
                    "error": "内容类型参数无效"
                }
        
        # 验证内容是否为已知类型
        valid_types = ["movie", "tv", "book", "game", "music", "drama"]
        if type_.lower() not in valid_types:
            logger.warning(f"未知的内容类型: {type_}")
            # 仍然继续处理，因为可能是新增的类型
        
        type_ = type_.lower()  # 规范化为小写
        cache_key = f"type_stats_{type_}"
        
        return self._get_cached_or_fetch(cache_key, self._compute_content_type_statistics, type_)
            
    def _compute_content_type_statistics(self, type_: str) -> Dict[str, Any]:
        """计算特定内容类型的统计信息
        
        参数:
            type_: 内容类型 (movie, tv, book 等)
            
        返回:
            详细统计信息
        """
        try:
            # 按状态统计
            status_stats = self.provider.get_status_counts_by_type(type_)
            
            # 按年份统计
            year_stats = self.provider.get_year_stats_by_type(type_)
            
            # 标签/分类统计
            genres_stats = self.provider.get_genres_by_type(type_)
            
            # 评分分布
            rating_stats = self.provider.get_rating_groups_by_type(type_)
            
            # 提取内容类型特有的元数据
            metadata_stats = self._extract_type_specific_metadata(type_)
            
            # 合并所有统计数据
            result = {
                "status": status_stats,
                "years": year_stats,
                "genres": genres_stats,
                "ratings": rating_stats,
                "total": sum(status_stats.values())
            }
            
            # 添加类型特有的统计数据
            result.update(metadata_stats)
            
            return result
            
        except Exception as e:
            logger.error(f"获取内容类型 {type_} 的统计信息失败: {e}")
            return {
                "status": {},
                "years": {},
                "genres": {},
                "ratings": {},
                "total": 0
            }

    def _extract_type_specific_metadata(self, type_: str) -> Dict[str, Dict[str, int]]:
        """提取特定内容类型的额外元数据统计
        
        参数:
            type_: 内容类型
            
        返回:
            包含元数据统计的字典
        """
        # 参数验证
        if not isinstance(type_, str):
            logger.warning(f"type_参数类型错误: {type(type_)}，尝试转换为字符串")
            try:
                type_ = str(type_)
            except:
                logger.error("type_参数无效，返回空结果")
                return {
                    "regions": {},
                    "publishers": {},
                    "authors": {},
                    "developers": {}
                }
        
        # 规范化为小写，确保一致性
        type_ = type_.lower()
        
        # 初始化结果字典
        result = {
            "regions": {},      # 地区统计 (movie/tv)
            "publishers": {},   # 出版社统计 (book)
            "authors": {},      # 作者统计 (book)
            "developers": {}    # 开发商统计 (game)
        }
        
        try:
            # 查询所有card_subtitle值和计数
            card_data = self.provider.get_card_subtitles_by_type(type_)

            # 验证返回数据是列表类型
            if not isinstance(card_data, list):
                logger.warning(f"card_data不是列表类型: {type(card_data)}")
                return result

            for row in card_data:
                # 验证行数据是字典类型
                if not isinstance(row, dict):
                    logger.debug(f"跳过非字典行: {row}")
                    continue
                    
                card_subtitle = row.get("card_subtitle", "")
                count = row.get("count", 0)
                
                # 确保count是整数
                try:
                    count = int(count)
                    if count <= 0:
                        continue
                except (TypeError, ValueError):
                    logger.debug(f"无效的count值: {count}")
                    continue
                    
                if not card_subtitle:
                    continue
                
                # 使用通用元数据提取方法解析数据
                metadata = self._extract_metadata(type_, card_subtitle)
                
                # 根据内容类型处理不同的元数据
                if type_ in ["movie", "tv"]:
                    # 处理地区数据，适当处理多地区情况
                    if "regions" in metadata and isinstance(metadata["regions"], list):
                        for region in metadata["regions"]:
                            if region and isinstance(region, str):
                                result["regions"][region] = result["regions"].get(region, 0) + count
                
                elif type_ == "book":
                    # 处理出版社
                    if "publisher" in metadata and metadata["publisher"]:
                        publisher = metadata["publisher"]
                        if isinstance(publisher, str):
                            result["publishers"][publisher] = result["publishers"].get(publisher, 0) + count
                    
                    # 处理作者，排除年份干扰
                    if "author" in metadata and isinstance(metadata["author"], dict):
                        author_info = metadata["author"]
                        author_name = author_info.get("name", "")
                        if author_name and isinstance(author_name, str):
                            # 如果有国籍信息，添加到作者名前
                            nationality = author_info.get("nationality", "")
                            if nationality and isinstance(nationality, str):
                                author_name = f"[{nationality}] {author_name}"
                            result["authors"][author_name] = result["authors"].get(author_name, 0) + count
                
                elif type_ == "game":
                    # 处理开发商
                    if "developer" in metadata and metadata["developer"]:
                        developer = metadata["developer"]
                        if isinstance(developer, str):
                            result["developers"][developer] = result["developers"].get(developer, 0) + count
        
        except Exception as e:
            logger.warning(f"提取类型 {type_} 的元数据统计时出错: {e}")
        
        return result

    def get_rating_statistics(self, type_: Optional[str] = None) -> Dict[str, Any]:
        """获取评分统计数据
        
        参数:
            type_: 可选，内容类型过滤 (movie, tv, book 等)
            
        返回:
            dict: 包含评分统计数据的字典
        """
        # 验证type_参数
        if type_ is not None:
            if not isinstance(type_, str):
                logger.warning(f"type_参数类型错误: {type(type_)}，尝试转换为字符串")
                try:
                    type_ = str(type_)
                except:
                    logger.warning("无法将type_转换为字符串，使用None")
                    type_ = None
            elif type_.strip() == '':
                type_ = None
        
        if type_ is not None:
            type_ = type_.lower()  # 规范化为小写
            
        cache_key = f"rating_stats_{type_ or 'all'}"
        
        return self._get_cached_or_fetch(cache_key, self._compute_rating_statistics, type_)
          
    def _compute_rating_statistics(self, type_: Optional[str] = None) -> Dict[str, Any]:
        """计算评分统计数据
        
        参数:
            type_: 内容类型过滤
            
        返回:
            评分统计数据
        """
        try:
            # 直接使用数据提供者获取评分统计
            return self.provider.get_rating_stats(type_)
        except Exception as e:
            logger.error(f"获取评分统计失败: {e}")
            return {
                'stats': {
                    'average': 0,
                    'max': 0,
                    'min': 0,
                    'count': 0
                },
                'distribution': [0] * 10
            }

    def get_year_statistics(self, type_: Optional[str] = None) -> Dict[str, Any]:
        """获取年份分布统计
        
        参数:
            type_: 可选，内容类型过滤 (movie, tv, book 等)
            
        返回:
            dict: 包含年份标签和数据的字典
        """
        # 验证type_参数
        if type_ is not None:
            if not isinstance(type_, str):
                logger.warning(f"type_参数类型错误: {type(type_)}，尝试转换为字符串")
                try:
                    type_ = str(type_)
                except:
                    logger.warning("无法将type_转换为字符串，使用None")
                    type_ = None
            elif type_.strip() == '':
                type_ = None
        
        if type_ is not None:
            type_ = type_.lower()  # 规范化为小写
            
        cache_key = f"year_stats_{type_ or 'all'}"
        
        return self._get_cached_or_fetch(cache_key, self._compute_year_statistics, type_)

    
    def _compute_year_statistics(self, type_: Optional[str] = None) -> Dict[str, Any]:
        """计算年份分布统计
        
        参数:
            type_: 内容类型过滤
            
        返回:
            年份分布统计
        """
        try:
            # 获取基本年份分布数据
            year_data = self.provider.get_year_distribution(type_)
            
            # 添加类型数据字段，为未来扩展保留
            year_data['type_data'] = {}
            
            # 可选:填充缺失年份 
            if 'labels' in year_data and len(year_data['labels']) > 1:
                try:
                    # 获取年份范围
                    first_year = int(year_data['labels'][0])
                    last_year = int(year_data['labels'][-1])
                    
                    # 如果范围合理，填充缺失年份
                    if 0 < last_year - first_year < 100:  # 避免过大的范围
                        # 创建字典以便查找
                        year_dict = dict(zip(year_data['labels'], year_data['all']))
                        
                        # 创建完整序列
                        full_years = []
                        full_counts = []
                        
                        for year in range(first_year, last_year + 1):
                            full_years.append(str(year))
                            full_counts.append(year_dict.get(str(year), 0))
                            
                        # 更新返回数据
                        year_data['labels'] = full_years
                        year_data['all'] = full_counts
                except Exception as e:
                    logger.warning(f"填充缺失年份失败: {e}")
            
            return year_data
            
        except Exception as e:
            logger.error(f"获取年份统计失败: {e}")
            return {
                'labels': [],
                'all': [],
                'type_data': {}
            }

    def get_genre_statistics(self, type_: Optional[str] = None, limit: int = 20) -> List[Dict[str, Any]]:
        """获取标签/分类统计数据
        
        参数:
            type_: 可选，内容类型过滤 (movie, tv, book 等)
            limit: 返回的标签数量上限，默认20，范围1-100
            
        返回:
            list: 包含标签统计的列表，每项为字典 {'name': 标签名, 'count': 数量}
        """
        # 参数验证和规范化
        if type_ is not None and not isinstance(type_, str):
            logger.warning(f"type_参数类型错误: {type(type_)}，尝试转换为字符串")
            try:
                type_ = str(type_)
            except:
                type_ = None
                
        # 验证limit参数
        try:
            limit = int(limit)
            if limit < 1:
                logger.warning(f"limit参数太小: {limit}，使用默认值20")
                limit = 20
            elif limit > 100:
                logger.warning(f"limit参数太大: {limit}，限制为100")
                limit = 100
        except (TypeError, ValueError):
            logger.warning(f"limit参数类型错误: {limit}，使用默认值20")
            limit = 20
            
        cache_key = f"genre_stats_{type_ or 'all'}_{limit}"
        
        return self._get_cached_or_fetch(cache_key, self._compute_genre_statistics, type_, limit)
    
    def _compute_genre_statistics(self, type_: Optional[str] = None, limit: int = 20) -> List[Dict[str, Any]]:
        """计算标签/分类统计数据
        
        参数:
            type_: 内容类型过滤
            limit: 返回数量限制
            
        返回:
            标签统计列表
        """
        try:
            # 直接使用数据提供者获取标签分布
            return self.provider.get_genre_distribution(type_, limit)
        except Exception as e:
            logger.error(f"获取标签统计失败: {e}")
            return []
        
    def get_collection_trend(self, period: str = 'month', months: int = 12, 
                        type_: Optional[str] = None) -> Dict[str, List]:
        """获取收藏趋势数据
        
        参数:
            period: 'month'(按月) 或 'year'(按年)
            months: 返回的月份/年份数量，默认12，范围1-120
            type_: 可选，内容类型过滤 (movie, tv, book 等)
            
        返回:
            dict: 包含标签和数据的字典
        """
        # 参数验证和规范化
        if not isinstance(period, str) or period.lower() not in ['month', 'year']:
            logger.warning(f"period参数无效: {period}，使用默认值'month'")
            period = 'month'
        else:
            period = period.lower()
            
        # 验证months参数
        try:
            months = int(months)
            if months < 1:
                logger.warning(f"months参数太小: {months}，使用默认值12")
                months = 12
            elif months > 120:
                logger.warning(f"months参数太大: {months}，限制为120")
                months = 120
        except (TypeError, ValueError):
            logger.warning(f"months参数类型错误: {months}，使用默认值12")
            months = 12
            
        # 验证type_参数
        if type_ is not None and not isinstance(type_, str):
            logger.warning(f"type_参数类型错误: {type(type_)}，尝试转换为字符串")
            try:
                type_ = str(type_)
            except:
                type_ = None
                
        cache_key = f"collection_trend_{period}_{months}_{type_ or 'all'}"
        
        return self._get_cached_or_fetch(
            cache_key, 
            self._compute_collection_trend, 
            period, months, type_
        )
        
    def _compute_collection_trend(self, period: str = 'month', months: int = 12, 
                               type_: Optional[str] = None) -> Dict[str, List]:
        """计算收藏趋势数据
        
        参数:
            period: 时间周期
            months: 月份数量
            type_: 内容类型过滤
            
        返回:
            收藏趋势数据
        """
        try:
            # 获取原始趋势数据（键值对形式）
            trend_data = self.provider.get_collection_trend(period, months, type_)
            
            # 将键值对转换为有序列表
            if trend_data:
                # 按时间排序（从早到晚）
                sorted_periods = sorted(trend_data.keys())
                
                # 如果有数据，处理时间序列的完整性
                if sorted_periods:
                    # 确保时间序列是完整的（填充缺失的月份/年份）
                    if len(sorted_periods) >= 2:
                        first_period = sorted_periods[0]
                        last_period = sorted_periods[-1]
                        
                        # 生成完整的时间序列
                        complete_periods = []
                        
                        if period.lower() == 'month':
                            # 月份序列
                            try:
                                # 解析起始和结束日期
                                start_date = datetime.strptime(first_period, '%Y-%m')
                                end_date = datetime.strptime(last_period, '%Y-%m')
                                
                                # 生成所有月份
                                current = start_date
                                while current <= end_date:
                                    period_key = current.strftime('%Y-%m')
                                    complete_periods.append(period_key)
                                    
                                    # 增加一个月
                                    year = current.year + ((current.month) // 12)
                                    month = (current.month % 12) + 1
                                    current = datetime(year, month, 1)
                            except Exception as e:
                                logger.warning(f"生成月份序列失败: {e}")
                                complete_periods = sorted_periods
                                
                        elif period.lower() == 'year':
                            # 年份序列
                            try:
                                start_year = int(first_period)
                                end_year = int(last_period)
                                complete_periods = [str(year) for year in range(start_year, end_year + 1)]
                            except Exception as e:
                                logger.warning(f"生成年份序列失败: {e}")
                                complete_periods = sorted_periods
                        else:
                            complete_periods = sorted_periods
                            
                        # 用0填充缺失值
                        labels = complete_periods
                        values = [trend_data.get(p, 0) for p in complete_periods]
                    else:
                        # 只有一个时间点
                        labels = sorted_periods
                        values = [trend_data[p] for p in sorted_periods]
                else:
                    labels = []
                    values = []
                    
                return {
                    'labels': labels,
                    'values': values
                }
            else:
                return {
                    'labels': [],
                    'values': []
                }
                
        except Exception as e:
            logger.error(f"获取收藏趋势失败: {e}")
            return {
                'labels': [],
                'values': []
            }

    def get_movie_statistics(self) -> Dict[str, Any]:
        """获取电影/电视剧特定统计
        
        返回:
            dict: 包含电影特有统计数据的字典
        """
        cache_key = "movie_stats"
        
        return self._get_cached_or_fetch(cache_key, self._compute_movie_statistics)
        
    def _compute_movie_statistics(self) -> Dict[str, Any]:
        """计算电影/电视剧特定统计
        
        返回:
            电影特定统计结果
        """
        try:
            movie_stats = {}
            tv_stats = {}
            
            # 获取电影统计
            movie_basic = self.get_content_type_statistics('movie')
            if movie_basic:
                movie_stats = {
                    'total': movie_basic.get('total', 0),
                    'status': movie_basic.get('status', {}),
                    'regions': movie_basic.get('regions', {})
                }
            
            # 获取电视剧统计
            tv_basic = self.get_content_type_statistics('tv')
            if tv_basic:
                tv_stats = {
                    'total': tv_basic.get('total', 0),
                    'status': tv_basic.get('status', {}),
                    'regions': tv_basic.get('regions', {})
                }
                
            # 获取年代分布
            decades = self.provider.get_movie_decades()
                
            # 获取评分最高的电影/电视剧标签
            top_genres = self.provider.get_top_movie_genres()
            
            return {
                'movie': movie_stats,
                'tv': tv_stats,
                'decades': decades,
                'top_genres': top_genres
            }
            
        except Exception as e:
            logger.error(f"获取电影统计失败: {e}")
            return {
                'movie': {'total': 0, 'status': {}, 'regions': {}},
                'tv': {'total': 0, 'status': {}, 'regions': {}},
                'decades': {},
                'top_genres': []
            }

    def get_book_statistics(self) -> Dict[str, Any]:
        """获取图书特定统计
        
        返回:
            dict: 包含图书特有统计数据的字典
        """
        cache_key = "book_stats"
        
        return self._get_cached_or_fetch(cache_key, self._compute_book_statistics)
        
    def _compute_book_statistics(self) -> Dict[str, Any]:
        """计算图书特定统计
        
        返回:
            图书特定统计结果
        """
        try:
            # 获取图书基本统计
            book_basic = self.get_content_type_statistics('book')
            book_stats = {
                'total': book_basic.get('total', 0),
                'status': book_basic.get('status', {}),
                'publishers': book_basic.get('publishers', {}),
                'authors': book_basic.get('authors', {})
            }
            
            # 提取前10位作者和出版社
            top_authors = []
            for author, count in sorted(book_stats['authors'].items(), key=lambda x: x[1], reverse=True)[:10]:
                top_authors.append({'name': author, 'count': count})
                
            top_publishers = []
            for publisher, count in sorted(book_stats['publishers'].items(), key=lambda x: x[1], reverse=True)[:10]:
                top_publishers.append({'name': publisher, 'count': count})
                
            # 获取阅读趋势
            reading_trend = self.provider.get_book_reading_trend()
                
            return {
                'basic': book_stats,
                'top_authors': top_authors,
                'top_publishers': top_publishers,
                'reading_trend': reading_trend
            }
            
        except Exception as e:
            logger.error(f"获取图书统计失败: {e}")
            return {
                'basic': {'total': 0, 'status': {}, 'publishers': {}, 'authors': {}},
                'top_authors': [],
                'top_publishers': [],
                'reading_trend': {'labels': [], 'values': []}
            }

    def get_game_statistics(self) -> Dict[str, Any]:
        """获取游戏特定统计
        
        返回:
            dict: 包含游戏特有统计数据的字典
        """
        cache_key = "game_stats"
        
        return self._get_cached_or_fetch(cache_key, self._compute_game_statistics)
        
    def _compute_game_statistics(self) -> Dict[str, Any]:
        """计算游戏特定统计
        
        返回:
            游戏特定统计结果
        """
        try:
            # 获取游戏基本统计
            game_basic = self.get_content_type_statistics('game')
            game_stats = {
                'total': game_basic.get('total', 0),
                'status': game_basic.get('status', {}),
                'developers': game_basic.get('developers', {})
            }
            
            # 提取前10位开发商
            top_developers = []
            for developer, count in sorted(game_stats['developers'].items(), key=lambda x: x[1], reverse=True)[:10]:
                top_developers.append({'name': developer, 'count': count})
                
            # 获取游戏年份统计
            year_stats = self.provider.get_game_year_stats()
                
            return {
                'basic': game_stats,
                'top_developers': top_developers,
                'year_stats': year_stats
            }
            
        except Exception as e:
            logger.error(f"获取游戏统计失败: {e}")
            return {
                'basic': {'total': 0, 'status': {}, 'developers': {}},
                'top_developers': [],
                'year_stats': {'labels': [], 'scores': [], 'counts': []}
            }
    
    def _log_execution_time(self, method_name, start_time):
        """记录方法执行时间"""
        end_time = time.time()
        execution_time = end_time - start_time
        logger.debug(f"方法 {method_name} 执行时间: {execution_time:.2f}秒")

    def get_complete_statistics(self) -> Dict[str, Any]:
        """获取完整的统计数据（用于首页或统计页面）
        
        返回:
            dict: 包含所有统计数据的字典
        """
        cache_key = "complete_stats"
        
        return self._get_cached_or_fetch(cache_key, self._compute_complete_statistics)
        
    def _compute_complete_statistics(self) -> Dict[str, Any]:
        """计算完整统计数据
        
        返回:
            完整统计结果
        """
        try:
            start_time = time.time()
            
            # 1. 获取基本统计数据 - 使用安全参数
            basic_stats = self.get_basic_statistics(type_=None)
            logger.debug("基本统计数据获取完成")
            
            # 2. 获取评分统计 - 使用安全参数
            rating_stats = self.get_rating_statistics(type_=None)
            logger.debug("评分统计数据获取完成")
            
            # 3. 获取年份统计 - 使用安全参数
            year_stats = self.get_year_statistics(type_=None)
            logger.debug("年份统计数据获取完成")
            
            # 4. 获取标签统计 - 使用安全参数和限制
            limit = 30  # 固定值，避免潜在的参数问题
            top_tags = self.get_genre_statistics(type_=None, limit=limit)
            logger.debug("标签统计数据获取完成")
            
            # 5. 获取收藏趋势 - 使用安全参数
            trend_data = self.get_collection_trend(period='month', months=12, type_=None)
            logger.debug("收藏趋势数据获取完成")
            
            # 记录总执行时间
            self._log_execution_time("get_complete_statistics", start_time)
            
            # 整合所有统计数据
            return {
                'basic': basic_stats,
                'ratings': rating_stats,
                'years': year_stats,
                'tags': top_tags,
                'trends': trend_data
            }
            
        except Exception as e:
            logger.error(f"获取完整统计数据失败: {e}")
            # 返回空结果
            return {
                'basic': {'total_count': 0, 'type_counts': {}, 'status_counts': {}},
                'ratings': {'stats': {}, 'distribution': []},
                'years': {'labels': [], 'all': []},
                'tags': [],
                'trends': {'labels': [], 'values': []}
            }

    def fix_invalid_data(self) -> Dict[str, int]:
        """修复数据库中的无效数据
        
        修复可能导致统计失败的无效数据格式
        
        返回:
            dict: 修复的记录数统计
        """
        fixes = {
            'genres': 0,
            'card_subtitle': 0,
            'create_time': 0,
            'total': 0
        }
        
        try:
            # 1. 修复无效的genres JSON
            invalid_genres = self.provider.find_invalid_genres()
            for row in invalid_genres:
                if self.provider.fix_invalid_genres(row.get('id')):
                    fixes['genres'] += 1
                
            # 2. 修复空的card_subtitle
            subtitle_count = self.provider.fix_null_card_subtitles()
            fixes['card_subtitle'] = subtitle_count
            
            # 3. 修复无效的create_time格式
            invalid_dates = self.provider.find_invalid_dates()
            for row in invalid_dates:
                if self.provider.fix_invalid_date(row.get('id')):
                    fixes['create_time'] += 1
            
            # 计算总修复数
            fixes['total'] = fixes['genres'] + fixes['card_subtitle'] + fixes['create_time']
            
            # 如果有修复，清除缓存
            if fixes['total'] > 0:
                self.clear_cache()
                logger.info(f"已修复 {fixes['total']} 条无效数据记录")
                
            return fixes
            
        except Exception as e:
            logger.error(f"修复无效数据失败: {e}")
            return fixes
            
    def get_analytics_status(self) -> Dict[str, Any]:
        """获取分析器状态信息
        
        返回:
            dict: 状态信息
        """
        # 获取数据提供者状态
        provider_stats = self.provider.get_stats()
        
        # 添加缓存信息
        cache_stats = {
            'size': len(self._cache),
            'keys': list(self._cache.keys())
        }
        
        return {
            'provider': provider_stats,
            'cache': cache_stats
        }