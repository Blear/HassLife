from homeassistant.const import (EVENT_HOMEASSISTANT_START,
                                 EVENT_HOMEASSISTANT_STOP, EVENT_STATE_CHANGED)

from .molo_client_config import MOLO_CONFIGS
from .molo_client_app import MOLO_CLIENT_APP
from .utils import LOGGER

DOMAIN = 'hasslife'
NOTIFYID = 'hasslifenotifyid'
VERSION = 101

def setup(hass, config):
    """Set up molobot component."""
    LOGGER.info("Begin setup hasslife!")

    # Load config mode from configuration.yaml.
    cfg = config[DOMAIN]
    cfg.update({"__version__": VERSION})

    if 'mode' in cfg:
        MOLO_CONFIGS.load(cfg['mode'])
    else:
        MOLO_CONFIGS.load('release')


    MOLO_CONFIGS.get_config_object()["hassconfig"] = cfg

    async def stop_molobot(event):
        """Stop Molobot while closing ha."""
        LOGGER.info("Begin stop hasslife!")
        from .molo_bot_main import stop_aligenie
        stop_aligenie()

    async def start_molobot(event):
        """Start Molobot while starting ha."""
        LOGGER.debug("hasslife started!")
        hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, stop_molobot)

    async def on_state_changed(event):
        """Disable the dismiss button."""
        if MOLO_CLIENT_APP.molo_client:
            MOLO_CLIENT_APP.molo_client.sync_device(True, 2)

    from .molo_bot_main import run_aligenie
    run_aligenie(hass)

    if not cfg.get("disablenotify", False):
        hass.components.persistent_notification.async_create(
            "Welcome to hasslife!", "hasslife Infomation", "hasslife_notify")

    hass.bus.async_listen_once(EVENT_HOMEASSISTANT_START, start_molobot)
    hass.bus.async_listen(EVENT_STATE_CHANGED, on_state_changed)

    return True
