import time
import threading
from typing import Dict, Any, Optional
from datetime import datetime
from utils.logger import get_logger
from services.analytics.data_provider import StatisticsDataProvider
from services.analytics.analyzer import DataAnalyzer
from services.analytics.formatter import StatisticsFormatter

# 配置日志
logger = get_logger("statistics_service")

class StatisticsService:
    """豆瓣统计服务，作为统计功能的统一接口
    
    整合数据提供者、分析器和格式化器，提供高级统计接口
    """
    
    # 缓存配置
    DASHBOARD_CACHE_TTL = 600  # 仪表板缓存有效期（秒）
    
    def __init__(self, db_instance=None):
        """初始化统计服务
        
        参数:
            db_instance: 数据库实例，传递给数据提供者
        """
        # 创建组件
        self.data_provider = StatisticsDataProvider(db_instance)
        self.analyzer = DataAnalyzer(self.data_provider)
        self.formatter = StatisticsFormatter(self.analyzer)
        
        # 仪表板缓存
        self._dashboard_cache = {}
        self._cache_times = {}
        self._cache_lock = threading.Lock()
        
        # 性能计数器
        self.request_count = 0
        self.error_count = 0
        self.total_processing_time = 0
        
        logger.info("统计服务初始化完成")
        
    def get_dashboard(self, type_: Optional[str] = None, skip_cache: bool = False) -> Dict[str, Any]:
        """获取统计仪表板数据
        
        参数:
            type_: 内容类型过滤 (movie, tv, book 等)，不提供则返回总览
            skip_cache: 是否跳过缓存，强制刷新数据
            
        返回:
            仪表板数据
        """
        self.request_count += 1
        start_time = time.time()
        
        try:
            cache_key = f"dashboard_{type_ or 'all'}"
            
            # 检查缓存
            if not skip_cache:
                cached_data = self._get_from_cache(cache_key)
                if cached_data:
                    logger.debug(f"从缓存获取仪表板数据: {cache_key}")
                    self._update_timing(start_time)
                    return cached_data
            
            # 获取格式化的仪表板数据
            dashboard_data = self.formatter.format_dashboard_statistics(type_)
            
            # 更新缓存
            self._save_to_cache(cache_key, dashboard_data)
            
            self._update_timing(start_time)
            return dashboard_data
            
        except Exception as e:
            self.error_count += 1
            logger.error(f"获取仪表板数据失败: {e}")
            
            # 返回错误信息
            error_response = {
                'error': '获取统计数据失败',
                'message': str(e),
                'timestamp': int(time.time())
            }
            self._update_timing(start_time)
            return error_response
    
    def get_basic_stats(self) -> Dict[str, Any]:
        """获取基础统计信息（快速返回）
        
        返回:
            基础统计数据
        """
        self.request_count += 1
        start_time = time.time()
        
        try:
            # 从缓存获取总体仪表板
            cache_key = "dashboard_all"
            cached_data = self._get_from_cache(cache_key)
            
            if cached_data and 'basic' in cached_data:
                result = {
                    'basic': cached_data['basic'],
                    '_metadata': cached_data.get('_metadata', {})
                }
                self._update_timing(start_time)
                return result
            
            # 如果没有缓存，只获取基础数据
            basic_data = self.analyzer.get_basic_statistics()
            result = {
                'basic': self.formatter.format_basic_statistics(basic_data),
                '_metadata': {
                    'timestamp': int(time.time()),
                    'generated': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                }
            }
            
            self._update_timing(start_time)
            return result
            
        except Exception as e:
            self.error_count += 1
            logger.error(f"获取基础统计数据失败: {e}")
            
            # 返回错误信息
            error_response = {
                'error': '获取基础统计数据失败',
                'message': str(e),
                'timestamp': int(time.time())
            }
            self._update_timing(start_time)
            return error_response
    
    def get_type_specific_stats(self, type_: str) -> Dict[str, Any]:
        """获取特定类型的详细统计信息
        
        参数:
            type_: 内容类型 (movie, tv, book 等)
            
        返回:
            指定类型的详细统计数据
        """
        if not type_:
            return {'error': '未提供内容类型'}
            
        self.request_count += 1
        start_time = time.time()
        
        try:
            # 检查类型是否有效
            valid_types = ['movie', 'tv', 'book', 'music', 'game', 'drama']
            if type_ not in valid_types:
                logger.warning(f"请求了无效的内容类型: {type_}")
                return {'error': f"无效的内容类型: {type_}"}
            
            # 获取该类型的特定统计数据
            if type_ == 'movie' or type_ == 'tv':
                movie_stats = self.analyzer.get_movie_statistics()
                result = self.formatter.format_movie_statistics(movie_stats)
            elif type_ == 'book':
                book_stats = self.analyzer.get_book_statistics()
                result = self.formatter.format_book_statistics(book_stats)
            elif type_ == 'game':
                game_stats = self.analyzer.get_game_statistics()
                result = self.formatter.format_game_statistics(game_stats)
            else:
                # 对于其他类型，只返回基本统计
                content_data = self.analyzer.get_content_type_statistics(type_)
                result = self.formatter.format_content_type_statistics(type_, content_data)
            
            # 添加元数据
            result['_metadata'] = {
                'type': type_,
                'display_name': self.formatter._localize_type_name(type_),
                'timestamp': int(time.time()),
                'generated': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            }
            
            self._update_timing(start_time)
            return result
            
        except Exception as e:
            self.error_count += 1
            logger.error(f"获取类型 {type_} 的统计数据失败: {e}")
            
            # 返回错误信息
            error_response = {
                'error': f'获取 {type_} 统计数据失败',
                'message': str(e),
                'timestamp': int(time.time())
            }
            self._update_timing(start_time)
            return error_response
    
    def get_rating_distribution(self, type_: Optional[str] = None) -> Dict[str, Any]:
        """获取评分分布数据
        
        参数:
            type_: 可选，内容类型过滤
            
        返回:
            评分分布数据
        """
        self.request_count += 1
        start_time = time.time()
        
        try:
            raw_data = self.analyzer.get_rating_statistics(type_)
            result = self.formatter.format_rating_statistics(raw_data)
            
            # 添加元数据
            result['_metadata'] = {
                'type': type_ or 'all',
                'timestamp': int(time.time())
            }
            
            self._update_timing(start_time)
            return result
            
        except Exception as e:
            self.error_count += 1
            logger.error(f"获取评分分布失败: {e}")
            
            # 返回错误信息
            error_response = {
                'error': '获取评分分布失败',
                'message': str(e),
                'timestamp': int(time.time())
            }
            self._update_timing(start_time)
            return error_response
    
    def get_year_distribution(self, type_: Optional[str] = None) -> Dict[str, Any]:
        """获取年份分布数据
        
        参数:
            type_: 可选，内容类型过滤
            
        返回:
            年份分布数据
        """
        self.request_count += 1
        start_time = time.time()
        
        try:
            raw_data = self.analyzer.get_year_statistics(type_)
            result = self.formatter.format_year_statistics(raw_data)
            
            # 添加元数据
            result['_metadata'] = {
                'type': type_ or 'all',
                'timestamp': int(time.time())
            }
            
            self._update_timing(start_time)
            return result
            
        except Exception as e:
            self.error_count += 1
            logger.error(f"获取年份分布失败: {e}")
            
            # 返回错误信息
            error_response = {
                'error': '获取年份分布失败',
                'message': str(e),
                'timestamp': int(time.time())
            }
            self._update_timing(start_time)
            return error_response
    
    def get_tag_distribution(self, type_: Optional[str] = None, limit: int = 30) -> Dict[str, Any]:
        """获取标签分布数据
        
        参数:
            type_: 可选，内容类型过滤
            limit: 返回的标签数量上限
            
        返回:
            标签分布数据
        """
        self.request_count += 1
        start_time = time.time()
        
        try:
            # 安全处理limit参数
            if limit <= 0:
                limit = 30
            elif limit > 100:
                limit = 100
                
            raw_data = self.analyzer.get_genre_statistics(type_, limit)
            result = self.formatter.format_genre_statistics(raw_data)
            
            # 添加元数据
            result['_metadata'] = {
                'type': type_ or 'all',
                'limit': limit,
                'timestamp': int(time.time())
            }
            
            self._update_timing(start_time)
            return result
            
        except Exception as e:
            self.error_count += 1
            logger.error(f"获取标签分布失败: {e}")
            
            # 返回错误信息
            error_response = {
                'error': '获取标签分布失败',
                'message': str(e),
                'timestamp': int(time.time())
            }
            self._update_timing(start_time)
            return error_response
    
    def get_collection_trend(self, period: str = 'month', 
                           months: int = 12, 
                           type_: Optional[str] = None) -> Dict[str, Any]:
        """获取收藏趋势数据
        
        参数:
            period: 'month'(按月) 或 'year'(按年)
            months: 如果period为'month'，返回最近几个月的数据
            type_: 可选，内容类型过滤
            
        返回:
            收藏趋势数据
        """
        self.request_count += 1
        start_time = time.time()
        
        try:
            # 参数验证
            if period not in ['month', 'year']:
                period = 'month'
                
            if months <= 0:
                months = 12
            elif months > 120:
                months = 120
                
            raw_data = self.analyzer.get_collection_trend(period, months, type_)
            result = self.formatter.format_collection_trend(raw_data)
            
            # 添加元数据
            result['_metadata'] = {
                'type': type_ or 'all',
                'period': period,
                'months': months,
                'timestamp': int(time.time())
            }
            
            self._update_timing(start_time)
            return result
            
        except Exception as e:
            self.error_count += 1
            logger.error(f"获取收藏趋势失败: {e}")
            
            # 返回错误信息
            error_response = {
                'error': '获取收藏趋势失败',
                'message': str(e),
                'timestamp': int(time.time())
            }
            self._update_timing(start_time)
            return error_response
    
    def fix_invalid_data(self) -> Dict[str, Any]:
        """修复无效数据
        
        扫描数据库中的无效记录并尝试修复
        
        返回:
            修复结果
        """
        self.request_count += 1
        start_time = time.time()
        
        try:
            fixes = self.analyzer.fix_invalid_data()
            
            # 修复后清除所有缓存
            self.clear_caches()
            
            result = {
                'success': True,
                'fixes': fixes,
                'timestamp': int(time.time())
            }
            
            self._update_timing(start_time)
            return result
            
        except Exception as e:
            self.error_count += 1
            logger.error(f"修复数据失败: {e}")
            
            # 返回错误信息
            error_response = {
                'success': False,
                'error': '修复数据失败',
                'message': str(e),
                'timestamp': int(time.time())
            }
            self._update_timing(start_time)
            return error_response
    
    def clear_caches(self) -> Dict[str, Any]:
        """清除所有缓存
        
        返回:
            操作结果
        """
        start_time = time.time()
        
        try:
            # 清除数据分析器的缓存
            self.analyzer.clear_cache()
            
            # 清除仪表板缓存
            with self._cache_lock:
                self._dashboard_cache.clear()
                self._cache_times.clear()
                
            result = {
                'success': True,
                'message': '已清除所有缓存',
                'timestamp': int(time.time())
            }
            
            self._update_timing(start_time)
            return result
            
        except Exception as e:
            self.error_count += 1
            logger.error(f"清除缓存失败: {e}")
            
            # 返回错误信息
            error_response = {
                'success': False,
                'error': '清除缓存失败',
                'message': str(e),
                'timestamp': int(time.time())
            }
            self._update_timing(start_time)
            return error_response
    
    def get_service_status(self) -> Dict[str, Any]:
        """获取服务状态信息
        
        返回:
            服务状态信息
        """
        start_time = time.time()
        
        try:
            # 获取组件状态
            analyzer_status = self.analyzer.get_analytics_status()
            formatter_status = self.formatter.get_status_summary()
            
            # 计算平均处理时间
            avg_time = 0
            if self.request_count > 0:
                avg_time = self.total_processing_time / self.request_count
                
            # 仪表板缓存状态
            dashboard_cache_status = {
                'size': len(self._dashboard_cache),
                'keys': list(self._dashboard_cache.keys())
            }
            
            status = {
                'service': {
                    'request_count': self.request_count,
                    'error_count': self.error_count,
                    'error_rate': f"{(self.error_count / max(1, self.request_count)) * 100:.2f}%",
                    'total_processing_time': round(self.total_processing_time, 2),
                    'avg_processing_time': round(avg_time, 4)
                },
                'dashboard_cache': dashboard_cache_status,
                'analyzer': analyzer_status,
                'formatter': formatter_status.get('formatter', {}),
                'timestamp': int(time.time()),
                'generated': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            }
            
            return status
            
        except Exception as e:
            logger.error(f"获取服务状态失败: {e}")
            
            # 返回基本状态信息
            return {
                'error': '获取完整状态信息失败',
                'service': {
                    'request_count': self.request_count,
                    'error_count': self.error_count
                },
                'timestamp': int(time.time())
            }
        finally:
            self._update_timing(start_time, count_as_request=False)
    
    def get_json_response(self, data: Dict[str, Any]) -> str:
        """将数据格式化为JSON响应
        
        参数:
            data: 要格式化的数据
            
        返回:
            JSON字符串
        """
        return self.formatter.format_analytics_response(data)
    
    def _get_from_cache(self, key: str) -> Optional[Dict[str, Any]]:
        """从缓存获取数据
        
        参数:
            key: 缓存键
            
        返回:
            缓存的数据，如果不存在或过期则返回None
        """
        with self._cache_lock:
            now = time.time()
            
            if (key in self._dashboard_cache and 
                key in self._cache_times and 
                now - self._cache_times[key] < self.DASHBOARD_CACHE_TTL):
                return self._dashboard_cache[key]
                
            return None
    
    def _save_to_cache(self, key: str, data: Dict[str, Any]) -> None:
        """保存数据到缓存
        
        参数:
            key: 缓存键
            data: 要缓存的数据
        """
        with self._cache_lock:
            # 限制缓存大小
            if len(self._dashboard_cache) > 20:
                # 删除最老的缓存
                oldest_key = min(self._cache_times.keys(), key=lambda k: self._cache_times.get(k, 0))
                if oldest_key in self._dashboard_cache:
                    del self._dashboard_cache[oldest_key]
                if oldest_key in self._cache_times:
                    del self._cache_times[oldest_key]
                    
            # 保存新数据
            self._dashboard_cache[key] = data
            self._cache_times[key] = time.time()
            
    def _update_timing(self, start_time: float, count_as_request: bool = True) -> None:
        """更新时间统计
        
        参数:
            start_time: 开始时间
            count_as_request: 是否计入请求计数
        """
        elapsed = time.time() - start_time
        self.total_processing_time += elapsed
        
        if elapsed > 1.0:  # 如果处理时间超过1秒，记录慢请求
            logger.warning(f"慢请求处理: {elapsed:.2f}秒")