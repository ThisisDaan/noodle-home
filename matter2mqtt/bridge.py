"""Publish Matter Switch-cluster events from matter-server to MQTT.

Home Assistant only accepts multi-press counts up to a switch's MultiPressMax,
so a fast spin on the IKEA BILRESA wheel (18 clicks) is dropped there. This
bridge forwards the raw events with their real counts:

  matter/<node_id>/<endpoint_id>/<event>   payload: event data as JSON

for example matter/3/7/multi_press_complete {"previousPosition": 1, "totalNumberOfPressesCounted": 18}
"""

import asyncio
import json
import logging
import os

import aiomqtt
import websockets

MATTER_URL = os.environ.get("MATTER_URL", "ws://127.0.0.1:5580/ws")
MQTT_HOST = os.environ.get("MQTT_HOST", "127.0.0.1")
MQTT_PORT = int(os.environ.get("MQTT_PORT", "1883"))
TOPIC_PREFIX = os.environ.get("TOPIC_PREFIX", "matter")

SWITCH_CLUSTER = 59
EVENTS = {
    0: "switch_latched",
    1: "initial_press",
    2: "long_press",
    3: "short_release",
    4: "long_release",
    5: "multi_press_ongoing",
    6: "multi_press_complete",
}

log = logging.getLogger("matter2mqtt")


async def run_once() -> None:
    async with aiomqtt.Client(MQTT_HOST, MQTT_PORT, identifier="matter2mqtt") as mqtt:
        async with websockets.connect(MATTER_URL, max_size=None) as ws:
            await ws.recv()  # server info
            await ws.send(json.dumps({"message_id": "listen", "command": "start_listening"}))
            log.info("listening to %s, publishing to %s:%s", MATTER_URL, MQTT_HOST, MQTT_PORT)
            async for raw in ws:
                msg = json.loads(raw)
                if msg.get("event") != "node_event":
                    continue
                data = msg["data"]
                if data.get("cluster_id") != SWITCH_CLUSTER:
                    continue
                name = EVENTS.get(data["event_id"], f"event_{data['event_id']}")
                topic = f"{TOPIC_PREFIX}/{data['node_id']}/{data['endpoint_id']}/{name}"
                await mqtt.publish(topic, json.dumps(data.get("data") or {}))
                log.debug("%s %s", topic, data.get("data"))


async def main() -> None:
    logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"), format="%(asctime)s %(levelname)s %(message)s")
    while True:
        try:
            await run_once()
        except Exception as err:  # matter-server or mosquitto restarted: retry
            log.warning("connection lost (%s), retrying in 5s", err)
        await asyncio.sleep(5)


if __name__ == "__main__":
    asyncio.run(main())
