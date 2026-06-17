import asyncio
import logging

_LOGGER = logging.getLogger(__name__)

from homeassistant.components.switch import SwitchEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity

POWER_POINT = "WH.OnOff"
BOOSTER_POINT = "PUB_WH.Booster"


async def async_setup_entry(hass, entry, async_add_entities):
    data = hass.data["istore_heatpump"][entry.entry_id]
    api = data["api"]
    coordinator = data["coordinator"]

    entities = [
        IStorePowerSwitch(coordinator, api),
        IStoreBoosterSwitch(coordinator, api),
        IStoreTimerSwitch(coordinator, api, 1),
        IStoreTimerSwitch(coordinator, api, 2),
    ]

    async_add_entities(entities)


class BaseIStoreSwitch(CoordinatorEntity, SwitchEntity):
    """Base class for iStore switches."""

    control_point = None  # override
    name_suffix = None    # override

    def __init__(self, coordinator, api):
        super().__init__(coordinator)
        self.api = api
        self._attr_name = f"iStore {self.name_suffix}"
        safe_key = self.control_point.lower().replace(".", "_")
        self._attr_unique_id = f"istore_{api.mdm_id}_{safe_key}"

        # Force sensor ID to be nicer
        safe_name = self.name_suffix.lower().replace(" ", "_")
        self.entity_id = f"switch.istore_{safe_name}"

    @property
    def device_info(self):
        return self.api.device_info

    @property
    def is_on(self):
        """Check if switch is ON based on coordinator data."""
        data = self.coordinator.data
        if not data:
            return None

        try:
            value = data[self.api.mdm_id]["points"][self.control_point]["value"]

            # POWER (0/1)
            if self.control_point == POWER_POINT:
                return value == 1

            # BOOSTER (1=ON, 2=OFF)
            if self.control_point == BOOSTER_POINT:
                return value == 1

        except Exception:
            return None

    async def async_turn_on(self):
        """Turn switch on."""
        if self.control_point == POWER_POINT:
            await self.api.set_onoff("Power", 1)
        elif self.control_point == BOOSTER_POINT:
            await self.api.set_onoff("Booster", 1)

        await asyncio.sleep(12)
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self):
        """Turn switch off."""
        if self.control_point == POWER_POINT:
            await self.api.set_onoff("Power", 0)
        elif self.control_point == BOOSTER_POINT:
            await self.api.set_onoff("Booster", 2)

        await asyncio.sleep(12)
        await self.coordinator.async_request_refresh()


class IStorePowerSwitch(BaseIStoreSwitch):
    control_point = POWER_POINT
    name_suffix = "Power"


class IStoreBoosterSwitch(BaseIStoreSwitch):
    control_point = BOOSTER_POINT
    name_suffix = "Booster"


class IStoreTimerSwitch(CoordinatorEntity, SwitchEntity):
    """Switch to enable/disable Timer 1 or 2 schedule."""

    def __init__(self, coordinator, api, timer_num: int):
        super().__init__(coordinator)
        self.api = api
        self.timer_num = timer_num
        self._attr_name = f"iStore Timer {timer_num}"
        self._attr_unique_id = f"istore_{api.mdm_id}_timer{timer_num}_switch"
        self.entity_id = f"switch.istore_timer{timer_num}"

        self._on_point = f"PRI_RE_WH.Timer{timer_num}On"
        self._off_point = f"PRI_RE_WH.Timer{timer_num}Off"

    @property
    def device_info(self):
        return self.api.device_info

    @property
    def is_on(self):
        """Return true if the On timer is enabled."""
        data = self.coordinator.data
        if not data:
            return None

        try:
            on_val = data[self.api.mdm_id]["points"][self._on_point]["value"]
            return on_val == 1
        except Exception:
            return None

    async def async_turn_on(self):
        """Turn the timer schedule on."""
        try:
            # We set both the ON time and OFF time timer enabled flags to 1
            await self.api.async_write_timer_settings({
                self._on_point: 1,
                self._off_point: 1
            })

            # Optimistically update
            if self.coordinator.data and self.api.mdm_id in self.coordinator.data:
                self.coordinator.data[self.api.mdm_id]["points"][self._on_point]["value"] = 1
                self.coordinator.data[self.api.mdm_id]["points"][self._off_point]["value"] = 1
            self.async_write_ha_state()

            await asyncio.sleep(12)
            await self.coordinator.async_request_refresh()
        except Exception as e:
            _LOGGER.error("Failed to turn on timer %d: %s", self.timer_num, e)
            raise

    async def async_turn_off(self):
        """Turn the timer schedule off."""
        try:
            # We set both the ON time and OFF time timer enabled flags to 0
            await self.api.async_write_timer_settings({
                self._on_point: 0,
                self._off_point: 0
            })

            # Optimistically update
            if self.coordinator.data and self.api.mdm_id in self.coordinator.data:
                self.coordinator.data[self.api.mdm_id]["points"][self._on_point]["value"] = 0
                self.coordinator.data[self.api.mdm_id]["points"][self._off_point]["value"] = 0
            self.async_write_ha_state()

            await asyncio.sleep(12)
            await self.coordinator.async_request_refresh()
        except Exception as e:
            _LOGGER.error("Failed to turn off timer %d: %s", self.timer_num, e)
            raise
