from __future__ import annotations

import logging
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.exceptions import ConfigEntryNotReady

from .api import iStoreApi
from .coordinator import iStoreCoordinator
from .const import (DOMAIN, CONF_USERNAME, CONF_PASSWORD, CONF_ACCESS_TOKEN, CONF_PARENT_ID, CONF_MDM_ID)
from .device import IStoreDevice

_LOGGER = logging.getLogger(__name__)

PLATFORMS = ["sensor", "switch", "binary_sensor", "text", "time"]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Set up iStore Heat Pump."""
    username = entry.data[CONF_USERNAME]
    password = entry.data[CONF_PASSWORD]
    access_token = entry.data[CONF_ACCESS_TOKEN]
    parent_id = entry.data[CONF_PARENT_ID]
    mdm_id = entry.data[CONF_MDM_ID]

    api = iStoreApi(username, password, access_token, parent_id, mdm_id, hass)

    # Fetch device details (architecture) to populate DeviceInfo
    try:
        api.arch_data = await api.get_architecture()
    except Exception as e:
        _LOGGER.warning("Failed to fetch architecture for DeviceInfo: %s", e)
        api.arch_data = None

    # Fetch device details (attributes) to populate DeviceInfo
    try:
        api.attrib_data = await api.get_attributes()
    except Exception as e:
        _LOGGER.warning("Failed to fetch attributes for DeviceInfo: %s", e)
        api.attrib_data = None

    # Initialize device helper and attach device_info to api so entities can access it
    istore_device = IStoreDevice(api)
    api.device_info = istore_device.device_info

    coordinator = iStoreCoordinator(hass, api)

    # First refresh
    await coordinator.async_config_entry_first_refresh()

    # Store data
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {
        "api": api,
        "coordinator": coordinator,
        "device": istore_device,
    }

    # Load sensor, switch, binary_sensor, and text platforms
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Register update listener to reload integration when options/data change
    entry.async_on_unload(entry.add_update_listener(update_listener))

    return True


async def update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle options/data update."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_migrate_entry(hass: HomeAssistant, config_entry: ConfigEntry) -> bool:
    """Migrate old entry."""
    _LOGGER.warning(
        "Migrating config entry from version %s to %s is not possible because the new version requires your iStore username and password. Please delete and re-add the integration.",
        config_entry.version,
        2,
    )
    return False


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Unload iStore."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok
