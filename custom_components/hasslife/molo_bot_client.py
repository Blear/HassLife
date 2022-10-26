"""Client protocol class for Molobot."""
import re
import copy
import asyncore
import queue
import socket
import time
import json
import hashlib
import traceback

from homeassistant.const import __short_version__

from .const import (BUFFER_SIZE, CLIENT_VERSION, CONFIG_FILE_NAME)
from .molo_client_app import MOLO_CLIENT_APP
from .molo_client_config import MOLO_CONFIGS
from .molo_tcp_pack import MoloTcpPack
from .utils import LOGGER, dns_open, get_rand_char, save_local_seed
from homeassistant.helpers.json import JSONEncoder


class MoloBotClient(asyncore.dispatcher):
    """Client protocol class for Molobot."""
    white_domains = ['button','binary_sensor','sensor','light','cover','switch','vacuum','water_heater','humidifier','fan','media_player','script','climate','input_boolean','automation','group','lock']
    protocol_func_bind_map = {}
    def __init__(self, host, port, map):
        """Initialize protocol arguments."""
        asyncore.dispatcher.__init__(self, map=map)
        self.host = host
        self.port = port
        self.molo_tcp_pack = MoloTcpPack()
        self.ping_dequeue = queue.Queue()
        self.append_recv_buffer = None
        self.append_send_buffer = None
        self.append_connect = None
        self._last_report_device = 0
        self._login_info={}
        self.clear()
        self.init_func_bind_map()
        self.entity_ids = []

    def handle_connect(self):
        """When connected, this method will be call."""
        LOGGER.debug("server connected")
        self.append_connect = False

    def handle_close(self):
        """When closed, this method will be call. clean itself."""
        LOGGER.debug("server closed")
        self.clear()
        self.close()

        # close all and restart
        asyncore.close_all()

    def handle_read(self):
        """Handle read message."""
        try:
            buff = self.recv(BUFFER_SIZE)
            self.append_recv_buffer += buff
            self.process_molo_tcp_pack()
        except Exception as e:
            LOGGER.info("recv error: %s", e)

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

    def sync_device(self, force=False, interval=180):
        now = time.time()
        if (not force) and (now - self._last_report_device < interval):
            return None
        self._last_report_device = now
        self._login_info = self.get_login_info()
        if not self._login_info:
            return None

        devicelist = MOLO_CLIENT_APP.hass_context.states.async_all()
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
        self.send_dict_pack(body)

    def sync_device_state(self, state):
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
        self.send_dict_pack(body)


    def writable(self):
        """If the socket send buffer writable."""
        ping_buffer = MOLO_CLIENT_APP.get_ping_buffer()
        if ping_buffer:
            self.append_send_buffer += ping_buffer
        return self.append_connect or (self.append_send_buffer)

    def handle_write(self):
        """Write socket send buffer."""
        sent = self.send(self.append_send_buffer)
        self.append_send_buffer = self.append_send_buffer[sent:]
        MOLO_CLIENT_APP.reset_activate_time()

    # The above are base class methods.
    def clear(self):
        """Reset client protocol arguments."""
        self.append_recv_buffer = bytes()
        self.append_send_buffer = bytes()
        self.append_connect = True

    def sock_connect(self):
        """Connect to host:port."""
        self.clear()
        dns_ip = dns_open(self.host)
        if not dns_ip:
            return
        self.create_socket(socket.AF_INET, socket.SOCK_STREAM)
        self.connect((dns_ip, self.port))


    def send_raw_pack(self, raw_data):
        """Send raw data packet."""
        if self.append_connect:
            return
        self.append_send_buffer += raw_data
        self.handle_write()

    def send_dict_pack(self, dict_data):
        """Convert and send dict packet."""
        if self.append_connect:
            return
        body = MoloTcpPack.generate_tcp_buffer(dict_data)
        self.send_raw_pack(body)

    def ping_server_buffer(self):
        """Get ping buffer."""
        body = dict()
        body['Type'] = 'Ping'
        body = MoloTcpPack.generate_tcp_buffer(body)
        return body

    def process_molo_tcp_pack(self):
        """Handle received TCP packet."""
        ret = True
        while ret:
            ret = self.molo_tcp_pack.recv_buffer(self.append_recv_buffer)
            if ret and self.molo_tcp_pack.error_code == MoloTcpPack.ERR_OK:
                self.process_json_pack(self.molo_tcp_pack.body_jdata)
            self.append_recv_buffer = self.molo_tcp_pack.tmp_buffer
        if self.molo_tcp_pack.error_code == MoloTcpPack.ERR_MALFORMED:
            LOGGER.error("tcp pack malformed!")
            self.handle_close()

    def process_json_pack(self, jdata):
        """Handle received json packet."""
        LOGGER.debug("process_json_pack %s", str(jdata))
        if jdata['Type'] in self.protocol_func_bind_map:
            MOLO_CLIENT_APP.reset_activate_time()
            self.protocol_func_bind_map[jdata['Type']](jdata)

    def init_func_bind_map(self):
        """Initialize protocol function bind map."""
        self.protocol_func_bind_map = {
            "DeviceControl": self.on_device_control,
            "UpdateEntitys": self.on_update_entitys,
            "Auth": self.on_auth,
            "Error": self.on_error,
            "SyncDevice": self.on_sync_device
        }

    def on_device_control(self, jdata):
        LOGGER.info("receive device state:%s", jdata)
        jpayload = jdata['Payload']
        rows=jpayload['Rows']
        for row in rows:
            data = row.get("data")
            exc = {}
            try:
                domain = row.get("domain")
                service = row.get("service")
                exc = MOLO_CLIENT_APP.hass_context.services.call(domain, service, data, blocking=True)
            except Exception as e:
                exc = traceback.format_exc()

    def on_update_entitys(self, jdata):
        LOGGER.info("receive entitys:%s", jdata)
        jpayload = jdata['Payload']
        try:
            self.entity_ids = jpayload.get("entity_ids")
        except Exception as e:
            exc = traceback.format_exc()

    def on_auth(self, jdata):
        LOGGER.info("receive entitys:%s", jdata)
        body = {
            'Type': 'Auth',
            'Payload': {
                'Username': self._login_info['username'],
                'Password': self._login_info['password'],
                'Version': self._login_info['version'],
            }
        }
        self.send_dict_pack(body)

    def on_sync_device(self, jdata):
        LOGGER.info("sync devices:%s", jdata)
        self.sync_device(True)

    def on_error(self, jdata):
        LOGGER.info("error:%s", jdata)
        jpayload = jdata['Payload']
        try:
            msg = jpayload.get("msg")
            LOGGER.error("error:%s", msg)
        except Exception as e:
            exc = traceback.format_exc()


