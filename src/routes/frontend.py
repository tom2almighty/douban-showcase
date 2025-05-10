# src/routes/frontend.py
from pathlib import Path
from mimetypes import guess_type
from flask import Blueprint, render_template, request, send_file, redirect, url_for, send_from_directory
import json
import time
import os
from io import BytesIO
import requests
from datetime import datetime
from utils.logger import get_logger
from config import config
from datetime import datetime
from utils.serialization_utils import safe_serialize, safe_json_loads  # 添加安全序列化工具


frontend_bp = Blueprint('frontend', __name__)
logger = get_logger('frontend')
db = None
scheduler = None
stats_service = None
image_service = None

def init_frontend(db_instance, stats_service_instance, scheduler_instance, image_service_instance):
    """初始化前端蓝图中的全局变量"""
    global db, stats_service, scheduler, image_service
    db = db_instance
    stats_service = stats_service_instance 
    scheduler = scheduler_instance
    image_service = image_service_instance 
    
    # 可选：记录初始化信息
    if db and stats_service:
        logger.info("前端蓝图初始化完成，数据库连接和统计服务正常")
    else:
        logger.warning("前端蓝图初始化，但数据库实例或统计实例为空")

@frontend_bp.route('/covers/<path:filename>')
def serve_cover(filename):
    """提供封面图片访问"""
    # 获取项目根目录的绝对路径
    root_dir = Path(__file__).parent.parent.parent.absolute()
    
    # 获取环境变量中的封面路径（相对于项目根目录）
    covers_rel_path = config['local_cover_path']
    
    # 构建封面目录的绝对路径
    covers_abs_path = root_dir / covers_rel_path
    
    logger.debug(f"访问封面图片: {filename}")
    logger.debug(f"项目根目录: {root_dir}")
    logger.debug(f"封面相对路径: {covers_rel_path}")
    logger.debug(f"封面绝对路径: {covers_abs_path}")
    
    try:
        if not covers_abs_path.exists():
            logger.error(f"封面目录不存在: {covers_abs_path}")
            return send_file(str(root_dir / 'src' / 'static' / 'images' / 'no-cover.png'), mimetype='image/png')
        
        # 构建完整的文件路径
        file_path = covers_abs_path / filename
        
        logger.debug(f"尝试访问文件: {file_path}")
        
        # 检查文件是否存在，并确保它在covers_abs_path目录下（安全检查）
        if file_path.exists() and str(file_path).startswith(str(covers_abs_path)):
            return send_file(str(file_path), mimetype=guess_type(str(file_path))[0] or 'image/jpeg')
        else:
            logger.warning(f"封面文件未找到: {file_path}")
            return send_file(str(root_dir / 'src' / 'static' / 'images' / 'no-cover.png'), mimetype='image/png')
            
    except Exception as e:
        logger.error(f"访问文件时出错: {str(e)}")
        return send_file(str(root_dir / 'src' / 'static' / 'images' / 'no-cover.png'), mimetype='image/png')

@frontend_bp.route('/proxy/image')
def proxy_image():
    """图片代理，解决CORS问题"""
    url = request.args.get('url', '')
    if not url:
        return "No URL provided", 400
        
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36',
            'Referer': 'https://www.douban.com/',
            'Accept': 'image/avif,image/webp,image/apng,image/*,*/*;q=0.8'
        }
        

        response = requests.get(url, headers=headers, stream=True, timeout=10)
        response.raise_for_status()
        
        # 获取内容类型
        content_type = response.headers.get('Content-Type', 'image/jpeg')
        
        # 将图片数据发送给客户端
        return send_file(
            BytesIO(response.content),
            mimetype=content_type
        )
    except Exception as e:
        logger.error(f"图片代理请求失败: {e}")
        return "Failed to fetch image", 500

