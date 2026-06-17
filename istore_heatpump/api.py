from __future__ import annotations

import base64
import logging
import aiohttp

from cryptography.hazmat.primitives import serialization, hashes
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.backends import default_backend

_LOGGER = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────────────────
# Authentication helpers
# ──────────────────────────────────────────────────────────────────────────────

async def _get_public_key(session: aiohttp.ClientSession) -> tuple[str, str]:
    """Return (publicKey_b64, strategy) from the iStore public-key endpoint."""
    url = "https://home.istore.net.au/hossain-bff/framework/v1.0/user/public-key"
    async with session.get(url) as resp:
        body = await resp.json(content_type=None)
        if body.get("code") != 0:
            raise Exception(f"public-key API error: {body}")
        data = body["data"]
        return data["publicKey"], data["strategy"]


def _encrypt_password(public_key_b64: str, password: str) -> str:
    """Encrypt password with the server's RSA public key.

    iStore uses RSA OAEP with SHA-256 for BOTH the main hash and the MGF1 hash.
    """
    key_der = base64.b64decode(public_key_b64)
    public_key = serialization.load_der_public_key(key_der, backend=default_backend())
    encrypted = public_key.encrypt(
        password.encode("utf-8"),
        padding.OAEP(
            mgf=padding.MGF1(algorithm=hashes.SHA256()),
            algorithm=hashes.SHA256(),
            label=None,
        ),
    )
    return base64.b64encode(encrypted).decode("utf-8")


async def _login(
    session: aiohttp.ClientSession, strategy: str, username: str, encrypted_password: str
) -> tuple[str, str]:
    """POST /user/login — returns (access_token, org_id)."""
    url = "https://home.istore.net.au/hossain-bff/framework/v1.0/user/login"
    payload = {
        "strategy": strategy,
        "account": username,
        "password": encrypted_password,
    }
    async with session.post(url, json=payload) as resp:
        body = await resp.json(content_type=None)
        _LOGGER.debug("login response: %s", body)
        if body.get("code") != 0:
            raise Exception(f"login failed: {body.get('message', body)}")
        data = body["data"]
        access_token = data["accessToken"]
        org_id = data["organizations"][0]["id"]
        return access_token, org_id


async def _set_session(
    session: aiohttp.ClientSession, access_token: str, org_id: str
) -> str:
    """POST /user/set-session — returns companyId."""
    url = "https://home.istore.net.au/hossain-bff/framework/v1.0/user/set-session"
    headers = {"Authorization": f"Bearer {access_token}"}
    async with session.post(url, json={"orgId": org_id}, headers=headers) as resp:
        body = await resp.json(content_type=None)
        _LOGGER.debug("set-session response: %s", body)
        if body.get("code") != 0:
            raise Exception(f"set-session failed: {body.get('message', body)}")
        return body["data"]["companyId"]


async def _get_app_id(session: aiohttp.ClientSession, access_token: str) -> str:
    """GET /user/category/app/resource/list — extract appId for Univers_EMS in Smart Grid."""
    url = "https://home.istore.net.au/app-portal/web/v1/user/category/app/resource/list?basicType=0"
    headers = {"Authorization": f"Bearer {access_token}"}
    async with session.get(url, headers=headers) as resp:
        body = await resp.json(content_type=None)
        _LOGGER.debug("app/resource/list response: %s", body)
        if body.get("code") not in (0, 200):
            raise Exception(f"app resource list failed: {body.get('message', body)}")

        categories = body["data"]["categories"]
        for cat in categories:
            if cat.get("name") == "Smart Grid":
                for app in cat.get("apps", []):
                    if app.get("code") == "Univers_EMS":
                        return app["id"]
        raise Exception("Could not find Univers_EMS app under Smart Grid category")


async def _get_site_id(
    session: aiohttp.ClientSession, access_token: str, app_id: str
) -> str:
    """POST /user/app/asset/tree — extract siteId for 'Istore home owner' device."""
    url = (
        f"https://home.istore.net.au/app-portal/web/v1/user/app/asset/tree"
        f"?appId={app_id}&needAssociateAsset=true&resourceTypes=all"
    )
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }
    async with session.post(url, data="null", headers=headers) as resp:
        body = await resp.json(content_type=None)
        _LOGGER.debug("asset/tree response: %s", body)
        if body.get("code") not in (0, 200):
            raise Exception(f"asset tree failed: {body.get('message', body)}")

        for top_child in body["data"].get("children", []):
            for mid_child in top_child.get("children", []):
                if mid_child.get("name") == "Istore home owner":
                    for leaf in mid_child.get("children", []):
                        site_id = leaf.get("id")
                        if site_id:
                            return site_id
        raise Exception("Could not find site under 'Istore home owner'")


