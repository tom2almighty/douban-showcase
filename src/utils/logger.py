# logger.py 实现概述
import os
import logging
from logging.handlers import RotatingFileHandler
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

# 获取配置
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
LOG_FILE = os.getenv("LOG_FILE", "backend/data/douban-sync.log")

# 确保日志目录存在
os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)

# 配置根记录器
def setup_logger():
    """配置并返回根记录器"""
    # 创建记录器
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, LOG_LEVEL))
    
    # 清除现有处理器(避免重复)
    if root_logger.handlers:
        root_logger.handlers.clear()
    
    # 创建格式化器
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    
    # 添加控制台处理器
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)
    
    # 添加文件处理器
    file_handler = RotatingFileHandler(
        LOG_FILE, 
        maxBytes=10*1024*1024,  # 10MB
        backupCount=5,           # 保留5个备份
        encoding='utf-8'
    )
    file_handler.setFormatter(formatter)
    root_logger.addHandler(file_handler)
    
    return root_logger

# 初始化根记录器
logger = setup_logger()

def get_logger(name):
    """获取指定名称的记录器"""
    return logging.getLogger(name)