@frontend_bp.route('/')
def index():
    """首页"""
    # 从数据库获取一些统计数据和最近项目
    stats = {}
    recent_items = []
    total_count = 0
    type_counts = {}
    
    try:
        # 获取总数据量和类型计数
        if db:
            total_count = get_total_count()
            type_counts = get_type_counts()
        
        # 获取统计数据 - 使用新的统计服务
        if scheduler and stats_service:
            for content_type in scheduler.sync_types:
                stats[content_type] = stats_service.get_type_specific_stats(content_type)
            
        # 获取最近的条目
        if db:
            recent_items = db.get_interests(limit=12, sort_by="create_time", sort_order="desc")
            # 安全序列化处理
            recent_items = _safe_serialize(recent_items)
        
    except Exception as e:
        logger.error(f"加载首页数据失败: {e}")
    
    return render_template('index.html', 
                          stats=stats,
                          recent_items=recent_items,
                          total_count=total_count,
                          type_counts=type_counts,
                          title="豆瓣收藏")

@frontend_bp.route('/<string:type_>')
def type_page(type_):
    """展示特定类型的内容"""
    available_types = []
    if db:
        available_types = db.get_distinct_types()
    
    if type_ not in available_types:
        return redirect(url_for('frontend.index'))
    

    # 获取查询参数
    status = request.args.get('status', 'all')
    sort_by = request.args.get('sort_by', 'create_time')
    sort_order = request.args.get('sort_order', 'desc')
    tag = request.args.get('tag', '')
    year = request.args.get('year', '')
    search = request.args.get('search', '')
    page = int(request.args.get('page', 1))
    limit = int(request.args.get('limit', 24))
    offset = (page - 1) * limit
    
    type_names = {
        'movie': '电影',
        'tv': '电视剧',
        'book': '图书',
        'music': '音乐',
        'game': '游戏',
        'drama': '舞台剧'
    }


    try:
        # 构建额外筛选条件
        filters = {}
        if tag:
            filters['genre'] = tag
        if year:
            try:
                filters['year'] = int(year)
            except ValueError:
                pass
        if search:
            filters['search_query'] = search
            
        # 获取条目
        items = []
        total = 0
        
        # 若状态为all，则不传入status参数
        status_param = status if status != 'all' else None
        
        if db:
            items = db.get_interests(
                type_=type_,
                status=status_param,
                sort_by=sort_by,
                sort_order=sort_order,
                limit=limit,
                offset=offset,
                **filters  # 添加额外筛选条件
            )
            # 获取总条目数（用于分页）
            count_query = f"SELECT COUNT(*) as count FROM interests WHERE type = ?"
            params = [type_]
            
            if status_param:
                count_query += " AND status = ?"
                params.append(status_param)
                
            if 'year' in filters:
                count_query += " AND year = ?"
                params.append(filters['year'])
                
            if 'genre' in filters:
                count_query += " AND genres LIKE ?"
                params.append(f"%{filters['genre']}%")
                
            if 'search_query' in filters:
                count_query += " AND (card_subtitle LIKE ? OR title LIKE ?)"
                params.append(f"%{filters['search_query']}%")
                params.append(f"%{filters['search_query']}%")
                
            count_result = db.execute_query(count_query, tuple(params))
            total = count_result[0]['count'] if count_result else 0
            
            # 安全序列化处理
            items = _safe_serialize(items)
        
        # 获取该类型的筛选选项
        stats = {}
        available_tags = []
        available_years = []

        if db:
            # 直接从数据库获取年份选项
            try:
                year_query = """
                SELECT DISTINCT year 
                FROM interests 
                WHERE type = ? AND year IS NOT NULL AND year > 0
                ORDER BY year DESC
                """
                year_results = db.execute_query(year_query, (type_,))
                available_years = [str(result['year']) for result in year_results if result['year']]
            except Exception as e:
                logger.error(f"获取年份选项失败: {e}")
            

            try:
                genres_query = """
                SELECT DISTINCT genres
                FROM interests
                WHERE type = ? AND genres IS NOT NULL AND genres != '[]'
                """
                genres_results = db.execute_query(genres_query, (type_,))
                available_tags = set()
                for result in genres_results:
                    try:
                        genres = json.loads(result['genres'])
                        if isinstance(genres, list):
                            for genre in genres:
                                if genre:
                                    available_tags.add(str(genre))
                    except (json.JSONDecodeError, TypeError):
                        logger.warning(f"无法解析genres JSON: {result['genres']}")
                        
                available_tags = sorted(list(available_tags))
            except Exception as e:
                logger.error(f"获取标签选项失败: {e}", exc_info=True)
                available_tags = []


        # 计算总页数
        total_pages = (total + limit - 1) // limit if total > 0 else 1
        
    except Exception as e:
        logger.error(f"加载{type_}页面数据失败: {e}")
        items = []
        stats = {}
        total = 0
        total_pages = 1
        available_tags = []
        available_years = []
    
    return render_template('type.html',
                          type_=type_,
                          items=items,
                          stats=stats,
                          status=status,
                          sort_by=sort_by,
                          sort_order=sort_order,
                          page=page,
                          limit=limit,
                          total=total,
                          total_pages=total_pages,
                          tag=tag,
                          year=year,
                          search=search,
                          available_tags=available_tags,
                          available_years=available_years,
                          title=f"豆瓣收藏 - {type_names.get(type_, type_)}")

