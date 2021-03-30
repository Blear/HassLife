"""Configuration class for Molobot."""


class MoloConfigs:
    """Configuration class for Molobot."""

    config_object = dict()

    config_debug = {
        'server': {
            'host': "192.168.199.9",
            'port': 4443,
            'bufsize': 1024
        }
    }

    config_release = {
        'server': {
            'host': "hass.blear.cn",
            'port': 4443,
            'bufsize': 1024
        }
    }

    def load(self, mode):
        """Load configs by reading mode in configuration.yaml."""
        if mode == 'debug':
            self.config_object = self.config_debug
        else:
            self.config_object = self.config_release

    def get_config_object(self):
        """Get config_object, reload if not exist."""
        if not self.config_object:
            self.load('release')
        return self.config_object


MOLO_CONFIGS = MoloConfigs()
