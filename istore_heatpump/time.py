from datetime import time
import logging
import asyncio

from homeassistant.components.time import TimeEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

TIMERS = {
    "timer1_start": ("PRI_RE_WH.Timer1OnTime", "Timer 1 Start"),
    "timer1_end": ("PRI_RE_WH.Timer1OffTime", "Timer 1 End"),
    "timer2_start": ("PRI_RE_WH.Timer2OnTime", "Timer 2 Start"),
    "timer2_end": ("PRI_RE_WH.Timer2OffTime", "Timer 2 End"),
}

async def async_setup_entry(hass, entry, async_add_entities):
    """Set up iStore time entities."""
    data = hass.data[DOMAIN][entry.entry_id]
    coordinator = data["coordinator"]
    api = data["api"]

    entities = [
        IStoreTimeEntity(coordinator, api, point, name)
        for key, (point, name) in TIMERS.items()
    ]
    async_add_entities(entities)


class IStoreTimeEntity(CoordinatorEntity, TimeEntity):
    """Representation of an iStore time entity."""

    def __init__(self, coordinator, api, point, name):
        super().__init__(coordinator)
        self.api = api
        self.point = point
        self._attr_name = name
        self._attr_unique_id = f"istore_{api.mdm_id}_{point.lower().replace('.', '_')}"
        self.entity_id = f"time.istore_{name.lower().replace(' ', '_')}"

    @property
    def device_info(self):
        return self.api.device_info

    @property
    def native_value(self) -> time | None:
        """Return the value of the time."""
        data = self.coordinator.data
        if not data:
            return None

        val_str = None
        try:
            val_str = data[self.api.mdm_id]["points"][self.point]["value"]
            if not val_str:
                return None
            # Parse "HH:MM" string
            parts = val_str.split(":")
            if len(parts) >= 2:
                return time(hour=int(parts[0]), minute=int(parts[1]))
        except Exception as e:
            _LOGGER.error("Error parsing time value %s for %s: %s", val_str, self.point, e)
            return None

    async def async_set_value(self, value: time) -> None:
        """Set the time."""
        time_str = value.strftime("%H:%M")
        _LOGGER.info("Setting iStore time point %s to %s", self.point, time_str)
        try:
            await self.api.async_write_timer_settings({self.point: time_str})
            # Optimistically update the coordinator local state so UI updates immediately
            if self.coordinator.data and self.api.mdm_id in self.coordinator.data:
                self.coordinator.data[self.api.mdm_id]["points"][self.point]["value"] = time_str
            self.async_write_ha_state()
            
            # Request refresh after a delay to match the physical update cycle
            await asyncio.sleep(12)
            await self.coordinator.async_request_refresh()
        except Exception as e:
            _LOGGER.error("Failed to set time point %s to %s: %s", self.point, time_str, e)
            raise
