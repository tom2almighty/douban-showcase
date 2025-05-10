from flask import Blueprint, request, jsonify, current_app
import threading
from datetime import datetime
from typing import Dict, Any, Optional, Union

# 导入工具
from utils.logger import get_logger
from utils.validation_utils import validate_int, validate_string, validate_bool
from utils.serialization_utils import safe_json_dumps, safe_serialize

# 创建API蓝图
api_bp = Blueprint('api', __name__, url_prefix='/api')

# 获取全局组件引用
logger = get_logger('api')

# 这些全局变量需要在注册蓝图时设置
db = None
scheduler = None
stats_service = None
image_service = None

def init_api(db_instance, stats_service_instance, scheduler_instance, image_service_instance):
    """初始化API蓝图中的全局变量"""
    global db, stats_service, scheduler, image_service
    db = db_instance
    stats_service = stats_service_instance
    scheduler = scheduler_instance
    image_service = image_service_instance
    
    logger.info("API初始化完成，使用了新的服务架构")

def api_response(data: Any, status_code: int = 200) -> tuple:
    """创建标准API响应
    
    使用安全序列化确保所有数据可以被序列化
    
    参数:
        data: 响应数据
        status_code: HTTP状态码
        
    返回:
        Flask响应元组
    """
    try:
        # 使用安全序列化工具处理数据
        serialized_data = safe_serialize(data)
        
        # 添加元数据
        if isinstance(serialized_data, dict) and '_metadata' not in serialized_data:
            serialized_data['_metadata'] = {
                'timestamp': datetime.now().timestamp(),
                'generated': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            }
        
        return jsonify(serialized_data), status_code
    except Exception as e:
        logger.error(f"序列化API响应时出错: {e}")
        return jsonify({
            'error': '内部服务器错误',
            'message': '无法序列化响应数据',
            'timestamp': datetime.now().timestamp()
        }), 500

def api_error(message: str, status_code: int = 400, error_type: str = 'BadRequest') -> tuple:
    """创建标准错误响应
    
    参数:
        message: 错误消息
        status_code: HTTP状态码
        error_type: 错误类型
        
    返回:
        Flask响应元组
    """
    error_response = {
        'error': error_type,
        'message': message,
        'timestamp': datetime.now().timestamp()
    }
    return jsonify(error_response), status_code

def check_services() -> Optional[tuple]:
    """检查必要的服务实例是否已初始化
    
    返回:
        None 如果所有服务可用，否则返回错误响应元组
    """
    services = {
        'db': db,
        'scheduler': scheduler,
        'stats_service': stats_service,
        'image_service': image_service
    }
    
    missing_services = [name for name, instance in services.items() if instance is None]
    
    if missing_services:
        return api_error(
            f"系统未完全初始化: 缺少 {', '.join(missing_services)}",
            status_code=503,
            error_type='ServiceUnavailable'
        )
    
    return None

@api_bp.route('/interests')
def api_interests():
    """获取兴趣列表API"""
    service_check = check_services()
    if service_check:
        return service_check
    
    try:
        type_ = validate_string(request.args.get('type'), 'type')
        status = validate_string(request.args.get('status'), 'status')
        year = validate_int(request.args.get('year'), 'year')
        
        sort_by = validate_string(
            request.args.get('sort_by'), 
            'sort_by',
            default='create_time'
        )
        sort_order = validate_string(
            request.args.get('sort_order'),
            'sort_order',
            default='desc'
        )
        limit = validate_int(
            request.args.get('limit'),
            'limit',
            default=50,
            min_value=1,
            max_value=200
        )
        offset = validate_int(
            request.args.get('offset'),
            'offset',
            default=0,
            min_value=0
        )
        
        items = db.get_interests(
            type_=type_,
            status=status,
            year=year,
            sort_by=sort_by,
            sort_order=sort_order,
            limit=limit,
            offset=offset
        )
        
        # 计算满足条件的总数
        # 使用更高效的方式 - 让数据库提供计数
        total_query_params = {
            'type_': type_, 
            'status': status,
            'year': year
        }
        total = db.count_interests(**total_query_params)
        
        return api_response({
            "items": items,
            "total": total,
            "limit": limit,
            "offset": offset,
            "params": {
                "type": type_,
                "status": status,
                "year": year,
                "sort_by": sort_by,
                "sort_order": sort_order
            }
        })
    except Exception as e:
        logger.error(f"API获取兴趣列表失败: {e}")
        return api_error(str(e), status_code=500, error_type="InternalServerError")

