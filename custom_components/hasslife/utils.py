"""Utils for HassLife."""
import logging
import random
import socket
import uuid
import yaml
import json

from .const import TCP_PACK_HEADER_LEN

LOGGER = logging.getLogger(__package__)


def get_mac_addr():
    """Get local mac address."""
    import uuid
    node = uuid.getnode()
    mac = uuid.UUID(int=node).hex[-12:]
    return mac


def dns_open(host):
    """Get ip from hostname."""
    try:
        ip_host = socket.gethostbyname(host)
    except socket.error:
        return None

    return ip_host


def len_to_byte(length):
    """Write length integer to bytes buffer."""
    return length.to_bytes(TCP_PACK_HEADER_LEN, byteorder='little')


def byte_to_len(byteval):
    """Read length integer from bytes."""
    if len(byteval) == TCP_PACK_HEADER_LEN:
        return int.from_bytes(byteval, byteorder='little')
    return 0


def get_rand_char(length):
    """Generate random string by length."""
    _chars = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789abcdefghijklmnopqrstuvwxyz"
    return ''.join(random.sample(_chars, length))


def get_local_seed(config_file):
    """Read seed from local file."""
    local_seed = ""
    try:
        with open(config_file, 'r') as file_obj:
            config_data = yaml.load(file_obj)
            if config_data and 'hasslife' in config_data:
                if 'localseed' in config_data['hasslife']:
                    local_seed = config_data['hasslife']['localseed']
    except (EnvironmentError, yaml.YAMLError):
        pass
    return local_seed


def save_local_seed(config_file, local_seed):
    """Save seed to local file."""
    config_data = None
    try:
        with open(config_file, 'r') as rfile:
            config_data = yaml.load(rfile)
    except (EnvironmentError, yaml.YAMLError):
        pass

    if not config_data:
        config_data = {}
        config_data['hasslife'] = {}
    try:
        with open(config_file, 'w') as wfile:
            config_data['hasslife']['localseed'] = local_seed
            yaml.dump(config_data, wfile, default_flow_style=False)
    except (EnvironmentError, yaml.YAMLError):
        pass


def load_uuid(hass, filename='.uuid'):
    """Load UUID from a file or return None."""
    try:
        with open(hass.config.path(filename)) as fptr:
            jsonf = json.loads(fptr.read())
            return uuid.UUID(jsonf['uuid'], version=4).hex
    except (ValueError, AttributeError, FileNotFoundError):
        return None
