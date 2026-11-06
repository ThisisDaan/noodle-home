"""Phones that report themselves through the Noodle app. Built in: no entry on the Integrations page."""

from .adapter import PhoneAdapter
from ..base import Plugin


class PhonePlugin(Plugin):
    id = "phone"
    source = "phone"
    adapter_class = PhoneAdapter
    name = "Phones"
    visible = False
    order = 220


PLUGIN = PhonePlugin()