async def _get_device_id(
    session: aiohttp.ClientSession, access_token: str, site_id: str
) -> str:
    """POST /asset-hierarchy — extract mdmId for Res_WaterHeater under the given siteId."""
    url = "https://home.istore.net.au/encompassbffservice/encompass-bff/asset-service/v1.0/asset-hierarchy"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/x-www-form-urlencoded",
    }
    payload = (
        f"mdmIds={site_id}&mdmTypes=Res_WaterHeater"
        "&attributes=name%2CmdmType&locale=en-US"
    )
    async with session.post(url, data=payload, headers=headers) as resp:
        body = await resp.json(content_type=None)
        _LOGGER.debug("asset-hierarchy response: %s", body)
        if body.get("code") != 10000:
            raise Exception(f"asset hierarchy failed: {body.get('msg', body)}")

        site_data = body["data"].get(site_id, {})
        wh_list = site_data.get("mdmObjects", {}).get("Res_WaterHeater", [])
        if not wh_list:
            raise Exception(f"No Res_WaterHeater device found under site {site_id}")
        return wh_list[0]["mdmId"]


# ──────────────────────────────────────────────────────────────────────────────
# Public auth entry-point
# ──────────────────────────────────────────────────────────────────────────────

async def authenticate(username: str, password: str) -> dict:
    """
    Full login flow.

    Returns a dict with keys:
        access_token, parent_id (siteId), mdm_id (device mdmId)
    """
    async with aiohttp.ClientSession() as session:
        # 1. Get public key
        pub_key_b64, strategy = await _get_public_key(session)

        # 2. Encrypt password
        encrypted_pw = _encrypt_password(pub_key_b64, password)

        # 3. Login
        access_token, org_id = await _login(session, strategy, username, encrypted_pw)

        # 4. Set session
        await _set_session(session, access_token, org_id)

        # 5. Get App ID
        app_id = await _get_app_id(session, access_token)
        _LOGGER.debug("Univers_EMS appId: %s", app_id)

        # 6. Get site ID / parent ID
        parent_id = await _get_site_id(session, access_token, app_id)
        _LOGGER.debug("site_id (parent_id): %s", parent_id)

        # 7. Get device mdmId
        mdm_id = await _get_device_id(session, access_token, parent_id)
        _LOGGER.debug("device mdm_id: %s", mdm_id)

    return {
        "access_token": access_token,
        "parent_id": parent_id,
        "mdm_id": mdm_id,
    }


# ──────────────────────────────────────────────────────────────────────────────
# API client
# ──────────────────────────────────────────────────────────────────────────────

