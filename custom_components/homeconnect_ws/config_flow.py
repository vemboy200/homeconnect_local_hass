"""Config flow."""

from __future__ import annotations

import json
import logging
import random
import re
from asyncio import Event, wait_for
from binascii import Error as BinasciiError
from copy import deepcopy
from datetime import timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast
from zipfile import ZipFile

import homeassistant.helpers.config_validation as cv
import voluptuous as vol
from aiohttp import ClientConnectionError, ClientConnectorSSLError
from home_disconnect import (
    ConnectionFailedError,
    ConnectionState,
    HomeAppliance,
    ParserError,
    parse_device_description,
)
from homeassistant.components.file_upload import process_uploaded_file
from homeassistant.components.http.auth import async_sign_path
from homeassistant.config_entries import SOURCE_IGNORE, ConfigFlow, OptionsFlow
from homeassistant.const import (
    CONF_DESCRIPTION,
    CONF_DEVICE,
    CONF_DEVICE_ID,
    CONF_HOST,
    CONF_MODE,
    CONF_NAME,
)
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.network import get_url
from homeassistant.helpers.selector import (
    FileSelector,
    FileSelectorConfig,
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
)

from . import HC_KEY, HCConfig
from .const import (
    CONF_AES_IV,
    CONF_FILE,
    CONF_MANUAL_HOST,
    CONF_PSK,
    CONF_REGION,
    DOMAIN,
    AppliancePayload,
)
from .export_profile import build_profile_zip, filename_stub
from .hc_cloud_api import REGION_ASSET_BASE, HCCloudApiError, async_fetch_appliances
from .hc_legacy_oauth import HCLegacyOAuthError
from .hc_legacy_oauth import async_exchange_code_for_token as legacy_async_exchange_code_for_token
from .hc_legacy_oauth import build_authorize_url as legacy_build_authorize_url
from .hc_legacy_oauth import extract_code_from_redirect as legacy_extract_code_from_redirect
from .hc_legacy_oauth import generate_code_verifier as legacy_generate_code_verifier
from .hc_legacy_oauth import generate_state as legacy_generate_state

CONF_LEGACY_REDIRECT_URL = "legacy_redirect_url"

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigFlowResult
    from homeassistant.helpers.service_info.zeroconf import ZeroconfServiceInfo

    from . import HCConfigEntry

_LOGGER = logging.getLogger(__name__)

CONFIG_FILE_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_FILE): FileSelector(config=FileSelectorConfig(accept=".zip")),
    }
)
CONFIG_FILE_SCHEMA_JSON = vol.Schema(
    {
        vol.Required(CONF_FILE): FileSelector(config=FileSelectorConfig(accept=".zip,.json")),
    }
)
CONFIG_HOST_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): cv.string,
    }
)
REGION_LABELS = {"EU": "Europe", "NA": "North America", "CN": "China"}
CONFIG_REGION_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_REGION, default="EU"): SelectSelector(
            SelectSelectorConfig(
                options=[
                    SelectOptionDict(value=region, label=REGION_LABELS[region])
                    for region in REGION_ASSET_BASE
                ]
            )
        ),
    }
)


def process_zip_file(config_path: Path) -> dict[str, AppliancePayload]:
    """Process uploaded zip file."""
    profile_file = ZipFile(config_path)

    appliances: dict[str, AppliancePayload] = {}
    re_info = re.compile(".*.json$")
    infolist = profile_file.infolist()
    for file in infolist:
        if re_info.match(file.filename):
            appliance_info = json.load(profile_file.open(file))

            description_file_name = appliance_info["deviceDescriptionFileName"]
            feature_file_name = appliance_info["featureMappingFileName"]
            description_file = profile_file.open(description_file_name).read()
            feature_file = profile_file.open(feature_file_name).read()

            # home_disconnect's parse_device_description() is typed as
            # str | TextIO, but it just forwards to xmltodict.parse(), which
            # also accepts bytes (as returned by ZipFile.open().read() here).
            appliance_description = parse_device_description(
                cast("str", description_file), cast("str", feature_file)
            )
            appliances[appliance_info["haId"]] = {
                "info": appliance_info,
                "description": appliance_description,
            }
            _LOGGER.debug("Found Appliance %s", appliance_info["vib"])
    return appliances


