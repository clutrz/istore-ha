from homeassistant.helpers.device_registry import DeviceInfo, CONNECTION_NETWORK_MAC, format_mac
from .const import DOMAIN, MANUFACTURER, CONFIG_PAGE
import logging

_LOGGER = logging.getLogger(__name__)

class IStoreDevice:
    """Simple wrapper that returns DeviceInfo for the heat pump."""
    def __init__(self, api, name: str = None):
        self.api = api
        self.name = name or "iStore Heat Pump"

    @property
    def device_info(self) -> DeviceInfo:
        """Return device registry information."""
        # Default values
        name = self.name
        modelId = None
        serial_number = None
        manufacturer = MANUFACTURER
        connections = None

        # Use attrib_data (Device Attributes) for Serial Number & Manufacturer Name
        attrib_data = getattr(self.api, "attrib_data", None)

        if attrib_data and "data" in attrib_data:
            _LOGGER.info(f"[DeviceInfo] attrib_data: {attrib_data}")
            attr_struct = attrib_data["data"]
            mdm_id = self.api.mdm_id
            
            if mdm_id in attr_struct:
                _LOGGER.info(f"[DeviceInfo] Found mdm_id: {mdm_id} in attributes")
                device_attrs = attr_struct[mdm_id]
                _LOGGER.info(f"[DeviceInfo] Attributes for {mdm_id}: {device_attrs}")

                if device_attrs.get("sn"):
                    serial_number = device_attrs.get("sn")
                
                if device_attrs.get("name"):
                    name = device_attrs.get("name")
                
                # Check for modelId, fallback to modelName if needed (though modelName is often empty)
                if device_attrs.get("modelId"):
                    modelId = device_attrs.get("modelId")
                elif device_attrs.get("modelName"):
                    modelId = device_attrs.get("modelName")

                if device_attrs.get("manufacturerName"):
                    manufacturer = device_attrs.get("manufacturerName")
                    
                if device_attrs.get("macCode"):
                    try:
                        formatted_mac = format_mac(device_attrs.get("macCode"))
                        connections = {(CONNECTION_NETWORK_MAC, formatted_mac)}
                    except Exception as e:
                        _LOGGER.warning(f"[DeviceInfo] Failed to format macCode: {device_attrs.get('macCode')}, error: {e}")
            else:
                _LOGGER.error(f"[DeviceInfo] mdm_id: {mdm_id} NOT FOUND in attr_struct keys: {list(attr_struct.keys())}")

        return DeviceInfo(
            identifiers={(DOMAIN, self.api.mdm_id)},
            manufacturer=manufacturer,
            name=name,
            model=modelId,
            serial_number=serial_number,
            connections=connections,
            via_device=None,
            configuration_url=CONFIG_PAGE,
        )
