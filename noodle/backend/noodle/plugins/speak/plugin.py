"""Speaking on a Google speaker (Chromecast) from flows. Built in."""

from ... import speak
from ..base import Node, NodeField, Plugin


async def run_speak(n) -> None:
    d = n.data
    try:
        await speak.say(str(d.get("speaker") or "Kitchen"), n.fill(d.get("message")))
        n.log(f"Said: {d.get('message')}")
    except Exception as err:  # a missing speaker should not stop the rest of the flow
        n.log(f"Speaking failed: {err}")
    await n.follow()


class SpeakPlugin(Plugin):
    id = "speak"
    name = "Google speakers"
    visible = False
    order = 240

    def nodes(self):
        return [Node(
            "action.speak", "Speak", "action", run_speak, icon="speaker", summary="{speaker}: {message}",
            defaults={"speaker": "Kitchen", "message": "Hallo"},
            fields=[NodeField("speaker", "Speaker name"), NodeField("message", "Text (Dutch)")])]


PLUGIN = SpeakPlugin()
