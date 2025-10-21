import os
import time
import threading

import paho.mqtt.client as mqtt


REMOTE_HOST = os.getenv("REMOTE_MQTT_HOST", "broker.hivemq.com")
REMOTE_PORT = int(os.getenv("REMOTE_MQTT_PORT", "1883"))
REMOTE_TOPIC = os.getenv("REMOTE_MQTT_TOPIC", "lobby/lift/packages")

LOCAL_HOST = os.getenv("LOCAL_MQTT_HOST", "mqtt_broker")
LOCAL_PORT = int(os.getenv("LOCAL_MQTT_PORT", "1883"))
LOCAL_TOPIC = os.getenv("LOCAL_MQTT_TOPIC", REMOTE_TOPIC)

RECONNECT_DELAY = int(os.getenv("REMOTE_RECONNECT_SECONDS", "5"))


def log(msg: str) -> None:
    print(f"[bridge] {msg}", flush=True)


def build_client(client_id: str) -> mqtt.Client:
    client = mqtt.Client(client_id=client_id)
    client.enable_logger()
    client.reconnect_delay_set(min_delay=1, max_delay=30)
    return client


def connect_local(local_client: mqtt.Client) -> None:
    while True:
        try:
            local_client.connect(LOCAL_HOST, LOCAL_PORT, keepalive=60)
            local_client.loop_start()
            log(f"Connected to local broker at {LOCAL_HOST}:{LOCAL_PORT}")
            return
        except Exception as exc:
            log(f"Local broker connection failed: {exc}")
            time.sleep(3)


def main() -> None:
    local_client = build_client("mqtt-bridge-local")
    connect_local(local_client)

    ready = threading.Event()

    def on_remote_connect(client: mqtt.Client, _userdata, _flags, rc: int) -> None:
        if rc == 0:
            log(f"Connected to remote broker at {REMOTE_HOST}:{REMOTE_PORT}")
            client.subscribe(REMOTE_TOPIC)
            log(f"Subscribed to remote topic {REMOTE_TOPIC}")
            ready.set()
        else:
            log(f"Remote broker connection refused rc={rc}")

    def on_remote_message(_client: mqtt.Client, _userdata, msg: mqtt.MQTTMessage) -> None:
        if not ready.is_set():
            return
        try:
            local_client.publish(LOCAL_TOPIC, msg.payload, qos=1, retain=False)
            log(f"Forwarded message to {LOCAL_TOPIC}")
        except Exception as exc:
            log(f"Publish error: {exc}")

    remote_client = build_client("mqtt-bridge-remote")
    remote_client.on_connect = on_remote_connect
    remote_client.on_message = on_remote_message

    while True:
        try:
            remote_client.connect(REMOTE_HOST, REMOTE_PORT, keepalive=60)
            remote_client.loop_forever()
        except Exception as exc:
            log(f"Remote connection error: {exc}")
            time.sleep(RECONNECT_DELAY)


if __name__ == "__main__":
    main()
