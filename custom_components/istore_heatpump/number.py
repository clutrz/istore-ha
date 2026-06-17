import asyncio

from homeassistant.components.number import NumberEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity

DOMAIN = "istore_heatpump"

TARGET_MIN = "WH.TargetTempMin"
TARGET_MAX = "WH.TargetTempMax"
TARGET_SET = "WH.TargetTemp"


async def async_setup_entry(hass, entry, async_add_entities):
    return  # disable all number entities (TargetTemp, Min, Max)
    
    # data = hass.data[DOMAIN][entry.entry_id]
    # coordinator = data["coordinator"]
    # api = data["api"]

    # entities = [
    #     IStoreTargetTemperature(coordinator, api),
    #     IStoreTargetMin(coordinator, api),
    #     IStoreTargetMax(coordinator, api)
    # ]

    # async_add_entities(entities)


# -------------------------------------------------------
# 1. TARGET TEMPERATURE
# -------------------------------------------------------
class IStoreTargetTemperature(CoordinatorEntity, NumberEntity):
    _attr_name = "iStore Target Temperature"
    _attr_icon = "mdi:thermometer"
    _attr_native_unit_of_measurement = "°C"
    _attr_native_step = 1

    def __init__(self, coordinator, api):
        super().__init__(coordinator)
        self.api = api
        self._attr_unique_id = f"istore_{api.mdm_id}_target_temperature"

    @property
    def native_value(self):
        return self.coordinator.data[self.api.mdm_id]["points"][TARGET_SET]["value"]

    @property
    def min_value(self):
        """Dynamic: min temp = current device min temp."""
        return self.coordinator.data[self.api.mdm_id]["points"][TARGET_MIN]["value"]

    @property
    def max_value(self):
        """Dynamic: max temp = current device max temp."""
        return self.coordinator.data[self.api.mdm_id]["points"][TARGET_MAX]["value"]

    async def async_set_native_value(self, value: float):
        minv = self.min_value
        maxv = self.max_value

        if not (minv <= value <= maxv):
            raise ValueError(f"Target temperature must be between {minv}°C and {maxv}°C")

        await self.api.set_target_temperature(int(value))
        await asyncio.sleep(12)
        await self.coordinator.async_request_refresh()


# -------------------------------------------------------
# 2. MINIMUM TARGET TEMPERATURE
# -------------------------------------------------------
class IStoreTargetMin(CoordinatorEntity, NumberEntity):
    _attr_name = "iStore Target Temperature Min"
    _attr_icon = "mdi:thermometer-low"
    _attr_native_unit_of_measurement = "°C"
    _attr_native_step = 1

    def __init__(self, coordinator, api):
        super().__init__(coordinator)
        self.api = api
        self._attr_unique_id = f"istore_{api.mdm_id}_target_temp_min"

    @property
    def native_value(self):
        return self.coordinator.data[self.api.mdm_id]["points"][TARGET_MIN]["value"]

    @property
    def min_value(self):
        """Device allows as low as 10°C."""
        return 10

    @property
    def max_value(self):
        """Min temp must be strictly lower than max temp."""
        max_temp = self.coordinator.data[self.api.mdm_id]["points"][TARGET_MAX]["value"]
        return max_temp - 1

    async def async_set_native_value(self, value: float):
        max_allowed = self.max_value

        if value >= max_allowed:
            raise ValueError(f"Min temp must be < {max_allowed}°C")

        await self.api.set_target_min(int(value))
        await asyncio.sleep(12)
        await self.coordinator.async_request_refresh()


# -------------------------------------------------------
# 3. MAXIMUM TARGET TEMPERATURE
# -------------------------------------------------------
class IStoreTargetMax(CoordinatorEntity, NumberEntity):
    _attr_name = "iStore Target Temperature Max"
    _attr_icon = "mdi:thermometer-high"
    _attr_native_unit_of_measurement = "°C"
    _attr_native_step = 1

    def __init__(self, coordinator, api):
        super().__init__(coordinator)
        self.api = api
        self._attr_unique_id = f"istore_{api.mdm_id}_target_temp_max"

    @property
    def native_value(self):
        return self.coordinator.data[self.api.mdm_id]["points"][TARGET_MAX]["value"]

    @property
    def min_value(self):
        """Max temp must always be > min temp."""
        min_temp = self.coordinator.data[self.api.mdm_id]["points"][TARGET_MIN]["value"]
        return min_temp + 1

    @property
    def max_value(self):
        """Device allows up to 75°C."""
        return 75

    async def async_set_native_value(self, value: float):
        min_allowed = self.min_value

        if value <= min_allowed:
            raise ValueError(f"Max temp must be > {min_allowed}°C")

        await self.api.set_target_max(int(value))
        await asyncio.sleep(12)
        await self.coordinator.async_request_refresh()
