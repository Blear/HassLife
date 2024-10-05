import voluptuous as vol
from typing import Any, Dict, Optional
from homeassistant import config_entries, core, exceptions
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.data_entry_flow import FlowResult
import json       
from . import DOMAIN
import aiohttp
from .utils import LOGGER
DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_USERNAME): str,
        vol.Required(CONF_PASSWORD): str,
    }
)

class HassLifeConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow"""
    VERSION = 1
    async def async_step_user(self, user_input= None) -> FlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}
        if self._async_current_entries():
            return self.async_abort(reason="single_instance_allowed")
        if self.hass.data.get(DOMAIN):
            return self.async_abort(reason="single_instance_allowed")

        if user_input is not None:
            unique_id = f"{user_input[CONF_USERNAME]}"
            await self.async_set_unique_id(unique_id)
            self._abort_if_unique_id_configured()
            info = None
            payload  = {'username': user_input[CONF_USERNAME], 'password': user_input[CONF_PASSWORD]}
            async with aiohttp.ClientSession() as session:
                async with session.post('https://hass.blear.cn/callback.php',data=payload) as response:
                    if response.status == 200:
                        data = await response.text()
                        LOGGER.info("login info: %s", data)
                        jsondata=json.loads(data)
                        if jsondata['code'] == 'ok':
                            info = {'title':user_input[CONF_USERNAME]}
                        else:
                            errors["base"] = 'login_error'
                    else:
                        errors["base"] = 'server_error'
            if info:
                return self.async_create_entry(title=info["title"], data=user_input)

        return self.async_show_form(
            step_id="user", data_schema=DATA_SCHEMA, errors=errors
        )

    async def async_step_import(self, user_input) -> FlowResult:
        """Handle import."""
        return await self.async_step_user(user_input)
