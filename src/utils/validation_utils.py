import logging
from datetime import datetime
from typing import Any, List, Dict, Union, Optional, Tuple, TypeVar, Callable, Type, Set

# 配置日志
logger = logging.getLogger(__name__)

# 类型变量定义
T = TypeVar('T')

def validate_type(value: Any, expected_type: Union[Type, Tuple[Type, ...]], 
                  param_name: str = "parameter", 
                  default: Any = None,
                  convert: bool = True) -> Any:
    """验证参数类型，如果类型不匹配则尝试转换或返回默认值
    
    参数:
        value: 要验证的值
        expected_type: 期望的类型或类型元组
        param_name: 参数名称（用于日志）
        default: 验证失败时返回的默认值
        convert: 是否尝试转换类型
        
    返回:
        验证或转换后的值，或者默认值
    """
    # 如果值为None且默认值不为None，直接返回默认值
    if value is None and default is not None:
        return default
        
    # 检查类型是否匹配
    if isinstance(value, expected_type):
        return value
        
    # 记录类型不匹配警告
    logger.warning(f"参数 '{param_name}' 类型不匹配: 期望 {expected_type.__name__ if hasattr(expected_type, '__name__') else str(expected_type)}, "
                  f"实际 {type(value).__name__}")
    
    # 尝试类型转换
    if convert:
        try:
            if isinstance(expected_type, tuple):
                # 对于元组类型，尝试第一个类型的转换
                converted = expected_type[0](value)
            else:
                converted = expected_type(value)
            logger.debug(f"参数 '{param_name}' 成功转换为 {type(converted).__name__}")
            return converted
        except (TypeError, ValueError) as e:
            logger.debug(f"参数 '{param_name}' 类型转换失败: {e}")
    
    # 转换失败或不尝试转换，返回默认值
    return default


def validate_string(value: Any, param_name: str = "string_parameter", 
                   default: str = "", allow_empty: bool = True,
                   strip: bool = True, lower: bool = False) -> str:
    """验证并规范化字符串参数
    
    参数:
        value: 要验证的值
        param_name: 参数名称（用于日志）
        default: 验证失败时返回的默认值
        allow_empty: 是否允许空字符串
        strip: 是否去除首尾空白
        lower: 是否转换为小写
        
    返回:
        验证后的字符串
    """
    # 首先验证类型
    result = validate_type(value, str, param_name, default, True)
    
    if not isinstance(result, str):
        return default
    
    # 去除首尾空白
    if strip and result:
        result = result.strip()
    
    # 检查是否为空字符串
    if not allow_empty and not result:
        logger.warning(f"参数 '{param_name}' 不允许为空字符串，使用默认值")
        return default
    
    # 转换为小写
    if lower and result:
        result = result.lower()
    
    return result


def validate_int(value: Any, param_name: str = "int_parameter",
                default: int = 0, min_value: Optional[int] = None,
                max_value: Optional[int] = None) -> int:
    """验证整数参数并检查范围
    
    参数:
        value: 要验证的值
        param_name: 参数名称（用于日志）
        default: 验证失败时返回的默认值
        min_value: 允许的最小值（包含）
        max_value: 允许的最大值（包含）
        
    返回:
        验证后的整数
    """
    # 首先验证类型
    result = validate_type(value, int, param_name, None, True)
    
    # 如果类型转换失败，尝试从字符串转换
    if result is None and isinstance(value, str):
        try:
            value = value.strip()
            if value.isdigit() or (value.startswith('-') and value[1:].isdigit()):
                result = int(value)
                logger.debug(f"参数 '{param_name}' 从字符串成功转换为整数: {result}")
        except (ValueError, TypeError):
            pass
    
    # 如果仍然失败，返回默认值
    if result is None:
        logger.warning(f"参数 '{param_name}' 无法转换为整数，使用默认值 {default}")
        return default
    
    # 检查最小值
    if min_value is not None and result < min_value:
        logger.warning(f"参数 '{param_name}' 值 {result} 小于最小值 {min_value}，使用最小值")
        return min_value
        
    # 检查最大值
    if max_value is not None and result > max_value:
        logger.warning(f"参数 '{param_name}' 值 {result} 大于最大值 {max_value}，使用最大值")
        return max_value
        
    return result


