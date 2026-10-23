import json
import httpx
from typing import Dict, Any, Optional
from app.logger import logger, log_audit
from app.emby_client import EmbyClient


class ShenYiConfigService:
    def __init__(self, emby_client: EmbyClient):
        self.emby_client = emby_client
        self._server_version = None
        
    async def _get_server_version(self) -> str:
        if self._server_version:
            return self._server_version
            
        try:
            async with httpx.AsyncClient(verify=False, timeout=30.0) as client:
                url = f"{self.emby_client.server_url}/System/Info"
                headers = {
                    'X-Emby-Token': self.emby_client.api_key
                }
                response = await client.get(url, headers=headers)
                response.raise_for_status()
                result = response.json()
                self._server_version = result.get('Version', '4.9.3.0')
                log_audit("神医", "处理", f"获取到EMBY服务器版本: {self._server_version}")
                return self._server_version
        except Exception as e:
            log_audit("神医", "失败", f"获取EMBY服务器版本失败，使用默认版本: {str(e)}", level="WARN")
            return '4.9.3.0'
        
    async def login(self, username: str, password: str) -> Dict[str, Any]:
        try:
            if not self.emby_client:
                raise Exception("Emby客户端未配置")
            
            url = f"{self.emby_client.server_url}/Users/authenticatebyname"
            data = {
                'Username': username,
                'Pw': password
            }
            headers = {
                'Content-Type': 'application/json',
                'X-Emby-Token': self.emby_client.api_key
            }
            
            log_audit("神医", "处理", f"尝试登录用户: {username}")
            async with httpx.AsyncClient(verify=False, timeout=30.0) as client:
                response = await client.post(url, json=data, headers=headers)
                
                if response.status_code == 400:
                    log_audit("神医", "失败", f"登录失败: {response.text}", level="ERROR")
                    raise Exception(f"登录失败: {response.text}")
                
                response.raise_for_status()
                result = response.json()
                
                session_token = result.get('AccessToken')
                user_id = result.get('User', {}).get('Id')
                
                log_audit("神医", "完成", f"登录成功，用户ID: {user_id}")
                return {
                    'session_token': session_token,
                    'user_id': user_id,
                    'user_info': result.get('User', {})
                }
        except Exception as e:
            log_audit("神医", "失败", f"登录失败: {str(e)}", level="ERROR")
            raise Exception(f"登录失败: {str(e)}")
    
    async def get_plugin_page(self, page_id: str, session_token: str) -> Dict[str, Any]:
        try:
            if not self.emby_client:
                raise Exception("Emby客户端未配置")
            
            url = f"{self.emby_client.server_url}/emby/UI/View"
            params = {
                'PageId': page_id,
                'ClientLocale': 'zh-cn',
                'X-Emby-Language': 'zh-cn'
            }
            headers = {
                'X-Emby-Token': session_token
            }
            
            log_audit("神医", "处理", f"获取插件页面: {page_id}")
            async with httpx.AsyncClient(verify=False, timeout=30.0) as client:
                response = await client.get(url, params=params, headers=headers)
                
                response.raise_for_status()
                result = response.json()
                
                log_audit("神医", "完成", f"成功获取插件页面: {page_id}")
                return result
        except Exception as e:
            log_audit("神医", "失败", f"获取插件页面失败: {str(e)}", level="ERROR")
            raise Exception(f"获取插件页面失败: {str(e)}")
    
    async def save_plugin_config(self, config_data: Dict[str, Any], session_token: str) -> Dict[str, Any]:
        try:
            if not self.emby_client:
                raise Exception("Emby客户端未配置")
            
            server_version = await self._get_server_version()
            
            url = f"{self.emby_client.server_url}/emby/UI/Command"
            params = {
                'reqformat': 'json'
            }
            headers = {
                'Content-Type': 'application/json',
                'X-Emby-Client': 'Emby Web',
                'X-Emby-Device-Name': 'Chrome Windows',
                'X-Emby-Device-Id': 'emby-manager-desktop',
                'X-Emby-Client-Version': server_version,
                'X-Emby-Language': 'zh-cn',
                'X-Emby-Token': session_token
            }
            
            page_id = config_data.get('PageId', '')
            object_data = config_data.get('EditObjectContainer', {}).get('Object', {})
            
            command_data = {
                'PageId': page_id,
                'CommandId': 'PageSave',
                'Data': json.dumps(object_data, ensure_ascii=False),
                'ItemId': 'undefined',
                'ClientLocale': 'zh-cn'
            }
            
            log_audit("神医", "更新", f"保存插件配置: {page_id}")
            log_audit("神医", "处理", f"请求URL: {url}")
            log_audit("神医", "处理", f"请求参数: {params}")
            log_audit("神医", "处理", f"请求头: {headers}")
            log_audit("神医", "处理", f"请求体: {json.dumps(command_data, indent=2, ensure_ascii=False)}")
            async with httpx.AsyncClient(verify=False, timeout=30.0) as client:
                response = await client.post(url, params=params, json=command_data, headers=headers)
                
                log_audit("神医", "处理", f"响应状态码: {response.status_code}")
                if response.status_code == 400:
                    log_audit("神医", "失败", f"保存配置失败: {response.text}", level="ERROR")
                    raise Exception(f"请求格式错误: {response.text}")
                elif response.status_code == 500:
                    log_audit("神医", "失败", f"保存配置失败: {response.text}", level="ERROR")
                    raise Exception(f"服务器内部错误: {response.text}")
                
                response.raise_for_status()
                result = response.json()
                
                log_audit("神医", "完成", f"插件配置保存成功!")
                log_audit("神医", "处理", f"完整响应内容: {json.dumps(result, indent=2, ensure_ascii=False)}")
                return result
        except Exception as e:
            log_audit("神医", "失败", f"保存插件配置失败: {str(e)}", level="ERROR")
            raise Exception(f"保存插件配置失败: {str(e)}")
    
    async def get_shenyi_config(self, page_id: str, session_token: str) -> Dict[str, Any]:
        return await self.get_plugin_page(page_id, session_token)
    
    async def save_shenyi_config(self, config_data: Dict[str, Any], session_token: str) -> Dict[str, Any]:
        return await self.save_plugin_config(config_data, session_token)