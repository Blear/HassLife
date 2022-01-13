from homeassistant.const import (EVENT_HOMEASSISTANT_START,
                                 EVENT_HOMEASSISTANT_STOP, EVENT_STATE_CHANGED)
from homeassistant.config_entries import SOURCE_IMPORT, ConfigEntry
from homeassistant.const import (
    CONF_NAME,
    CONF_PASSWORD,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.typing import ConfigType
from .molo_client_config import MOLO_CONFIGS
from .molo_client_app import MOLO_CLIENT_APP
from .utils import LOGGER
import time
DOMAIN = 'hasslife'
NOTIFYID = 'hasslifenotifyid'
VERSION = 103
is_init = False
last_start_time = time.time()

async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    # Load config mode from configuration.yaml.
    hass.data.setdefault(DOMAIN, {})

    if DOMAIN in config:
        hass.async_create_task(
                hass.config_entries.flow.async_init(
                    DOMAIN, context={"source": SOURCE_IMPORT}, data=config[DOMAIN]
                )
            )
    return True
    
async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up molobot component."""
    LOGGER.info("Begin setup hasslife!")
    hass.data.setdefault(DOMAIN, {})

    # Load config mode from configuration.yaml.
    cfg = dict(entry.data)
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
        global is_init
        is_init = True
        hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, stop_molobot)
        last_start_time = time.time()

    async def on_state_changed(event):
        """Disable the dismiss button."""
        global is_init
        global last_start_time

        if MOLO_CLIENT_APP.molo_client:
            if is_init :
                MOLO_CLIENT_APP.molo_client.sync_device(True, 2)
                is_init = False
            elif last_start_time and (time.time() - last_start_time > 30):
                last_start_time = None
                MOLO_CLIENT_APP.molo_client.sync_device(True, 2)
            elif not is_init or not last_start_time:
                new_state = event.data.get("new_state")
                if not new_state:
                    return
                MOLO_CLIENT_APP.molo_client.sync_device_state(new_state)


    from .molo_bot_main import run_aligenie
    run_aligenie(hass)

    if not cfg.get("disablenotify", False):
        hass.components.persistent_notification.async_create(
            "Welcome to hasslife!", "hasslife Infomation", "hasslife_notify")
    hass.bus.async_listen_once(EVENT_HOMEASSISTANT_START, start_molobot)
    hass.bus.async_listen(EVENT_STATE_CHANGED, on_state_changed)

    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    from .molo_bot_main import stop_aligenie
    await stop_aligenie()
    return True
