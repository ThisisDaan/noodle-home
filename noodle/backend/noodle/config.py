"""Settings from environment variables. Defaults fit the Pi (host network)."""

import json
import logging
import os
import time
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .yamlfile import YamlFile

def _env(name: str, default=None):
    """NOODLE_<NAME> from the environment; the older HOMEPI_<NAME> still works."""
    return os.environ.get(f"NOODLE_{name}", os.environ.get(f"HOMEPI_{name}", default))


DATA_DIR = Path(_env("DATA", "/data"))


def db_path() -> Path:
    """The database: noodle.db for a new hub, homepi.db on a hub that already had it under the old name."""
    new, old = DATA_DIR / "noodle.db", DATA_DIR / "homepi.db"
    return old if old.exists() and not new.exists() else new
# Files you can edit by hand (flows as YAML). Next to the database by default.
CONFIG_DIR = Path(_env("CONFIG", DATA_DIR / "config"))
# The web interface: inside the installed package (pip), or next to it (the Docker image sets NOODLE_STATIC).
_PACKAGED_STATIC = Path(__file__).resolve().parent / "static"
STATIC_DIR = Path(_env("STATIC") or (
    _PACKAGED_STATIC if _PACKAGED_STATIC.exists() else Path(__file__).resolve().parent.parent / "static"))
PORT = int(_env("PORT", "8090"))
EXTRA_PORT = int(_env("EXTRA_PORT", "80"))  # also served here (0 = off), so http://noodle.local works without a port

MQTT_HOST = os.environ.get("MQTT_HOST", "127.0.0.1")
MQTT_PORT = int(os.environ.get("MQTT_PORT", "1883"))
Z2M_BASE_TOPIC = os.environ.get("Z2M_BASE_TOPIC", "zigbee2mqtt")
# Where the Zigbee2MQTT web interface lives, for links to its advanced pages. Empty = port 8081 on the host you browse to.
Z2M_URL = os.environ.get("Z2M_URL", "")

MATTER_URL = os.environ.get("MATTER_URL", "ws://127.0.0.1:5580/ws")
OTBR_URL = os.environ.get("OTBR_URL", "http://127.0.0.1:8082")
# Phone notifications through ntfy. The topic name is the secret: anyone who knows it can read along.
NTFY_URL = os.environ.get("NTFY_URL", "https://ntfy.sh").rstrip("/")
NTFY_TOPIC = os.environ.get("NTFY_TOPIC", "")

# How the phone reaches noodle, for notification buttons (webhooks).
PUBLIC_URL = _env("URL", "").rstrip("/")

# Where the home is, for sunrise and sunset and for "is the phone home" (default: Amsterdam, until it is set on the
# Integrations page under This hub). LOCATION_SET says whether someone has set it.
LATITUDE = float(_env("LAT", "52.37"))
LONGITUDE = float(_env("LON", "4.90"))
LOCATION_SET = _env("LAT") is not None and _env("LON") is not None
# Set once the first-run wizard is finished or skipped (installs from before the wizard count as done).
SETUP_DONE = False
HOME_NAME = ""
# Time zone name such as Europe/Amsterdam. Empty: the one of this machine (the TZ variable).
TIMEZONE = _env("TZ", "")
_ORIGINAL_TZ = os.environ.get("TZ")

# Set to 0 for local development against the real devices, so rules and flows don't run twice.
AUTOMATIONS = _env("AUTOMATIONS", "1") != "0"
DOCKER_SOCKET = os.environ.get("DOCKER_SOCKET", "/var/run/docker.sock")
# Where "Check for updates" looks (GitHub releases), and the name of the hub's own container.
UPDATE_REPO = os.environ.get("NOODLE_UPDATE_REPO", "ThisisDaan/noodle-home")
CONTAINER_NAME = os.environ.get("NOODLE_CONTAINER", "noodle")

