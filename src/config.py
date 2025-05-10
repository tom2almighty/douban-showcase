# 配置文件内容如下
import os
from dotenv import load_dotenv

# 确保加载环境变量
load_dotenv()

def load_config():
    """加载应用配置
    
    从环境变量中读取配置，设置默认值，并进行必要的类型转换
    
    返回:
        dict: 包含所有配置项的字典
    """
    config = {
        # 基础设置
        'timezone': os.getenv("TIMEZONE", "Asia/Shanghai"),
        'debug': os.getenv("DEBUG", "false").lower() == "true",
        
        # 服务器设置
        'host': os.getenv("API_HOST", "0.0.0.0"),
        'port': int(os.getenv("API_PORT", "5000")),
        'server_domain': os.getenv("SERVER_DOMAIN", "").rstrip("/"),
        
        # 同步设置
        'enable_auto_sync': os.getenv("ENABLE_AUTO_SYNC", "false").lower() == "true",
        'sync_interval': int(os.getenv("SYNC_INTERVAL_HOURS", "24")),
        
        # 豆瓣API设置
        'douban_user_id': os.getenv("DOUBAN_USER_ID"),
        'douban_sync_types': os.getenv("DOUBAN_SYNC_TYPES", "movie,book").split(","),
        
        # 图片设置
        'download_covers': os.getenv("DOWNLOAD_COVERS", "false").lower() == "true",
        'local_cover_path': os.getenv("LOCAL_COVER_PATH", "data/covers"),
        'cover_display_strategy': os.getenv("COVER_DISPLAY_STRATEGY", "mixed").lower(),
        
        # 日志设置
        'log_level': os.getenv("LOG_LEVEL", "INFO"),
        'log_file': os.getenv("LOG_FILE", "data/douban-sync.log"),
    }
    
    # 应用系统时区
    os.environ["TZ"] = config['timezone']
    try:
        # 尝试设置系统时区
        import time
        time.tzset()
    except AttributeError:
        # Windows不支持tzset
        pass
    
    return config

# 导出默认配置
config = load_config()