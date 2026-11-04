"""The hub's own settings. Always present; cannot be added or removed."""

import os
import time
from datetime import datetime

from .. import config
from .base import Field, Plugin


class HubSettingsPlugin(Plugin):
    id = "system"
    name = "This hub"
    help = ("How phones reach Noodle (for notification buttons) and where the Docker socket is, if you run "
            "services in Docker and want to restart them from here.")
    fields = [Field("home_name", "Name of your home", "My home"), Field("latitude", "Latitude of your home", "52.37"), Field("longitude", "Longitude of your home", "4.90"),
              Field("timezone", "Time zone (empty: this machine's)", "Europe/Amsterdam"),
              Field("public_url", "Address of this hub", "http://192.168.1.10:8090"),
              Field("docker_socket", "Docker socket", "/var/run/docker.sock")]
    always = True
    icon = "system"
    panel = "location"

    def details(self, adapter):
        now = datetime.now().astimezone()
        return {"location_set": config.LOCATION_SET, "timezone_now": config.TIMEZONE or os.environ.get("TZ") or now.tzname(),
                "time_now": now.strftime("%H:%M")}
    order = 90


PLUGIN = HubSettingsPlugin()
