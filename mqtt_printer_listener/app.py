import json
import os
import subprocess
import time
import uuid
from datetime import datetime
from typing import Any, Dict

import paho.mqtt.client as mqtt

BROKER = os.environ.get("MQTT_HOST", "mqtt_broker")
PORT = int(os.environ.get("MQTT_PORT", "1883"))
TOPIC = os.environ.get("MQTT_TOPIC", "lobby/lift/packages")


def on_connect(client, _userdata, _flags, rc):
    print(f"[listener] connected rc={rc}")
    client.subscribe(TOPIC)
    print(f"[listener] subscribed to {TOPIC}")


def _first_non_empty(data: Dict[str, Any], keys, default="") -> str:
    for key in keys:
        value = data.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return default


def build_label_payload(raw: str) -> Dict[str, Any]:
    data = json.loads(raw)

    if isinstance(data, dict) and "labelItems" in data:
        return data

    if not isinstance(data, dict):
        raise ValueError("Payload must be a JSON object")

    product = _first_non_empty(
        data,
        keys=("product_name", "productName", "product", "name", "title", "label", "message", "text"),
        default="",
    )

    combined_text = str(data.get("combinedText", "") or "").strip()
    if combined_text:
        product = combined_text

    if not combined_text:
        texts = data.get("texts")
        if isinstance(texts, (list, tuple)):
            lines = [str(item).strip() for item in texts if str(item).strip()]
            if lines:
                product = "\n".join(lines)

    if not product:
        product = "Package"

    note = _first_non_empty(
        data,
        keys=("note", "notes", "description", "details", "comment"),
        default="",
    )

    timestamp = _first_non_empty(
        data,
        keys=("timestamp", "time", "datetime", "date", "createdAt", "created_at"),
        default="",
    )
    if not timestamp:
        timestamp = datetime.utcnow().isoformat(timespec="seconds") + "Z"


    qr_value = (
        _first_non_empty(data, keys=("qr", "qrValue", "qr_code", "code"))
        or str(uuid.uuid4())
    )

    try:
        qty = max(1, int(data.get("qty", 1)))
    except (TypeError, ValueError):
        qty = 1

    label_items = []

    if product:
        label_items.append({"labelType": "text", "labelKey": "", "labelValue": product})

    if note:
        label_items.append({"labelType": "text", "labelKey": "", "labelValue": note})

    if timestamp:
        label_items.append({"labelType": "text", "labelKey": "", "labelValue": timestamp})

    label_items.append({"labelType": "QR", "labelKey": "", "labelValue": qr_value})

    return {"qty": qty, "labelItems": label_items}


def on_message(client, _userdata, msg):
    payload = msg.payload.decode(errors="ignore").strip()
    print(f"[listener] msg on {msg.topic}: {payload[:200]}")
    try:
        label_payload = build_label_payload(payload)
        rendered = json.dumps(label_payload)
        res = subprocess.run(
            ["python3", "/code/print.py", rendered],
            capture_output=True,
            text=True,
            check=False,
        )
        print(f"[printer.py stdout]\n{res.stdout}")
        if res.stderr:
            print(f"[printer.py stderr]\n{res.stderr}")
        if res.returncode != 0:
            print(f"[listener] printer.py exited with {res.returncode}")
    except Exception as exc:
        print(f"[listener] error handling message: {exc}")


def main():
    while True:
        try:
            client = mqtt.Client()
            client.on_connect = on_connect
            client.on_message = on_message
            client.connect(BROKER, PORT, 60)
            client.loop_forever()
        except Exception as exc:
            print(f"[listener] connection error: {exc}")
            time.sleep(3)


if __name__ == "__main__":
    main()