@api_bp.route('/sync', methods=['POST'])
def api_sync():
    """触发数据同步"""
    service_check = check_services()
    if service_check:
        return service_check
    
    if scheduler.is_syncing:
        return api_error("同步已在进行中", status_code=409, error_type="SyncInProgress")
    
    # 获取参数 - 支持JSON和URL参数
    if request.is_json:
        data = request.json or {}
        incremental = validate_bool(data.get('incremental'), 'incremental', True)
    else:
        incremental = validate_bool(request.args.get('incremental'), 'incremental', True)
    
    # 启动异步同步
    try:
        success = scheduler.start_async_sync(incremental)
        
        if success:
            return api_response({
                "status": "started",
                "incremental": incremental,
                "message": "同步已启动"
            })
        else:
            return api_error("无法启动同步", status_code=500, error_type="SyncError")
    except Exception as e:
        logger.error(f"启动同步失败: {e}")
        return api_error(f"启动同步失败: {str(e)}", status_code=500, error_type="InternalServerError")

@api_bp.route('/status', methods=['GET'])
def get_status():
    """获取系统同步状态信息 (不包含统计数据)"""
    service_check = check_services()
    if service_check:
        return service_check
    
    try:
        # 只获取同步状态信息，不包含统计数据
        sync_status = scheduler.get_sync_status()
        
        # 添加说明文字以明确接口职责
        result = {
            "sync_status": sync_status,
            "status_type": "sync_only",
            "message": "此接口仅提供同步状态信息，不包含统计数据。统计数据请使用 /api/statistics 接口获取。"
        }
        
        return api_response(result)
    except Exception as e:
        logger.error(f"获取同步状态失败: {e}")
        return api_error(f"获取同步状态失败: {str(e)}", status_code=500, error_type="InternalServerError")

@api_bp.route('/statistics', methods=['GET'])
def get_statistics():
    """获取所有类型的统计数据概览"""
    service_check = check_services()
    if service_check:
        return service_check
    
    try:
        skip_cache = validate_bool(request.args.get('skip_cache'), 'skip_cache', False)
        result = stats_service.get_dashboard(type_=None, skip_cache=skip_cache)
        
        return api_response(result)
    except Exception as e:
        logger.error(f"获取统计数据失败: {e}")
        return api_error(f"获取统计数据失败: {str(e)}", status_code=500, error_type="InternalServerError")

@api_bp.route('/sync/images', methods=['POST'])
def trigger_image_sync():
    """触发图片同步"""
    service_check = check_services()
    if service_check:
        return service_check
    
    # 获取参数
    data = request.json or {}
    max_items = validate_int(data.get('max_items'), 'max_items', None, min_value=1)
    
    try:
        # 使用sync_manager中的函数
        from services.sync.sync_manager import sync_images
        
        # 创建线程执行图片同步，传递所需的组件实例
        thread = threading.Thread(
            target=sync_images,
            args=(db, scheduler, image_service, max_items),
            daemon=True
        )
        thread.start()
        
        return api_response({
            "status": "started",
            "message": "图片同步已启动",
            "max_items": max_items
        })
    except Exception as e:
        logger.error(f"启动图片同步失败: {e}")
        return api_error(f"无法启动图片同步: {str(e)}", status_code=500, error_type="InternalServerError")
    
@api_bp.route('/sync/images/status', methods=['GET'])
def image_sync_status():
    """获取图片同步状态"""
    service_check = check_services()
    if service_check:
        return service_check
    
    try:
        # 获取未缓存图片的数量
        no_cache_count = len(db.get_items_without_local_image())
        
        # 使用新的服务架构获取状态信息
        status = image_service.get_service_status() if image_service else {}
        status["no_cache_count"] = no_cache_count
        
        return api_response(status)
    except Exception as e:
        logger.error(f"获取图片同步状态失败: {e}")
        return api_error(f"获取图片同步状态失败: {str(e)}", status_code=500, error_type="InternalServerError")