# Xiaomi Bluetooth thermometers to listen for: "MAC=Name,MAC=Name".
BLE_SENSORS = dict(item.split("=", 1) for item in os.environ.get(
    "BLE_SENSORS", "").split(",") if "=" in item)

# Philips Hue bridge: address and the application key from pairing (see the Integrations page).
HUE_HOST = os.environ.get("HUE_HOST", "")
HUE_KEY = os.environ.get("HUE_KEY", "")
# More Hue bridges, as {address: application key}. The bridge in HUE_HOST/HUE_KEY (the only place a single bridge used to be
# kept) is still read, so nothing has to be moved: see hue_bridges().
HUE_BRIDGES: dict = dict(item.split("=", 1) for item in os.environ.get("HUE_BRIDGES", "").split(",") if "=" in item)

# Integrations the user added on the Integrations page (empty = work it out from what is set up, see integrations.py).
INTEGRATIONS: list[str] = []

# The old thermostat integration (a room sensor and a heater plug). It is now the Thermostat node in a flow;
# these are only read once, to turn an old install's settings into that flow (migrations.retire_thermostat).
THERMOSTAT_ID = "thermostat:main"
THERMOSTAT_NAME = "Thermostat"
THERMOSTAT_SENSOR_DEVICE = THERMOSTAT_SENSOR_KEY = THERMOSTAT_HEATER_DEVICE = THERMOSTAT_HEATER_KEY = ""

# LIFX: the bulbs the user added (address by hardware id), and extra addresses to search when a broadcast
# does not reach them. Nothing searches except when the user presses Search.
LIFX_BULBS = dict(item.split("=", 1) for item in os.environ.get("LIFX_BULBS", "").split(",") if "=" in item)
LIFX_HOSTS: list[str] = [h.strip() for h in os.environ.get("LIFX_HOSTS", "").split(",") if h.strip()]
# Devices reached by address (plugins/lan/adapter.py): what the user added, as {key: address}. Nanoleaf also keeps the
# token each one gave when it was paired.
def _pairs(name: str) -> dict:
    return dict(item.split("=", 1) for item in os.environ.get(name, "").split(",") if "=" in item)


SHELLY_DEVICES, WLED_DEVICES, KASA_DEVICES = _pairs("SHELLY_DEVICES"), _pairs("WLED_DEVICES"), _pairs("KASA_DEVICES")
SONOS_DEVICES, NANOLEAF_DEVICES, NANOLEAF_TOKENS = _pairs("SONOS_DEVICES"), _pairs("NANOLEAF_DEVICES"), _pairs("NANOLEAF_TOKENS")
WIZ_DEVICES, YEELIGHT_DEVICES = _pairs("WIZ_DEVICES"), _pairs("YEELIGHT_DEVICES")
GOVEE_DEVICES, ROKU_DEVICES, YAMAHA_DEVICES = _pairs("GOVEE_DEVICES"), _pairs("ROKU_DEVICES"), _pairs("YAMAHA_DEVICES")
# Pi-hole (6 or later): its address and the password of its web interface.
PIHOLE_URL, PIHOLE_PASSWORD = os.environ.get("PIHOLE_URL", ""), os.environ.get("PIHOLE_PASSWORD", "")
# UniFi presence: the controller, a local account, and the devices to follow as {mac: name}.
UNIFI_URL, UNIFI_USERNAME, UNIFI_PASSWORD = os.environ.get("UNIFI_URL", ""), os.environ.get("UNIFI_USERNAME", ""), os.environ.get("UNIFI_PASSWORD", "")
UNIFI_SITE, UNIFI_DEVICES = os.environ.get("UNIFI_SITE", "default"), _pairs("UNIFI_DEVICES")
# Home Assistant (a long-lived token), the IKEA DIRIGERA hub (the token pairing gave), and the MQTT discovery topic.
HA_URL, HA_TOKEN = os.environ.get("HA_URL", ""), os.environ.get("HA_TOKEN", "")
DIRIGERA_HOST, DIRIGERA_TOKEN = os.environ.get("DIRIGERA_HOST", ""), os.environ.get("DIRIGERA_TOKEN", "")
MQTT_DISCOVERY_PREFIX = os.environ.get("MQTT_DISCOVERY_PREFIX", "homeassistant")
# Room names used to guess a device's area from its name ("Keuken Lamp" -> Keuken).
DEFAULT_AREAS = ["Living room", "Kitchen", "Bedroom", "Bathroom", "Hallway", "Garden"]


