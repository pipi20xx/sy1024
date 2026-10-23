# app/query_parser.py

import re
from typing import Dict, Any, Optional

class QueryParser:
    """
    一个用于解析带有特殊指令的搜索字符串的类。
    
    支持的指令格式:
    - key:value (例如: year:2023)
    - key:"value with spaces" (例如: path:"My Series")
    - key:>value, key:<value (例如: year:>2020)
    
    解析后，会将原始字符串分为两部分:
    1. `base_search_term`: 移除了所有特殊指令后，剩下的普通搜索文本。
    2. `conditions`: 一个包含所有已解析指令的字典。
    """
    def __init__(self, search_term: Optional[str]):
        self.raw_term: str = search_term or ""
        self.conditions: Dict[str, Any] = {}
        self.base_search_term: str = ""
        self._parse()

    def _parse(self) -> None:
        """
        私有方法，在初始化时自动执行解析。
        """
        # 正则表达式，用于匹配 "key:value" 或 "key:'value with spaces'" 格式的指令
        # 它会处理 > < = 等操作符
        pattern = re.compile(r'(\w+):([<>]=?|!=)?(?:("([^"]+)")|(\S+))')
        
        # 先提取所有特殊指令
        found_commands = []
        for match in pattern.finditer(self.raw_term):
            key = match.group(1).lower()
            operator = match.group(2)
            # 优先获取引号内的值，否则获取不带空格的值
            value = match.group(4) if match.group(4) is not None else match.group(5)
            
            self.conditions[key] = {'value': value, 'operator': operator}
            found_commands.append(match.group(0))

        # 从原始字符串中移除所有已解析的指令，剩下的就是基本搜索词
        temp_term = self.raw_term
        for cmd in found_commands:
            temp_term = temp_term.replace(cmd, '', 1)
        
        self.base_search_term = temp_term.strip()

    def get_conditions(self) -> Dict[str, Any]:
        """返回解析出的条件字典。"""
        return self.conditions

    def get_base_search_term(self) -> str:
        """返回基础搜索文本。"""
        return self.base_search_term