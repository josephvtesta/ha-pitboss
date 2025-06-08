"""
Custom integration to integrate PitBoss grills and smokers with Home Assistant.

For more details about this integration, please refer to
https://github.com/dknowles2/ha-pitboss
"""

import json
import base64
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_DEVICE_ID, CONF_MODEL, CONF_PASSWORD, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.device_registry import DeviceInfo
from pytboss.api import PitBoss
from pytboss.wss import WebSocketConnection

from .const import DOMAIN, LOGGER, MANUFACTURER
from .coordinator import PitBossDataUpdateCoordinator

PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.CLIMATE,
    Platform.LIGHT,
    Platform.SENSOR,
    Platform.SWITCH,
]


def _convert_bytes_for_json(obj):
    """Recursively convert bytes objects to base64 strings for JSON serialization."""
    if isinstance(obj, bytes):
        return base64.b64encode(obj).decode('ascii')
    elif isinstance(obj, dict):
        return {key: _convert_bytes_for_json(value) for key, value in obj.items()}
    elif isinstance(obj, list):
        return [_convert_bytes_for_json(value) for value in obj]
    return obj


# Store the original json.dumps
_original_json_dumps = json.dumps


def _bytes_safe_json_dumps(obj, **kwargs):
    """JSON dumps that safely handles bytes objects."""
    try:
        # First try the original dumps
        return _original_json_dumps(obj, **kwargs)
    except TypeError as e:
        if "not JSON serializable" in str(e) and "bytes" in str(e):
            # If it's a bytes serialization error, convert and try again
            LOGGER.debug("Converting bytes objects for JSON serialization")
            converted_obj = _convert_bytes_for_json(obj)
            return _original_json_dumps(converted_obj, **kwargs)
        else:
            # Re-raise if it's a different error
            raise


# Apply the monkey patch
json.dumps = _bytes_safe_json_dumps


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up this integration using UI."""
    hass.data.setdefault(DOMAIN, {})
    device_id = entry.data[CONF_DEVICE_ID]
    model = entry.data[CONF_MODEL]
    password = entry.data.get(CONF_PASSWORD, "")
    
    conn = WebSocketConnection(
        device_id, session=async_get_clientsession(hass), loop=hass.loop
    )
    
    api = PitBoss(conn, model, password=password)
    device_info = DeviceInfo(
        identifiers={(DOMAIN, device_id)},
        name=device_id,
        model=model,
        manufacturer=MANUFACTURER,
    )
    hass.data[DOMAIN][entry.entry_id] = coordinator = PitBossDataUpdateCoordinator(
        hass, device_info, api
    )
    
    await coordinator.async_config_entry_first_refresh()
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Handle removal of an entry."""
    if unloaded := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        coordinator: PitBossDataUpdateCoordinator = hass.data[DOMAIN].pop(
            entry.entry_id
        )
        await coordinator.api.stop()
    return unloaded
