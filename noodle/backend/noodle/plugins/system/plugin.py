"""The hub's own settings. Always present; cannot be added or removed."""

import os
import time
from datetime import datetime

from ... import config
from ..base import Field, Plugin


class HubSettingsPlugin(Plugin):
    id = "system"
    name = "This hub"
    help = "The name of your home and where it is: sunrise and sunset, and knowing when a phone is home, depend on it."
    fields = [Field("home_name", "Name of your home", "My home"),
              # Picked on the map in the panel (the map also fills in the time zone).
              Field("latitude", "Latitude of your home", "52.37", hidden=True),
              Field("longitude", "Longitude of your home", "4.90", hidden=True),
              Field("timezone", "Time zone (empty: this machine's)", "Europe/Amsterdam", hidden=True),
              Field("public_url", "Address phones use to reach this hub", "http://192.168.1.10:8090",
                    help="Only used for the links behind notification buttons, so your phone knows where Noodle is. "
                         "Changing it does not change the hub's real address. Leave it empty if you do not use buttons.",
                    advanced=True),
              Field("docker_socket", "Docker socket", "/var/run/docker.sock",
                    help="Only needed for \"Update to …\" on this page. Leave it as it is.", advanced=True)]
    always = True
    support = "supported"
    icon = "system"
    panel = "location"

    def details(self, adapter):
        now = datetime.now().astimezone()
        return {"location_set": config.LOCATION_SET, "timezone_now": config.TIMEZONE or os.environ.get("TZ") or now.tzname(),
                "time_now": now.strftime("%H:%M")}
    order = 90


PLUGIN = HubSettingsPlugin()
