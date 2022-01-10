"""TCP packet header define for Molobot."""
import json
import logging

from .utils import LOGGER

# pack format:
# BODY_LEN 4BYTES
# BODY_JSON_STR BODY_LEN


def bytetolen(byteval):
    """Read length integer from bytes."""
    if len(byteval) == MoloTcpPack.PACK_LEN_SIZE:
        return int.from_bytes(byteval, byteorder='little')
    return 0


def lentobyte(length):
    """Write length integer to bytes buffer."""
    return length.to_bytes(MoloTcpPack.PACK_LEN_SIZE, byteorder='little')


class MoloTcpPack():
    """TCP packet header define class for Molobot."""

    PACK_LEN_SIZE = 32
    ERR_OK = 0
    ERR_INSUFFICIENT_BUFFER = 1
    ERR_MALFORMED = 2

    @classmethod
    def generate_tcp_buffer(cls, body_jdata):
        """Construct TCP packet from json data."""
        body_jdata_str = json.dumps(body_jdata)
        body_jdata_bytes = body_jdata_str.encode('utf-8')
        tcp_buffer = lentobyte(
            len(body_jdata_bytes)) + body_jdata_bytes
        return tcp_buffer

    def __init__(self):
        """Initialize TCP packet arguments."""
        self.tmp_buffer = None
        self.error_code = None
        self.body_len = None
        self.body_jdata = None
        self.clear()

    def clear(self):
        """Reset TCP packet arguments."""
        self.tmp_buffer = None
        self.error_code = MoloTcpPack.ERR_OK
        self.body_len = None
        self.body_jdata = None

    def recv_body_len(self):
        """Read received TCP body length."""
        if len(self.tmp_buffer) < MoloTcpPack.PACK_LEN_SIZE:
            return False
        self.body_len = bytetolen(
            self.tmp_buffer[:MoloTcpPack.PACK_LEN_SIZE])
        self.tmp_buffer = self.tmp_buffer[MoloTcpPack.PACK_LEN_SIZE:]
        return True

    def recv_body(self):
        """Read received TCP body."""
        if len(self.tmp_buffer) < self.body_len:
            return False
        try:
            json_buff = self.tmp_buffer[:self.body_len].decode('utf-8')
            self.body_jdata = json.loads(json_buff)
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            self.error_code = MoloTcpPack.ERR_MALFORMED
            LOGGER.error("MoloTcpPack recv body error %s",
                         self.tmp_buffer[:self.body_len])
            logging.exception(exc)
            return False
        self.tmp_buffer = self.tmp_buffer[self.body_len:]
        return True


    def has_recved_body_len(self):
        """If self has received body length."""
        return self.body_len is not None

    def has_recved_body(self):
        """If self has received body."""
        return self.body_jdata is not None

    def recv_buffer(self, buffer):
        """Handle received."""
        if not buffer:
            return False

        ret = False
        if self.error_code == MoloTcpPack.ERR_OK:
            self.clear()
        self.error_code = MoloTcpPack.ERR_INSUFFICIENT_BUFFER

        self.tmp_buffer = buffer

        if not self.has_recved_body_len():
            ret = self.recv_body_len()
            if not ret:
                return ret

        if not self.has_recved_body():
            ret = self.recv_body()
            if not ret:
                return ret

        self.error_code = MoloTcpPack.ERR_OK
        return True