@frontend_bp.context_processor
def inject_template_vars():
    """注入模板变量"""
    types = []
    type_counts = {}
    
    if db:
        try:
            types = db.get_distinct_types()
            type_counts = get_type_counts()
        except Exception as e:
            logger.error(f"无法从数据库中获取可用类型: {e}")
    
    # 类型显示名称映射
    type_names = {
        'movie': '电影',
        'tv': '电视剧',
        'book': '图书',
        'music': '音乐',
        'game': '游戏',
        'drama': '舞台剧'
    }
    
    # 状态显示名称映射
    status_names = {
        'all': '全部',
        'mark': '想看',
        'doing': '在看',
        'done': '看过'
    }
    
    # 排序选项映射
    sort_options = {
        'create_time': '添加时间',
        'year': '发布年份',
        'douban_score': '豆瓣评分',
        'my_rating': '我的评分',
        'title': '标题'
    }
    
    # 排序方向映射
    sort_order_options = {
        'desc': '降序',
        'asc': '升序'
    }
    
    # 获取当前时间供模板使用
    now = datetime.now()
    
    return {
        'available_types': types,
        'type_names': type_names,
        'status_names': status_names,
        'sort_options': sort_options,
        'sort_order_options': sort_order_options,
        'type_counts': type_counts,
        'now': now
    }

@frontend_bp.app_template_filter('image_url')
def image_url_filter(item):
    """处理图片URL，确保使用正确的图片源"""
    if not item:
        return "/static/images/no-cover.png"

    item_id = item.get('id')
    cover_url = item.get('cover_url', '')

    try:
        if image_service and item_id and db:
            return image_service.get_image_url(db, item_id, cover_url)
    except Exception as e:
        logger.error(f"获取图片URL失败: {e}")

    # 如果发生异常或未找到图片，返回占位图
    return "/static/images/no-cover.png"