@api_bp.route('/interests/<string:item_id>', methods=['GET'])
def api_interest_detail(item_id):
    """获取单个条目详情API"""
    service_check = check_services()
    if service_check:
        return service_check
    
    try:
        # 获取条目详情
        item = db.get_interest_by_id(item_id)
        if not item:
            return api_error(f"未找到条目: {item_id}", status_code=404, error_type="NotFound")
            
        # 解析原始JSON (使用安全工具)
        if 'raw_json' in item and item['raw_json']:
            try:
                from utils.serialization_utils import safe_json_loads
                item['raw_data'] = safe_json_loads(item['raw_json'])
            except Exception as e:
                logger.warning(f"解析条目 {item_id} 的raw_json失败: {e}")
        
        # 删除大型JSON字段，避免响应过大
        if 'raw_json' in item:
            del item['raw_json']
            
        return api_response(item)
    except Exception as e:
        logger.error(f"获取条目详情失败: {item_id}: {e}")
        return api_error(f"获取条目详情失败: {str(e)}", status_code=500, error_type="InternalServerError")
    
@api_bp.route('/statistics/<string:type_>', methods=['GET'])
def get_type_statistics(type_):
    """获取特定内容类型的统计数据"""
    service_check = check_services()
    if service_check:
        return service_check
    
    try:
        if not type_ or not isinstance(type_, str):
            return api_error("无效的类型参数", status_code=400, error_type="InvalidParameter")
            
        # 使用新的统计服务获取内容类型统计
        result = stats_service.get_type_specific_stats(type_)
        
        # 处理错误情况
        if 'error' in result:
            return api_error(result['error'], status_code=400, error_type="StatisticsError")
            
        return api_response(result)
    except Exception as e:
        logger.error(f"获取{type_}统计数据失败: {e}")
        return api_error(f"获取{type_}统计数据失败: {str(e)}", status_code=500, error_type="InternalServerError")

@api_bp.route('/statistics/ratings', methods=['GET'])
def get_rating_statistics():
    """获取评分统计数据"""
    service_check = check_services()
    if service_check:
        return service_check
    
    try:
        # 获取可选的类型参数
        type_ = validate_string(request.args.get('type'), 'type')
        
        # 使用新的统计服务获取评分分布
        result = stats_service.get_rating_distribution(type_)
        
        return api_response(result)
    except Exception as e:
        logger.error(f"获取评分统计失败: {e}")
        return api_error(f"获取评分统计失败: {str(e)}", status_code=500, error_type="InternalServerError")

@api_bp.route('/statistics/years', methods=['GET'])
def get_year_statistics():
    """获取年份统计数据"""
    service_check = check_services()
    if service_check:
        return service_check
    
    try:
        # 获取可选的类型参数
        type_ = validate_string(request.args.get('type'), 'type')
        
        # 使用统计服务获取年份分布
        result = stats_service.get_year_distribution(type_)
        
        return api_response(result)
    except Exception as e:
        logger.error(f"获取年份统计失败: {e}")
        return api_error(f"获取年份统计失败: {str(e)}", status_code=500, error_type="InternalServerError")

@api_bp.route('/statistics/genres', methods=['GET'])
def get_genre_statistics():
    """获取标签/分类统计数据"""
    service_check = check_services()
    if service_check:
        return service_check
    
    try:
        # 获取可选的类型和限制参数
        type_ = validate_string(request.args.get('type'), 'type')
        limit = validate_int(
            request.args.get('limit'),
            'limit',
            default=20,
            min_value=1,
            max_value=100
        )
        
        # 使用统计服务获取标签分布
        result = stats_service.get_tag_distribution(type_, limit)
        
        return api_response(result)
    except Exception as e:
        logger.error(f"获取标签统计失败: {e}")
        return api_error(f"获取标签统计失败: {str(e)}", status_code=500, error_type="InternalServerError")

@api_bp.route('/statistics/trends', methods=['GET'])
def get_trend_statistics():
    """获取收藏趋势数据"""
    service_check = check_services()
    if service_check:
        return service_check
    
    try:
        # 获取可选参数
        period = validate_string(request.args.get('period'), 'period', default='month')
        months = validate_int(
            request.args.get('months'),
            'months',
            default=12,
            min_value=1,
            max_value=120
        )
        type_ = validate_string(request.args.get('type'), 'type')
        
        # 使用统计服务获取趋势数据
        result = stats_service.get_collection_trend(period, months, type_)
        
        return api_response(result)
    except Exception as e:
        logger.error(f"获取收藏趋势失败: {e}")
        return api_error(f"获取收藏趋势失败: {str(e)}", status_code=500, error_type="InternalServerError")

