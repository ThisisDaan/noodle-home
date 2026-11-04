"""Phone notifications through ntfy (no adapter: notify.py sends them)."""

from .. import config
from .base import Field, Plugin


class NtfyPlugin(Plugin):
    id = "ntfy"
    name = "Phone notifications (ntfy)"
    help = ("Sends notifications to your phone through ntfy. The topic name is the secret: anyone who knows it "
            "can read along.")
    fields = [Field("ntfy_url", "Server", "https://ntfy.sh"), Field("ntfy_topic", "Topic", "my-secret-topic", secret=True)]
    icon = "bell"
    panel = "notify"
    forget = ["ntfy_topic"]
    order = 50

    def status(self, adapter):
        return bool(config.NTFY_TOPIC) or None

    def preset(self):
        return bool(config.NTFY_TOPIC)


PLUGIN = NtfyPlugin()
