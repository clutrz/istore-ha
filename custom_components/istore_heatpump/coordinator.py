from datetime import timedelta
import logging
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

_LOGGER = logging.getLogger(__name__)

class iStoreCoordinator(DataUpdateCoordinator):
    def __init__(self, hass, api):
        self.api = api

        super().__init__(
            hass,
            _LOGGER,
            name="iStore Heat Pump",
            update_interval=timedelta(seconds=30),
        )

    async def _async_update_data(self):
        """Fetch latest data from iStore API."""
        try:
            data = await self.api.get_measurements()
            if data is None:
                raise UpdateFailed("Failed to fetch measurements: API returned an empty or invalid response (HTTP error or connection failure).")
            
            if not isinstance(data, dict) or "data" not in data:
                # Log the actual response structure to help diagnose auth/API errors
                _LOGGER.error("iStore API returned unexpected response format: %s", data)
                raise UpdateFailed(f"Failed to fetch measurements: response does not contain 'data' key. Response: {data}")

            return data["data"]  # the dict keyed by mdm_id
        except UpdateFailed:
            raise
        except Exception as e:
            _LOGGER.error("iStore update failed: %s", e)
            raise UpdateFailed(f"Unexpected error updating iStore data: {e}")

