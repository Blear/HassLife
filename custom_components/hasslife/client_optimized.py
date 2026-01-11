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
import random
from typing import Optional, Dict, Any
from homeassistant.const import EVENT_STATE_CHANGED, EVENT_HOMEASSISTANT_STOP
from homeassistant.core import HomeAssistant, State
from homeassistant.helpers.json import JSONEncoder

from .const import VERSION
from .hasslife_config import HASSLIFE_CONFIGS
from .utils import LOGGER
from .state_manager import StateSyncManager


class OptimizedTcpClient:
    white_domains = ['button','light','cover','switch','vacuum','water_heater','humidifier','fan','media_player','script','climate','input_boolean','input_button','scene','automation','group','lock']
    is_exited = False
    
    def __init__(self, host: str, port: int, hass: HomeAssistant):
        self.host = host
        self.port = port
        self.hass = hass
        
        self.reader: Optional[asyncio.StreamReader] = None
        self.writer: Optional[asyncio.StreamWriter] = None
        
        self.is_connected = False
        self.is_init = True
        self._connection_lock = asyncio.Lock()
        self._disconnect_event = asyncio.Event()
        # 消息队列
        self._message_queue = asyncio.Queue(maxsize=1000)
        self._sender_task: Optional[asyncio.Task] = None
        self._receiver_task: Optional[asyncio.Task] = None
        self._heartbeat_task: Optional[asyncio.Task] = None
        self._main_loop_task: Optional[asyncio.Task] = None
        
        self._login_info: Dict[str, Any] = {}
        self.entity_ids = []
        
        # 优化配置参数
        self.heartbeat_interval = 10
        self.heartbeat_timeout = 60
        self._last_pong_time=time.time()

        # 连接管理
        self._retry_count = 0
        self._base_reconnect_delay = 2
        self._max_reconnect_delay = 300

        self.protocol_func_bind_map = {}
        self.init_func_bind_map()

        # 状态同步管理器
        self._state_manager = StateSyncManager(hass, self, self.white_domains)

    async def start(self):
        """启动客户端 - 最佳实践"""
        LOGGER.info("Starting OptimizedTcpClient")
        self._state_manager.start()
        self.hass.bus.async_listen(EVENT_STATE_CHANGED, self._async_on_state_changed)
        self.hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, self._on_hass_stop)
        self._main_loop_task = asyncio.create_task(self._main_loop())

    async def stop(self):
        """停止客户端 - 最佳实践"""
        LOGGER.info("Stopping OptimizedTcpClient")
        self.is_exited = True
        self._disconnect_event.set()

        self._state_manager.stop()

        await self._cleanup_tasks(
            self._sender_task,
            self._receiver_task,
            self._heartbeat_task,
            self._main_loop_task,
        )

        await self._close_connection()
        LOGGER.info("OptimizedTcpClient stopped")

    async def _on_hass_stop(self, _):
        await self.stop()

    async def _main_loop(self):
        """主循环"""
        await asyncio.sleep(random.uniform(0, 5))
        while not self.is_exited:
            try:
                await self._connect_with_backoff()
                self._disconnect_event.clear() 
                self._last_pong_time = time.time()
                self._sender_task = asyncio.create_task(self._send_worker())
                self._receiver_task = asyncio.create_task(self._receive_worker())
                self._heartbeat_task = asyncio.create_task(self._heartbeat_worker())
                await self._disconnect_event.wait()
            except asyncio.CancelledError:
                break
            except Exception:
                LOGGER.error("Main loop error:\n%s", traceback.format_exc())
            finally:
                await self._cleanup_tasks(
                    self._sender_task,
                    self._receiver_task,
                    self._heartbeat_task,
                )
                await self._close_connection()
                self._clear_message_queue()

    async def _connect_with_backoff(self):
        """异步连接 - 非阻塞实现"""
        # 首次连接（_retry_count = 0）加一个小随机延迟，避免瞬时雪崩
        if self._retry_count == 0:
            initial_delay = random.uniform(0, 5)  # 0~5秒随机延迟
            if initial_delay > 0:
                LOGGER.info("Initial connection random delay: %.2fs", initial_delay)
                await asyncio.sleep(initial_delay)
        if self._retry_count > 0:
            base = min(
                self._base_reconnect_delay * (2 ** (self._retry_count - 1)),
                self._max_reconnect_delay,
            )
            random_factor = random.uniform(0.5, 1.5)
            delay = base * random_factor
            LOGGER.warning(
                "Reconnect backoff retry=%d delay=%.2fs",
                self._retry_count,
                delay,
            )
            await asyncio.sleep(delay)
        async with self._connection_lock:
            try:
                async with asyncio.timeout(5):
                    self.reader, self.writer = await asyncio.open_connection(self.host, self.port)
                self._retry_count = 0
                LOGGER.info("Connected to %s:%s", self.host, self.port)
            except Exception:
                self._retry_count += 1
                raise

    async def _close_connection(self):
        if self.writer:
            try:
                self.writer.close()
                await self.writer.wait_closed()
            except Exception:
                pass
        self.writer = None
        self.reader = None

    async def _send_worker(self):
        """消息发送工作协程 - 防阻塞"""
        try:
            while True:
                msg = await self._message_queue.get()
                await self._send_now(msg)
        except Exception as e:
            LOGGER.error("_send_worker failed: %s", e)
            self._disconnect_event.set()

    async def _receive_worker(self):
        """消息接收工作协程 - 防止阻塞"""
        try:
            while True:
                msg = await self._receive_one()
                await self.process_json_pack(msg)
        except Exception as e:
            LOGGER.error("_receive_worker failed: %s", e)
            self._disconnect_event.set()

    async def _heartbeat_worker(self):
        """异步心跳 - 防阻塞"""
        try:
            while True:
                await asyncio.sleep(self.heartbeat_interval)
                await self.send_message_async({"Type": "Ping"})
                if time.time() - self._last_pong_time > self.heartbeat_timeout:
                    raise TimeoutError("heartbeat timeout")
        except Exception as e:
            LOGGER.error("_heartbeat_worker failed: %s", e)
            self._disconnect_event.set()

    async def send_message_async(self, message: Dict[str, Any]) -> bool:
        """异步发送消息 - 加入队列"""
        try:
            await self._message_queue.put(message)
            return True
        except asyncio.QueueFull:
            LOGGER.error("Message queue full, dropping: %s", message.get("Type"))
            return False

    async def _send_now(self, message: Dict[str, Any]) -> bool:
        """立即发送消息 - 保持协议格式"""
        if not self.writer:
            return False
        try:
            body = json.dumps(message, cls=JSONEncoder).encode()
            header = struct.pack("<I", len(body)).ljust(32, b"\x00")
            self.writer.write(header + body)
            await self.writer.drain()
            LOGGER.info("Sent: %s", message.get("Type"))
            return True
        except Exception as e:
            LOGGER.error("_send_now failed: %s", e)
            self._disconnect_event.set()
            return False

    async def _receive_one(self):
        """异步接收消息 - 防阻塞实现"""
        if not self.reader:
            raise ConnectionError("Reader is None")
        try:
            header = await self.reader.readexactly(32)
            size = struct.unpack("<I", header[:4])[0]
            if size <= 0 or size > 1024 * 1024:
                raise ValueError(f"invalid packet size: {size}")
            body = await self.reader.readexactly(size)
            return json.loads(body.decode())
        except Exception as e:
            LOGGER.error("_receive_one failed: %s", e)
            self._disconnect_event.set()
            raise

    def _clear_message_queue(self):
        while not self._message_queue.empty():
            try:
                self._message_queue.get_nowait()
            except Exception:
                break

    async def _cleanup_tasks(self, *tasks):
        for task in tasks:
            if task and not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

    def init_func_bind_map(self):
        """初始化函数映射"""
        self.protocol_func_bind_map = {
            "DeviceControl": self.on_device_control,
            "UpdateEntitys": self.on_update_entitys,
            "Auth": self.on_auth,
            "Error": self.on_error,
            "SyncDevice": self.on_sync_device,
            "Pong": self.on_pong
        }

    async def process_json_pack(self, jdata):
        """消息处理"""
        LOGGER.debug("process_json_pack %s", str(jdata))
        self._last_pong_time = time.time()
        handler = self.protocol_func_bind_map.get(jdata.get("Type"))
        if handler:
            await handler(jdata)
    

    async def on_pong(self, jdata):
        """处理服务器的心跳响应"""
        self._last_pong_time = time.time()

    async def _async_on_state_changed(self, event):
        """异步状态变化处理"""
        new_state = event.data.get("new_state")
        old_state = event.data.get("old_state")
        
        if new_state:
            LOGGER.debug("状态变化事件触发: %s", new_state.entity_id)
            self._state_manager.on_state_changed(
                new_state.entity_id, old_state, new_state
            )

    # 委托给状态管理器的方法
    async def sync_device_async(self,  page=1, page_size=30, search_keyword=None, request_id=''):
        """设备同步 - 委托给状态管理器，支持分页、搜索和请求ID"""
        await self._state_manager.sync_all_devices(page, page_size, search_keyword, request_id)
    
    async def sync_device_state_async(self, state: State):
        if not state or state.entity_id not in self.entity_ids:
            return

        payload = {
            "attributes": state.attributes,
            "entity_id": state.entity_id,
            "state": state.state,
        }

        login = self.get_login_info()
        await self.send_message_async({
            "Type": "SyncState",
            "Payload": {
                **login,
                "State": json.dumps(payload, cls=JSONEncoder, default=str),
            }
        })

    async def on_device_control(self, jdata):
        rows = jdata.get("Payload", {}).get("Rows", [])
        tasks = []
        for row in rows:
            try:
                tasks.append(
                    self.hass.services.async_call(
                        row["domain"], row["service"], row.get("data"), blocking=False
                    )
                )
            except Exception:
                pass
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def on_update_entitys(self, jdata):
        self.entity_ids = jdata.get("Payload", {}).get("entity_ids", [])

    async def on_auth(self, jdata):
        await self.send_message_async({
            "Type": "Auth",
            "Payload": self.get_login_info(),
        })
    
    async def on_error(self, jdata):
        """错误处理"""
        LOGGER.error("Server error: %s", jdata)
        self.is_exited = True
        self._disconnect_event.set()

    async def on_sync_device(self, jdata):
        """设备同步请求 - 支持分页和搜索，包含请求ID"""
        LOGGER.info("sync devices:%s", jdata)
        payload = jdata.get("Payload", {})
        await self.sync_device_async(
            payload.get("page", 1),
            payload.get("page_size", 30),
            payload.get("search_keyword"),
            jdata.get("RequestID", ""),
        )
    
    def get_login_info(self):
        """获取登录信息"""
        if self._login_info:
            return self._login_info

        conf = HASSLIFE_CONFIGS.get_config_object().get("hassconfig", {})
        self._login_info = {
            "Username": conf.get("username", ""),
            "Password": hashlib.sha1(conf.get("password", "").encode()).hexdigest(),
            "Version": VERSION,
        }
        return self._login_info
    

    