def validate_float(value: Any, param_name: str = "float_parameter",
                  default: float = 0.0, min_value: Optional[float] = None,
                  max_value: Optional[float] = None) -> float:
    """验证浮点数参数并检查范围
    
    参数:
        value: 要验证的值
        param_name: 参数名称（用于日志）
        default: 验证失败时返回的默认值
        min_value: 允许的最小值（包含）
        max_value: 允许的最大值（包含）
        
    返回:
        验证后的浮点数
    """
    # 首先验证类型
    result = validate_type(value, (float, int), param_name, None, True)
    
    # 如果类型转换失败，尝试从字符串转换
    if result is None and isinstance(value, str):
        try:
            value = value.strip()
            if value and (
                value.replace('.', '', 1).isdigit() or 
                (value.startswith('-') and value[1:].replace('.', '', 1).isdigit())
            ):
                result = float(value)
                logger.debug(f"参数 '{param_name}' 从字符串成功转换为浮点数: {result}")
        except (ValueError, TypeError):
            pass
    
    # 如果仍然失败，返回默认值
    if result is None:
        logger.warning(f"参数 '{param_name}' 无法转换为浮点数，使用默认值 {default}")
        return default
    
    # 确保结果是浮点数
    result = float(result)
    
    # 检查最小值
    if min_value is not None and result < min_value:
        logger.warning(f"参数 '{param_name}' 值 {result} 小于最小值 {min_value}，使用最小值")
        return min_value
        
    # 检查最大值
    if max_value is not None and result > max_value:
        logger.warning(f"参数 '{param_name}' 值 {result} 大于最大值 {max_value}，使用最大值")
        return max_value
        
    return result


def validate_bool(value: Any, param_name: str = "bool_parameter",
                 default: bool = False) -> bool:
    """验证布尔参数
    
    参数:
        value: 要验证的值
        param_name: 参数名称（用于日志）
        default: 验证失败时返回的默认值
        
    返回:
        验证后的布尔值
    """
    # 直接布尔类型
    if isinstance(value, bool):
        return value
        
    # 字符串类型的布尔值
    if isinstance(value, str):
        value = value.lower().strip()
        if value in ('true', 'yes', '1', 'y', 'on'):
            return True
        if value in ('false', 'no', '0', 'n', 'off'):
            return False
    
    # 数值类型
    if isinstance(value, (int, float)):
        return bool(value)
    
    # 其他类型，返回默认值
    logger.warning(f"参数 '{param_name}' 无法转换为布尔值，使用默认值 {default}")
    return default


