"""Main interface for Molobot."""
from .molo_client_app import MOLO_CLIENT_APP
from .molo_client_config import MOLO_CONFIGS
from .molo_bot_client import MoloBotClient


def run_aligenie(hass):
    """Run Molobot application."""
    molo_client = MoloBotClient(
        MOLO_CONFIGS.get_config_object()['server']['host'],
        int(MOLO_CONFIGS.get_config_object()['server']['port']),
        MOLO_CLIENT_APP.async_map)
    MOLO_CLIENT_APP.run_aligenie_bot(hass, molo_client)


def stop_aligenie():
    """Stop Molobot application."""
    MOLO_CLIENT_APP.stop_aligenie_bot()
