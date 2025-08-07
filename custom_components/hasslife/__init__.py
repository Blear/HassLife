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
from .client import TcpClient
from .utils import LOGGER

DOMAIN = 'hasslife'
NOTIFYID = 'hasslifenotifyid'
VERSION = 3.5

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
    cfg.update({"version": VERSION})
    if 'mode' in cfg:
        MOLO_CONFIGS.load(cfg['mode'])
    else:
        MOLO_CONFIGS.load('release')
    MOLO_CONFIGS.get_config_object()["hassconfig"] = cfg
    client = TcpClient(MOLO_CONFIGS.get_config_object()['server']['host'],
        int(MOLO_CONFIGS.get_config_object()['server']['port']),hass)
    client.run()
    hass.data[DOMAIN][entry.entry_id] = {
        "client": client,
    }
    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    data = hass.data[DOMAIN].get(entry.entry_id)
    if data is not None:
        data["client"].stop()
        hass.data[DOMAIN].pop(entry.entry_id)
    return True