def validate_list(value: Any, param_name: str = "list_parameter",
                 default: Optional[List] = None, 
                 item_type: Optional[Type] = None,
                 min_length: Optional[int] = None,
                 max_length: Optional[int] = None) -> List:
    """验证列表参数
    
    参数:
        value: 要验证的值
        param_name: 参数名称（用于日志）
        default: 验证失败时返回的默认值，默认为空列表
        item_type: 列表项的预期类型
        min_length: 列表的最小长度
        max_length: 列表的最大长度
        
    返回:
        验证后的列表
    """
    if default is None:
        default = []
        
    # 检查类型
    if not isinstance(value, (list, tuple, set)):
        # 尝试转换为列表
        try:
            if isinstance(value, str):
                # 尝试解析JSON字符串
                import json
                try:
                    parsed = json.loads(value)
                    if isinstance(parsed, list):
                        value = parsed
                    else:
                        # 简单地将字符串分割成列表
                        value = value.split(',')
                except json.JSONDecodeError:
                    value = value.split(',')
            else:
                # 其他类型尝试转换为列表
                value = list(value)
        except (TypeError, ValueError):
            logger.warning(f"参数 '{param_name}' 无法转换为列表，使用默认值")
            return default
    
    # 转换为列表类型
    result = list(value)
    
    # 验证列表项类型
    if item_type is not None:
        valid_items = []
        for i, item in enumerate(result):
            if not isinstance(item, item_type):
                try:
                    item = item_type(item)
                    logger.debug(f"列表参数 '{param_name}' 的项 {i} 成功转换为 {item_type.__name__}")
                except (TypeError, ValueError):
                    logger.warning(f"列表参数 '{param_name}' 的项 {i} 无法转换为 {item_type.__name__}，跳过")
                    continue
            valid_items.append(item)
        result = valid_items
    
    # 检查最小长度
    if min_length is not None and len(result) < min_length:
        logger.warning(f"列表参数 '{param_name}' 长度 {len(result)} 小于最小长度 {min_length}，使用默认值")
        return default
        
    # 检查最大长度
    if max_length is not None and len(result) > max_length:
        logger.warning(f"列表参数 '{param_name}' 长度 {len(result)} 大于最大长度 {max_length}，截断")
        result = result[:max_length]
        
    return result


def validate_dict(value: Any, param_name: str = "dict_parameter",
                 default: Optional[Dict] = None,
                 required_keys: Optional[Set[str]] = None) -> Dict:
    """验证字典参数
    
    参数:
        value: 要验证的值
        param_name: 参数名称（用于日志）
        default: 验证失败时返回的默认值，默认为空字典
        required_keys: 必须包含的键集合
        
    返回:
        验证后的字典
    """
    if default is None:
        default = {}
        
    # 检查类型
    if not isinstance(value, dict):
        # 尝试转换为字典
        try:
            if isinstance(value, str):
                # 尝试解析JSON字符串
                import json
                try:
                    parsed = json.loads(value)
                    if isinstance(parsed, dict):
                        value = parsed
                    else:
                        raise ValueError("JSON解析结果不是字典")
                except json.JSONDecodeError:
                    raise ValueError("无法解析JSON字符串")
            else:
                raise TypeError(f"无法将类型 {type(value).__name__} 转换为字典")
        except (TypeError, ValueError) as e:
            logger.warning(f"参数 '{param_name}' 无法转换为字典: {e}，使用默认值")
            return default
    
    # 检查必须的键
    if required_keys:
        missing_keys = required_keys - set(value.keys())
        if missing_keys:
            logger.warning(f"字典参数 '{param_name}' 缺少必需键: {missing_keys}，使用默认值")
            return default
            
    return value


def validate_choice(value: Any, choices: List[T], param_name: str = "choice_parameter",
                   default: Optional[T] = None, case_sensitive: bool = False) -> T:
    """验证选择参数
    
    参数:
        value: 要验证的值
        choices: 可选值列表
        param_name: 参数名称（用于日志）
        default: 验证失败时返回的默认值
        case_sensitive: 字符串比较是否区分大小写
        
    返回:
        验证后的选择值
    """
    # 确保有choices可选
    if not choices:
        logger.error(f"参数 '{param_name}' 的choices列表为空")
        return default
        
    # 设置默认值为第一个选项（如果未提供）
    if default is None:
        default = choices[0]
    elif default not in choices:
        logger.warning(f"默认值 {default} 不在choices列表中，使用第一个选项")
        default = choices[0]
    
    # 检查value是否在choices中
    if value in choices:
        return value
        
    # 字符串特殊处理（不区分大小写比较）
    if isinstance(value, str) and not case_sensitive:
        value_lower = value.lower()
        for choice in choices:
            if isinstance(choice, str) and choice.lower() == value_lower:
                return choice
    
    # 尝试转换并再次检查
    for choice in choices:
        try:
            if type(choice)(value) == choice:
                return choice
        except (TypeError, ValueError):
            continue
    
    logger.warning(f"参数 '{param_name}' 值 {value} 不在可选值 {choices} 中，使用默认值 {default}")
    return default