@api_bp.route('/statistics/movie-tv', methods=['GET'])
def get_movie_tv_statistics():
    """获取电影与电视剧特定统计数据"""
    service_check = check_services()
    if service_check:
        return service_check
    
    try:
        # 直接获取movie类型的详细统计，包含了tv类型
        result = stats_service.get_type_specific_stats('movie')
        
        return api_response(result)
    except Exception as e:
        logger.error(f"获取电影/电视剧统计失败: {e}")
        return api_error(f"获取电影/电视剧统计失败: {str(e)}", status_code=500, error_type="InternalServerError")

@api_bp.route('/statistics/books', methods=['GET'])
def get_book_statistics():
    """获取图书特定统计数据"""
    service_check = check_services()
    if service_check:
        return service_check
    
    try:
        result = stats_service.get_type_specific_stats('book')
        
        return api_response(result)
    except Exception as e:
        logger.error(f"获取图书统计失败: {e}")
        return api_error(f"获取图书统计失败: {str(e)}", status_code=500, error_type="InternalServerError")

@api_bp.route('/statistics/games', methods=['GET'])
def get_game_statistics():
    """获取游戏特定统计数据"""
    service_check = check_services()
    if service_check:
        return service_check
    
    try:
        result = stats_service.get_type_specific_stats('game')
        
        return api_response(result)
    except Exception as e:
        logger.error(f"获取游戏统计失败: {e}")
        return api_error(f"获取游戏统计失败: {str(e)}", status_code=500, error_type="InternalServerError")

@api_bp.route('/statistics/data-health', methods=['GET'])
def get_data_health():
    """获取数据健康状况"""
    service_check = check_services()
    if service_check:
        return service_check
    
    try:
        # 修复无效数据并返回结果
        result = stats_service.fix_invalid_data()
        
        return api_response(result)
    except Exception as e:
        logger.error(f"数据健康检查失败: {e}")
        return api_error(f"数据健康检查失败: {str(e)}", status_code=500, error_type="InternalServerError")

@api_bp.route('/statistics/complete', methods=['GET'])
def get_complete_stats():
    """获取完整统计数据（用于仪表盘）"""
    service_check = check_services()
    if service_check:
        return service_check
    
    try:
        # 检查是否跳过缓存
        skip_cache = validate_bool(request.args.get('skip_cache'), 'skip_cache', False)
        result = stats_service.get_dashboard(type_=None, skip_cache=skip_cache)
        
        return api_response(result)
    except Exception as e:
        logger.error(f"获取完整统计失败: {e}")
        return api_error(f"获取完整统计失败: {str(e)}", status_code=500, error_type="InternalServerError")

@api_bp.route('/service/status', methods=['GET'])
def get_service_status():
    """获取所有服务组件的状态信息"""
    # 这个接口即使部分服务不可用也尝试提供信息
    services_status = {}
    
    try:
        # 收集所有可用服务的状态
        if stats_service:
            services_status['stats_service'] = stats_service.get_service_status()
            
        if scheduler:
            services_status['scheduler'] = scheduler.get_sync_status()
            
        if image_service:
            services_status['image_service'] = image_service.get_service_status()
            
        if db:
            # 只包含简单的信息，避免泄露敏感数据
            db_status = {
                'available': True,
                'type': type(db).__name__
            }
            
            # 如果数据库实例有get_stats方法，调用它
            if hasattr(db, 'get_stats'):
                try:
                    db_status.update(db.get_stats())
                except Exception as e:
                    logger.warning(f"获取数据库统计信息失败: {e}")
                    
            services_status['database'] = db_status
        
        # 添加全局状态信息
        services_status['global'] = {
            'services_available': all([stats_service, scheduler, image_service, db]),
            'timestamp': datetime.now().timestamp(),
            'server_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }
            
        return api_response(services_status)
    except Exception as e:
        logger.error(f"获取服务状态信息失败: {e}")
        return api_error(f"获取服务状态信息失败: {str(e)}", status_code=500, error_type="InternalServerError")