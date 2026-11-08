"""Phone notifications from flows (the Noodle app, and ntfy when it is set up). Built in."""

from ... import config, notify
from ..base import Node, NodeField, Plugin


async def run_notify(n) -> None:
    d = n.data
    buttons = [(b["label"], f"{config.PUBLIC_URL}/api/hook/{n.store.hook_token()}/{b['hook']}")
               for b in d.get("buttons") or [] if b.get("label") and b.get("hook")]
    await notify.send(n.fill(d.get("message")), n.fill(d.get("title") or "Noodle"), str(d.get("priority") or "default"),
                      buttons=buttons, service=str(d.get("service") or "all"))
    n.log(f"Notified: {d.get('title') or 'Noodle'}")
    await n.follow()


class NotificationsPlugin(Plugin):
    id = "notifications"
    name = "Notifications"
    visible = False
    order = 230

    def nodes(self):
        return [Node(
            "action.notify", "Notify", "action", run_notify, icon="bell", summary="{title}: {message}",
            defaults={"service": "all", "title": "Noodle", "message": "Something happened", "priority": "default",
                      "buttons": []},
            fields=[
                NodeField("service", "Send through", "select", [("all", "All (Noodle app + ntfy)"),
                                                                ("app", "Noodle app only"), ("ntfy", "ntfy only")]),
                NodeField("title", "Title"),
                NodeField("message", "Message ({count} = presses)", "textarea"),
                NodeField("priority", "Priority", "select", [("low", "low"), ("default", "normal"), ("high", "high"),
                                                             ("urgent", "urgent")]),
                NodeField("buttons", "Buttons on the notification (max 3). Tapping one runs the "
                                     "\"Notification button\" trigger with the same name.", "buttons")])]


PLUGIN = NotificationsPlugin()