@frontend_bp.route('/stats')
def stats():
    """统计分析页面 - 使用API获取数据"""
    if not db:
        logger.error("统计功能不可用：数据库未初始化")
        return render_template('error.html', message="统计功能不可用"), 500
    
    try:
        logger.info("开始加载统计页面数据")
        start_time = time.time()  # 记录开始时间

        # 使用API获取统计数据
        from routes.api import get_complete_stats
        
        # 处理refresh参数
        if request.args.get('refresh') == '1':
            request.args = {'skip_cache': '1'}  # 修改请求参数
            
        # 调用API函数
        api_response, status_code = get_complete_stats()
        
        # 检查API调用是否成功
        if status_code != 200:
            logger.error(f"API调用失败，状态码: {status_code}")
            return render_template('error.html', message="无法获取统计数据"), status_code
            
        # 获取API响应中的数据
        stats_data = api_response.get_json()
        
        # 计算加载时间
        load_time = time.time() - start_time
        logger.info(f"统计数据加载完成，耗时：{load_time:.2f}秒")
        
        # 在构建template_data前添加
        print("stats_data['trends']内容:", stats_data.get('trends', {}))
        print("trend_data.values的类型:", type(stats_data.get('trends', {}).get('values', [])))

        # 提取需要传递给模板的数据
        template_data = {
            'total_count': stats_data.get('basic', {}).get('total', 0),
            'type_counts': stats_data.get('basic', {}).get('type_stats', {}).get('raw_data', {}),
            'status_counts': stats_data.get('basic', {}).get('status_stats', {}).get('raw_data', {}),
            'rating_stats': {
                'average': stats_data.get('ratings', {}).get('average', 0),
                'count': stats_data.get('ratings', {}).get('count', 0)
            },
            'rating_distribution': stats_data.get('ratings', {}).get('chart', {}).get('values', [0] * 10),
            'year_data': {
                'labels': stats_data.get('years', {}).get('chart', {}).get('labels', []),
                'all': stats_data.get('years', {}).get('chart', {}).get('values', [])
            },
            'trend_data': {
                'labels': list(reversed(stats_data.get('trends', {}).get('labels', []))),
                'values': list(reversed(stats_data.get('trends', {}).get('values', [])))
            },
            'load_time': round(load_time, 2),
            'title': "豆瓣收藏 - 统计分析"
        }
        
        # 处理标签数据 (如果有)
        if 'genres' in stats_data:
            top_tags = []
            labels = stats_data['genres'].get('raw_labels', [])
            values = stats_data['genres'].get('values', [])
            
            if labels and values and len(labels) == len(values):
                max_count = max(values) if values else 1
                for i, label in enumerate(labels):
                    count = values[i]
                    top_tags.append({
                        'name': str(label),
                        'count': int(count),
                        'weight': round((count / max_count) * 100) if max_count > 0 else 1
                    })
            template_data['top_tags'] = top_tags
        
        # 记录请求完成
        logger.info(f"成功加载统计页面，共 {template_data['total_count']} 条数据")
        
        return render_template('stats.html', **template_data)
                         
    except Exception as e:
        logger.error(f"加载统计页面失败: {e}", exc_info=True)
        error_message = f"加载统计数据失败。具体错误: {str(e)}"
        return render_template('error.html', 
                              message=error_message,
                              error_details=str(e),
                              title="统计分析 - 错误"), 500

def _safe_serialize(obj):
    """确保数据可被安全序列化、传递给模板
    
    递归处理复杂数据结构，防止不可序列化对象传递给模板引擎
    
    参数:
        obj: 任意Python对象
        
    返回:
        可安全序列化的对象
    """
    # 我们可以直接使用导入的 safe_serialize
    return safe_serialize(obj)

def get_total_count():
    """获取所有条目总数"""
    if not db:
        return 0
    
    try:
        return db.execute_query("SELECT COUNT(*) as count FROM interests")[0]["count"]
    except Exception as e:
        logger.error(f"获取总条目数失败: {e}")
        return 0

def get_type_counts():
    """获取各类型条目数量"""
    if not db:
        return {}
    
    try:
        results = db.execute_query("""
        SELECT type, COUNT(*) as count
        FROM interests
        GROUP BY type
        ORDER BY count DESC
        """)
        
        counts = {}
        for item in results:
            counts[item["type"]] = item["count"]
            
        return counts
    except Exception as e:
        logger.error(f"获取类型计数失败: {e}")
        return {}