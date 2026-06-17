from homeassistant.helpers.entity import Entity
from .const import DOMAIN

class IStoreEntity(Entity):
    """Base class that links an entity to the heat pump device."""
    def __init__(self, hass, api, point):
        self.hass = hass
        self.api = api
        self.point = point

    @property
    def device_info(self):
        # the device object is stored per entry; we retrieve it here
        if DOMAIN in self.hass.data and self.api.mdm_id in self.hass.data[DOMAIN]:
            return self.hass.data[DOMAIN][self.api.mdm_id].get("device").device_info
        return self.api.device_info
