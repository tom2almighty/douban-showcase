import time
import threading
from typing import Dict, List, Any, Optional, Tuple
from utils.logger import get_logger

# 配置日志
logger = get_logger("sync_manager")

def sync_images(db, scheduler=None, image_service=None, max_items: int = None):
    """同步所有条目的封面图片
    
    参数:
        db: 数据库实例
        scheduler: 调度器实例，可选
        image_service: 图片服务实例
        max_items: 每次处理的最大数量，None表示处理所有
    """
    if not image_service:
        logger.error("图片服务未初始化，无法同步图片")
        return
    
    try:
        logger.info("开始同步封面图片...")
        success, failed = image_service.sync_all_images(db, max_items)
        logger.info(f"图片同步完成: 成功 {success}, 失败 {failed}")
        return success, failed
    except Exception as e:
        logger.error(f"同步图片过程中发生错误: {e}")
        return 0, 0

def sync_images_override(db, scheduler, image_service, max_items=None):
    """强制同步图片，忽略download_covers设置
    
    参数:
        db: 数据库实例
        scheduler: 调度器实例
        image_service: 图片服务实例
        max_items: 最大处理数量，None表示处理所有
        
    返回:
        (成功数, 失败数)
    """
    if not image_service:
        logger.error("图片服务未初始化，无法同步图片")
        return 0, 0
        
    try:
        logger.info("开始强制同步封面图片（忽略DOWNLOAD_COVERS设置）...")
        # 直接使用force_download=True参数调用sync_all_images
        success, failed = image_service.sync_all_images(db, max_items, force_download=True)
        logger.info(f"强制图片同步完成: 成功 {success}, 失败 {failed}")
        return success, failed
    except Exception as e:
        logger.error(f"强制同步图片过程中发生错误: {e}")
        return 0, 0


def sync_all(scheduler, incremental: bool = True) -> bool:
    """同步所有数据和图片
    
    参数:
        scheduler: 调度器实例
        incremental: 是否增量更新
        
    返回:
        是否全部成功
    """
    if not scheduler:
        logger.error("调度器未初始化，无法执行同步")
        return False
        
    try:
        # 首先同步数据
        data_success = scheduler.sync_all_data(incremental)
        
        # 然后同步图片 - 使用image_service.download_covers属性判断
        if scheduler.image_service:
            if scheduler.image_service.download_covers:
                logger.info("开始同步封面图片...")
                sync_images(scheduler.db, scheduler, scheduler.image_service)
                logger.info("封面图片同步完成")
            else:
                logger.info("图片下载功能已禁用（DOWNLOAD_COVERS=false），跳过图片同步")
        else:
            logger.warning("图片服务未初始化，无法同步图片")
        
        return data_success
    except Exception as e:
        logger.error(f"全面同步过程中发生错误: {e}")
        return False

def schedule_sync_tasks(scheduler, data_interval_hours: int = 24, 
                       image_interval_hours: int = 48, startup_delay: int = 10):
    """安排定期同步任务
    
    参数:
        scheduler: 调度器实例
        data_interval_hours: 数据同步间隔（小时）
        image_interval_hours: 图片同步间隔（小时）
        startup_delay: 启动延迟（秒）
    """
    if not scheduler:
        logger.error("调度器未初始化，无法安排同步任务")
        return
    
    # 启动数据同步定时任务
    scheduler.schedule_periodic_sync(data_interval_hours)
    
    # 使用image_service的属性检查图片下载是否启用
    if scheduler.image_service and scheduler.image_service.download_covers:
        # 创建并启动调度器线程
        thread = threading.Thread(
            target=_periodic_image_sync_worker,
            args=(scheduler, image_interval_hours, startup_delay),
            daemon=True
        )
        thread.start()
        logger.info(f"定期图片同步调度器已启动，间隔: {image_interval_hours}小时")
    else:
        logger.info("图片下载功能已禁用（DOWNLOAD_COVERS=false），跳过定期图片同步")

        
def _periodic_image_sync_worker(scheduler, interval_hours: int, startup_delay: int = 60):
    """定期图片同步工作线程"""
    interval_seconds = interval_hours * 3600
    
    # 启动时等待一段时间
    logger.info(f"定期图片同步调度器已启动，间隔: {interval_hours}小时，启动延迟: {startup_delay}秒")
    time.sleep(startup_delay)
    
    while True:
        try:
            # 检查是否可以执行同步并且图片下载仍然启用
            if not scheduler.is_syncing and scheduler.image_service.download_covers:
                logger.info(f"开始执行定期图片同步")
                sync_images(scheduler.db, scheduler, scheduler.image_service)
                logger.info("定期图片同步完成")
            elif not scheduler.image_service.download_covers:
                logger.info("图片下载功能已禁用，跳过本次图片同步")
            else:
                logger.info("数据同步正在进行中，跳过本次图片同步")
                
        except Exception as e:
            logger.error(f"定期图片同步失败: {e}")
            
        # 休眠指定时间
        logger.info(f"下一次图片同步将在 {interval_hours} 小时后执行")
        time.sleep(interval_seconds)