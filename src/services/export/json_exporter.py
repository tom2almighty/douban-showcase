#!/usr/bin/env python3
"""
豆瓣数据JSON导出工具

此模块提供将数据库中的豆瓣收藏数据导出为JSON文件的功能，
支持按类型和状态筛选，便于前端导入或备份。
"""

import os
import sys
import json
import threading
from datetime import datetime
from typing import Dict, List, Optional
from pathlib import Path

# 添加路径处理，确保可以导入项目模块
script_dir = Path(__file__).parent
project_root = script_dir.parent.parent.parent  # 调整路径以适应新的目录结构

# 导入项目模块
from services.data.database import Database
from utils.logger import get_logger
from utils.serialization_utils import safe_serialize, safe_json_dumps
from utils.validation_utils import validate_string, validate_int, validate_bool

# 配置日志
logger = get_logger("json_export")

class JsonExporter:
    """豆瓣数据导出器，将数据库内容导出为JSON格式"""
    
    def __init__(self, db_instance=None):
        """初始化导出器
        
        参数:
            db_instance: 数据库实例，如果为None则创建新实例
        """
        # 使用传入的数据库实例或创建新实例
        self.db = db_instance or Database()
        logger.info(f"初始化导出器，使用数据库: {self.db.db_path}")
        
        # 获取支持的内容类型
        self.supported_types = self.db.get_distinct_types()
        logger.info(f"支持的内容类型: {', '.join(self.supported_types)}")
        
    def export_data(self, 
                   type_: Optional[str] = None, 
                   status: Optional[str] = None,
                   year: Optional[int] = None,
                   output_path: Optional[str] = None,
                   include_raw: bool = False,
                   pretty_print: bool = True,
                   limit: int = None) -> str:
        """导出数据为JSON格式
        
        参数:
            type_: 内容类型筛选
            status: 状态筛选
            year: 年份筛选
            output_path: 输出文件路径，如果为None则自动生成
            include_raw: 是否包含raw_json字段
            pretty_print: 是否美化JSON输出
            limit: 最大导出条目数，None表示不限制
            
        返回:
            输出文件路径
        """
        # 验证输入参数
        type_ = validate_string(type_, 'type_')
        status = validate_string(status, 'status')
        year = validate_int(year, 'year') 
        limit = validate_int(limit, 'limit', min_value=1, max_value=10000) if limit is not None else None
        include_raw = validate_bool(include_raw, 'include_raw', False)
        pretty_print = validate_bool(pretty_print, 'pretty_print', True)
        
        logger.info(f"开始导出数据: 类型={type_ or '全部'}, 状态={status or '全部'}, 年份={year or '全部'}")
        
        # 获取数据
        data_limit = 10000 if limit is None else limit
        items = self.db.get_interests(
            type_=type_,
            status=status,
            year=year,
            limit=data_limit
        )
        
        if not items:
            logger.warning("没有找到匹配的数据")
            return None
            
        logger.info(f"获取到 {len(items)} 条记录")
        
        # 准备输出数据
        export_data = {
            "metadata": {
                "exported_at": datetime.now().isoformat(),
                "exported_by": "Mouban JSON Exporter",
                "version": "2.0",
                "total_count": len(items),
                "filters": {
                    "type": type_,
                    "status": status,
                    "year": year
                }
            },
            "statistics": self._generate_statistics(items),
            "interests": []
        }
        
        # 处理每条记录，确保可序列化
        for item in items:
            export_item = safe_serialize(item)
            
            # 处理raw_json字段
            if not include_raw and 'raw_json' in export_item:
                del export_item['raw_json']
                
            # 添加到输出列表
            export_data["interests"].append(export_item)
            
        # 确定输出路径
        if not output_path:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"douban_export_{timestamp}"
            
            # 添加筛选信息到文件名
            if type_:
                filename += f"_{type_}"
            if status:
                filename += f"_{status}"
            if year:
                filename += f"_{year}"
                
            filename += ".json"
            
            # 创建导出目录
            exports_dir = os.path.join(project_root, "exports")
            os.makedirs(exports_dir, exist_ok=True)
            
            output_path = os.path.join(exports_dir, filename)
            
        # 导出为JSON，使用安全序列化
        indent = 2 if pretty_print else None
        try:
            with open(output_path, 'w', encoding='utf-8') as f:
                json_str = safe_json_dumps(export_data, indent=indent)
                f.write(json_str)
                
            logger.info(f"数据已导出到: {output_path}")
            return output_path
        except Exception as e:
            logger.error(f"写入JSON文件失败: {e}")
            return None
    
    def _generate_statistics(self, items: List[Dict]) -> Dict:
        """生成导出数据的统计信息
        
        参数:
            items: 要分析的记录列表
            
        返回:
            统计信息字典
        """
        stats = {
            "by_type": {},
            "by_status": {},
            "by_year": {},
            "by_rating": {
                "未评分": 0,
                "1-2星": 0,
                "3-5星": 0,
                "6-7星": 0,
                "8-10星": 0
            },
            "by_score": {
                "douban": {
                    "总计": 0,
                    "平均分": 0.0
                },
                "personal": {
                    "总计": 0,
                    "平均分": 0.0
                }
            }
        }
        
        # 收集唯一类型
        types = set()
        status_values = set()
        
        # 评分累计
        douban_score_sum = 0.0
        douban_score_count = 0
        my_rating_sum = 0
        my_rating_count = 0
        
        # 生成统计信息
        for item in items:
            # 按类型统计
            item_type = item.get("type", "unknown")
            types.add(item_type)
            if item_type not in stats["by_type"]:
                stats["by_type"][item_type] = 0
            stats["by_type"][item_type] += 1
            
            # 按状态统计
            item_status = item.get("status", "unknown")
            status_values.add(item_status)
            if item_status not in stats["by_status"]:
                stats["by_status"][item_status] = 0
            stats["by_status"][item_status] += 1
            
            # 按年份统计
            item_year = item.get("year")
            if item_year and item_year > 0:
                year_str = str(item_year)
                if year_str not in stats["by_year"]:
                    stats["by_year"][year_str] = 0
                stats["by_year"][year_str] += 1
            
            # 按个人评分统计
            rating = item.get("my_rating", 0)
            if rating == 0:
                stats["by_rating"]["未评分"] += 1
            elif 1 <= rating <= 2:
                stats["by_rating"]["1-2星"] += 1
            elif 3 <= rating <= 5:
                stats["by_rating"]["3-5星"] += 1
            elif 6 <= rating <= 7:
                stats["by_rating"]["6-7星"] += 1
            elif 8 <= rating <= 10:
                stats["by_rating"]["8-10星"] += 1
                
            # 累计评分
            if rating > 0:
                my_rating_sum += rating
                my_rating_count += 1
                
            douban_score = item.get("douban_score", 0)
            if douban_score > 0:
                douban_score_sum += douban_score
                douban_score_count += 1
        
        # 计算平均分
        if douban_score_count > 0:
            stats["by_score"]["douban"]["总计"] = douban_score_count
            stats["by_score"]["douban"]["平均分"] = round(douban_score_sum / douban_score_count, 1)
            
        if my_rating_count > 0:
            stats["by_score"]["personal"]["总计"] = my_rating_count
            stats["by_score"]["personal"]["平均分"] = round(my_rating_sum / my_rating_count, 1)
            
        # 添加总计
        stats["total_count"] = len(items)
        stats["unique_types"] = list(types)
        stats["unique_statuses"] = list(status_values)
        
        # 年份统计排序
        stats["by_year"] = dict(sorted(stats["by_year"].items()))
        
        return stats
        
    def export_all_types(self, output_dir: str = None, include_raw: bool = False):
        """导出所有支持的类型数据
        
        参数:
            output_dir: 输出目录
            include_raw: 是否包含原始数据
        """
        # 参数验证
        include_raw = validate_bool(include_raw, 'include_raw', False)
        
        if not output_dir:
            output_dir = os.path.join(project_root, "exports", 
                                      datetime.now().strftime("%Y%m%d_%H%M%S"))
            
        os.makedirs(output_dir, exist_ok=True)
        logger.info(f"开始导出所有类型数据到目录: {output_dir}")
        
        export_tasks = []
        for type_ in self.supported_types:
            for status in ["wish", "doing", "done"]:  # 标准化状态值
                task = threading.Thread(
                    target=self._export_single_type_status,
                    args=(type_, status, output_dir, include_raw)
                )
                export_tasks.append(task)
                task.start()
                
        # 等待所有导出任务完成
        for task in export_tasks:
            task.join()
            
        logger.info(f"所有数据导出完成，共 {len(export_tasks)} 个文件")
        
        # 创建索引文件
        index_path = os.path.join(output_dir, "index.json")
        with open(index_path, 'w', encoding='utf-8') as f:
            index_data = {
                "exported_at": datetime.now().isoformat(),
                "files": [os.path.basename(f) for f in os.listdir(output_dir) if f.endswith('.json') and f != 'index.json'],
                "types": self.supported_types,
                "statuses": ["wish", "doing", "done"]  # 标准化状态值
            }
            json_str = safe_json_dumps(index_data, indent=2)
            f.write(json_str)
            
        return output_dir
        
    def _export_single_type_status(self, type_: str, status: str, output_dir: str, include_raw: bool):
        """导出单个类型和状态的数据（用于多线程导出）"""
        filename = f"{type_}_{status}.json"
        output_path = os.path.join(output_dir, filename)
        
        try:
            self.export_data(
                type_=type_,
                status=status,
                output_path=output_path,
                include_raw=include_raw
            )
        except Exception as e:
            logger.error(f"导出 {type_} {status} 失败: {e}")