# --- settings made in the web interface ---------------------------------------------------------
# Saved as YAML in CONFIG_DIR and laid over the defaults above, so nothing has to be edited by hand (but it can be):
#   settings.yaml   one section per integration (zigbee:, hue:, ...), plus the list of added integrations
#   secrets.yaml    keys and tokens, readable by the owner only
# Code reads config.<ATTRIBUTE> when it connects, so a changed setting is picked up by restarting that integration.

log = logging.getLogger(__name__)

# setting key -> (attribute above, kind, section in settings.yaml). kind: str, int, or "pairs" (BLE_SENSORS) /
# "list" (DEFAULT_AREAS). The section is the id of the integration the setting belongs to (None: top level).
SETTINGS: dict[str, tuple[str, str, str | None]] = {
    "mqtt_host": ("MQTT_HOST", "str", "zigbee"), "mqtt_port": ("MQTT_PORT", "int", "zigbee"),
    "z2m_base_topic": ("Z2M_BASE_TOPIC", "str", "zigbee"), "z2m_url": ("Z2M_URL", "str", "zigbee"),
    "matter_url": ("MATTER_URL", "str", "matter"), "otbr_url": ("OTBR_URL", "str", "matter"),
    "ntfy_url": ("NTFY_URL", "str", "ntfy"), "ntfy_topic": ("NTFY_TOPIC", "str", "ntfy"),
    "latitude": ("LATITUDE", "lat", "system"), "longitude": ("LONGITUDE", "lon", "system"),
    "timezone": ("TIMEZONE", "tz", "system"), "home_name": ("HOME_NAME", "str", "system"),
    "setup_done": ("SETUP_DONE", "bool", None),
    "public_url": ("PUBLIC_URL", "str", "system"), "docker_socket": ("DOCKER_SOCKET", "str", "system"),
    "hue_host": ("HUE_HOST", "str", "hue"), "hue_key": ("HUE_KEY", "str", "hue"), "hue_bridges": ("HUE_BRIDGES", "pairs", "hue"),
    "thermostat_id": ("THERMOSTAT_ID", "str", "thermostat"), "thermostat_name": ("THERMOSTAT_NAME", "str", "thermostat"),
    "thermostat_sensor_device": ("THERMOSTAT_SENSOR_DEVICE", "str", "thermostat"),
    "thermostat_sensor_key": ("THERMOSTAT_SENSOR_KEY", "str", "thermostat"),
    "thermostat_heater_device": ("THERMOSTAT_HEATER_DEVICE", "str", "thermostat"),
    "thermostat_heater_key": ("THERMOSTAT_HEATER_KEY", "str", "thermostat"),
    "lifx_hosts": ("LIFX_HOSTS", "list", "lifx"), "lifx_bulbs": ("LIFX_BULBS", "pairs", "lifx"),
    "shelly_devices": ("SHELLY_DEVICES", "pairs", "shelly"), "wled_devices": ("WLED_DEVICES", "pairs", "wled"),
    "kasa_devices": ("KASA_DEVICES", "pairs", "kasa"), "sonos_devices": ("SONOS_DEVICES", "pairs", "sonos"),
    "govee_devices": ("GOVEE_DEVICES", "pairs", "govee"), "roku_devices": ("ROKU_DEVICES", "pairs", "roku"),
    "yamaha_devices": ("YAMAHA_DEVICES", "pairs", "yamaha"),
    "unifi_url": ("UNIFI_URL", "str", "unifi"), "unifi_username": ("UNIFI_USERNAME", "str", "unifi"),
    "unifi_password": ("UNIFI_PASSWORD", "str", "unifi"), "unifi_site": ("UNIFI_SITE", "str", "unifi"),
    "unifi_devices": ("UNIFI_DEVICES", "pairs", "unifi"),
    "pihole_url": ("PIHOLE_URL", "str", "pihole"), "pihole_password": ("PIHOLE_PASSWORD", "str", "pihole"),
    "wiz_devices": ("WIZ_DEVICES", "pairs", "wiz"), "yeelight_devices": ("YEELIGHT_DEVICES", "pairs", "yeelight"),
    "nanoleaf_devices": ("NANOLEAF_DEVICES", "pairs", "nanoleaf"), "nanoleaf_tokens": ("NANOLEAF_TOKENS", "pairs", "nanoleaf"),
    "ha_url": ("HA_URL", "str", "homeassistant"), "ha_token": ("HA_TOKEN", "str", "homeassistant"),
    "dirigera_host": ("DIRIGERA_HOST", "str", "dirigera"), "dirigera_token": ("DIRIGERA_TOKEN", "str", "dirigera"),
    "mqtt_discovery_prefix": ("MQTT_DISCOVERY_PREFIX", "str", "mqtt"),
    "ble_sensors": ("BLE_SENSORS", "pairs", "ble"), "integrations": ("INTEGRATIONS", "list", None),
}
SECRET_KEYS = {"hue_key", "hue_bridges", "ntfy_topic", "nanoleaf_tokens", "ha_token", "dirigera_token", "pihole_password", "unifi_password"}  # kept in secrets.yaml, not in settings.yaml
_DEFAULTS = {attr: globals()[attr] for attr, _, _ in SETTINGS.values()} | {"LOCATION_SET": LOCATION_SET}
_SETTINGS = YamlFile(CONFIG_DIR / "settings.yaml")
_SECRETS = YamlFile(CONFIG_DIR / "secrets.yaml", private=True)
_OLD_FILE = DATA_DIR / "settings.json"  # before settings were YAML


