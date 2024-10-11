import asyncio
import time
import struct
import json
import hashlib
import traceback
import threading
from homeassistant.const import (__short_version__,EVENT_STATE_CHANGED)

from .const import (BUFFER_SIZE, CLIENT_VERSION, CONFIG_FILE_NAME)
from .molo_client_config import MOLO_CONFIGS
from .utils import LOGGER, dns_open, get_rand_char, save_local_seed
from homeassistant.helpers.json import JSONEncoder

class TcpClient:
    white_domains = ['button','binary_sensor','sensor','light','cover','switch','vacuum','water_heater','humidifier','fan','media_player','script','climate','input_boolean','automation','group','lock']
    protocol_func_bind_map = {}
    is_exited = False

    def __init__(self, host, port,hass):
        self.host = host
        self.port = port
        self.hass = hass
        self.reader = None
        self.writer = None
        self.is_connected = False
        self.is_init=True

        self._last_report_device = 0
        self._login_info={}
        self.init_func_bind_map()
        self.entity_ids = []

        # 设置心跳间隔
        self.heartbeat_interval = 10
        # 设置心跳超时时间
        self.heartbeat_timeout = 60
        self.heartbeat_timer = time.time()
        self.last_start_time=None

    async def connect(self):
        self.reader, self.writer = await asyncio.open_connection(self.host, self.port)
        self.is_connected = True
        LOGGER.info("Connected to:%s:%d", self.host,self.port)
        

    async def send_message(self, message):
        if self.is_connected:
            try:
                # 发送消息前确保连接是打开的
                message_body = json.dumps(message).encode('utf-8')
                # 计算消息体的长度  
                message_length = len(message_body)
                # 构造首部数据  
                header_data = struct.pack('<I', message_length)
                header_data=header_data.ljust(32, b'\x00')
                #header_data=message_length.to_bytes(32, byteorder='little')
                self.writer.write(header_data + message_body)
                await self.writer.drain()
                LOGGER.info("send :%s", message)
            except Exception as exc:
                    exc = traceback.format_exc()
        else:
            LOGGER.info("Not connected. Cannot send message.")

    async def receive_message(self):
        if self.is_connected:
            while True:
                try:
                    header_data = await self.reader.read(32)  
                    if not header_data:  
                        current_time = asyncio.get_running_loop().time()
                        if current_time - self.heartbeat_timer > self.heartbeat_timeout:
                            LOGGER.info("Heartbeat timed out!")
                            break
                        else:
                            continue
                    # 解析首部的unsigned int数据  
                    message_length = int.from_bytes(header_data, byteorder='little')
                    # 读取包体数据  
                    data = await self.reader.read(message_length)
                    if data:
                        LOGGER.info("Received:%s",data.decode())
                        json_buff = data.decode('utf-8')
                        body_jdata = json.loads(json_buff)
                        await self.process_json_pack(body_jdata) 
                        # 如果收到响应，重置未响应计数器
                        self.heartbeat_timer = asyncio.get_running_loop().time()
                except Exception as exc:
                    LOGGER.error("Exception occurred: %s", traceback.format_exc())
                    break
        else:
            LOGGER.error("Not connected. Cannot receive message.")

    async def close_connection(self):
        if self.writer is not None:
            try:
                self.writer.close()
                await self.writer.wait_closed()
                self.writer = None
                self.reader = None
                self.is_connected=False
                LOGGER.info("Connection closed")
            except Exception as exc:
                    exc = traceback.format_exc()

    def run(self):
        self.last_start_time=time.time()
        self.hass.bus.async_listen(EVENT_STATE_CHANGED, self.on_state_changed)
        client_thread = threading.Thread(target=self.main)  
        client_thread.start()  

    def main(self):
        # 运行事件循环
        asyncio.run(self.loop())

    async def loop(self):
        while not self.is_exited:
            heartbeat_task = None  # 初始化心跳任务
            listen_task = None  # 初始化监听任务

            try:
                await self.connect()
                heartbeat_task = asyncio.create_task(self.heartbeat())
                listen_task = asyncio.create_task(self.receive_message())
                await listen_task
            except Exception as e: 
                LOGGER.error("Connection failed:%s",e)
                # 取消并等待心跳任务
            if heartbeat_task is not None:
                heartbeat_task.cancel()
                try:
                    await heartbeat_task
                except asyncio.CancelledError:
                    pass

            # 取消并等待监听任务
            if listen_task is not None:
                listen_task.cancel()
                try:
                    await listen_task
                except asyncio.CancelledError:
                    pass

            # 关闭连接并等待5秒重连
            await self.close_connection()
            await asyncio.sleep(5)
        heartbeat_task.cancel()
        try:
            await heartbeat_task
        except asyncio.CancelledError:
            pass
        await self.close_connection()

    def stop(self):
        self.is_exited=True

    async def heartbeat(self):
        """发送心跳消息的协程，interval为心跳间隔时间（秒）。"""
        if self.writer is not None:
            while True:
                await self.send_message({"Type":"Ping"})
                LOGGER.info("Heartbeat send")
                await asyncio.sleep(self.heartbeat_interval)
        else:
            LOGGER.error("Not connected. Cannot send heartbeat.")

    async def sync_device(self, force=False, interval=180):
        now = time.time()
        if (not force) and (now - self._last_report_device < interval):
            return None
        self._last_report_device = now
        if not self._login_info:
            return None

        devicelist = self.hass.states.async_all()
        usefull_entity = []
        for sinfo in devicelist:
            dinfo = sinfo.as_dict()
            entity_id = dinfo['entity_id']
            domain = self._get_domain(entity_id)

            if domain in self.white_domains:
                usefull_entity.append(dinfo)
        
        jlist = json.dumps(
                usefull_entity, sort_keys=True, cls=JSONEncoder)
        if not jlist:
            return None
        body = {
            'Type': 'SyncDevice',
            'Payload': {
                'Username': self._login_info['username'],
                'Password': self._login_info['password'],
                'Version': self._login_info['version'],
                'List': jlist
            }
        }
        await self.send_message(body)

    async def sync_device_state(self, state):
        if not state:
            return None
        if not self._login_info:
            return None
        entity_id = state.entity_id
        if entity_id not in  self.entity_ids:
            return None
        State = json.dumps(
            state, sort_keys=True, cls=JSONEncoder)

        body = {
            'Type': 'SyncState',
            'Payload': {
                'Username': self._login_info['username'],
                'Password': self._login_info['password'],
                'Version': self._login_info['version'],
                'State': State
            }
        }
        await self.send_message(body)

    async def on_sync_device(self, jdata):
        LOGGER.info("sync devices:%s", jdata)
        await self.sync_device(True)

    async def on_device_control(self, jdata):
        LOGGER.info("receive device state:%s", jdata)
        jpayload = jdata['Payload']
        rows=jpayload['Rows']
        tasks = []
        for row in rows:
            data = row.get("data")
            try:
                domain = row.get("domain")
                service = row.get("service")
                tasks.append(self.hass.services.async_call(domain, service, data, blocking=True))
            except Exception as e:
                exc = traceback.format_exc()
                LOGGER.error("Error during service call: %s", exc)
        try:
            await asyncio.gather(*tasks)
        except Exception as e:
            LOGGER.error("Error executing tasks: %s", str(e))


    async def on_auth(self, jdata):
        LOGGER.info("receive entitys:%s", jdata)
        self._login_info = self.get_login_info()
        if not self._login_info:
            return None
        body = {
            'Type': 'Auth',
            'Payload': {
                'Username': self._login_info['username'],
                'Password': self._login_info['password'],
                'Version': self._login_info['version'],
            }
        }
        await self.send_message(body)

    async def on_update_entitys(self, jdata):
        LOGGER.info("receive entitys:%s", jdata)
        jpayload = jdata['Payload']
        try:
            self.entity_ids = jpayload.get("entity_ids")
        except Exception as e:
            exc = traceback.format_exc()


    async def on_error(self, jdata):
        LOGGER.info("error:%s", jdata)
        jpayload = jdata['Payload']
        self.is_exited=True
        await self.close_connection()
        try:
            msg = jpayload.get("msg")
            LOGGER.error("error:%s", msg)
        except Exception as e:
            exc = traceback.format_exc()


    def get_login_info(self):
        if self._login_info:
            return self._login_info
        hassconfig = MOLO_CONFIGS.get_config_object().get("hassconfig", {})
        username = hassconfig.get("username", "")
        password = hassconfig.get("password", "")
        version = hassconfig.get("version", 1.0)
        password = hashlib.sha1(password.encode('utf-8')).hexdigest()
        self._login_info={'username':username,'password':password,'version':version}
        return self._login_info

    def _get_domain(self, entity_id):
        return entity_id.split(".")[0]


    async def process_json_pack(self, jdata):
        """Handle received json packet."""
        LOGGER.debug("process_json_pack %s", str(jdata))
        if jdata['Type'] in self.protocol_func_bind_map:
            await self.protocol_func_bind_map[jdata['Type']](jdata)

    def init_func_bind_map(self):
        """Initialize protocol function bind map."""
        self.protocol_func_bind_map = {
            "DeviceControl": self.on_device_control,
            "UpdateEntitys": self.on_update_entitys,
            "Auth": self.on_auth,
            "Error": self.on_error,
            "SyncDevice": self.on_sync_device
        }

    async def on_state_changed(self,event):
        # if self.is_init :
        #     await self.sync_device(True, 2)
        #     self.is_init=False
        # elif self.last_start_time and (time.time() - self.last_start_time > 30):
        #     self.last_start_time = None
        #     await self.sync_device(True, 2)
        # elif not self.is_init or not last_start_time:
        new_state = event.data.get("new_state")
        if not new_state:
            return
        await self.sync_device_state(new_state)


