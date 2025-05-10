from flask import Flask, render_template
from .api import api_bp, init_api
from .frontend import frontend_bp, init_frontend

def init_routes(app, db, stats_service, scheduler, image_service):
    """初始化所有路由
    
    参数:
        app: Flask应用实例
        db: 数据库实例
        stats_service: 统计服务实例
        scheduler: 调度器实例
        image_service: 图片服务实例
    """
    # 初始化API蓝图
    init_api(db, stats_service, scheduler, image_service)
    app.register_blueprint(api_bp)
    
    # 初始化前端蓝图
    init_frontend(db, stats_service, scheduler, image_service)
    app.register_blueprint(frontend_bp)
    
    # 注册错误处理程序
    register_error_handlers(app)
    
    return app

def register_error_handlers(app):
    """注册全局错误处理程序"""
    @app.errorhandler(404)
    def not_found_error(error):
        return render_template('error.html', message="页面未找到"), 404
        
    @app.errorhandler(500)
    def internal_error(error):
        return render_template('error.html', message="服务器内部错误"), 500