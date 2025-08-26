from homeassistant.const import (EVENT_HOMEASSISTANT_START,
                                 EVENT_HOMEASSISTANT_STOP, EVENT_STATE_CHANGED)
from homeassistant.config_entries import SOURCE_IMPORT, ConfigEntry
from homeassistant.const import (
    CONF_NAME,
    CONF_PASSWORD,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.typing import ConfigType
from .hasslife_config import HASSLIFE_CONFIGS
from .client_optimized import OptimizedTcpClient as TcpClient
from .utils import LOGGER
from .const import VERSION

DOMAIN = 'hasslife'
NOTIFYID = 'hasslifenotifyid'

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
    """Set up hasslife component."""
    LOGGER.info("Begin setup hasslife!")
    hass.data.setdefault(DOMAIN, {})
    # Load config mode from configuration.yaml.
    cfg = dict(entry.data)
    cfg.update({"version": VERSION})
    if 'mode' in cfg:
        HASSLIFE_CONFIGS.load(cfg['mode'])
    else:
        HASSLIFE_CONFIGS.load('release')
    HASSLIFE_CONFIGS.get_config_object()["hassconfig"] = cfg
    client = TcpClient(HASSLIFE_CONFIGS.get_config_object()['server']['host'],
        int(HASSLIFE_CONFIGS.get_config_object()['server']['port']),hass)
    await client.start()
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
