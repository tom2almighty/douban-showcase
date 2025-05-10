import os
import sys
import argparse
import time
import signal
import threading
from flask import Flask
from dotenv import load_dotenv
from routes import init_routes
from config import config
from utils.logger import get_logger
from utils.validation_utils import validate_int, validate_string, validate_bool

load_dotenv() 

# 添加当前目录及父目录到模块搜索路径，确保可以导入现有模块
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.append(current_dir)

# 导入服务组件
from services.data.database import Database
from services.sync.scheduler import Scheduler
from services.media.image_service import ImageService
from services.analytics.statistics_service import StatisticsService
from services.sync.sync_manager import sync_images, sync_all, schedule_sync_tasks, sync_images_override

# 配置日志
logger = get_logger("flask_app")

# 创建应用工厂函数
def create_app(test_config=None):
    """创建并配置Flask应用
    
    参数:
        test_config (dict): 测试配置，如果提供则覆盖默认配置
        
    返回:
        tuple: (app, db, stats_service, scheduler, image_service) 元组
    """
    # 创建Flask应用
    app = Flask(__name__, 
                template_folder="templates",
                static_folder="static")
    
    # 加载配置
    app_config = test_config if test_config else config
    
    # 设置Flask配置
    app.config.update(
        SECRET_KEY=os.urandom(24),
        DEBUG=validate_bool(app_config.get('debug'), 'debug', False)
    )
    
    # 初始化组件
    db, stats_service, scheduler, image_service = initialize_components(app_config)
    
    # 初始化路由
    if db and stats_service and scheduler and image_service:
        init_routes(app, db, stats_service, scheduler, image_service)
    else:
        logger.error("组件初始化失败，无法注册路由")
        return None, None, None, None, None
        
    # 注册优雅关闭处理函数
    register_shutdown_handler()
    
    return app, db, stats_service, scheduler, image_service

def initialize_components(app_config):
    """初始化必要的组件
    
    实现依赖注入模式，确保组件按正确顺序初始化
    
    参数:
        app_config (dict): 应用配置
        
    返回:
        tuple: (db, stats_service, scheduler, image_service) 组件元组
    """
    components = {
        'db': None,
        'image_service': None,
        'scheduler': None,
        'stats_service': None
    }
    
    try:
        # 1. 首先初始化数据库，作为核心依赖
        logger.info("初始化数据库...")
        components['db'] = Database()
        if not components['db']:
            logger.error("数据库初始化失败")
            return None, None, None, None
            
        # 2. 初始化独立服务（不依赖于其他服务的组件）
        logger.info("初始化图片服务...")
        components['image_service'] = ImageService()
        
        # 3. 初始化依赖于数据库和图片服务的调度器
        logger.info("初始化调度器...")
        if components['db'] and components['image_service']:
            components['scheduler'] = Scheduler(
                db_instance=components['db'], 
                image_service=components['image_service']
            )
        else:
            logger.error("调度器初始化失败：缺少必要的依赖组件")
            return None, None, None, None
        
        # 4. 初始化统计服务（依赖于数据库）
        logger.info("初始化统计服务...")
        if components['db']:
            components['stats_service'] = StatisticsService(db_instance=components['db'])
        else:
            logger.error("统计服务初始化失败：缺少数据库实例")
            return None, None, None, None
        
        # 5. 配置自动同步（如果启用）
        if validate_bool(app_config.get('enable_auto_sync'), 'enable_auto_sync', False):
            sync_interval = validate_int(
                app_config.get('sync_interval'), 
                'sync_interval', 
                24,  # 默认24小时
                min_value=1, 
                max_value=168  # 最多一周
            )
            logger.info(f"启动自动同步，间隔: {sync_interval}小时")
            
            # 确保所有依赖组件都已成功初始化
            if all(components.values()):
                schedule_sync_tasks(components['scheduler'], sync_interval)
                time.sleep(0.5)  # 等待调度器启动
            else:
                logger.warning("无法启动自动同步，某些组件初始化失败")
        
        logger.info("组件初始化完成")
        
        # 验证所有组件是否都已成功初始化
        if not all(components.values()):
            missing = [k for k, v in components.items() if v is None]
            logger.error(f"组件初始化不完整，缺少: {', '.join(missing)}")
            return None, None, None, None
            
        return (
            components['db'], 
            components['stats_service'], 
            components['scheduler'], 
            components['image_service']
        )
        
    except Exception as e:
        logger.error(f"初始化组件失败: {e}")
        # 在出错时，尝试清理已创建的资源
        try:
            # 关闭数据库连接
            if components['db']:
                if hasattr(components['db'], 'close_all_connections'):
                    components['db'].close_all_connections()
        except Exception as cleanup_error:
            logger.error(f"清理资源时出错: {cleanup_error}")
            
        return None, None, None, None

