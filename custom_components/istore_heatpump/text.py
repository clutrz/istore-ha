from homeassistant.components.text import TextEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.helpers import device_registry as dr
from .const import DOMAIN
import logging

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass, entry, async_add_entities):
    """Set up iStore text entities."""
    data = hass.data[DOMAIN][entry.entry_id]
    api = data["api"]
    coordinator = data["coordinator"]

    async_add_entities([IStoreDeviceNameText(coordinator, api)])


class IStoreDeviceNameText(CoordinatorEntity, TextEntity):
    """Representation of the iStore Device Name as an editable text entity."""

    def __init__(self, coordinator, api):
        super().__init__(coordinator)
        self.api = api
        self._attr_name = "Device Name"
        self._attr_unique_id = f"istore_{api.mdm_id}_device_name"
        self._attr_icon = "mdi:rename-box"
        self.entity_id = f"text.istore_{api.mdm_id.lower()}_name"
        self._local_value = None

    @property
    def native_value(self):
        """Return the value reported by the text entity."""
        if self._local_value is not None:
            return self._local_value
        
        # Get data from arch_data
        arch_data = getattr(self.api, "arch_data", None)
        if arch_data and "data" in arch_data:
            struct = arch_data["data"]
            parent_id = self.api.parent_id
            if parent_id in struct:
                objects = struct[parent_id].get("mdmObjects", {})
                wh_list = objects.get("Res_WaterHeater", [])
                my_device = next((d for d in wh_list if d.get("mdmId") == self.api.mdm_id), None)
                if my_device and "attributes" in my_device:
                    return my_device["attributes"].get("name")
        
        return None

    @property
    def device_info(self):
        return self.api.device_info

    async def async_set_value(self, value: str) -> None:
        """Update the current value."""
        if not value:
            return

        try:
            # Update iStore
            await self.api.update_asset_name(value)
            self._local_value = value
            self.async_write_ha_state()

            # Update Device Registry
            dev_reg = dr.async_get(self.hass)
            device = dev_reg.async_get_device(identifiers={(DOMAIN, self.api.mdm_id)})
            if device:
                dev_reg.async_update_device(device.id, name=value)
            
            # Update local cache in api.arch_data
            arch_data = getattr(self.api, "arch_data", None)
            if arch_data and "data" in arch_data:
                struct = arch_data["data"]
                parent_id = self.api.parent_id
                if parent_id in struct:
                    objects = struct[parent_id].get("mdmObjects", {})
                    wh_list = objects.get("Res_WaterHeater", [])
                    my_device = next((d for d in wh_list if d.get("mdmId") == self.api.mdm_id), None)
                    if my_device and "attributes" in my_device:
                        my_device["attributes"]["name"] = value
            
        except Exception as e:
            _LOGGER.error("Failed to update device name: %s", e)
            raise