def hue_bridges() -> dict[str, str]:
    """Every paired Hue bridge, {address: application key}: the one from before there could be several (HUE_HOST and
    HUE_KEY) and the ones in HUE_BRIDGES. Only reads, so there is nothing to migrate."""
    old = {HUE_HOST: HUE_KEY} if HUE_HOST and HUE_KEY else {}
    return {**old, **HUE_BRIDGES}


def _text(value) -> str:
    """The setting as the text shown in a form."""
    if isinstance(value, dict):
        return ",".join(f"{k}={v}" for k, v in value.items())
    if isinstance(value, list):
        return ", ".join(str(v) for v in value)
    return "" if value is None else str(value)


def get_text(key: str) -> str:
    return _text(globals()[SETTINGS[key][0]])


def _parse(kind: str, text):
    if kind == "pairs" and isinstance(text, dict):
        return {str(k): str(v) for k, v in text.items()}
    if kind == "list" and isinstance(text, list):
        return [str(v) for v in text]
    text = _text(text).strip()
    if kind == "int":
        return int(text)
    if kind == "bool":
        return text.lower() in ("1", "true", "yes", "on")
    if kind in ("lat", "lon"):
        value, limit, what = float(text), 90 if kind == "lat" else 180, "latitude" if kind == "lat" else "longitude"
        if not -limit <= value <= limit:
            raise ValueError(f"{what} must be between -{limit} and {limit}")
        return value
    if kind == "tz":
        if text:
            try:
                ZoneInfo(text)
            except (ZoneInfoNotFoundError, ValueError, OSError):
                raise ValueError(f"unknown time zone {text!r} (like Europe/Amsterdam)") from None
        return text
    if kind == "pairs":
        return dict(item.strip().split("=", 1) for item in text.split(",") if "=" in item)
    if kind == "list":
        return [item.strip() for item in text.split(",") if item.strip()]
    return text.rstrip("/") if text.startswith(("http", "ws")) else text


