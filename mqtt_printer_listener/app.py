from __future__ import annotations

import json
import os
import subprocess
import time
import uuid
from datetime import datetime, timedelta
from typing import Any, Dict

import paho.mqtt.client as mqtt

BROKER = os.environ.get("MQTT_HOST", "broker.hivemq.com")
PORT = int(os.environ.get("MQTT_PORT", "1883"))
TOPIC = os.environ.get("MQTT_TOPIC", "lift/lobby/packages/print")


def on_connect(client, _userdata, _flags, rc):
    print(f"[listener] connected rc={rc}")
    client.subscribe(TOPIC)
    print(f"[listener] subscribed to {TOPIC}")


def _first_non_empty(data: Dict[str, Any], keys, default="") -> str:
    for key in keys:
        value = data.get(key)
        if isinstance(value, str):
            stripped = value.strip()
            if stripped:
                return stripped
        elif isinstance(value, (int, float)):
            text = str(value).strip()
            if text and text.lower() not in {"nan", "inf", "-inf"}:
                return text
    return default


QR_KEYS = ("qrcode_value", "qrCodeValue", "qrcodeValue")
BARCODE_KEYS = ("product_code", "productCode", "barcode", "barcode_value", "barcodeValue", "code")
LOT_KEYS = ("lot_number", "lotNumber", "lot", "lotNo", "batch", "batchNumber", "batch_number")
EXPIRY_KEYS = ("expiry", "expiration", "expiryDate", "expirationDate", "expireDate", "expDate")
TIMESTAMP_KEYS = ("timestamp", "time", "datetime", "date", "createdAt", "created_at")
NOTE_KEYS = ("note", "notes", "description", "details", "comment")
PRODUCT_NAME_KEYS = ("product_name", "productName", "product", "name", "title", "label", "message", "text")
PRODUCT_OBJ_NAME_KEYS = ("name", "product_name", "productName", "title")


def _parse_datetime(value: Any) -> datetime | None:
    if value is None:
        return None

    if isinstance(value, (int, float)):
        if value > 0:
            try:
                return datetime.utcfromtimestamp(value)
            except (ValueError, OSError):
                return None

    if not isinstance(value, str):
        return None

    raw = value.strip()
    if not raw:
        return None

    iso_candidate = raw.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(iso_candidate)
    except ValueError:
        pass

    formats = [
        "%Y-%m-%d",
        "%Y/%m/%d",
        "%d-%m-%Y",
        "%m/%d/%Y",
        "%Y%m%d",
        "%y%m%d",
    ]
    for fmt in formats:
        try:
            return datetime.strptime(raw, fmt)
        except ValueError:
            continue
    return None


def _normalize_gtin(value: str) -> str:
    digits = "".join(ch for ch in value if ch.isdigit())
    if not digits:
        return ""
    digits = digits[:14]
    return digits.zfill(14)


def _default_gtin() -> str:
    random_digits = str(uuid.uuid4().int)
    random_digits = random_digits[:14]
    return random_digits.zfill(14)


def _build_gs1_code(product_code: str, lot_number: str, expiry: datetime) -> str:
    gtin = _normalize_gtin(product_code)
    if not gtin:
        gtin = _default_gtin()

    lot = (lot_number or "000").strip() or "000"
    lot = lot.replace(" ", "")
    lot = lot[:20]

    expiry_str = expiry.strftime("%y%m%d")
    return f"01{gtin}17{expiry_str}10{lot}"


def build_label_payload(raw: str) -> Dict[str, Any]:
    data = json.loads(raw)

    if isinstance(data, dict) and "labelItems" in data:
        return data

    if not isinstance(data, dict):
        raise ValueError("Payload must be a JSON object")

    now = datetime.utcnow()

    product = _first_non_empty(data, keys=PRODUCT_NAME_KEYS, default="")

    qr_code_override = _first_non_empty(data, keys=QR_KEYS, default="")

    product_obj = data.get("product") if isinstance(data.get("product"), dict) else {}
    if isinstance(product_obj, dict):
        if not product:
            product = _first_non_empty(product_obj, keys=PRODUCT_OBJ_NAME_KEYS, default="")
        if not qr_code_override:
            qr_code_override = _first_non_empty(product_obj, keys=QR_KEYS, default="")

    product_code = qr_code_override
    if not product_code:
        product_code = _first_non_empty(data, keys=BARCODE_KEYS, default="")
        if isinstance(product_obj, dict) and not product_code:
            product_code = _first_non_empty(product_obj, keys=BARCODE_KEYS, default="")

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

    note = _first_non_empty(data, keys=NOTE_KEYS, default="")

    timestamp = _first_non_empty(data, keys=TIMESTAMP_KEYS, default="")
    if not timestamp:
        timestamp = now.isoformat(timespec="seconds") + "Z"

    lot_number = _first_non_empty(data, keys=LOT_KEYS, default="")
    if isinstance(product_obj, dict) and not lot_number:
        lot_number = _first_non_empty(product_obj, keys=LOT_KEYS, default="")
    if not lot_number:
        lot_number = "000"

    expiry_raw = _first_non_empty(data, keys=EXPIRY_KEYS, default="")
    expiry_dt = _parse_datetime(expiry_raw)
    if isinstance(product_obj, dict) and not expiry_dt:
        expiry_dt = _parse_datetime(_first_non_empty(product_obj, keys=EXPIRY_KEYS, default=""))
    if not expiry_dt:
        expiry_dt = now + timedelta(days=365 * 3)

    qr_value = _build_gs1_code(product_code or "", lot_number, expiry_dt)

    try:
        qty = max(1, int(data.get("qty", 1)))
    except (TypeError, ValueError):
        qty = 1

    label_items = []

    if product:
        label_items.append({"labelType": "text", "labelKey": "", "labelValue": product})

    if product_code:
        label_items.append({"labelType": "text", "labelKey": "Code", "labelValue": product_code})

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
