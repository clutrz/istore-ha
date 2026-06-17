from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from .const import DOMAIN

BINARY_SENSORS = {
    "running_state": ("WH.OnOff", None),
    "booster": ("PUB_WH.Booster", None),
    "compressor_status": ("PUB_WH.CompressorStatus", None),
    "4_way_status": ("PUB_WH.4WayStatus", None),
    "fan_status": ("PUB_WH.FanSpeed", None),
    "defrost_status": ("PUB_WH.DefrostStatus", None)
}

async def async_setup_entry(hass, entry, async_add_entities):
    """Set up iStore binary sensors."""
    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    api = hass.data[DOMAIN][entry.entry_id]["api"]

    entities = [
        IStoreBinarySensor(coordinator, api, point, name, unit)
        for name, (point, unit) in BINARY_SENSORS.items()
    ]
    async_add_entities(entities, update_before_add=True)


class IStoreBinarySensor(CoordinatorEntity, BinarySensorEntity):
    """Representation of a single iStore binary sensor point."""

    def __init__(self, coordinator, api, key, name, unit):
        super().__init__(coordinator)
        self.api = api
        self.key = key
        self.unit = unit

        # Display name in UI
        self._attr_name = name.replace("_", " ").title()

        # Unique ID
        safe_key = key.lower().replace(".", "_")
        safe_name = name.lower()
        self._attr_unique_id = f"istore_{api.mdm_id}_{safe_name}_{safe_key}"
        
        # Entity ID
        self.entity_id = f"binary_sensor.istore_{safe_name}"

    @property
    def device_info(self):
        return self.api.device_info

    @property
    def is_on(self):
        """Return true if the binary sensor is on."""
        data = self.coordinator.data
        if not data:
            return None

        try:
            value = data[self.api.mdm_id]["points"][self.key]["value"]
        except Exception:
            return None
        
        # Special logic for some sensors
        # Booster: 1 is On, 2 is Off (based on sensor.py logic)
        if self._attr_name.lower() == "booster":
            if value == 1:
                return True
            if value == 2:
                return False
            return None

        # Default logic: 1 is On
        if value == 1:
            return True
        if value == 0:
            return False
            
        return bool(value)
