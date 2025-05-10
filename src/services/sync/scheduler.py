import os
import time
import threading
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime, timedelta

# 更新导入路径
from services.api.douban_api import DoubanAPI
from services.data.database import Database
from services.media.image_service import ImageService
from utils.logger import get_logger

# 配置日志
logger = get_logger("scheduler")

class Scheduler:
    """豆瓣数据增量更新调度器
    
    负责定期从豆瓣API获取最新数据并更新数据库，支持增量更新以减少API请求
    """
    
    # 预检机制配置
    PRE_CHECK_SAMPLE_SIZE = 5  # 用于预检的样本大小
    CONSECUTIVE_OLD_PAGES_THRESHOLD = 3  # 连续遇到旧页面的阈值，用于提前终止
    MIN_PAGES_TO_CHECK = 2  # 至少要检查的页面数，即使第一页就全是旧数据
    FULL_SYNC_DAYS = 30  # 每隔多少天执行一次全量同步
    
    def __init__(self, user_id: str = None, db_instance: Database = None, 
                api_instance: DoubanAPI = None, image_service: ImageService = None):
        """初始化调度器
        
        参数:
            user_id: 豆瓣用户ID，如果为None则从环境变量获取
            db_instance: 数据库实例，如果为None则创建新实例
            api_instance: API客户端实例，如果为None则创建新实例
            image_service: 图片服务实例，如果为None则创建新实例
        """
        self.user_id = user_id or os.getenv("DOUBAN_USER_ID")
        if not self.user_id:
            raise ValueError("未设置豆瓣用户ID，请设置DOUBAN_USER_ID环境变量")
            
        # 初始化依赖组件
        self.api = api_instance or DoubanAPI()
        self.db = db_instance or Database()
        self.image_service = image_service
        
        # 获取需要同步的数据类型 (默认为 movie 和 book)
        sync_types_str = os.getenv("DOUBAN_SYNC_TYPES", "movie,book")
        self.sync_types = [t.strip() for t in sync_types_str.split(",") if t.strip()]
        logger.info(f"配置的同步类型: {', '.join(self.sync_types)}")
        
        # 下载图片设置
        self.download_covers = os.getenv("DOWNLOAD_COVERS", "false").lower() == "true"
        logger.info(f"图片下载设置: {'启用' if self.download_covers else '禁用'}")
        
        # 同步状态记录
        self._sync_lock = threading.Lock()
        self._is_syncing = False
        self._last_sync = None
        self._last_full_sync = None
        
        logger.info(f"调度器初始化完成，用户ID: {self.user_id}")
    
    @property
    def is_syncing(self) -> bool:
        """是否正在同步中"""
        with self._sync_lock:
            return self._is_syncing
    
    @property
    def last_sync(self) -> Optional[datetime]:
        """上次同步时间"""
        return self._last_sync
        
    @property
    def last_full_sync(self) -> Optional[datetime]:
        """上次全量同步时间"""
        return self._last_full_sync
    
    def _set_sync_state(self, state: bool, is_full: bool = False):
        """设置同步状态"""
        with self._sync_lock:
            self._is_syncing = state
            if state is False:
                self._last_sync = datetime.now()
                if is_full:
                    self._last_full_sync = datetime.now()
    
    def sync_all_data(self, incremental: bool = True):
        """同步所有配置的内容类型数据
        
        参数:
            incremental: 是否使用增量更新
        
        返回:
            bool: 同步是否成功
        """
        if self.is_syncing:
            logger.warning("已有同步任务在进行中，请稍后再试")
            return False
            
        try:
            self._set_sync_state(True, not incremental)
            logger.info(f"开始同步所有数据，模式: {'增量' if incremental else '全量'}")
            
            # 检查是否需要强制全量同步
            if incremental and self._last_full_sync:
                days_since_full_sync = (datetime.now() - self._last_full_sync).days
                if days_since_full_sync >= self.FULL_SYNC_DAYS:
                    logger.info(f"距离上次全量同步已有 {days_since_full_sync} 天，强制执行全量同步")
                    incremental = False
                    self._set_sync_state(True, True)  # 更新为全量同步状态
            
            # 遍历同步所有配置的内容类型
            all_success = True
            
            # 跳过tv类型的同步，因为它会在movie同步时被处理
            sync_types = [t for t in self.sync_types if t != "tv" or "movie" not in self.sync_types]
            for content_type in sync_types:
                result = self.sync_data_by_type(content_type, incremental)
                if not result:
                    all_success = False
                    logger.warning(f"类型 {content_type} 同步未完全成功")
            
            # 如果配置了图片服务，同步图片 - 改为使用image_service的download_covers属性
            if self.image_service:
                if self.image_service.download_covers:  # 使用image_service的属性而非scheduler的
                    from services.sync.sync_manager import sync_images
                    logger.info("开始同步封面图片...")
                    sync_images(self.db, self, self.image_service)
                    logger.info("封面图片同步完成")
                else:
                    logger.info("图片下载功能已禁用（DOWNLOAD_COVERS=false），跳过图片同步")
            
            logger.info("所有数据同步完成")
            return all_success
        except Exception as e:
            logger.error(f"同步过程中发生错误: {e}")
            return False
        finally:
            self._set_sync_state(False, not incremental)
    
    def _pre_check_updates(self, type_: str, status: str, latest_timestamp: str) -> Tuple[bool, int, int]:
        """预检是否有新数据"""
        if not latest_timestamp:
            logger.info(f"{type_} {status} 没有历史数据，需要完整同步")
            return True, 0, 0
        
        try:
            # 只获取第一页数据进行预检
            logger.info(f"{type_} {status} 执行预检，最新时间戳: {latest_timestamp}")
            first_page = self.api.get_interests_page(self.user_id, type_, status, page=1)
            
            if not first_page or not first_page.get('interests'):
                logger.info(f"{type_} {status} 预检: API返回空结果")
                return False, 0, 0
            
            # 获取总条目数
            total_count = first_page.get('total', 0)
            
            # 特殊处理movie类型，需要考虑tv类型
            if type_ == "movie":
                # 获取本地计数
                local_movie_count = self.db.get_interest_count("movie", status)
                local_tv_count = self.db.get_interest_count("tv", status)
                local_count = local_movie_count + local_tv_count
                logger.info(f"{type_} {status} 预检: API返回 {total_count} 条，本地 movie({local_movie_count})+tv({local_tv_count})={local_count} 条")
                
                # 同时获取movie和tv类型的最新时间戳，使用较新的那个
                tv_timestamp = self.db.get_latest_timestamps("tv").get(status, "")
                if tv_timestamp and tv_timestamp > latest_timestamp:
                    logger.info(f"使用tv类型的时间戳 {tv_timestamp} 代替 movie类型时间戳 {latest_timestamp} 进行比较")
                    latest_timestamp = tv_timestamp
            else:
                local_count = self.db.get_interest_count(type_, status)
                logger.info(f"{type_} {status} 预检: API返回 {total_count} 条，本地 {local_count} 条")
            
            # 如果数量不一致，认为有更新
            if total_count != local_count:
                # 为了避免微小差异导致不必要的同步，添加容差
                diff = abs(total_count - local_count)
                # 对于大量数据，允许小幅差异
                if diff <= 3 or (total_count > 100 and diff / total_count <= 0.02):
                    logger.info(f"{type_} {status} 预检: 条目数差异在容许范围内 ({diff} 条), 继续检查时间戳")
                else:
                    logger.info(f"{type_} {status} 预检: 条目数不一致，需要同步")
                    return True, total_count, local_count
            
            # 获取前几条记录并比对时间戳
            interests = first_page.get('interests', [])
            for i, item in enumerate(interests[:self.PRE_CHECK_SAMPLE_SIZE]):
                item_time = item.get("create_time", "")
                
                # 如果有任何一条记录比最新时间戳新，则有更新
                if item_time > latest_timestamp:
                    logger.info(f"{type_} {status} 预检: 发现新数据，时间戳 {item_time} > {latest_timestamp}")
                    return True, total_count, local_count
            
            logger.info(f"{type_} {status} 预检: 没有发现新数据")
            return False, total_count, local_count
            
        except Exception as e:
            logger.error(f"{type_} {status} 预检失败: {e}")
            # 预检失败时保守起见认为有更新
            return True, 0, 0
    
    def sync_data_by_type(self, type_: str, incremental: bool = True) -> bool:
        """同步指定类型的数据
        
        参数:
            type_: 内容类型 ('movie', 'book', 'tv', 'music', 'game', 'drama' 等)
            incremental: 是否使用增量更新
            
        返回:
            bool: 同步是否成功
        """
        logger.info(f"开始同步{type_}数据，增量模式: {incremental}")
        
        # 获取当前数据库中的最新时间戳
        latest_timestamps = {}
        if incremental:
            latest_timestamps = self.db.get_latest_timestamps(type_)
            logger.info(f"{type_}数据最新时间戳: {latest_timestamps}")
        
        # 状态映射 - 所有类型都使用这三种状态
        statuses = ["mark", "doing", "done"]
        overall_success = True
        
        # 遍历每种状态
        for status in statuses:
            try:
                logger.info(f"同步{type_}状态: {status}")
                
                # 增量模式下进行预检
                has_updates = True
                total_count = 0
                local_count = 0
                
                if incremental:
                    last_time = latest_timestamps.get(status, "")
                    has_updates, total_count, local_count = self._pre_check_updates(type_, status, last_time)
                    
                    # 如果没有更新，跳过此状态
                    if not has_updates:
                        logger.info(f"{type_}状态 {status} 没有新数据，跳过同步")
                        continue
                
                # 获取完整数据
                interests = self.api.get_interests(self.user_id, type_, status)
                
                if not interests:
                    logger.info(f"{type_}状态 {status} 没有数据")
                    continue
                
                logger.info(f"获取到 {len(interests)} 条{type_}记录")
                
                # 获取上次同步时间，用于增量更新
                last_time = latest_timestamps.get(status, "")
                
                # 计数器
                new_count = 0
                update_count = 0
                skip_count = 0
                
                # 连续旧条目页面计数
                consecutive_old_pages = 0
                current_page = 1
                page_size = 20  # 假设API一页返回20条
                current_page_all_old = True
                
                # 遍历并保存/更新记录
                for i, item in enumerate(interests):
                    if not isinstance(item, dict):
                        logger.warning(f"跳过无效数据: {type(item)}")
                        continue
                        
                    # 检测页面边界，用于智能终止
                    if incremental and i > 0 and i % page_size == 0:
                        current_page += 1
                        
                        # 如果上一页全是旧数据，增加连续旧页面计数
                        if current_page_all_old:
                            consecutive_old_pages += 1
                        else:
                            consecutive_old_pages = 0
                        
                        # 重置当前页标记
                        current_page_all_old = True
                        
                        # 如果连续多页都是旧数据，且已经检查了最小页数，提前终止
                        if consecutive_old_pages >= self.CONSECUTIVE_OLD_PAGES_THRESHOLD and current_page > self.MIN_PAGES_TO_CHECK:
                            logger.info(f"连续 {consecutive_old_pages} 页都是旧数据，提前终止同步")
                            break
                        
                    item_time = item.get("create_time", "")
                    interest_id = item.get("id")

                    if not interest_id:
                        logger.warning("跳过没有ID的条目")
                        continue
                        
                    # 增量更新：如果有上次同步时间，且当前记录不比它新，则跳过
                    if incremental and last_time and item_time <= last_time:
                        skip_count += 1
                        continue
                    else:
                        # 有新数据，当前页不全是旧数据
                        current_page_all_old = False
                    
                    # 判断记录是否已存在
                    existing = self.db.get_interest_by_id(interest_id) if interest_id else None
                    
                    # 保存或更新记录
                    result = self.db.save_interest(item)
                    if result:
                        if existing:
                            update_count += 1
                        else:
                            new_count += 1
                
                logger.info(f"{type_}状态 {status} 同步完成: 新增 {new_count}, 更新 {update_count}, 跳过 {skip_count}")
                
            except Exception as e:
                logger.error(f"同步{type_}状态 {status} 失败: {e}")
                overall_success = False
                
        return overall_success
    
    def start_async_sync(self, incremental: bool = True):
        """异步启动同步过程
        
        参数:
            incremental: 是否使用增量更新
            
        返回:
            是否成功启动同步线程
        """
        # 使用锁检查状态
        with self._sync_lock:
            if self._is_syncing:
                logger.warning("已有同步任务在进行中，请稍后再试")
                return False
            self._is_syncing = True
            
        # 创建并启动同步线程
        thread = threading.Thread(
            target=self._async_sync_worker,
            args=(incremental,),
            daemon=True
        )
        thread.start()
        
        logger.info("异步同步任务已启动")
        return True
        
    def _async_sync_worker(self, incremental: bool):
        """异步同步工作线程"""
        try:
            self._set_sync_state(True, not incremental)
            
            # 同步所有数据
            self.sync_all_data(incremental)
            
            logger.info("异步同步任务完成")
        except Exception as e:
            logger.error(f"异步同步任务失败: {e}")
        finally:
            self._set_sync_state(False, not incremental)
    
    def schedule_periodic_sync(self, interval_hours: int = 24):
        """启动定期同步调度器
        
        参数:
            interval_hours: 同步间隔（小时）
            
        注意: 这会启动一个长期运行的线程
        """
        if interval_hours < 1:
            raise ValueError("同步间隔必须大于等于1小时")
            
        # 创建并启动调度器线程
        thread = threading.Thread(
            target=self._periodic_sync_worker,
            args=(interval_hours,),
            daemon=True
        )
        thread.start()
        
        logger.info(f"定期同步调度器已启动，间隔: {interval_hours}小时")
    
    def _periodic_sync_worker(self, interval_hours: int):
        """定期同步工作线程"""
        interval_seconds = interval_hours * 3600
        
        # 第一次启动时等待一段时间
        logger.info(f"定期同步调度器已启动，间隔: {interval_hours}小时")
        time.sleep(10)  # 等待10秒
        
        while True:
            try:
                # 使用原子操作检查并设置同步状态
                can_sync = False
                with self._sync_lock:
                    if not self._is_syncing:
                        can_sync = True
                        self._is_syncing = True
                
                if can_sync:
                    # 检查是否需要全量同步
                    do_incremental = True
                    if self._last_full_sync:
                        days_since_full_sync = (datetime.now() - self._last_full_sync).days
                        if days_since_full_sync >= self.FULL_SYNC_DAYS:
                            logger.info(f"距离上次全量同步已有 {days_since_full_sync} 天，将执行全量同步")
                            do_incremental = False
                    
                    # 执行同步
                    logger.info(f"定期同步开始（间隔: {interval_hours}小时, 模式: {'增量' if do_incremental else '全量'}）")
                    try:
                        self.sync_all_data(do_incremental)
                        logger.info("定期同步任务完成")
                    finally:
                        # 确保同步状态被重置
                        with self._sync_lock:
                            self._is_syncing = False
                            self._last_sync = datetime.now()
                            if not do_incremental:
                                self._last_full_sync = datetime.now()
                else:
                    logger.warning("上一次同步任务仍在进行中，跳过本次定期同步")
                    
            except Exception as e:
                logger.error(f"定期同步失败: {e}")
                # 确保出错时同步状态重置
                with self._sync_lock:
                    self._is_syncing = False
            
            # 休眠指定时间
            logger.info(f"下一次定期同步将在 {interval_hours} 小时后执行")
            time.sleep(interval_seconds)
            
    def get_sync_status(self) -> Dict[str, Any]:
        """获取同步状态信息
        
        返回:
            包含同步状态的字典，不包含统计数据
        """
        with self._sync_lock:
            # 计算自上次同步以来的时间
            time_since_last_sync = None
            if self._last_sync:
                time_since_last_sync = int((datetime.now() - self._last_sync).total_seconds())
                
            # 计算距离下次建议全量同步的时间
            next_full_sync = None
            days_to_next_full = None
            if self._last_full_sync:
                next_full_sync = self._last_full_sync + timedelta(days=self.FULL_SYNC_DAYS)
                days_to_next_full = (next_full_sync - datetime.now()).days
                next_full_sync = next_full_sync.isoformat()
            
            status = {
                # 同步状态信息
                "is_syncing": self._is_syncing,
                "last_sync": self._last_sync.isoformat() if self._last_sync else None,
                "last_full_sync": self._last_full_sync.isoformat() if self._last_full_sync else None,
                "time_since_last_sync_seconds": time_since_last_sync,
                
                # 配置信息
                "user_id": self.user_id,
                "download_covers": self.download_covers,
                "sync_types": self.sync_types,
                
                # 下次同步计划
                "next_full_sync": next_full_sync,
                "days_to_next_full_sync": days_to_next_full
            }
            
        return status