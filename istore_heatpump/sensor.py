from homeassistant.components.sensor import SensorEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from .const import DOMAIN

SENSORS = {
    "work_mode": ("PUB_WH.WorkMode", None),
    "top_temperature": ("WH.TopTemp", "°C"),
    "bottom_temperature": ("WH.BottomTemp", "°C"),
    "target_temperature": ("WH.TargetTemp", "°C"),
    "target_temp_min": ("WH.TargetTempMin", "°C"),
    "target_temp_max": ("WH.TargetTempMax", "°C"),
    "ambient_temperature": ("PUB_WH.EnvirTemp", "°C"),
    "coil_temperature": ("PUB_WH.CoilTemp", "°C"),
    "suction_temperature": ("PUB_WH.SuctionTemp", "°C")
}

async def async_setup_entry(hass, entry, async_add_entities):
    """Set up iStore sensors."""
    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    api = hass.data[DOMAIN][entry.entry_id]["api"]

    entities = [
        IStoreSensor(coordinator, api, point, name, unit)
        for name, (point, unit) in SENSORS.items()
    ]
    # Add calculated hot water/shower remaining sensors
    entities.append(IStoreRemainingHotWaterSensor(coordinator, api, entry))
    entities.append(IStoreShowerTimeRemainingSensor(coordinator, api, entry))
    
    async_add_entities(entities, update_before_add=True)


class IStoreSensor(CoordinatorEntity, SensorEntity):
    """Representation of a single iStore sensor point."""

    def __init__(self, coordinator, api, key, name, unit):
        super().__init__(coordinator)
        self.api = api
        self.key = key

        # Display name in UI
        self._attr_name = name.replace("_", " ").title()

        # Unit
        self._attr_native_unit_of_measurement = unit

        # Unique ID
        safe_key = key.lower().replace(".", "_")
        safe_name = name.lower()
        self._attr_unique_id = f"istore_{api.mdm_id}_{safe_name}_{safe_key}"

        # Keep your custom entity_id
        self.entity_id = f"sensor.istore_{safe_name}"

    @property
    def device_info(self):
        return self.api.device_info

    @property
    def native_value(self):
        """Return the current sensor value."""
        data = self.coordinator.data
        if not data:
            return None

        try:
            value = data[self.api.mdm_id]["points"][self.key]["value"]
        except Exception:
            return None

        if self._attr_name.lower() == "work mode":
            if value == 0:
                return "Standby"
            elif value == 1:
                return "Heating"
            elif value == 2:
                return "Eco"
            elif value == 3:
                return "Hybrid"
            elif value == 4:
                return "Boost"
            else:
                return value   # fallback for unknown values

        return value


class IStoreRemainingHotWaterSensor(CoordinatorEntity, SensorEntity):
    """Calculated sensor showing remaining usable hot water at the configured tempering temperature."""

    def __init__(self, coordinator, api, entry):
        super().__init__(coordinator)
        self.api = api
        self.entry = entry
        self._attr_unique_id = f"istore_{api.mdm_id}_remaining_hot_water_50"
        self.entity_id = "sensor.istore_remaining_hot_water_at_50c"
        self._attr_native_unit_of_measurement = "L"
        self._attr_icon = "mdi:water-percent"

    @property
    def name(self):
        """Return the name of the sensor."""
        tempering_temp = self.entry.options.get("tempering_temp", 50)
        return f"Remaining Hot Water at {tempering_temp}°C"

    @property
    def device_info(self):
        return self.api.device_info

    @property
    def native_value(self):
        """Calculate the remaining hot water in Liters."""
        data = self.coordinator.data
        if not data or self.api.mdm_id not in data:
            return None

        try:
            points = data[self.api.mdm_id]["points"]
            top_temp = float(points["WH.TopTemp"]["value"])
            bottom_temp = float(points["WH.BottomTemp"]["value"])
        except Exception:
            return None

        # Retrieve cold water temp from options (default 15)
        cold_temp = self.entry.options.get("cold_water_temp", 15)
        
        # Output temperature tempered to target_temp
        target_temp = float(self.entry.options.get("tempering_temp", 50.0))
        avg_temp = (top_temp + bottom_temp) / 2.0

        if top_temp < target_temp:
            # If even the top of the tank is below target_temp, we cannot deliver tempered water at that temp
            return 0.0

        if bottom_temp >= target_temp:
            # Whole tank is hot
            liters = 270.0 * (avg_temp - cold_temp) / (target_temp - cold_temp)
        else:
            # Stratified tank: calculate height fraction of tank above target_temp
            div = top_temp - bottom_temp
            y = (top_temp - target_temp) / div if div > 0 else 1.0
            
            # Average temperature of the hot portion is between top_temp and target_temp
            hot_avg = (top_temp + target_temp) / 2.0
            
            # Tempered volume available from the hot portion
            liters = (270.0 * y) * (hot_avg - cold_temp) / (target_temp - cold_temp)
        
        return round(max(0.0, liters), 1)


class IStoreShowerTimeRemainingSensor(CoordinatorEntity, SensorEntity):
    """Calculated sensor showing estimated shower time remaining."""

    def __init__(self, coordinator, api, entry):
        super().__init__(coordinator)
        self.api = api
        self.entry = entry
        self._attr_name = "Estimated Shower Time Remaining"
        self._attr_unique_id = f"istore_{api.mdm_id}_shower_time_remaining"
        self.entity_id = "sensor.istore_estimated_shower_time_remaining"
        self._attr_native_unit_of_measurement = "min"
        self._attr_icon = "mdi:shower"

    @property
    def device_info(self):
        return self.api.device_info

    @property
    def native_value(self):
        """Calculate remaining shower time in minutes."""
        data = self.coordinator.data
        if not data or self.api.mdm_id not in data:
            return None

        try:
            points = data[self.api.mdm_id]["points"]
            top_temp = float(points["WH.TopTemp"]["value"])
            bottom_temp = float(points["WH.BottomTemp"]["value"])
        except Exception:
            return None

        # Retrieve options
        cold_temp = self.entry.options.get("cold_water_temp", 15)
        flow_rate = self.entry.options.get("shower_flow_rate", 9.0)
        shower_temp = float(self.entry.options.get("shower_temp", 40.0))
        
        avg_temp = (top_temp + bottom_temp) / 2.0

        if flow_rate <= 0 or top_temp < shower_temp:
            return 0.0

        if bottom_temp >= shower_temp:
            # Whole tank is hot enough
            minutes = (270.0 * (avg_temp - cold_temp)) / (flow_rate * (shower_temp - cold_temp))
        else:
            # Stratified tank: calculate height fraction of tank above shower_temp
            div = top_temp - bottom_temp
            y = (top_temp - shower_temp) / div if div > 0 else 1.0
            
            # Average temperature of the hot portion is between top_temp and shower_temp
            hot_avg = (top_temp + shower_temp) / 2.0
            
            # Time remaining is the usable energy in the hot portion
            minutes = (270.0 * y * (hot_avg - cold_temp)) / (flow_rate * (shower_temp - cold_temp))
        
        return round(max(0.0, minutes), 1)