def process_json_file(config_path: Path) -> dict[str, AppliancePayload]:
    """Process uploaded json file."""
    with config_path.open() as file:
        entry_data = json.load(file)
    return {"config_entry": entry_data["data"]["entry_data"]}


class HomeConnectConfigFlow(ConfigFlow, domain=DOMAIN):
    """HomeConnect Config flow."""

    @staticmethod
    def async_get_options_flow(config_entry: HCConfigEntry) -> HCOptionsFlowHandler:
        """Get the options flow for this handler."""
        return HCOptionsFlowHandler(config_entry)

    def __init__(self) -> None:
        super().__init__()
        self.errors: dict[str, str] = {}
        self.data: dict[str, Any] = {}
        self.appliances: dict[str, AppliancePayload] = {}
        self.reauth_entry: HCConfigEntry | None = None
        self.global_config: HCConfig | None = None
        self._region: str = "EU"
        self._legacy_code_verifier: str | None = None
        self._legacy_state: str | None = None

    def _process_profile_file(
        self, uploaded_file_id: str
    ) -> dict[str, AppliancePayload]:
        with process_uploaded_file(self.hass, uploaded_file_id) as config_path:
            if config_path.suffix == ".zip":
                return process_zip_file(config_path)
            if config_path.suffix == ".json":
                return process_json_file(config_path)
            msg = "Unexpected profile file suffix: %s"
            raise ValueError(msg, config_path.name)

    def _set_encryption_keys(self, appliance_info: dict[str, Any]) -> None:
        self.data[CONF_MODE] = appliance_info["connectionType"]
        if self.data[CONF_MODE] == "TLS":
            if CONF_HOST not in self.data:
                self.data[CONF_HOST] = (
                    f"{appliance_info['brand']}-{appliance_info['type']}-{appliance_info['haId']}"
                )
                _LOGGER.debug("Set Host to: %s", self.data[CONF_HOST])
            self.data[CONF_PSK] = appliance_info["key"]
        else:
            if CONF_HOST not in self.data:
                self.data[CONF_HOST] = appliance_info["haId"]
                _LOGGER.debug("Set Host to: %s", self.data[CONF_HOST])
            self.data[CONF_PSK] = appliance_info["key"]
            self.data[CONF_AES_IV] = appliance_info["iv"]
        _LOGGER.debug("Set Keys for %s Appliance", self.data[CONF_MODE])

        if self.global_config:
            if self.global_config.override_host is not None:
                # Dev mode host override
                self.data[CONF_HOST] = self.global_config.override_host
                self.data[CONF_MANUAL_HOST] = True
                _LOGGER.info("Host override: %s", self.data[CONF_HOST])
            if self.global_config.override_psk is not None:
                # Dev mode psk override
                self.data[CONF_PSK] = self.global_config.override_psk
                self.data[CONF_MODE] = "TLS"
                self.data[CONF_AES_IV] = None
                _LOGGER.info("PSK override")

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Handle a flow initialized by the user."""
        _LOGGER.debug("Config flow initialized by user")
        self.global_config = self.hass.data.get(HC_KEY)
        return self.async_show_menu(step_id="user", menu_options=["legacy_oauth_region", "upload"])

    async def async_step_legacy_oauth_region(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask which Home Connect account region to use, then show the authorize URL."""
        if user_input is not None:
            self._region = user_input[CONF_REGION]
            self._legacy_code_verifier = legacy_generate_code_verifier()
            self._legacy_state = legacy_generate_state()
            return await self.async_step_legacy_oauth_paste()
        return self.async_show_form(step_id="legacy_oauth_region", data_schema=CONFIG_REGION_SCHEMA)

    async def async_step_legacy_oauth_paste(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Show the authorize URL, then accept the pasted-back redirect."""
        # Set together, one step earlier, by async_step_legacy_oauth_region -
        # only None if this step is somehow reached without going through it.
        if self._legacy_code_verifier is None or self._legacy_state is None:
            return self.async_abort(reason="oauth_fetch_failed")

        if user_input is not None:
            session = async_get_clientsession(self.hass)
            try:
                code = legacy_extract_code_from_redirect(
                    user_input[CONF_LEGACY_REDIRECT_URL], self._legacy_state
                )
                access_token = await legacy_async_exchange_code_for_token(
                    session, self._region, code, self._legacy_code_verifier
                )
                self.appliances = await async_fetch_appliances(session, access_token, self._region)
            except (HCLegacyOAuthError, HCCloudApiError) as err:
                _LOGGER.debug("Legacy OAuth flow failed: %s", err)
                return self.async_abort(
                    reason="oauth_fetch_failed", description_placeholders={"error": str(err)}
                )
            return await self.async_step_device_select()

        authorize_url = legacy_build_authorize_url(
            self._region, self._legacy_code_verifier, self._legacy_state
        )
        schema = vol.Schema({vol.Required(CONF_LEGACY_REDIRECT_URL): cv.string})
        return self.async_show_form(
            step_id="legacy_oauth_paste",
            data_schema=schema,
            description_placeholders={"authorize_url": authorize_url},
        )

    async def async_step_upload(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Handle profile file upload."""
        if user_input is not None:
            _LOGGER.debug("Got Profile file")
            try:
                self.appliances = await self.hass.async_add_executor_job(
                    self._process_profile_file, user_input[CONF_FILE]
                )
                _LOGGER.debug("Found %s Appliances in Profile file", len(self.appliances))
                if "config_entry" in self.appliances:
                    _LOGGER.debug("Setting up form config entry")
                    self.data = cast("dict[str, Any]", self.appliances["config_entry"])
                    if self.global_config:
                        if self.global_config.override_host is not None:
                            # Dev mode host override
                            self.data[CONF_HOST] = self.global_config.override_host
                            self.data[CONF_MANUAL_HOST] = True
                            _LOGGER.info("Host override: %s", self.data[CONF_HOST])
                        if self.global_config.override_psk is not None:
                            # Dev mode psk override
                            self.data[CONF_PSK] = self.global_config.override_psk
                            self.data[CONF_MODE] = "TLS"
                            self.data[CONF_AES_IV] = None
                            _LOGGER.info("PSK override")

            except ParserError as exc:
                return self.async_abort(
                    reason="profile_file_parser_error",
                    description_placeholders={"error": exc.args[0]},
                )
            except (KeyError, ValueError):
                return self.async_abort(reason="invalid_profile_file")

            if not self.errors:
                if "config_entry" in self.appliances:
                    return await self.async_step_test_connection()

                if self.unique_id:
                    return await self.async_step_set_data()
                return await self.async_step_device_select()

        if (global_config := self.hass.data.get(HC_KEY)) and global_config.setup_from_dump:
            scheam = CONFIG_FILE_SCHEMA_JSON
        else:
            scheam = CONFIG_FILE_SCHEMA
        return self.async_show_form(step_id="upload", data_schema=scheam, errors=self.errors)

    async def async_step_device_select(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle device selection."""
        if user_input is not None:
            await self.async_set_unique_id(user_input[CONF_DEVICE])
            return await self.async_step_set_data()

        appliance_options: list[SelectOptionDict] = []
        try:
            for appliance_id, appliance_info in self.appliances.items():
                existing_entry = self.hass.config_entries.async_entry_for_domain_unique_id(
                    self.handler, appliance_id
                )

                if not existing_entry or existing_entry.source == SOURCE_IGNORE:
                    brand = appliance_info["info"]["brand"]
                    appliance_type = appliance_info["info"]["type"]
                    vib = appliance_info["info"]["vib"]
                    appliance_name = f"{brand} {appliance_type} ({vib})"
                    appliance_options.append(
                        SelectOptionDict(
                            value=appliance_id,
                            label=appliance_name,
                        )
                    )
                else:
                    _LOGGER.debug("Found Setup Appliance %s", appliance_info["info"]["vib"])
        except KeyError:
            return self.async_abort(reason="invalid_profile_file")
        if len(appliance_options) == 0:
            _LOGGER.debug("No Appliances left to setup")
            return self.async_abort(reason="all_setup")
        if len(appliance_options) == 1:
            _LOGGER.debug("Only one Appliances left to setup")
            await self.async_set_unique_id(appliance_options[0]["value"])
            return await self.async_step_set_data()
        _LOGGER.debug("Found %s Appliances not setup", len(appliance_options))
        schema = vol.Schema(
            {
                vol.Required(CONF_DEVICE): SelectSelector(
                    SelectSelectorConfig(options=appliance_options, sort=True)
                )
            }
        )
        return self.async_show_form(step_id="device_select", data_schema=schema, errors=self.errors)

    async def async_step_test_connection(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Test connection with Appliance."""
        _LOGGER.debug("Testing connection to %s Appliance", self.data[CONF_MODE])
        self.errors = {}
        event = Event()

        async def connection_callback(state: ConnectionState) -> None:
            if state == ConnectionState.CONNECTED:
                event.set()

        appliance = HomeAppliance(
            description=deepcopy(self.data[CONF_DESCRIPTION]),
            host=self.data[CONF_HOST],
            app_name="Homeassistant",
            app_id=self.data[CONF_DEVICE_ID],
            psk64=self.data[CONF_PSK],
            iv64=self.data.get(CONF_AES_IV, None),
            connection_callback=connection_callback,
        )
        try:
            await appliance.connect()
            await wait_for(event.wait(), timeout=20)
            self.data[CONF_DESCRIPTION]["info"].update(appliance.info)

        except ClientConnectorSSLError as ex:
            _LOGGER.debug("validate_config failed: %s", ex)
            if self.data[CONF_MODE] == "TLS":
                self.errors["base"] = "cannot_connect"
            else:
                return self.async_abort(reason="auth_failed")
        except BinasciiError as ex:
            _LOGGER.debug("validate_config failed: %s", ex)
            return self.async_abort(reason="auth_failed")
        except (TimeoutError, ClientConnectionError, ConnectionFailedError) as ex:
            _LOGGER.debug("validate_config failed: %s", ex)
            self.errors["base"] = "cannot_connect"
        finally:
            await appliance.close()
        if self.errors:
            _LOGGER.debug("Connection error, showing host step")
            return await self.async_step_host()
        _LOGGER.debug("config vaild, adding config entry")
        return await self.async_step_create_entry(self.data)

    async def async_step_host(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Handle Host setting."""
        if user_input is not None:
            self.data[CONF_MANUAL_HOST] = True
            self.data[CONF_HOST] = user_input[CONF_HOST]
            _LOGGER.debug("User set Host to: %s", self.data[CONF_HOST])
            return await self.async_step_test_connection()

        schema = self.add_suggested_values_to_schema(
            CONFIG_HOST_SCHEMA, {CONF_HOST: self.data[CONF_HOST]}
        )
        return self.async_show_form(
            step_id="host",
            data_schema=schema,
            errors=self.errors,
            description_placeholders={CONF_HOST: self.data[CONF_HOST]},
        )

    async def async_step_create_entry(self, data: dict[str, Any]) -> ConfigFlowResult:
        """Create an config entry or update existing entry for reauth."""
        if self.reauth_entry:
            return self.async_update_reload_and_abort(
                self.reauth_entry,
                data_updates=data,
            )
        return self.async_create_entry(title=data[CONF_NAME], data=data)

    async def async_step_reauth(self, user_input: dict[str, Any]) -> ConfigFlowResult:
        """Reauth flow initialized."""
        _LOGGER.debug("Reauth flow initialized")
        self.reauth_entry = self.hass.config_entries.async_get_entry(self.context["entry_id"])
        if self.reauth_entry is None:
            return self.async_abort(reason="reauth_entry_not_found")
        self.data[CONF_HOST] = self.reauth_entry.data[CONF_HOST]
        return await self.async_step_user()

    async def async_step_set_data(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Confirm reauth dialog."""
        if self.unique_id not in self.appliances:
            return self.async_abort(reason="appliance_not_in_profile_file")

        appliance = self.appliances[self.unique_id]
        try:
            appliance_info = appliance["info"]

            self.data[CONF_DESCRIPTION] = appliance["description"]

            self.data[CONF_DEVICE_ID] = random.randbytes(4).hex()  # noqa: S311
            self.data[CONF_NAME] = f"{appliance_info['brand']} {appliance_info['type']}"

            self._set_encryption_keys(appliance_info)
        except (KeyError, ValueError):
            return self.async_abort(reason="invalid_profile_file")

        return await self.async_step_test_connection()

    async def async_step_zeroconf(self, discovery_info: ZeroconfServiceInfo) -> ConfigFlowResult:
        try:
            _LOGGER.debug(
                "Discovered Appliance %s @ %s",
                discovery_info.properties["vib"],
                discovery_info.host,
            )
            appliance_id = discovery_info.properties["id"]
            await self.async_set_unique_id(appliance_id)
            updates = None
            config_entry = self.hass.config_entries.async_entry_for_domain_unique_id(
                self.handler, appliance_id
            )
            if config_entry and not config_entry.data.get(CONF_MANUAL_HOST, False):
                updates = {CONF_HOST: str(discovery_info.ip_address)}
            self._abort_if_unique_id_configured(updates=updates)
            self.data[CONF_HOST] = str(discovery_info.ip_address)
            self.data[CONF_NAME] = (
                f"{discovery_info.properties['brand']} {discovery_info.properties['type']}"
            )

            self.context.update(
                {
                    "title_placeholders": {"name": discovery_info.name.split(".")[0]},
                }
            )

            return await self.async_step_upload()
        except KeyError:
            return self.async_abort(reason="invalid_discovery_info")


class HCOptionsFlowHandler(OptionsFlow):
    """Options flow: export the appliance's profile as a downloadable ZIP."""

    def __init__(self, config_entry: HCConfigEntry) -> None:
        """Initialize options flow."""
        # Do not assign to self.config_entry - it's a read-only property in HA.
        self._config_entry = config_entry

    async def _notify_and_close(self, message: str) -> ConfigFlowResult:
        await self.hass.services.async_call(
            "persistent_notification",
            "create",
            {
                "title": "Home Connect Local export",
                "message": message,
                "notification_id": f"homeconnect_ws_export_{self._config_entry.entry_id}",
            },
        )
        return self.async_create_entry(title="", data=self._config_entry.options)

    async def _handle_export_safe(self) -> ConfigFlowResult:
        # Safe has no sensitive content (no key, no MAC/serial - just the
        # feature schema, meant to be shared), so a signed link is fine even
        # though the link itself briefly appears in the notification and in
        # HA's own access log.
        base_url = get_url(self.hass)
        path = f"/api/{DOMAIN}/export/{self._config_entry.entry_id}"
        signed_path = async_sign_path(self.hass, path, timedelta(minutes=5))
        stub = filename_stub(self._config_entry)
        message = (
            f"Open this link in your browser to download `{stub}_profile_safe.zip`"
            f" (valid for 5 minutes):\n\n{base_url.rstrip('/')}{signed_path}"
        )
        return await self._notify_and_close(message)

    async def _handle_export_full(self) -> ConfigFlowResult:
        # Full contains the appliance's real encryption key. Deliberately NOT
        # served over HTTP even via a signed link - a link is "possession
        # equals access" and would sit in the notification history and in
        # HA's own access log for its whole validity window. Writing to the
        # config directory instead requires actual filesystem access
        # (Samba/SSH/File Editor) to retrieve, a real access-control boundary
        # rather than a leaked-link problem.
        stub = filename_stub(self._config_entry)
        filename = f"{stub}_profile_full.zip"
        folder = Path(self.hass.config.path("homeconnect_ws_export"))

        def _write() -> None:
            folder.mkdir(exist_ok=True)
            zip_bytes = build_profile_zip(self._config_entry, True)  # noqa: FBT003
            (folder / filename).write_bytes(zip_bytes)

        try:
            await self.hass.async_add_executor_job(_write)
        except OSError as err:
            return await self._notify_and_close(f"Could not write export file: {err}")
        return await self._notify_and_close(
            f"Wrote `{filename}` to your config directory, under"
            f" `homeconnect_ws_export/`. Retrieve it via Samba, SSH, or the File"
            f" Editor add-on."
        )

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Show the export menu."""
        if user_input is not None:
            if user_input["mode"] == "full":
                return await self._handle_export_full()
            return await self._handle_export_safe()
        schema = vol.Schema(
            {
                vol.Required("mode", default="safe"): SelectSelector(
                    SelectSelectorConfig(
                        options=[
                            SelectOptionDict(value="safe", label="Export Safe Profile"),
                            SelectOptionDict(value="full", label="Export Full Profile"),
                        ]
                    )
                ),
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
