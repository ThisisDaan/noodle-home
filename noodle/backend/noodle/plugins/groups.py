"""Device groups. Built in: always runs, no entry on the Integrations page."""

from ..adapters.groups import GroupAdapter
from .base import Plugin


class GroupsPlugin(Plugin):
    id = "groups"
    source = "group"
    adapter_class = GroupAdapter
    name = "Groups"
    visible = False
    order = 210


PLUGIN = GroupsPlugin()
