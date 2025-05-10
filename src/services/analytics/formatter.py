import json
import time
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime
from utils.logger import get_logger

# 配置日志
logger = get_logger("formatter")

class StatisticsFormatter:
    """统计数据格式化器，负责将分析数据转换为前端可用的格式
    
    将分析器提供的原始数据进行格式化，确保符合前端的数据结构要求
    """
    
    # 图表配色方案
    CHART_COLORS = {
        'primary': ['#3ba272', '#2c7fb8', '#f28e2c', '#e15759', '#76b7b2', '#59a14f', '#4e79a7'],
        'status': {
            'done': '#3ba272',   # 绿色
            'doing': '#4e79a7',  # 蓝色
            'wish': '#f28e2c'    # 橙色
        }
    }
    
    # 类型显示名称映射
    TYPE_DISPLAY_NAMES = {
        'movie': '电影',
        'tv': '剧集',
        'book': '图书',
        'music': '音乐',
        'game': '游戏',
        'drama': '舞台剧'
    }
    
    # 状态显示名称映射
    STATUS_DISPLAY_NAMES = {
        'done': '看过',
        'doing': '在看',
        'wish': '想看'
    }
    
    def __init__(self, analyzer=None):
        """初始化格式化器
        
        参数:
            analyzer: 数据分析器实例，用于获取原始数据
        """
        self.analyzer = analyzer
        logger.info("统计数据格式化器初始化完成")
    
    def _localize_type_name(self, type_name: str) -> str:
        """将类型名称本地化为中文显示名称"""
        return self.TYPE_DISPLAY_NAMES.get(type_name, type_name)
    
    def _localize_status_name(self, status_name: str) -> str:
        """将状态名称本地化为中文显示名称"""
        return self.STATUS_DISPLAY_NAMES.get(status_name, status_name)
    
    def _sort_dict_by_key(self, data: Dict) -> Dict:
        """按键名排序字典"""
        return {k: data[k] for k in sorted(data.keys())}
        
    def _sort_dict_by_value(self, data: Dict, reverse: bool = True) -> Dict:
        """按值排序字典"""
        return {k: v for k, v in sorted(data.items(), key=lambda item: item[1], reverse=reverse)}
        
    def _find_top_n_rest(self, data: Dict[str, int], n: int = 10) -> Tuple[Dict[str, int], int]:
        """提取字典中前N个键值对，其余归入'其他'类别
        
        参数:
            data: 原始数据字典
            n: 提取的前N项数量
            
        返回:
            (前N项字典, 其余项总和)
        """
        if len(data) <= n:
            return data, 0
            
        # 按值排序
        sorted_items = sorted(data.items(), key=lambda x: x[1], reverse=True)
        
        # 提取前N项
        top_n = dict(sorted_items[:n])
        
        # 计算其余项总和
        rest_sum = sum(v for _, v in sorted_items[n:])
        
        return top_n, rest_sum
        
    def _truncate_label(self, label: str, max_len: int = 12) -> str:
        """截断过长的标签文本
        
        参数:
            label: 原始标签
            max_len: 最大长度
            
        返回:
            截断后的标签
        """
        if not label or len(label) <= max_len:
            return label
            
        # 特别处理带有方括号的标签（如作者名）
        if label.startswith('['):
            bracket_end = label.find(']')
            if 0 < bracket_end < max_len:
                # 保留方括号内容，截断后面的部分
                return label[:bracket_end+1] + label[bracket_end+1:max_len-2].strip() + '...'
        
        # 普通截断
        return label[:max_len-3].strip() + '...'
        
    def format_basic_statistics(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """格式化基本统计信息
        
        参数:
            data: 原始数据
            
        返回:
            格式化后的数据
        """
        if not data:
            return {}
            
        result = {
            'total': data.get('total_count', 0),
        }
        
        # 处理类型计数
        type_counts = data.get('type_counts', {})
        result['type_stats'] = {
            'labels': [self._localize_type_name(t) for t in type_counts.keys()],
            'values': list(type_counts.values()),
            'raw_data': type_counts
        }
        
        # 处理状态计数
        status_counts = data.get('status_counts', {})
        result['status_stats'] = {
            'labels': [self._localize_status_name(s) for s in status_counts.keys()],
            'values': list(status_counts.values()),
            'raw_data': status_counts,
            'colors': [self.CHART_COLORS['status'].get(s, '#999') for s in status_counts.keys()]
        }
        
        return result
        
    def format_content_type_statistics(self, type_: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """格式化特定内容类型的统计信息
        
        参数:
            type_: 内容类型
            data: 原始数据
            
        返回:
            格式化后的数据
        """
        if not data:
            return {}
            
        result = {
            'type': type_,
            'display_name': self._localize_type_name(type_),
            'total': data.get('total', 0)
        }
        
        # 处理状态统计
        status_data = data.get('status', {})
        result['status'] = {
            'labels': [self._localize_status_name(s) for s in status_data.keys()],
            'values': list(status_data.values()),
            'colors': [self.CHART_COLORS['status'].get(s, '#999') for s in status_data.keys()]
        }
        
        # 处理标签/分类统计
        genres_data = data.get('genres', {})
        if genres_data:
            # 找出前10个标签，其余归为"其他"
            top_genres, rest = self._find_top_n_rest(genres_data, 10)
            
            # 添加"其他"类别（如果有）
            if rest > 0:
                chart_genres = dict(top_genres)
                chart_genres['其他'] = rest
            else:
                chart_genres = top_genres
                
            result['genres'] = {
                'labels': list(chart_genres.keys()),
                'values': list(chart_genres.values()),
                'raw_data': genres_data
            }
        else:
            result['genres'] = {'labels': [], 'values': [], 'raw_data': {}}
            
        # 处理评分分布
        ratings_data = data.get('ratings', {})
        if ratings_data:
            # 确保评分组按逻辑顺序排列
            rating_order = ['未评分', '1-2星', '3-5星', '6-7星', '8-10星']
            sorted_ratings = {k: ratings_data.get(k, 0) for k in rating_order if k in ratings_data}
            
            result['ratings'] = {
                'labels': list(sorted_ratings.keys()),
                'values': list(sorted_ratings.values()),
                'raw_data': ratings_data
            }
        else:
            result['ratings'] = {'labels': [], 'values': [], 'raw_data': {}}
        
        # 处理年份统计
        years_data = data.get('years', {})
        if years_data:
            # 年份需要排序
            sorted_years = self._sort_dict_by_key(years_data)
            result['years'] = {
                'labels': list(sorted_years.keys()),
                'values': list(sorted_years.values()),
                'raw_data': years_data
            }
        else:
            result['years'] = {'labels': [], 'values': [], 'raw_data': {}}
            
        # 处理类型特有的额外数据
        if type_ == 'movie' or type_ == 'tv':
            # 地区数据
            regions_data = data.get('regions', {})
            if regions_data:
                # 找出前10个地区，其余归为"其他"
                top_regions, rest = self._find_top_n_rest(regions_data, 10)
                
                # 添加"其他"类别（如果有）
                if rest > 0:
                    chart_regions = dict(top_regions)
                    chart_regions['其他'] = rest
                else:
                    chart_regions = top_regions
                    
                result['regions'] = {
                    'labels': list(chart_regions.keys()),
                    'values': list(chart_regions.values()),
                    'raw_data': regions_data
                }
                
        elif type_ == 'book':
            # 出版社数据
            publishers_data = data.get('publishers', {})
            if publishers_data:
                # 找出前10个出版社，其余归为"其他"
                top_publishers, rest = self._find_top_n_rest(publishers_data, 10)
                
                # 添加"其他"类别（如果有）
                if rest > 0:
                    chart_publishers = dict(top_publishers)
                    chart_publishers['其他'] = rest
                else:
                    chart_publishers = top_publishers
                    
                result['publishers'] = {
                    'labels': [self._truncate_label(l) for l in chart_publishers.keys()],
                    'values': list(chart_publishers.values()),
                    'raw_data': publishers_data
                }
                
            # 作者数据
            authors_data = data.get('authors', {})
            if authors_data:
                # 找出前10个作者，其余归为"其他"
                top_authors, rest = self._find_top_n_rest(authors_data, 10)
                
                # 添加"其他"类别（如果有）
                if rest > 0:
                    chart_authors = dict(top_authors)
                    chart_authors['其他'] = rest
                else:
                    chart_authors = top_authors
                    
                result['authors'] = {
                    'labels': [self._truncate_label(l) for l in chart_authors.keys()],
                    'values': list(chart_authors.values()),
                    'raw_data': authors_data
                }
                
        elif type_ == 'game':
            # 开发商数据
            developers_data = data.get('developers', {})
            if developers_data:
                # 找出前10个开发商，其余归为"其他"
                top_developers, rest = self._find_top_n_rest(developers_data, 10)
                
                # 添加"其他"类别（如果有）
                if rest > 0:
                    chart_developers = dict(top_developers)
                    chart_developers['其他'] = rest
                else:
                    chart_developers = top_developers
                    
                result['developers'] = {
                    'labels': [self._truncate_label(l) for l in chart_developers.keys()],
                    'values': list(chart_developers.values()),
                    'raw_data': developers_data
                }
                
        return result
        
    def format_rating_statistics(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """格式化评分统计信息
        
        参数:
            data: 原始评分数据
            
        返回:
            格式化后的数据
        """
        if not data:
            return {}
            
        stats = data.get('stats', {})
        distribution = data.get('distribution', [])
        
        # 准备标签（1-10分）
        labels = [str(i) for i in range(1, 11)]
        
        # 计算平均分四舍五入到小数点后一位
        avg_score = stats.get('average', 0)
        if avg_score:
            avg_score = round(avg_score, 1)
            
        result = {
            'average': avg_score,
            'count': stats.get('count', 0),
            'chart': {
                'labels': labels,
                'values': distribution,
                'colors': self.CHART_COLORS['primary'] * 2  # 循环使用颜色
            }
        }
        
        return result
        
    def format_year_statistics(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """格式化年份统计信息
        
        参数:
            data: 原始年份数据
            
        返回:
            格式化后的数据
        """
        if not data:
            return {}
            
        labels = data.get('labels', [])
        values = data.get('all', [])
        
        # 对数据进行降采样，避免图表上显示太多点
        if len(labels) > 20:
            step = max(1, len(labels) // 20)  # 保持最多20个点
            labels = labels[::step]
            values = values[::step]
        
        result = {
            'chart': {
                'labels': labels,
                'values': values,
                'colors': [self.CHART_COLORS['primary'][0]]  # 使用主色
            }
        }
        
        return result
        
    def format_genre_statistics(self, data: List[Dict[str, Any]]) -> Dict[str, Any]:
        """格式化标签统计信息
        
        参数:
            data: 原始标签数据
            
        返回:
            格式化后的数据
        """
        if not data:
            return {'labels': [], 'values': [], 'colors': []}
            
        # 提取标签和计数
        labels = [item.get('name', '') for item in data]
        values = [item.get('count', 0) for item in data]
        
        # 如果标签太多，限制显示数量
        if len(labels) > 20:
            labels = labels[:20]
            values = values[:20]
        
        # 为标签添加计数
        labels_with_count = [f"{label} ({value})" for label, value in zip(labels, values)]
        
        # 生成颜色序列
        colors = []
        for i in range(len(labels)):
            color_index = i % len(self.CHART_COLORS['primary'])
            colors.append(self.CHART_COLORS['primary'][color_index])
        
        result = {
            'labels': labels_with_count,
            'values': values,
            'raw_labels': labels,
            'colors': colors
        }
        
        return result
        
    def format_collection_trend(self, data: Dict[str, List]) -> Dict[str, Any]:
        """格式化收藏趋势数据
        
        参数:
            data: 原始趋势数据
            
        返回:
            格式化后的数据
        """
        if not data:
            return {'labels': [], 'values': []}
            
        labels = data.get('labels', [])
        values = data.get('values', [])
        
        # 反转数据顺序（最新的在右侧）
        labels = list(reversed(labels))
        values = list(reversed(values))
        
        # 格式化月份标签，从 "2023-01" 变为 "1月"
        formatted_labels = []
        for label in labels:
            if '-' in label:  # 月份格式
                try:
                    year_month = label.split('-')
                    if len(year_month) == 2:
                        month = int(year_month[1])
                        formatted_labels.append(f"{month}月")
                    else:
                        formatted_labels.append(label)
                except:
                    formatted_labels.append(label)
            else:  # 年份格式
                formatted_labels.append(label)
        
        result = {
            'labels': formatted_labels,
            'original_labels': labels,
            'values': values,
            'colors': [self.CHART_COLORS['primary'][0]]  # 使用主色
        }
        
        return result
        
    def format_movie_statistics(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """格式化电影特定统计信息
        
        参数:
            data: 原始电影统计数据
            
        返回:
            格式化后的数据
        """
        if not data:
            return {}
            
        result = {}
        
        # 电影数据
        movie_data = data.get('movie', {})
        if movie_data:
            result['movie'] = {
                'total': movie_data.get('total', 0),
                'status': movie_data.get('status', {})
            }
            
        # 电视剧数据
        tv_data = data.get('tv', {})
        if tv_data:
            result['tv'] = {
                'total': tv_data.get('total', 0),
                'status': tv_data.get('status', {})
            }
            
        # 年代分布
        decades_data = data.get('decades', {})
        if decades_data:
            # 按年代排序
            sorted_decades = self._sort_dict_by_key(decades_data)
            result['decades'] = {
                'labels': list(sorted_decades.keys()),
                'values': list(sorted_decades.values()),
                'colors': self.CHART_COLORS['primary'][:len(sorted_decades)]
            }
            
        # 评分最高的标签
        top_genres = data.get('top_genres', [])
        if top_genres:
            result['top_genres'] = {
                'labels': [f"{item.get('name')} ({item.get('count')})" for item in top_genres],
                'scores': [item.get('score') for item in top_genres],
                'counts': [item.get('count') for item in top_genres],
                'raw_data': top_genres
            }
            
        # 统计看过的国家/地区
        regions = {}
        for container in [movie_data, tv_data]:
            container_regions = container.get('regions', {})
            for region, count in container_regions.items():
                regions[region] = regions.get(region, 0) + count
        
        if regions:
            # 找出前10个地区，其余归为"其他"
            top_regions, rest = self._find_top_n_rest(regions, 10)
            
            # 添加"其他"类别（如果有）
            if rest > 0:
                chart_regions = dict(top_regions)
                chart_regions['其他'] = rest
            else:
                chart_regions = top_regions
                
            result['regions'] = {
                'labels': list(chart_regions.keys()),
                'values': list(chart_regions.values()),
                'colors': self.CHART_COLORS['primary'][:len(chart_regions)]
            }
            
        return result
        
    def format_book_statistics(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """格式化图书特定统计信息
        
        参数:
            data: 原始图书统计数据
            
        返回:
            格式化后的数据
        """
        if not data:
            return {}
            
        result = {}
        
        # 基本数据
        basic_data = data.get('basic', {})
        if basic_data:
            result['total'] = basic_data.get('total', 0)
            result['status'] = basic_data.get('status', {})
            
        # 顶级作者
        top_authors = data.get('top_authors', [])
        if top_authors:
            result['top_authors'] = {
                'labels': [self._truncate_label(item.get('name', '')) for item in top_authors],
                'values': [item.get('count', 0) for item in top_authors],
                'colors': self.CHART_COLORS['primary'][:len(top_authors)]
            }
            
        # 顶级出版社
        top_publishers = data.get('top_publishers', [])
        if top_publishers:
            result['top_publishers'] = {
                'labels': [self._truncate_label(item.get('name', '')) for item in top_publishers],
                'values': [item.get('count', 0) for item in top_publishers],
                'colors': self.CHART_COLORS['primary'][:len(top_publishers)]
            }
            
        # 阅读趋势
        reading_trend = data.get('reading_trend', {})
        if reading_trend:
            result['reading_trend'] = {
                'labels': reading_trend.get('labels', []),
                'values': reading_trend.get('values', []),
                'colors': [self.CHART_COLORS['primary'][0]]
            }
            
        return result
        
    def format_game_statistics(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """格式化游戏特定统计信息
        
        参数:
            data: 原始游戏统计数据
            
        返回:
            格式化后的数据
        """
        if not data:
            return {}
            
        result = {}
        
        # 基本数据
        basic_data = data.get('basic', {})
        if basic_data:
            result['total'] = basic_data.get('total', 0)
            result['status'] = basic_data.get('status', {})
            
        # 顶级开发商
        top_developers = data.get('top_developers', [])
        if top_developers:
            result['top_developers'] = {
                'labels': [self._truncate_label(item.get('name', '')) for item in top_developers],
                'values': [item.get('count', 0) for item in top_developers],
                'colors': self.CHART_COLORS['primary'][:len(top_developers)]
            }
            
        # 年份统计
        year_stats = data.get('year_stats', {})
        if year_stats:
            result['year_stats'] = {
                'labels': year_stats.get('labels', []),
                'scores': year_stats.get('scores', []),
                'counts': year_stats.get('counts', []),
                'colors': [self.CHART_COLORS['primary'][0]]
            }
            
        return result
        
    def format_dashboard_statistics(self, type_: Optional[str] = None) -> Dict[str, Any]:
        """格式化仪表板统计信息
        
        参数:
            type_: 可选的内容类型过滤
            
        返回:
            仪表板数据
        """
        if not self.analyzer:
            logger.error("未设置分析器，无法获取数据")
            return {}
            
        try:
            start_time = time.time()
            
            # 获取基础数据
            if type_:
                # 单一类型仪表板
                basic_data = self.analyzer.get_basic_statistics(type_)
                content_data = self.analyzer.get_content_type_statistics(type_)
                
                # 格式化数据
                result = {
                    'type': type_,
                    'display_name': self._localize_type_name(type_),
                    'basic': self.format_content_type_statistics(type_, content_data),
                    'ratings': self.format_rating_statistics(self.analyzer.get_rating_statistics(type_)),
                    'years': self.format_year_statistics(self.analyzer.get_year_statistics(type_)),
                    'genres': self.format_genre_statistics(self.analyzer.get_genre_statistics(type_, 20)),
                    'trends': self.format_collection_trend(self.analyzer.get_collection_trend(period='month', months=12, type_=type_))
                }
                
                # 类型特定数据
                if type_ == 'movie' or type_ == 'tv':
                    movie_stats = self.analyzer.get_movie_statistics()
                    result['specific'] = self.format_movie_statistics(movie_stats)
                elif type_ == 'book':
                    book_stats = self.analyzer.get_book_statistics()
                    result['specific'] = self.format_book_statistics(book_stats)
                elif type_ == 'game':
                    game_stats = self.analyzer.get_game_statistics()
                    result['specific'] = self.format_game_statistics(game_stats)
                    
            else:
                # 全局仪表板
                complete_stats = self.analyzer.get_complete_statistics()
                
                # 格式化数据
                result = {
                    'basic': self.format_basic_statistics(complete_stats.get('basic', {})),
                    'ratings': self.format_rating_statistics(complete_stats.get('ratings', {})),
                    'years': self.format_year_statistics(complete_stats.get('years', {})),
                    'genres': self.format_genre_statistics(complete_stats.get('tags', [])),
                    'trends': self.format_collection_trend(complete_stats.get('trends', {}))
                }
                
                # 添加一些针对全局仪表板的额外数据
                result['type_specific'] = {}
                for content_type in ['movie', 'book', 'game', 'tv', 'music']:
                    # 仅获取基本计数数据，避免生成太多查询
                    type_data = self.analyzer.get_content_type_statistics(content_type)
                    result['type_specific'][content_type] = {
                        'total': type_data.get('total', 0),
                        'display_name': self._localize_type_name(content_type),
                        'status': type_data.get('status', {})
                    }
            
            # 添加格式化时间信息
            execution_time = time.time() - start_time
            result['_metadata'] = {
                'execution_time_ms': round(execution_time * 1000),
                'timestamp': int(time.time()),
                'generated': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            }
            
            return result
            
        except Exception as e:
            logger.error(f"格式化仪表板数据失败: {e}")
            return {
                'error': '生成统计数据时出错',
                'timestamp': int(time.time())
            }
    
    def format_analytics_response(self, data: Dict[str, Any]) -> str:
        """将分析数据格式化为JSON响应
        
        参数:
            data: 分析数据
            
        返回:
            JSON字符串
        """
        try:
            return json.dumps(data, ensure_ascii=False)
        except Exception as e:
            logger.error(f"序列化JSON响应失败: {e}")
            return json.dumps({'error': '序列化数据时出错'})
            
    def get_status_summary(self) -> Dict[str, Any]:
        """获取状态摘要，包括数据提供者和分析器状态
        
        返回:
            状态摘要
        """
        summary = {
            'formatter': {
                'version': '1.0',
                'colors': self.CHART_COLORS,
                'type_names': self.TYPE_DISPLAY_NAMES,
                'status_names': self.STATUS_DISPLAY_NAMES
            }
        }
        
        # 如果有分析器，也获取其状态
        if self.analyzer:
            summary['analyzer'] = self.analyzer.get_analytics_status()
            
        return summary