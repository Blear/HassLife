"""Constants for HassLife."""
import os
import json

def get_version():
    """从manifest.json获取插件版本号"""
    try:
        manifest_path = os.path.join(os.path.dirname(__file__), 'manifest.json')
        with open(manifest_path, 'r') as f:
            manifest = json.load(f)
            return manifest.get('version', '3.6')
    except Exception:
        return '3.6'

# 版本号统一从manifest.json获取
VERSION = get_version()
CLIENT_VERSION = VERSION

BUFFER_SIZE = 1024
CONNECTED = 1

PING_INTERVAL_DEFAULT = 10

RECONNECT_INTERVAL = 5

STAGE_SERVER_UNCONNECTED = 'server_unconnected'
STAGE_SERVER_CONNECTED = 'server_connected'
STAGE_AUTH_BINDED = 'auth_binded'

TCP_PACK_HEADER_LEN = 16
TOKEN_KEY_NAME = 'slavertoken'

CLIENT_STATUS_UNBINDED = "unbinded"
CLIENT_STATUS_BINDED = "binded"

CONFIG_FILE_NAME = "hasslife_config.yaml"

TCP_CONNECTION_ACTIVATE_TIME = 60