def validate_date(value: Any, param_name: str = "date_parameter",
                 default: Optional[datetime] = None,
                 min_date: Optional[datetime] = None,
                 max_date: Optional[datetime] = None,
                 format_str: str = "%Y-%m-%d") -> datetime:
    """验证日期参数
    
    参数:
        value: 要验证的值
        param_name: 参数名称（用于日志）
        default: 验证失败时返回的默认值
        min_date: 允许的最早日期
        max_date: 允许的最晚日期
        format_str: 字符串日期的格式
        
    返回:
        验证后的日期
    """
    # 如果未提供默认值，使用当前日期
    if default is None:
        default = datetime.now()
        
    # 已经是datetime对象
    if isinstance(value, datetime):
        result = value
    else:
        # 尝试从字符串解析日期
        if isinstance(value, str):
            try:
                result = datetime.strptime(value, format_str)
            except ValueError:
                logger.warning(f"参数 '{param_name}' 无法按格式 '{format_str}' 解析日期，使用默认值")
                return default
        else:
            logger.warning(f"参数 '{param_name}' 类型 {type(value).__name__} 无法转换为日期，使用默认值")
            return default
    
    # 检查最小日期
    if min_date is not None and result < min_date:
        logger.warning(f"参数 '{param_name}' 日期 {result} 早于最小日期 {min_date}，使用最小日期")
        return min_date
        
    # 检查最大日期
    if max_date is not None and result > max_date:
        logger.warning(f"参数 '{param_name}' 日期 {result} 晚于最大日期 {max_date}，使用最大日期")
        return max_date
        
    return result


def is_valid_email(email: str) -> bool:
    """验证邮箱格式是否有效
    
    参数:
        email: 待验证的邮箱地址
        
    返回:
        是否为有效邮箱
    """
    import re
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return bool(re.match(pattern, email))


def is_valid_url(url: str) -> bool:
    """验证URL格式是否有效
    
    参数:
        url: 待验证的URL
        
    返回:
        是否为有效URL
    """
    import re
    pattern = r'^(https?|ftp):\/\/[^\s/$.?#].[^\s]*$'
    return bool(re.match(pattern, url))


def is_valid_phone(phone: str, region: str = 'CN') -> bool:
    """验证手机号格式是否有效
    
    参数:
        phone: 待验证的手机号
        region: 国家/地区代码，默认中国大陆
        
    返回:
        是否为有效手机号
    """
    import re
    # 简单的中国大陆手机号验证（开头为1，共11位）
    if region == 'CN':
        pattern = r'^1[3-9]\d{9}$'
        return bool(re.match(pattern, phone))
    
    # 国际通用格式验证（更宽松）
    pattern = r'^\+?[\d\s()-]{8,20}$'
    return bool(re.match(pattern, phone))


def sanitize_html(html: str) -> str:
    """清理HTML内容，移除潜在危险标签
    
    参数:
        html: HTML内容
        
    返回:
        清理后的HTML
    """
    # 简单实现，移除脚本和样式标签及其内容
    import re
    
    # 移除脚本标签及内容
    html = re.sub(r'<script[^>]*>[\s\S]*?</script>', '', html)
    
    # 移除样式标签及内容
    html = re.sub(r'<style[^>]*>[\s\S]*?</style>', '', html)
    
    # 移除事件属性
    html = re.sub(r' on\w+=["\'][^"\']*["\']', '', html)
    
    return html


def validate_file_extension(filename: str, allowed_extensions: List[str]) -> bool:
    """验证文件扩展名是否在允许列表中
    
    参数:
        filename: 文件名
        allowed_extensions: 允许的扩展名列表，不含点号
        
    返回:
        扩展名是否有效
    """
    import os
    extension = os.path.splitext(filename)[1].lower()
    
    # 移除点号
    if extension.startswith('.'):
        extension = extension[1:]
        
    return extension.lower() in [ext.lower() for ext in allowed_extensions]