class iStoreApi:
    def __init__(self, username: str, password: str, access_token: str, parent_id: str, mdm_id: str, hass):
        self.username = username
        self.password = password
        self.access_token = access_token
        self.parent_id = parent_id
        self.mdm_id = mdm_id
        self.hass = hass
        
        # Placeholders for device info populated on setup
        self.arch_data = None
        self.attrib_data = None
        self.device_info = None

    async def re_authenticate(self):
        """Re-run the full auth flow and refresh stored credentials."""
        _LOGGER.info("iStore: re-authenticating...")
        creds = await authenticate(self.username, self.password)
        self.access_token = creds["access_token"]
        self.parent_id = creds["parent_id"]
        self.mdm_id = creds["mdm_id"]
        _LOGGER.info("iStore: re-authentication successful")

        # Update ConfigEntry data so the updated credentials persist
        # (Needed so that username/password changes stay persistent on disk)
        from homeassistant.config_entries import ConfigEntry
        entries = self.hass.config_entries.async_entries(self.hass.data.get("istore_heatpump", {}))
        for entry in entries:
            if entry.data.get("mdm_id") == self.mdm_id:
                self.hass.config_entries.async_update_entry(
                    entry,
                    data={
                        **entry.data,
                        "access_token": self.access_token,
                        "parent_id": self.parent_id,
                        "mdm_id": self.mdm_id,
                    }
                )

    # -------------------------------------------------------------------------
    # Asset hierarchy (used during config validation)
    # -------------------------------------------------------------------------
    async def get_architecture(self):
        url = "https://home.istore.net.au/encompassbffservice/encompass-bff/asset-service/v1.0/asset-hierarchy"

        payload = {
            "mdmIds": self.parent_id,
            "mdmTypes": "Res_WaterHeater",
            "attributes": "name,mdmType",
            "locale": "en-US",
        }

        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/x-www-form-urlencoded",
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, data=payload) as resp:
                if resp.status == 401:
                    _LOGGER.warning("iStore 401 on architecture - re-authenticating")
                    await self.re_authenticate()
                    headers["Authorization"] = f"Bearer {self.access_token}"
                    async with session.post(url, headers=headers, data=payload) as retry:
                        if retry.status != 200:
                            raise Exception(f"iStore hierarchy API failed after re-auth: {retry.status}")
                        return await retry.json(content_type=None)

                if resp.status != 200:
                    raise Exception(f"iStore hierarchy API failed: {resp.status}")

                return await resp.json(content_type=None)

    # -------------------------------------------------------------------------
    # Read device attributes (DeviceState,modelName,name,sn,manufacturerName,macCode)
    # -------------------------------------------------------------------------
    async def get_attributes(self):
        url = (
            "https://home.istore.net.au/encompassbffservice/"
            "encompass-bff/anti-timeseries/v1.0/attributes?"
            "attributes=DeviceState,modelName,name,sn,manufacturerName,macCode"
        )

        payload = {
            "withI18n": "true",
            "mdmIds": self.mdm_id,
            "locale": "en-US",
        }

        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/x-www-form-urlencoded",
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, data=payload) as resp:
                if resp.status == 401:
                    _LOGGER.warning("iStore 401 on attributes - re-authenticating")
                    await self.re_authenticate()
                    headers["Authorization"] = f"Bearer {self.access_token}"
                    async with session.post(url, headers=headers, data=payload) as retry:
                        if retry.status != 200:
                            raise Exception(f"iStore attributes API failed after re-auth: {retry.status}")
                        return await retry.json(content_type=None)

                if resp.status != 200:
                    raise Exception(f"iStore attributes API failed: {resp.status}")

                return await resp.json(content_type=None)

    # -------------------------------------------------------------------------
    # Read measurement points (temperatures, compressor, on/off, timers)
    # -------------------------------------------------------------------------
    async def get_measurements(self):
        url = (
            "https://home.istore.net.au/encompassbffservice/"
            "encompass-bff/anti-timeseries/v1.0/measurement-points"
        )

        POINTS = [
            "WH.OnOff",
            "WH.TargetTemp",
            "WH.TopTemp",
            "WH.BottomTemp",
            "PUB_WH.CompressorStatus",
            "PUB_WH.EnvirTemp",
            "PUB_WH.SuctionTemp",
            "PUB_WH.CoilTemp",
            "PUB_WH.Booster",
            "PRI_RE_WH.Timer1On",
            "PRI_RE_WH.Timer1OnTime",
            "PRI_RE_WH.Timer1Off",
            "PRI_RE_WH.Timer1OffTime",
            "PRI_RE_WH.Timer2On",
            "PRI_RE_WH.Timer2OnTime",
            "PRI_RE_WH.Timer2Off",
            "PRI_RE_WH.Timer2OffTime",
            "PUB_WH.WorkMode",
            "WH.TargetTempMin",
            "WH.TargetTempMax",
            "PUB_WH.4WayStatus",
            "PUB_WH.FanSpeed",
            "PUB_WH.DefrostStatus",
        ]

        payload = f"mdmIds={self.mdm_id}&pointIds=" + ",".join(POINTS)

        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, data=payload) as resp:
                if resp.status == 401:
                    _LOGGER.warning("iStore 401 on measurements - re-authenticating")
                    await self.re_authenticate()
                    headers["Authorization"] = f"Bearer {self.access_token}"
                    async with session.post(url, headers=headers, data=payload) as retry:
                        if retry.status != 200:
                            _LOGGER.error("iStore measurement API returned %s after re-auth", retry.status)
                            return None
                        return await retry.json(content_type=None)

                if resp.status != 200:
                    _LOGGER.error("iStore measurement API returned %s", resp.status)
                    return None

                return await resp.json(content_type=None)

    # -------------------------------------------------------------------------
    # Control (On / Off / Booster)
    # -------------------------------------------------------------------------
    async def set_onoff(self, point, value):
        """Control WH.OnOff or PUB_WH.Booster."""
        url = "https://home.istore.net.au/hossain-bff/connect/v1.0/device/control"

        if point == "Power":
            control_point = "WH.OnOff"
        elif point == "Booster":
            control_point = "PUB_WH.Booster"
        else:
            return

        payload = [
            {
                "assetId": self.mdm_id,
                "controlPointId": control_point,
                "value": value,
            }
        ]

        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }

        _LOGGER.debug("Sending iStore control request to %s: %s", url, payload)
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, json=payload) as resp:
                if resp.status == 401:
                    _LOGGER.warning("iStore 401 on control - re-authenticating")
                    await self.re_authenticate()
                    headers["Authorization"] = f"Bearer {self.access_token}"
                    async with session.post(url, headers=headers, json=payload) as retry:
                        res_json = await retry.json(content_type=None)
                        _LOGGER.debug("iStore control retry response: %s", res_json)
                        if res_json.get("code") not in [0, 10000, 200]:
                            raise Exception(f"Control failed: {res_json}")
                        return res_json
                
                res_json = await resp.json(content_type=None)
                _LOGGER.debug("iStore control response: %s", res_json)
                if res_json.get("code") not in [0, 10000, 200]:
                    raise Exception(f"Control failed: {res_json}")
                return res_json

    # -------------------------------------------------------------------------
    # Timer control
    # -------------------------------------------------------------------------
    async def set_timers_batch(self, timer_settings: dict):
        """Set all timer parameters together in a single batch request."""
        url = "https://home.istore.net.au/hossain-bff/connect/v1.0/device/control"
        
        payload = []
        for point_id, value in timer_settings.items():
            payload.append({
                "assetId": self.mdm_id,
                "controlPointId": point_id,
                "value": value
            })

        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }
        
        _LOGGER.debug("Sending iStore batch timer request to %s: %s", url, payload)
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, json=payload) as resp:
                if resp.status == 401:
                    _LOGGER.warning("iStore 401 on batch timer - re-authenticating")
                    await self.re_authenticate()
                    headers["Authorization"] = f"Bearer {self.access_token}"
                    async with session.post(url, headers=headers, json=payload) as retry:
                        res_json = await retry.json(content_type=None)
                        _LOGGER.debug("iStore batch timer retry response: %s", res_json)
                        if res_json.get("code") not in [0, 10000, 200]:
                            raise Exception(f"Batch timer update failed: {res_json}")
                        return res_json
                
                res_json = await resp.json(content_type=None)
                _LOGGER.debug("iStore batch timer response: %s", res_json)
                if res_json.get("code") not in [0, 10000, 200]:
                    raise Exception(f"Batch timer update failed: {res_json}")
                return res_json

    async def async_write_timer_settings(self, updates: dict):
        """Read all timer points from coordinator, apply a dictionary of updates, and write as a batch."""
        from .const import DOMAIN
        
        coordinator = None
        if self.hass and DOMAIN in self.hass.data:
            for entry_id, entry_data in self.hass.data[DOMAIN].items():
                if entry_data.get("api") == self:
                    coordinator = entry_data.get("coordinator")
                    break

        if not coordinator or not coordinator.data:
            raise Exception("Coordinator data not available to build timer batch")

        timer_points = [
            "PRI_RE_WH.Timer1On",
            "PRI_RE_WH.Timer1OnTime",
            "PRI_RE_WH.Timer1Off",
            "PRI_RE_WH.Timer1OffTime",
            "PRI_RE_WH.Timer2On",
            "PRI_RE_WH.Timer2OnTime",
            "PRI_RE_WH.Timer2Off",
            "PRI_RE_WH.Timer2OffTime",
            "PUB_WH.WorkMode",
        ]
        
        batch_settings = {}
        points_data = coordinator.data.get(self.mdm_id, {}).get("points", {})
        
        for p in timer_points:
            val = points_data.get(p, {}).get("value")
            
            if val is None:
                if p.endswith("Time"):
                    val = "00:00"
                elif p == "PUB_WH.WorkMode":
                    val = 3
                else:
                    val = 0
            
            if not p.endswith("Time"):
                try:
                    val = int(val)
                except Exception:
                    val = 3 if p == "PUB_WH.WorkMode" else 0
            else:
                val = str(val)
                
            batch_settings[p] = val

        # Apply updates
        for point_id, value in updates.items():
            if not point_id.endswith("Time"):
                try:
                    batch_settings[point_id] = int(value)
                except Exception:
                    batch_settings[point_id] = 3 if point_id == "PUB_WH.WorkMode" else 0
            else:
                batch_settings[point_id] = str(value)

        # Write the batch
        return await self.set_timers_batch(batch_settings)

    # -------------------------------------------------------------------------
    # Update Asset Name
    # -------------------------------------------------------------------------
    async def update_asset_name(self, name):
        """Update the asset name on the iStore server."""
        url = "https://home.istore.net.au/hossain-bff/monitor/v1.0/asset/update"
        payload = {
            "assetId": self.mdm_id,
            "name": name
        }

        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, json=payload) as resp:
                if resp.status == 401:
                    _LOGGER.warning("iStore 401 on asset update - re-authenticating")
                    await self.re_authenticate()
                    headers["Authorization"] = f"Bearer {self.access_token}"
                    async with session.post(url, headers=headers, json=payload) as retry:
                        if retry.status != 200:
                            raise Exception(f"Failed to update asset name after re-auth: {retry.status}")
                        res_json = await retry.json(content_type=None)
                        if res_json.get("code") not in [0, 10000]:
                            raise Exception(f"Update failed with code: {res_json.get('code')}")
                        return True

                if resp.status != 200:
                    raise Exception(f"Failed to update asset name: {resp.status}")
                
                res_json = await resp.json(content_type=None)
                if res_json.get("code") not in [0, 10000]:
                    raise Exception(f"Update failed with code: {res_json.get('code')}")
                     
                return True
