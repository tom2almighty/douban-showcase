import os
import time
import random
import requests
import json
from typing import Dict, List, Any, Optional
from retrying import retry
from dotenv import load_dotenv
from utils.logger import get_logger

# 配置日志
logger = get_logger("douban_api")

# 加载环境变量
load_dotenv()

class DoubanAPI:
    """豆瓣API客户端，处理与豆瓣API的所有交互"""
    
    # 默认设置
    DEFAULT_API_HOST = "frodo.douban.com"
    DEFAULT_API_KEY = "0ac44ae016490db2204ce0a042db2916"
    
    # 请求超时
    REQUEST_TIMEOUT = 10
    
    # 支持的内容类型列表
    CONTENT_TYPES = ["movie", "tv", "book", "music", "game", "drama"]
    
    def __init__(self):
        """初始化API客户端"""
        self.api_host = os.getenv("DOUBAN_API_HOST", self.DEFAULT_API_HOST)
        self.api_key = os.getenv("DOUBAN_API_KEY", self.DEFAULT_API_KEY)
        # 可选: 授权令牌
        self.auth_token = os.getenv("AUTH_TOKEN")
        
        # 设置基础请求头
        self.headers = {
            "Host": self.api_host,
            "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 15_3 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 MicroMessenger/8.0.16(0x18001023) NetType/WIFI Language/zh_CN",
            "Referer": "https://servicewechat.com/wx2f9b06c1de1ccfca/84/page-frame.html",
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8"
        }
        
        # 如果存在AUTH_TOKEN，添加到请求头
        if self.auth_token:
            self.headers["Authorization"] = f"Bearer {self.auth_token}"
            
        # 请求计数器（用于后续添加的功能）
        self.request_count = 0
            
        logger.info(f"DoubanAPI初始化完成，使用API主机: {self.api_host}")

    def _add_random_delay(self, min_delay: float = 0.5, max_delay: float = 2.0):
        """添加随机延迟，避免请求过于频繁"""
        delay = random.uniform(min_delay, max_delay)
        time.sleep(delay)
    
    def _handle_rate_limit(self, resp: requests.Response) -> bool:
        """处理可能的速率限制
        
        返回:
            bool: 如果被限制返回True，否则返回False
        """
        if resp.status_code == 429:
            logger.warning("请求受到速率限制，等待60秒后重试")
            time.sleep(60)
            return True
        return False
    
    @retry(stop_max_attempt_number=3, wait_fixed=2000, 
           retry_on_exception=lambda e: isinstance(e, (requests.RequestException, ConnectionError)))
    def get_interests_page(self, user_id: str, type_: str, status: str, page: int = 1) -> Dict[str, Any]:
        """获取单页用户兴趣列表（不自动处理分页）
        
        参数:
            user_id: 豆瓣用户ID
            type_: 内容类型 ('movie', 'tv', 'book', 'music', 'game', 'drama' 等)
            status: 状态 ('mark', 'doing', 或 'done')
            page: 页码，从1开始
            
        返回:
            包含当前页结果的字典，包含interests和total字段
        """
        # 添加随机延迟
        self._add_random_delay()
        
        # 请求计数增加
        self.request_count += 1
        
        url = f"https://{self.api_host}/api/v2/user/{user_id}/interests"
        
        # 计算偏移量，页码从1开始
        offset = (page - 1) * 20  # 每页20条
        
        params = {
            "type": type_,
            "status": status,
            "start": offset,
            "count": 20,
            "apiKey": self.api_key
        }
        
        logger.debug(f"请求第 {page} 页 {type_} 数据，偏移量: {offset}")
        
        try:
            resp = requests.get(url, headers=self.headers, params=params, timeout=self.REQUEST_TIMEOUT)
            
            # 处理速率限制
            if self._handle_rate_limit(resp):
                # 递归重试
                return self.get_interests_page(user_id, type_, status, page)
                
            resp.raise_for_status()
            
            # 明确检查内容是否为空
            if not resp.content:
                logger.warning("获取到空响应")
                return {"interests": [], "total": 0}
                
            return resp.json()
            
        except requests.RequestException as e:
            logger.error(f"请求第 {page} 页 {type_} 数据失败: {e}")
            return {"interests": [], "total": 0}
        except json.JSONDecodeError as e:
            logger.error(f"JSON解析失败: {e}")
            # 输出响应内容前100字符帮助调试
            if resp and hasattr(resp, 'text'):
                logger.debug(f"响应内容片段: {resp.text[:100]}")
            return {"interests": [], "total": 0}
    
    def get_interests(self, user_id: str, type_: str, status: str) -> List[Dict[str, Any]]:
        """获取用户兴趣列表（自动处理分页）
        
        参数:
            user_id: 豆瓣用户ID
            type_: 内容类型 ('movie', 'tv', 'book', 'music', 'game', 'drama' 等)
            status: 状态 ('mark', 'doing', 或 'done')
            
        返回:
            包含所有页结果的列表
        """
        results = []
        offset = 0
        page = 1
        max_errors = 3
        error_count = 0
        
        logger.info(f"开始获取用户 {user_id} 的 {type_} 列表，状态: {status}")
        
        while True:
            # 添加随机延迟
            self._add_random_delay()
            
            url = f"https://{self.api_host}/api/v2/user/{user_id}/interests"
            params = {
                "type": type_,
                "status": status,
                "start": offset,
                "count": 50,
                "apiKey": self.api_key
            }
            
            logger.debug(f"请求第 {page} 页 {type_} 数据，偏移量: {offset}")
            
            try:
                # 请求计数增加
                self.request_count += 1
                
                resp = requests.get(url, headers=self.headers, params=params, timeout=self.REQUEST_TIMEOUT)
                
                # 处理速率限制
                if self._handle_rate_limit(resp):
                    continue
                    
                resp.raise_for_status()
                
                # 检查内容是否为空
                if not resp.content:
                    logger.warning("获取到空响应")
                    break
                    
                data = resp.json()
                
                # 检查是否有结果
                interests = data.get("interests", [])
                if not interests:
                    logger.info(f"没有更多结果，共获取 {len(results)} 条 {type_} 记录")
                    break
                    
                results.extend(interests)
                logger.info(f"获取到 {len(interests)} 条 {type_} 记录，总计: {len(results)}")
                
                # 重置错误计数
                error_count = 0
                
                # 更新偏移量和页码
                offset += len(interests)
                page += 1
                
            except requests.RequestException as e:
                error_count += 1
                logger.error(f"请求 {type_} 数据失败: {e}")
                
                if error_count >= max_errors:
                    logger.error(f"连续失败 {error_count} 次，中止获取")
                    break
                    
                # 增加延迟后重试
                time.sleep(5)
                continue
                
            except json.JSONDecodeError as e:
                error_count += 1
                logger.error(f"解析JSON失败: {e}")
                
                # 输出响应内容前100字符帮助调试
                if resp and hasattr(resp, 'text'):
                    logger.debug(f"响应内容片段: {resp.text[:100]}")
                
                if error_count >= max_errors:
                    logger.error(f"连续解析失败 {error_count} 次，中止获取")
                    break
                    
                # 增加延迟后重试下一页
                time.sleep(5)
                offset += 50  # 尝试跳过可能有问题的这一批数据
                page += 1
                continue
                
        return results
        
    @retry(stop_max_attempt_number=3, wait_fixed=2000)
    def get_item_detail(self, item_id: str, type_: str) -> Dict[str, Any]:
        """获取单个条目的详细信息
        
        参数:
            item_id: 条目ID
            type_: 条目类型 ('movie', 'tv', 'book', 'music', 'game', 'drama' 等)
            
        返回:
            包含详情的字典
        """
        # 添加随机延迟
        self._add_random_delay()
        
        # 请求计数增加
        self.request_count += 1
        
        url = f"https://{self.api_host}/api/v2/{type_}/{item_id}"
        params = {"apiKey": self.api_key}
        
        try:
            resp = requests.get(url, headers=self.headers, params=params, timeout=self.REQUEST_TIMEOUT)
            
            # 处理速率限制
            if self._handle_rate_limit(resp):
                # 递归调用直到成功
                return self.get_item_detail(item_id, type_)
                
            resp.raise_for_status()
            
            # 检查内容是否为空
            if not resp.content:
                logger.warning(f"获取 {type_} 条目 {item_id} 详情返回空响应")
                return {}
                
            return resp.json()
            
        except requests.RequestException as e:
            logger.error(f"获取 {type_} 条目 {item_id} 详情失败: {e}")
            return {}
        except json.JSONDecodeError as e:
            logger.error(f"解析 {type_} 条目 {item_id} JSON失败: {e}")
            # 输出响应内容前100字符帮助调试
            if resp and hasattr(resp, 'text'):
                logger.debug(f"响应内容片段: {resp.text[:100]}")
            return {}
            
    def search_items(self, query: str, type_: Optional[str] = None, page: int = 1, count: int = 20) -> Dict[str, Any]:
        """搜索条目
        
        参数:
            query: 搜索关键词
            type_: 条目类型 (可选)
            page: 页码
            count: 每页条数
            
        返回:
            搜索结果
        """
        if not query:
            logger.error("搜索关键词不能为空")
            return {"items": [], "total": 0}
            
        # 添加随机延迟
        self._add_random_delay()
        
        # 请求计数增加
        self.request_count += 1
        
        url = f"https://{self.api_host}/api/v2/search"
        params = {
            "q": query,
            "start": (page - 1) * count,
            "count": count,
            "apiKey": self.api_key
        }
        
        if type_ and type_ in self.CONTENT_TYPES:
            params["type"] = type_
            
        try:
            resp = requests.get(url, headers=self.headers, params=params, timeout=self.REQUEST_TIMEOUT)
            
            # 处理速率限制
            if self._handle_rate_limit(resp):
                # 递归调用直到成功
                return self.search_items(query, type_, page, count)
                
            resp.raise_for_status()
            
            # 检查内容是否为空
            if not resp.content:
                logger.warning(f"搜索 '{query}' 返回空响应")
                return {"items": [], "total": 0}
                
            return resp.json()
            
        except requests.RequestException as e:
            logger.error(f"搜索 '{query}' 失败: {e}")
            return {"items": [], "total": 0}
        except json.JSONDecodeError as e:
            logger.error(f"解析搜索 '{query}' JSON失败: {e}")
            # 输出响应内容前100字符帮助调试
            if resp and hasattr(resp, 'text'):
                logger.debug(f"响应内容片段: {resp.text[:100]}")
            return {"items": [], "total": 0}