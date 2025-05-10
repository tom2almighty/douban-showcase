import os
import requests
import time
import random
import mimetypes
import hashlib
import threading
from flask import url_for
from datetime import datetime, timedelta
from typing import Dict, Optional, Tuple, List, Any
from urllib.parse import urlparse
from utils.logger import get_logger

# 配置日志
logger = get_logger("image_service")

class ImageService:
    """封面图片下载和管理服务
    
    支持从豆瓣下载封面图片，并提供缓存、智能存储和批量处理功能
    """
    
    # 缓存超时时间（秒）
    MEMORY_CACHE_TTL = 3600  # 1小时
    REQUEST_TIMEOUT = 15  # 请求超时时间
    RETRY_ATTEMPTS = 3  # 重试次数
    
    def __init__(self):
        """初始化图片服务"""
        # 从环境变量中读取配置
        self.download_covers = os.getenv("DOWNLOAD_COVERS", "false").lower() == "true"
        # 本地存储路径
        self.local_path = os.getenv("LOCAL_COVER_PATH", "data/covers")
        # 域名设置
        self.server_domain = os.getenv("SERVER_DOMAIN", "").rstrip("/")
        self.display_strategy = os.getenv("COVER_DISPLAY_STRATEGY", "mixed").lower()
        # 存储类型设置
        self.storage_type = "local"
        logger.info(f"图片服务配置: 下载={self.download_covers}, 策略={self.display_strategy}, 路径={self.local_path}")
        # 从环境变量中获取支持的内容类型
        sync_types_str = os.getenv("DOUBAN_SYNC_TYPES", "movie,book")
        self.supported_types = [type_.strip() for type_ in sync_types_str.split(",") if type_.strip()]
        
        # 请求头设置 - 添加随机User-Agent池
        self.user_agents = [
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15',
            'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36',
            'Mozilla/5.0 (iPhone; CPU iPhone OS 16_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.5 Mobile/15E148 Safari/604.1'
        ]
        
        self.referers = [
            'https://movie.douban.com/',
            'https://book.douban.com/',
            'https://music.douban.com/',
            'https://www.douban.com/'
        ]
        
        # 更新请求头
        self._update_headers()
        
        # 创建会话对象复用连接
        self.session = requests.Session()
        self.session.headers.update(self.headers)
        
        # 初始化内存缓存
        self._cache = {}
        self._cache_lock = threading.Lock()
        
        # 初始化计数器
        self.download_count = 0
        self.error_count = 0
        
        # 初始化存储目录
        if self.download_covers and self.storage_type == "local":
            self._init_storage_dirs()
            
        logger.info(f"图片服务初始化完成，存储类型: {self.storage_type}, 下载图片: {'是' if self.download_covers else '否'}")
        
    def _update_headers(self):
        """更新请求头，使用随机User-Agent和Referer"""
        self.headers = {
            'User-Agent': random.choice(self.user_agents),
            'Referer': random.choice(self.referers),
            'Accept': 'image/avif,image/webp,image/apng,image/*,*/*;q=0.8',
            'Accept-Encoding': 'gzip, deflate, br',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
            'Cache-Control': 'no-cache'
        }
        
    def _init_storage_dirs(self):
        """初始化存储目录结构"""
        try:
            # 创建主目录
            os.makedirs(self.local_path, exist_ok=True)
            
            # 为所有支持的类型创建目录
            created = 0
            for type_dir in self.supported_types:
                dir_path = os.path.join(self.local_path, type_dir.lower())
                if not os.path.exists(dir_path):
                    os.makedirs(dir_path, exist_ok=True)
                    created += 1
            
            if created > 0:
                logger.info(f"创建了 {created} 个图片存储目录")
        except Exception as e:
            logger.error(f"初始化存储目录失败: {e}")
     
    def _add_random_delay(self, error_count: int = 0):
        """添加随机延迟，避免请求过于频繁
        
        参数:
            error_count: 错误计数，用于增加延迟
        """
        # 基础延迟
        base_delay = 0.5
        # 根据错误次数增加延迟
        if error_count > 0:
            base_delay += 0.5 * min(error_count, 10)
            
        # 增加随机因子
        delay = random.uniform(base_delay, base_delay * 2.0)
        time.sleep(delay)
        
    def _get_file_extension(self, url: str, content_type: str = None) -> str:
        """根据URL或内容类型获取文件扩展名
        
        参数:
            url: 图片URL
            content_type: 内容类型，例如 'image/jpeg'
            
        返回:
            文件扩展名（包括点，例如 '.jpg'）
        """
        # 尝试从URL路径中获取扩展名
        path = urlparse(url).path
        ext = os.path.splitext(path)[1].lower()
        
        # 检查扩展名是否是已知的图片扩展名
        valid_image_exts = ['.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp']
        if ext in valid_image_exts:
            return ext
            
        # 如果URL中没有有效扩展名，使用内容类型判断
        if content_type:
            if content_type == 'image/jpeg':
                return '.jpg'
            elif content_type == 'image/png':
                return '.png'
            elif content_type == 'image/gif':
                return '.gif'
            elif content_type == 'image/webp':
                return '.webp'
            elif content_type == 'image/bmp':
                return '.bmp'
            # 尝试通过mimetypes库猜测
            ext = mimetypes.guess_extension(content_type)
            if ext:
                return ext
            
        # 如果仍无法确定，使用默认扩展名
        return '.jpg'
    
    def _get_cache_key(self, url: str, item_id: str, item_type: str) -> str:
        """生成缓存键"""
        # 使用URL、ID和类型生成唯一键
        combined = f"{url}|{item_id}|{item_type}"
        return hashlib.md5(combined.encode()).hexdigest()
        
    def _get_from_cache(self, url: str, item_id: str, item_type: str) -> Optional[Dict[str, Any]]:
        """从缓存获取结果"""
        cache_key = self._get_cache_key(url, item_id, item_type)
        
        with self._cache_lock:
            if cache_key in self._cache:
                cache_entry = self._cache[cache_key]
                # 检查缓存是否过期
                if datetime.now() < cache_entry['expires']:
                    return cache_entry['data']
                else:
                    # 删除过期缓存
                    del self._cache[cache_key]
                    
        return None
        
    def _save_to_cache(self, url: str, item_id: str, item_type: str, data: Dict[str, Any]) -> None:
        """保存结果到缓存"""
        cache_key = self._get_cache_key(url, item_id, item_type)
        expires = datetime.now() + timedelta(seconds=self.MEMORY_CACHE_TTL)
        
        with self._cache_lock:
            # 删除旧缓存，保证内存不爆炸
            if len(self._cache) > 1000:  # 最多缓存1000项
                # 找出并删除最老的10%缓存
                items = list(self._cache.items())
                items.sort(key=lambda x: x[1]['expires'])
                for k, _ in items[:len(items)//10]:
                    del self._cache[k]
            
            # 保存新结果
            self._cache[cache_key] = {
                'data': data,
                'expires': expires
            }

    def download_cover(self, image_url: str, item_type: str, item_id: str, force_download: bool = False) -> Optional[str]:
        """下载并存储封面图片
        
        参数:
            image_url: 图片URL
            item_type: 条目类型 ('movie' 或 'book')
            item_id: 条目ID
            force_download: 是否强制下载，忽略环境变量设置
            
        返回:
            本地存储路径（相对路径），失败则返回None
        """
        # 检查参数
        if not image_url or not item_id or not item_type:
            logger.warning("缺少参数，无法下载图片")
            return None
            
        # 如果禁用了图片下载且不是强制下载，直接返回None
        if not self.download_covers and not force_download:
            return None
            
        # 检查缓存
        cached_result = self._get_from_cache(image_url, item_id, item_type)
        if cached_result and cached_result.get('local_path'):
            return cached_result['local_path']
        
        # 每10次下载更新一次请求头，避免被反爬
        if self.download_count % 10 == 0:
            self._update_headers()
            self.session.headers.update(self.headers)
            
        self.download_count += 1
        
        # 添加随机延迟
        self._add_random_delay(self.error_count)
        
        # 执行下载请求，支持重试
        for attempt in range(self.RETRY_ATTEMPTS):
            try:
                # 防止URL没有协议前缀
                if not image_url.startswith(('http://', 'https://')):
                    image_url = f"https:{image_url}" if image_url.startswith('//') else f"https://{image_url}"
                    
                # 发送HTTP请求获取图片
                response = self.session.get(
                    image_url, 
                    timeout=self.REQUEST_TIMEOUT,
                    stream=True  # 使用流式请求，避免大图片占用太多内存
                )
                response.raise_for_status()
                
                # 获取文件扩展名
                ext = self._get_file_extension(image_url, response.headers.get('Content-Type'))
                
                # 构建文件名和路径
                filename = f"{item_id}{ext}"
                type_dir = item_type.lower()
                
                # 确保类型目录存在
                type_path = os.path.join(self.local_path, type_dir)
                if not os.path.exists(type_path):
                    os.makedirs(type_path, exist_ok=True)
                
                # 构建存储路径
                rel_path = os.path.join(type_dir, filename)
                abs_path = os.path.join(self.local_path, rel_path)
                
                # 写入文件 - 使用流式写入处理大文件
                with open(abs_path, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
                
                # 检查文件是否写入成功
                if os.path.exists(abs_path) and os.path.getsize(abs_path) > 0:
                    # 计算文件大小
                    file_size = os.path.getsize(abs_path)
                    
                    # 记录成功
                    logger.debug(f"图片保存成功: {type_dir}/{item_id}, 大小: {file_size/1024:.1f}KB")
                    
                    # 缓存结果
                    result = {
                        "original_url": image_url,
                        "local_path": rel_path,
                        "file_size": file_size
                    }
                    self._save_to_cache(image_url, item_id, item_type, result)
                    
                    # 重置错误计数
                    self.error_count = max(0, self.error_count - 1)
                    return rel_path
                else:
                    # 文件写入失败
                    logger.warning(f"图片保存失败，文件为空: {type_dir}/{item_id}")
                    # 删除空文件
                    try:
                        if os.path.exists(abs_path):
                            os.remove(abs_path)
                    except:
                        pass
                    continue
                
            except requests.RequestException as e:
                self.error_count += 1
                retry_wait = min(2 ** attempt, 10)  # 指数退避策略
                logger.warning(f"下载图片失败({attempt+1}/{self.RETRY_ATTEMPTS}): {type(e).__name__}, 等待{retry_wait}秒后重试")
                time.sleep(retry_wait)
                continue
            except Exception as e:
                self.error_count += 1
                logger.error(f"处理图片失败: {type(e).__name__}: {str(e)}")
                return None
                
        # 所有重试都失败
        logger.error(f"下载图片失败，已尝试{self.RETRY_ATTEMPTS}次: {item_type}/{item_id}")
        return None

    def sync_all_images(self, db_instance, max_items: int = None, force_download: bool = False) -> Tuple[int, int]:
        """同步所有需要下载的图片
        
        参数:
            db_instance: 数据库实例
            max_items: 最大处理数量，None表示处理所有
            force_download: 是否强制下载，忽略环境变量设置
            
        返回:
            (成功数, 失败数)
        """
        # 如果禁用了图片下载且不是强制下载，直接返回
        if not self.download_covers and not force_download:
            logger.info("图片下载功能已禁用，跳过同步")
            return (0, 0)
        
        try:
            # 获取所有需要同步图片的条目（没有本地图片的条目）
            items = db_instance.get_items_without_local_image()
            
            if not items:
                logger.info("没有需要同步的图片")
                return (0, 0)
                
            logger.info(f"找到 {len(items)} 个需要同步封面图片的条目")
            
            return self._batch_process_items(db_instance, items, max_items, force_download)
            
        except Exception as e:
            logger.error(f"图片同步过程中发生错误: {e}")
            return (0, 0)
    





    def get_image_url(self, db_instance, item_id: str, cover_url: str) -> str:
        """获取图片URL，根据display_strategy决定返回策略"""
        if not item_id and not cover_url:
            logger.warning(f"获取图片URL参数不完整: ID={item_id}, URL={cover_url}")
            return "/static/images/no-cover.png"

        # 获取环境变量配置
        proxy_enabled = os.getenv("COVER_PROXY", "false").lower() == "true"
        # 优先处理 local 策略
        if self.display_strategy in ["local", "mixed"]:
            try:
                # 检查数据库中是否有本地路径记录
                item = db_instance.get_interest_by_id(item_id)
                if item and item.get('local_path'):
                    rel_path = item['local_path']
                    abs_path = os.path.join(self.local_path, rel_path)

                    # 确认本地文件存在
                    if os.path.exists(abs_path) and os.path.getsize(abs_path) > 0:
                        # 使用正斜杠统一路径格式，确保URL正确生成
                        normalized_path = rel_path.replace("\\", "/")
                        # 移除可能存在的前导斜杠，避免路径重复
                        if normalized_path.startswith('/'):
                            normalized_path = normalized_path[1:]
                        # 使用 url_for 动态生成 URL
                        return url_for('frontend.serve_cover', filename=normalized_path)
                    else:
                        logger.warning(f"本地图片文件丢失: {rel_path}")
            except Exception as e:
                logger.error(f"获取本地图片路径时出错: {e}")

        # original 策略或 mixed 策略的回退
        if self.display_strategy in ["original", "mixed"]:
            if cover_url:
                if proxy_enabled:
                    # 使用代理解决防盗链问题
                    return f"/proxy/image?url={cover_url}"
                else:
                    # 使用 no-referrer 方式
                    return cover_url

        # 如果没有找到图片，返回占位图
        return "/static/images/no-cover.png"
           
    def _batch_process_items(self, db_instance, items: List[Dict[str, Any]], max_items: int = None, force_download: bool = False) -> Tuple[int, int]:
        """批量处理图片下载
        
        参数:
            db_instance: 数据库实例
            items: 条目列表
            max_items: 最大处理数量
            force_download: 是否强制下载，忽略环境变量设置
            
        返回:
            (成功数, 失败数)
        """
        if not items:
            return (0, 0)
            
        # 限制处理数量
        if max_items and len(items) > max_items:
            items = items[:max_items]
            logger.info(f"限制处理数量为 {max_items} 个")
            
        success = 0
        failed = 0
        start_time = time.time()
        
        # 进度显示间隔
        progress_interval = max(1, min(len(items) // 10, 50))
        
        for i, item in enumerate(items):
            # 定期显示进度
            if i > 0 and i % progress_interval == 0:
                elapsed = time.time() - start_time
                items_per_second = i / elapsed if elapsed > 0 else 0
                estimated_remaining = (len(items) - i) / items_per_second if items_per_second > 0 else 0
                logger.info(f"进度: {i}/{len(items)} ({i/len(items)*100:.1f}%), "
                        f"速度: {items_per_second:.2f}项/秒, "
                        f"预计剩余时间: {int(estimated_remaining/60)}分{int(estimated_remaining%60)}秒")
            
            item_id = item.get("id")
            item_type = item.get("type")
            cover_url = item.get("cover_url")
            
            # 验证必要字段
            if not all([item_id, item_type, cover_url]):
                logger.warning(f"跳过不完整的条目: {item}")
                failed += 1
                continue
                
            try:
                # 下载封面，传递force_download参数
                local_path = self.download_cover(cover_url, item_type, item_id, force_download)
                
                if local_path:
                    # 更新数据库中的本地路径
                    if db_instance.update_interest_local_path(item_id, local_path):
                        success += 1
                    else:
                        logger.warning(f"更新数据库路径失败: {item_id}")
                        failed += 1
                else:
                    failed += 1
            except Exception as e:
                logger.error(f"处理条目 {item_id} ({item_type}) 图片时出错: {e}")
                failed += 1
        
        # 显示最终结果
        elapsed = time.time() - start_time
        logger.info(f"图片同步完成，成功: {success}, 失败: {failed}, 耗时: {elapsed:.1f}秒")
        
        return (success, failed)
        
    def clear_cache(self):
        """清空内存缓存"""
        with self._cache_lock:
            self._cache = {}
        logger.info("内存缓存已清空")
        
    def get_service_status(self) -> Dict[str, Any]:
        """获取服务状态信息"""
        status = {
            "enabled": self.download_covers,
            "storage_type": self.storage_type,
            "display_strategy": self.display_strategy,
            "supported_types": self.supported_types,
            "cache_size": len(self._cache),
            "download_count": self.download_count,
            "error_count": self.error_count
        }
        
        if self.storage_type == "local":
            # 尝试获取存储统计信息
            try:
                total_size = 0
                file_count = 0
                
                for root, dirs, files in os.walk(self.local_path):
                    for file in files:
                        try:
                            file_path = os.path.join(root, file)
                            total_size += os.path.getsize(file_path)
                            file_count += 1
                        except:
                            pass
                            
                status["storage_stats"] = {
                    "file_count": file_count,
                    "total_size_mb": round(total_size / (1024 * 1024), 2),
                    "storage_path": self.local_path
                }
            except Exception as e:
                logger.error(f"获取存储统计信息失败: {e}")
                
        return status