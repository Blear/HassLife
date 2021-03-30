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
from .utils import LOGGER, dns_open, get_rand_char, save_local_seed
from homeassistant.helpers.json import JSONEncoder


class MoloBotClient(asyncore.dispatcher):
    """Client protocol class for Molobot."""

    def __init__(self, host, port, map):
        """Initialize protocol arguments."""
        asyncore.dispatcher.__init__(self, map=map)
        self.host = host
        self.port = port
        self.ping_dequeue = queue.Queue()
        self.append_recv_buffer = None
        self.append_send_buffer = None
        self.append_connect = None
        self._last_report_device = 0
        self._login_info={}
        self.clear()

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
        except Exception as e:
            LOGGER.info("recv error: %s", e)

    def get_login_info(self):
        if self._login_info:
            return self._login_info
        hassconfig = MOLO_CONFIGS.get_config_object().get("hassconfig", {})
        username = hassconfig.get("username", "")
        password = hassconfig.get("password", "")
        password = hashlib.sha1(password.encode('utf-8')).hexdigest()
        self._login_info={'username':username,'password':password}
        return self._login_info

    def sync_device(self, force=False, interval=180):
        now = time.time()
        if (not force) and (now - self._last_report_device < interval):
            return None
        self._last_report_device = now
        self._login_info = self.get_login_info()
        if not self._login_info:
            return None

        devicelist = MOLO_CLIENT_APP.hass_context.states.async_all()
        jlist = json.dumps(
            devicelist, sort_keys=True, cls=JSONEncoder).encode('UTF-8')
        if not jlist:
            return None

        body = {
            'Type': 'SyncDevice',
            'Payload': {
                'Username': self._login_info['username'],
                'Password': self._login_info['password'],
                'Action': "synclist",
                'List': jlist.decode("UTF-8")
            }
        }
        body_jdata_str = json.dumps(body)
        self.send_raw_pack(body_jdata_str)

    def writable(self):
        """If the socket send buffer writable."""
        ping_buffer = MOLO_CLIENT_APP.get_ping_buffer()
        if ping_buffer:
            self.append_send_buffer += ping_buffer
        self.sync_device()
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


    def send_raw_pack(self, body_str):
        """Send raw data packet."""
        if self.append_connect:
            return
        body_str+="\t"
        body_bytes = body_str.encode('utf-8')
        self.append_send_buffer += body_bytes
        self.handle_write()


    def ping_server_buffer(self):
        """Get ping buffer."""
        body = dict()
        body['Type'] = 'Ping'
        body_jdata_str = json.dumps(body)+"\t"
        body_jdata_bytes = body_jdata_str.encode('utf-8')
        return body_jdata_bytes