def register_shutdown_handler():
    """注册信号处理函数，用于优雅关闭应用"""
    def graceful_shutdown(signum, frame):
        logger.info("接收到关闭信号，正在关闭应用...")
        # 这里可以添加清理逻辑，如关闭连接等
        sys.exit(0)

    # 注册信号处理函数
    signal.signal(signal.SIGINT, graceful_shutdown)
    signal.signal(signal.SIGTERM, graceful_shutdown)
    
def main():
    """主函数，应用入口点"""
    # 解析命令行参数
    parser = argparse.ArgumentParser(description="豆瓣数据同步与展示服务")
    parser.add_argument('--sync', action='store_true', help="启动时执行全量同步")
    parser.add_argument('--sync-incremental', action='store_true', help="启动时执行增量同步")
    parser.add_argument('--sync-images', action='store_true', help="启动时同步封面图片")
    parser.add_argument('--clear-cache', action='store_true', help="清除统计数据缓存")
    parser.add_argument('--port', type=int, default=None, help="服务端口")
    parser.add_argument('--host', type=str, default=None, help="服务监听地址")
    args = parser.parse_args()
    
    # 使用工厂函数创建应用
    app, db, stats_service, scheduler, image_service = create_app()
    
    if not app or not stats_service or not db or not scheduler or not image_service:
        logger.error("应用初始化失败")
        sys.exit(1)
    
    # 如果指定了清除缓存
    if args.clear_cache:
        logger.info("清除统计数据缓存...")
        result = stats_service.clear_caches()
        if result.get('success', False):
            logger.info("缓存清除成功")
        else:
            logger.warning(f"缓存清除失败: {result.get('error', '未知错误')}")
    
    if args.sync:
        logger.info("执行启动时全量同步...")
        success = sync_all(scheduler, incremental=False)
        if success:
            logger.info("全量同步完成")
            # 同步完成后清除统计缓存
            stats_service.clear_caches()
        else:
            logger.warning("全量同步未完全成功")
    
    # 如果指定了启动时增量同步
    elif args.sync_incremental:
        logger.info("执行启动时增量同步...")
        success = sync_all(scheduler, incremental=True)
        if success:
            logger.info("增量同步完成")
            stats_service.clear_caches()
        else:
            logger.warning("增量同步未完全成功")
    

    # 如果指定了启动时图片同步
    if args.sync_images:
        logger.info("执行启动时图片同步...")
        thread = threading.Thread(
            target=sync_images_override, 
            args=(db, scheduler, image_service),
            daemon=True
        )
        thread.start()
    
    # 运行应用 - 优先使用命令行参数，其次是配置文件
    port = validate_int(
        args.port if args.port is not None else config.get('port'),
        'port',
        5000,  # 默认端口
        min_value=1024,
        max_value=65535
    )
    
    host = validate_string(
        args.host if args.host is not None else config.get('host'),
        'host',
        '0.0.0.0'  # 默认监听所有接口
    )
    
    debug = validate_bool(config.get('debug'), 'debug', False)
    
    logger.info(f"启动服务，监听: {host}:{port}")
    app.run(debug=debug, host=host, port=port)

if __name__ == '__main__':
    main()