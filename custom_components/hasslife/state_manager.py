"""
状态同步管理器
优化状态同步机制，减少网络开销，保持数据格式不变
"""

import asyncio
import json
import time
from typing import Dict, List, Optional, Set
from homeassistant.core import HomeAssistant, State, Event
from homeassistant.helpers.json import JSONEncoder

from .utils import LOGGER


class StateSyncManager:
    """状态同步管理器 - 优化状态上报"""
    
    def __init__(self, hass: HomeAssistant, client, white_domains: List[str]):
        self.hass = hass
        self.client = client
        self.white_domains = set(white_domains)
        
        # 状态缓存
        self._last_device_sync = 0
        self._last_states = {}
        self._pending_sync_states = set()
        
        # 批量同步配置
        self._batch_interval = 0.5  # 500ms批量处理
        self._batch_size = 50  # 每批最多50个设备
        self._sync_task: Optional[asyncio.Task] = None
        
        # 防抖机制
        self._state_change_debounce = 0.1  # 100ms防抖
        self._last_state_change = {}
        
    def start(self):
        """启动状态管理器"""
        self._sync_task = asyncio.create_task(self._sync_worker())
        LOGGER.info("StateSyncManager started")
    
    def stop(self):
        """停止状态管理器"""
        if self._sync_task:
            self._sync_task.cancel()
        LOGGER.info("StateSyncManager stopped")
    
    async def _sync_worker(self):
        """状态同步工作协程"""
        while True:
            try:
                await asyncio.sleep(self._batch_interval)
                
                if self._pending_sync_states:
                    states_to_sync = list(self._pending_sync_states)
                    self._pending_sync_states.clear()
                    
                    # 批量同步
                    await self._batch_sync_states(states_to_sync)
                    
            except asyncio.CancelledError:
                break
            except Exception as e:
                LOGGER.error("State sync worker error: %s", e)
                await asyncio.sleep(1)
    
    async def _batch_sync_states(self, entity_ids: List[str]):
        """批量同步状态"""
        if not entity_ids:
            return
            
        # 分批次处理
        for i in range(0, len(entity_ids), self._batch_size):
            batch = entity_ids[i:i + self._batch_size]
            await self._sync_batch_states(batch)
    
    async def _sync_batch_states(self, entity_ids: List[str]):
        """同步一批状态"""
        states = []
        for entity_id in entity_ids:
            state = self.hass.states.get(entity_id)
            if state:
                states.append(state)
        
        for state in states:
            await self.client.sync_device_state_async(state)
    
    def on_state_changed(self, entity_id: str, old_state: State, new_state: State):
        """处理状态变化 - 只上报服务器指定的实体"""
        if not new_state:
            return
            
        LOGGER.debug("状态变化检测: %s 从 %s 到 %s", entity_id, 
                    old_state.state if old_state else "None", new_state.state)
            
        # 检查是否在服务器指定的实体列表中
        if not hasattr(self.client, 'entity_ids') or not self.client.entity_ids:
            LOGGER.debug("服务器未指定实体列表，跳过: %s", entity_id)
            return
            
        if entity_id not in self.client.entity_ids:
            LOGGER.debug("实体不在服务器指定列表中: %s", entity_id)
            return
            
        # 检查是否需要同步
        if not self._should_sync_state(entity_id, old_state, new_state):
            LOGGER.debug("状态未变化，跳过同步: %s", entity_id)
            return
            
        # 防抖处理
        now = time.time()
        last_change = self._last_state_change.get(entity_id, 0)
        if now - last_change < self._state_change_debounce:
            LOGGER.debug("防抖跳过: %s", entity_id)
            return
            
        LOGGER.info("添加状态同步队列: %s", entity_id)
        self._last_state_change[entity_id] = now
        self._pending_sync_states.add(entity_id)
    
    def _should_sync_state(self, entity_id: str, old_state: State, new_state: State) -> bool:
        """判断是否需要同步状态 - 现在上报所有属性变化"""
        # 首次出现的状态
        if not old_state:
            return True
            
        # 状态值变化
        if old_state.state != new_state.state:
            return True
            
        # 所有属性变化都上报
        old_attrs = old_state.attributes or {}
        new_attrs = new_state.attributes or {}
        
        # 检查所有属性，不再过滤重要属性
        if old_attrs != new_attrs:
            return True
                
        return False
    
    async def sync_all_devices(self, force=False, interval=180, page=1, page_size=None, search_keyword=None, request_id=''):
        """同步所有设备 - 支持分页、搜索、请求ID和实时发送"""
        now = time.time()
        if not force and (now - self._last_device_sync < interval):
            return
            
        self._last_device_sync = now
        
        # 获取所有需要同步的设备
        devicelist = self.hass.states.async_all()
        all_devices = []
        
        # 第一步：过滤domain并收集所有设备
        for sinfo in devicelist:
            dinfo = sinfo.as_dict()
            entity_id = dinfo['entity_id']
            domain = entity_id.split(".")[0]
            
            if domain in self.white_domains:
                # 精简attributes，只保留friendly_name
                original_attrs = dinfo.get('attributes', {})
                filtered_attrs = {}
                friendly_name = ""
                if 'friendly_name' in original_attrs:
                    friendly_name = original_attrs['friendly_name']
                    filtered_attrs['friendly_name'] = friendly_name
                
                # 创建新的设备信息，保持原有格式但精简attributes
                filtered_device = dict(dinfo)
                filtered_device['attributes'] = filtered_attrs
                all_devices.append((filtered_device, entity_id, friendly_name))
        
        # 按entity_id排序
        all_devices.sort(key=lambda x: x[1])
        
        # 第二步：搜索过滤（如果有搜索条件）
        if search_keyword:
            keyword = search_keyword.lower()
            filtered_devices = []
            for device, entity_id, friendly_name in all_devices:
                entity_id_lower = entity_id.lower()
                friendly_name_lower = friendly_name.lower()
                
                # 匹配entity_id或friendly_name
                if keyword in entity_id_lower or keyword in friendly_name_lower:
                    filtered_devices.append(device)
            
            # 搜索结果
            usefull_entity = filtered_devices
            total_count = len(filtered_devices)
        else:
            # 无搜索条件，使用所有设备
            usefull_entity = [device for device, _, _ in all_devices]
            total_count = len(all_devices)
        if page_size is not None:
            # 计算分页
            start_idx = (page - 1) * page_size
            end_idx = start_idx + page_size
            paginated_devices = usefull_entity[start_idx:end_idx]
            
            # 实时发送分页数据
            jlist = json.dumps(paginated_devices, sort_keys=True, cls=JSONEncoder, default=str)
            body = {
                'Type': 'SyncDevice',
                'Payload': {
                    'Username': self.client.get_login_info()['username'],
                    'Password': self.client.get_login_info()['password'],
                    'Version': self.client.get_login_info()['version'],
                    'List': jlist,
                    'TotalCount': total_count,
                    'Page': page,
                    'PageSize': page_size,
                    'HasMore': end_idx < total_count
                }
            }
        else:
            # 不分页，发送全部数据
            jlist = json.dumps(usefull_entity, sort_keys=True, cls=JSONEncoder, default=str)
            body = {
                'Type': 'SyncDevice',
                'Payload': {
                    'Username': self.client.get_login_info()['username'],
                    'Password': self.client.get_login_info()['password'],
                    'Version': self.client.get_login_info()['version'],
                    'List': jlist,
                    'TotalCount': total_count,
                    'Page': 1,
                    'PageSize': total_count,
                    'HasMore': False
                }
            }
        
        # 包含请求ID在响应中（如果有）
        if request_id:
            body['RequestID'] = request_id
            
        # 实时发送，不经过队列
        await self.client.send_message_async(body)
    
    def get_sync_stats(self) -> Dict[str, int]:
        """获取同步统计信息"""
        return {
            "pending_sync_count": len(self._pending_sync_states),
            "last_device_sync": int(self._last_device_sync),
            "cached_state_count": len(self._last_states)
        }