def apply(values: dict[str, str]) -> None:
    """Validate and use values; all or nothing."""
    parsed = {SETTINGS[key][0]: _parse(SETTINGS[key][1], text) for key, text in values.items() if key in SETTINGS}
    globals().update(parsed)  # a bad value raises above, before anything changes
    _apply_timezone()


def _apply_timezone() -> None:
    """Make the process use TIMEZONE (or go back to the machine's own when it is empty)."""
    if TIMEZONE:
        os.environ["TZ"] = TIMEZONE
    elif _ORIGINAL_TZ is not None:
        os.environ["TZ"] = _ORIGINAL_TZ
    else:
        os.environ.pop("TZ", None)
    if hasattr(time, "tzset"):
        time.tzset()


def _from_files() -> dict:
    """The settings the files hold, by key."""
    found: dict = {}
    settings, secrets = _SETTINGS.read(), _SECRETS.read()
    for key, (_, _, section) in SETTINGS.items():
        source = secrets if key in SECRET_KEYS else settings.get(section, {}) if section else settings
        if isinstance(source, dict) and key in source and source[key] is not None:
            found[key] = source[key]
    return found


def _to_files(values: dict) -> None:
    """Write settings (key -> typed value) into settings.yaml and secrets.yaml."""
    plain: dict = {}
    secrets: dict = {}
    for key, value in values.items():
        _, _, section = SETTINGS[key]
        if key in SECRET_KEYS:
            secrets[key] = value
        elif section:
            plain.setdefault(section, {})[key] = value
        else:
            plain[key] = value
    if plain:
        _SETTINGS.write(plain, sections=True)  # saving one setting must not drop the others in its section
    if secrets:
        _SECRETS.write(secrets)


def _typed(values: dict) -> dict:
    return {key: _parse(SETTINGS[key][1], text) for key, text in values.items() if key in SETTINGS}


def _migrate_json() -> None:
    """Settings used to be one settings.json: move them to the YAML files, keeping the old file as a backup."""
    if _SETTINGS.exists() or _SECRETS.exists() or not _OLD_FILE.exists():
        return
    try:
        _to_files(_typed(json.loads(_OLD_FILE.read_text())))
        _OLD_FILE.rename(_OLD_FILE.with_name("settings.json.migrated"))
        log.info("settings moved from settings.json to %s", CONFIG_DIR)
    except (OSError, ValueError) as err:
        log.warning("could not move settings.json to YAML: %s", err)


def load() -> set[str]:
    """Read the files. Returns the keys whose value is now different (also used to pick up hand edits)."""
    before = {key: get_text(key) for key in SETTINGS}
    try:
        values = _from_files()
        apply({key: _text(value) if not isinstance(value, (dict, list)) else value for key, value in values.items()})
        for key, (attr, _, _) in SETTINGS.items():
            if key not in values:
                globals()[attr] = _DEFAULTS[attr]  # a setting taken out of the file goes back to its default
        globals()["LOCATION_SET"] = _DEFAULTS["LOCATION_SET"] or ("latitude" in values and "longitude" in values)
        _apply_timezone()
    except (ValueError, TypeError) as err:
        log.warning("settings not applied: %s", err)
    return {key for key in SETTINGS if get_text(key) != before[key]}


def files_changed() -> bool:
    return _SETTINGS.changed() or _SECRETS.changed()


def save(values: dict[str, str]) -> None:
    """Check and apply new values, then keep them in the files for the next start."""
    typed = _typed(values)  # raises ValueError on a bad number, before anything is written
    apply(values)
    _to_files(typed)
    if {"latitude", "longitude"} & values.keys():
        globals()["LOCATION_SET"] = True


_migrate_json()
load()
