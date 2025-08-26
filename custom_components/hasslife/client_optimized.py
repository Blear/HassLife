"""
完全优化的异步TCP客户端
保持100%协议兼容性，集成所有优化功能
"""
import asyncio
import time
import struct
import json
import hashlib
import traceback
from typing import Optional, Dict, List, Any
from homeassistant.const import EVENT_STATE_CHANGED, EVENT_HOMEASSISTANT_STOP
from homeassistant.core import HomeAssistant, State
from homeassistant.helpers.json import JSONEncoder

from .const import BUFFER_SIZE
from .hasslife_config import HASSLIFE_CONFIGS
from .utils import LOGGER, dns_open, get_rand_char, save_local_seed
from .state_manager import StateSyncManager


class OptimizedTcpClient:
    white_domains = ['button','light','cover','switch','vacuum','water_heater','humidifier','fan','media_player','script','climate','input_boolean','automation','group','lock']
    protocol_func_bind_map = {}
    is_exited = False
    
    def __init__(self, host: str, port: int, hass: HomeAssistant):
        self.host = host
        self.port = port
        self.hass = hass
        self.reader: Optional[asyncio.StreamReader] = None
        self.writer: Optional[asyncio.StreamWriter] = None
        self.is_connected = False
        self.is_init = True
        
        self._login_info = {}
        self.init_func_bind_map()
        self.entity_ids = []
        
        # 优化配置参数
        self.heartbeat_interval = 10
        self.heartbeat_timeout = 60
        
        # 消息队列
        self._message_queue = asyncio.Queue(maxsize=1000)
        self._sender_task: Optional[asyncio.Task] = None
        self._receiver_task: Optional[asyncio.Task] = None
        
        # 连接管理
        self._reconnect_delay = 5
        self._max_reconnect_delay = 300
        self._connection_lock = asyncio.Lock()
        
        # 状态同步管理器
        self._state_manager = StateSyncManager(hass, self, self.white_domains)
    
    async def connect(self) -> bool:
        """异步连接 - 非阻塞实现"""
        if self.is_connected:
            return True
            
        try:
            async with asyncio.timeout(5):
                self.reader, self.writer = await asyncio.open_connection(self.host, self.port)
            self.is_connected = True
            LOGGER.info("Connected to: %s:%d", self.host, self.port)
            return True
        except asyncio.TimeoutError:
            LOGGER.error("Connection timeout to %s:%d", self.host, self.port)
            return False
        except Exception as e:
            LOGGER.error("Failed to connect: %s", traceback.format_exc())
            return False
    
    async def send_message_async(self, message: Dict[str, Any]) -> bool:
        """异步发送消息 - 加入队列"""
        try:
            await self._message_queue.put(message)
            return True
        except asyncio.QueueFull:
            LOGGER.error("Message queue full, dropping: %s", message.get("Type"))
            return False
    
    async def _send_worker(self):
        """消息发送工作协程 - 防阻塞"""
        while not self.is_exited:
            try:
                if not self.is_connected:
                    await asyncio.sleep(1)
                    continue
                
                try:
                    message = await asyncio.wait_for(self._message_queue.get(), timeout=1.0)
                except asyncio.TimeoutError:
                    continue
                    
                if not self.is_connected:
                    continue
                
                await self._send_message_now(message)
                
            except asyncio.CancelledError:
                break
            except Exception:
                self.is_connected = False
                await asyncio.sleep(1)
    
    async def _send_message_now(self, message: Dict[str, Any]) -> bool:
        """立即发送消息 - 保持协议格式"""
        if not self.is_connected or not self.writer:
            return False
            
        try:
            async with asyncio.timeout(3):
                # 保持原有消息格式不变
                message_body = json.dumps(message, sort_keys=True, cls=JSONEncoder, default=str).encode('utf-8')
                message_length = len(message_body)
                
                header_data = struct.pack('<I', message_length)
                header_data = header_data.ljust(32, b'\x00')
                
                self.writer.write(header_data + message_body)
                await self.writer.drain()
                
                LOGGER.debug("Sent: %s", message.get("Type"))
                return True
                
        except Exception as e:
            LOGGER.error("Send error: %s", e)
            self.is_connected = False
            return False
    
    async def receive_message_async(self) -> Optional[Dict[str, Any]]:
        """异步接收消息 - 防阻塞实现"""
        if not self.is_connected or not self.reader or self.reader.at_eof():
            return None
            
        try:
            async with asyncio.timeout(5):  # 减少超时时间
                # 读取头部
                try:
                    header_data = await self.reader.readexactly(32)
                except (asyncio.IncompleteReadError, ConnectionResetError, OSError) as e:
                    self.is_connected = False
                    return None
                
                if len(header_data) != 32:
                    self.is_connected = False
                    return None
                
                message_length = struct.unpack('<I', header_data[:4])[0]
                if message_length <= 0 or message_length > 1024 * 1024:  # 限制1MB
                    self.is_connected = False
                    return None
                
                # 读取消息体
                try:
                    data = await self.reader.readexactly(message_length)
                except (asyncio.IncompleteReadError, ConnectionResetError, OSError):
                    self.is_connected = False
                    return None
                
                if len(data) != message_length:
                    self.is_connected = False
                    return None
                
                try:
                    return json.loads(data.decode('utf-8'))
                except (json.JSONDecodeError, UnicodeDecodeError):
                    return None
                    
        except asyncio.TimeoutError:
            return None
        except Exception:
            self.is_connected = False
            return None
    
    async def start(self):
        """启动客户端 - 最佳实践"""
        try:
            # 启动状态管理器
            self._state_manager.start()
            
            # 注册事件监听器 - 使用异步回调
            self.hass.bus.async_listen(EVENT_STATE_CHANGED, self._async_on_state_changed)
            
            # 立即在后台启动主循环（最佳实践）
            self._main_loop_task = asyncio.create_task(self._main_loop())
            
            # 注册停止回调
            self.hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, self._on_homeassistant_stop)
            
            LOGGER.info("OptimizedTcpClient started successfully")
            
        except Exception as e:
            LOGGER.error("Failed to start OptimizedTcpClient: %s", e)
            raise
    
    async def _on_homeassistant_stop(self, event):
        """Homeassistant停止时的清理"""
        await self.stop()
    
    
    async def _main_loop(self):
        """主循环"""
        reconnect_delay = self._reconnect_delay
        
        while not self.is_exited:
            try:
                async with self._connection_lock:
                    if await self.connect():
                        # 启动工作协程
                        self._sender_task = asyncio.create_task(self._send_worker())
                        self._receiver_task = asyncio.create_task(self._receive_worker())
                        heartbeat_task = asyncio.create_task(self.heartbeat_async())
                        
                        try:
                            while self.is_connected and not self.is_exited:
                                await asyncio.sleep(1)
                        finally:
                            # 清理连接
                            self.is_connected = False
                            if self.writer:
                                try:
                                    self.writer.close()
                                    await self.writer.wait_closed()
                                except Exception:
                                    pass
                                finally:
                                    self.writer = None
                                    self.reader = None
                            
                            # 清理任务
                            for task in [self._sender_task, self._receiver_task, heartbeat_task]:
                                if task and not task.done():
                                    task.cancel()
                                    try:
                                        await task
                                    except asyncio.CancelledError:
                                        pass
                        
                        reconnect_delay = self._reconnect_delay
                    else:
                        LOGGER.info("Reconnecting in %d seconds...", reconnect_delay)
                        await asyncio.sleep(reconnect_delay)
                        reconnect_delay = min(reconnect_delay * 2, self._max_reconnect_delay)
                        
            except asyncio.CancelledError:
                break
            except Exception as e:
                LOGGER.error("Main loop error: %s", e)
                await asyncio.sleep(reconnect_delay)
            finally:
                # 确保连接正确关闭
                if self.writer:
                    try:
                        self.writer.close()
                        await self.writer.wait_closed()
                    except Exception:
                        pass
                    finally:
                        self.writer = None
                        self.reader = None
    
    async def _receive_worker(self):
        """消息接收工作协程 - 防止阻塞"""
        while not self.is_exited:
            try:
                if not self.is_connected or not self.reader or self.reader.at_eof():
                    await asyncio.sleep(1)
                    continue
                    
                message = await self.receive_message_async()
                if message and "Type" in message:
                    await self.process_json_pack(message)
                elif not self.is_connected:
                    # 连接已断开，等待重连
                    await asyncio.sleep(1)
                    
            except asyncio.CancelledError:
                break
            except Exception as e:
                LOGGER.debug("Receive worker handled error: %s", e)
                self.is_connected = False
                await asyncio.sleep(1)
    
    async def heartbeat_async(self):
        """异步心跳 - 防阻塞"""
        while not self.is_exited:
            if self.is_connected and self.writer and not self.writer.is_closing():
                try:
                    await self.send_message_async({"Type": "Ping"})
                except Exception:
                    self.is_connected = False
            
            try:
                await asyncio.sleep(self.heartbeat_interval)
            except asyncio.CancelledError:
                break
    
    # 委托给状态管理器的方法
    async def sync_device_async(self, force=False, interval=180):
        """设备同步 - 委托给状态管理器"""
        await self._state_manager.sync_all_devices(force, interval)
    
    async def sync_device_state_async(self, state: State):
        """状态同步 - 发送单个设备状态，使用原有SyncState格式"""
        if not state:
            return
            
        if not hasattr(self, 'entity_ids') or not self.entity_ids:
            return
            
        entity_id = state.entity_id
        if entity_id not in self.entity_ids:
            return
            
        LOGGER.info("上报设备状态: %s = %s", entity_id, state.state)
        
        # 使用原有格式序列化状态
        from homeassistant.helpers.json import JSONEncoder
        import json
        State = json.dumps(state.as_dict(), sort_keys=True, cls=JSONEncoder, default=str)
        
        login_info = self.get_login_info()
        if not login_info:
            return
            
        body = {
            'Type': 'SyncState',
            'Payload': {
                'Username': login_info['username'],
                'Password': login_info['password'],
                'Version': login_info['version'],
                'State': State
            }
        }
        
        await self.send_message_async(body)
    
    def _on_state_changed_optimized(self, event):
        """优化状态变化处理 - 已废弃"""
        pass
        
    async def _async_on_state_changed(self, event):
        """异步状态变化处理"""
        new_state = event.data.get("new_state")
        old_state = event.data.get("old_state")
        
        if new_state:
            LOGGER.debug("状态变化事件触发: %s", new_state.entity_id)
            self._state_manager.on_state_changed(
                new_state.entity_id, old_state, new_state
            )
    
    # 保持所有消息处理函数不变
    async def on_sync_device(self, jdata):
        """设备同步请求"""
        LOGGER.info("sync devices:%s", jdata)
        await self.sync_device_async(True)
    
    async def on_device_control(self, jdata):
        """设备控制 - 非阻塞实现"""
        LOGGER.info("receive device state:%s", jdata)
        jpayload = jdata['Payload']
        rows = jpayload['Rows']
        
        tasks = []
        for row in rows:
            data = row.get("data")
            try:
                domain = row.get("domain")
                service = row.get("service")
                task = self.hass.services.async_call(domain, service, data, blocking=False)
                tasks.append(task)
            except Exception as e:
                LOGGER.error("Error creating service call: %s", e)
        
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
    
    async def on_auth(self, jdata):
        """认证处理"""
        LOGGER.info("receive entitys:%s", jdata)
        self._login_info = self.get_login_info()
        if not self._login_info:
            return
            
        body = {
            'Type': 'Auth',
            'Payload': {
                'Username': self._login_info['username'],
                'Password': self._login_info['password'],
                'Version': self._login_info['version'],
            }
        }
        await self.send_message_async(body)
    
    async def on_update_entitys(self, jdata):
        """实体更新"""
        LOGGER.info("receive entitys:%s", jdata)
        jpayload = jdata['Payload']
        try:
            self.entity_ids = jpayload.get("entity_ids", [])
        except Exception as e:
            LOGGER.error("Error updating entity_ids: %s", e)
    
    async def on_error(self, jdata):
        """错误处理"""
        LOGGER.info("error:%s", jdata)
        jpayload = jdata['Payload']
        self.is_exited = True
        await self.close_connection()
        try:
            msg = jpayload.get("msg")
            LOGGER.error("error:%s", msg)
        except Exception as e:
            LOGGER.error("Error processing error message: %s", e)
    
    async def process_json_pack(self, jdata):
        """消息处理"""
        LOGGER.debug("process_json_pack %s", str(jdata))
        if jdata['Type'] in self.protocol_func_bind_map:
            await self.protocol_func_bind_map[jdata['Type']](jdata)
    
    def init_func_bind_map(self):
        """初始化函数映射"""
        self.protocol_func_bind_map = {
            "DeviceControl": self.on_device_control,
            "UpdateEntitys": self.on_update_entitys,
            "Auth": self.on_auth,
            "Error": self.on_error,
            "SyncDevice": self.on_sync_device
        }
    
    def get_login_info(self):
        """获取登录信息"""
        if self._login_info:
            return self._login_info
            
        hassconfig = HASSLIFE_CONFIGS.get_config_object().get("hassconfig", {})
        username = hassconfig.get("username", "")
        password = hassconfig.get("password", "")
        
        # 使用统一的插件版本号
        from .const import VERSION
        version = VERSION
        
        password = hashlib.sha1(password.encode('utf-8')).hexdigest()
        self._login_info = {
            'username': username,
            'password': password,
            'version': version
        }
        return self._login_info
    
    def _get_domain(self, entity_id):
        """获取设备域"""
        return entity_id.split(".")[0]
    
    def stop(self):
        """停止客户端 - 最佳实践"""
        LOGGER.info("Stopping OptimizedTcpClient...")
        self.is_exited = True
        
        # 停止状态管理器
        if hasattr(self, '_state_manager'):
            self._state_manager.stop()
        
        # 取消所有任务
        tasks_to_cancel = []
        if hasattr(self, '_main_loop_task') and self._main_loop_task and not self._main_loop_task.done():
            tasks_to_cancel.append(self._main_loop_task)
        if hasattr(self, '_sender_task') and self._sender_task and not self._sender_task.done():
            tasks_to_cancel.append(self._sender_task)
        if hasattr(self, '_receiver_task') and self._receiver_task and not self._receiver_task.done():
            tasks_to_cancel.append(self._receiver_task)
        
        for task in tasks_to_cancel:
            task.cancel()
        
        # 异步关闭连接
        if hasattr(self.hass, 'is_running') and self.hass.is_running:
            asyncio.create_task(self.close_connection())
        
        LOGGER.info("OptimizedTcpClient stopped")