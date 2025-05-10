import json
import datetime
import decimal
import uuid
from typing import Any, Dict, List, Set, Tuple, Union, Optional
from pathlib import Path
import sqlite3
import logging
import re

# 配置日志
logger = logging.getLogger(__name__)

class SafeJSONEncoder(json.JSONEncoder):
    """扩展的JSON编码器，能处理更多类型"""
    
    def default(self, obj: Any) -> Any:
        """处理特殊类型的序列化
        
        参数:
            obj: 待序列化的对象
            
        返回:
            可序列化的值
        """
        # 日期时间类型
        if isinstance(obj, (datetime.datetime, datetime.date, datetime.time)):
            return obj.isoformat()
            
        # 小数类型
        elif isinstance(obj, decimal.Decimal):
            return float(obj)
            
        # UUID 类型
        elif isinstance(obj, uuid.UUID):
            return str(obj)
            
        # 集合类型
        elif isinstance(obj, set):
            return list(obj)
            
        # 字节类型
        elif isinstance(obj, bytes):
            try:
                return obj.decode('utf-8')
            except UnicodeDecodeError:
                return str(obj)
                
        # 路径类型
        elif isinstance(obj, Path):
            return str(obj)
            
        # SQLite行类型
        elif isinstance(obj, sqlite3.Row):
            return {key: obj[key] for key in obj.keys()}
            
        # 正则表达式模式
        elif isinstance(obj, re.Pattern):
            return obj.pattern
            
        # 异常类型
        elif isinstance(obj, Exception):
            return {
                'error_type': obj.__class__.__name__,
                'error_message': str(obj),
                'error_args': obj.args
            }
            
        # 默认处理方式
        try:
            # 尝试用 __dict__ 方法
            if hasattr(obj, '__dict__'):
                return obj.__dict__
                
            # 转换为字符串
            return str(obj)
            
        except Exception as e:
            logger.warning(f"无法序列化对象 {type(obj)}: {e}")
            return f"<不可序列化对象: {type(obj).__name__}>"


def safe_serialize(obj: Any) -> Any:
    """递归地将对象转换为可序列化的形式
    
    参数:
        obj: 要处理的对象
        
    返回:
        转换后的可序列化对象
    """
    # 处理基本类型
    if obj is None or isinstance(obj, (str, int, float, bool)):
        return obj
    
    # 处理列表或元组
    if isinstance(obj, (list, tuple)):
        return [safe_serialize(item) for item in obj]
        
    # 处理字典
    if isinstance(obj, dict):
        result = {}
        for key, value in obj.items():
            # 确保键是字符串
            if not isinstance(key, str):
                key = str(key)
            result[key] = safe_serialize(value)
        return result
        
    # 处理日期时间类型
    if isinstance(obj, (datetime.datetime, datetime.date, datetime.time)):
        return obj.isoformat()
        
    # 处理小数类型
    if isinstance(obj, decimal.Decimal):
        return float(obj)
        
    # 处理UUID
    if isinstance(obj, uuid.UUID):
        return str(obj)
        
    # 处理集合
    if isinstance(obj, set):
        return [safe_serialize(item) for item in obj]
        
    # 处理字节类型
    if isinstance(obj, bytes):
        try:
            return obj.decode('utf-8')
        except UnicodeDecodeError:
            return str(obj)
            
    # 处理路径
    if isinstance(obj, Path):
        return str(obj)
        
    # 处理SQLite行对象
    if isinstance(obj, sqlite3.Row):
        return safe_serialize({key: obj[key] for key in obj.keys()})
        
    # 处理正则表达式模式
    if isinstance(obj, re.Pattern):
        return obj.pattern
        
    # 处理异常类型
    if isinstance(obj, Exception):
        return {
            'error_type': obj.__class__.__name__,
            'error_message': str(obj),
            'error_args': safe_serialize(obj.args)
        }
        
    # 处理具有__dict__属性的对象
    if hasattr(obj, '__dict__'):
        try:
            return safe_serialize(obj.__dict__)
        except Exception as e:
            logger.debug(f"无法使用__dict__序列化对象: {e}")
            
    # 尝试转为字符串作为最后手段
    try:
        return str(obj)
    except Exception as e:
        logger.warning(f"对象 {type(obj)} 无法序列化: {e}")
        return f"<不可序列化对象: {type(obj).__name__}>"


def safe_json_dumps(obj: Any, indent: Optional[int] = None, ensure_ascii: bool = False) -> str:
    """安全地将对象序列化为JSON字符串
    
    参数:
        obj: 待序列化的对象
        indent: JSON缩进值，None表示不缩进
        ensure_ascii: 是否确保ASCII输出
        
    返回:
        JSON字符串
    """
    try:
        # 尝试直接使用扩展的编码器
        return json.dumps(obj, cls=SafeJSONEncoder, indent=indent, ensure_ascii=ensure_ascii)
    except (TypeError, ValueError, OverflowError) as e:
        logger.debug(f"使用SafeJSONEncoder序列化失败: {e}，尝试预处理...")
        
        # 如果直接序列化失败，预处理后再尝试
        safe_obj = safe_serialize(obj)
        
        try:
            return json.dumps(safe_obj, indent=indent, ensure_ascii=ensure_ascii)
        except Exception as e2:
            logger.error(f"序列化对象到JSON彻底失败: {e2}")
            # 最后的备选方案，返回错误信息
            return json.dumps({
                "error": "序列化失败",
                "error_type": type(e2).__name__,
                "error_message": str(e2)
            }, ensure_ascii=ensure_ascii)


def safe_json_loads(json_str: str) -> Any:
    """安全地解析JSON字符串为Python对象
    
    参数:
        json_str: JSON字符串
        
    返回:
        解析后的Python对象，解析失败则返回None
    """
    try:
        return json.loads(json_str) if json_str else None
    except json.JSONDecodeError as e:
        logger.warning(f"JSON解析失败: {e}")
        return None
        

def sanitize_for_json(obj: Any) -> Any:
    """清理对象，确保可以安全序列化为JSON
    
    参数:
        obj: 待清理的对象
        
    返回:
        清理后的对象
    """
    return safe_serialize(obj)


def convert_to_serializable_dict(obj: Any) -> Dict[str, Any]:
    """将对象转换为可序列化的字典
    
    参数:
        obj: 任意对象
        
    返回:
        可序列化的字典
    """
    if isinstance(obj, dict):
        return {str(k): safe_serialize(v) for k, v in obj.items()}
        
    # 尝试将对象转换为字典
    try:
        if hasattr(obj, '__dict__'):
            return {k: safe_serialize(v) for k, v in obj.__dict__.items() 
                   if not k.startswith('_')}
                   
        elif hasattr(obj, 'to_dict'):
            return safe_serialize(obj.to_dict())
            
        elif hasattr(obj, '__slots__'):
            return {slot: safe_serialize(getattr(obj, slot)) for slot in obj.__slots__ 
                   if hasattr(obj, slot) and not slot.startswith('_')}
                   
    except Exception as e:
        logger.debug(f"转换对象到字典失败: {e}")
        
    # 最后尝试使用安全序列化
    serialized = safe_serialize(obj)
    if isinstance(serialized, dict):
        return serialized
    
    # 如果不是字典，包装在一个字典中返回
    return {"value": serialized}