# Inventory Barcode Integration Edge

An MQTT-first edge deployment that listens for product payloads, renders
print-ready labels with barcodes/QR codes, and sends them to a Brother QL
printer. The stack runs entirely in Docker so it can be deployed on a
Raspberry Pi or any Linux host that can access the printer over USB.

## Stack Overview

- **mqtt_bridge** – bridges messages from a remote MQTT broker (e.g. HiveMQ
  Cloud) onto the local broker so the printer stack can run offline.
- **mqtt_broker** – Eclipse Mosquitto with MQTT + WebSocket listeners.
- **mqtt_printer_listener** – converts messages delivered on
  `lobby/lift/packages` into ready-to-print labels by calling
  `printer/code/print.py`.
- **printer/code** – label rendering and printer control logic (barcodes,
  QR generation, rasterization, and Brother QL USB output).

```
docker-compose.yml
├── mqtt_bridge/
├── mqtt_broker/
└── mqtt_printer_listener/
    └── mounts ./printer/code -> /code inside the container
```

## Requirements

- Docker Engine 24+
- docker compose plugin
- Brother QL series printer accessible over USB
- Optional: internet access for the remote MQTT broker

## Quick Start

```bash
git clone https://github.com/anandarupmukherjee/inventory_barcode_integration_edge.git
cd inventory_barcode_integration_edge
docker compose up -d
```

By default the bridge listens to `broker.hivemq.com` on topic
`lobby/lift/packages`. Edit `docker-compose.yml` to point at your own broker or
override the environment variables listed below.

## Environment Variables

| Service               | Variable                | Purpose                                      |
|-----------------------|-------------------------|----------------------------------------------|
| `mqtt_bridge`         | `REMOTE_MQTT_HOST`      | Remote broker hostname                       |
|                       | `REMOTE_MQTT_TOPIC`     | Topic to mirror from remote broker           |
|                       | `LOCAL_MQTT_TOPIC`      | Topic to publish to on the local broker      |
| `mqtt_printer_listener` | `MQTT_HOST`           | Local broker hostname                        |
|                       | `MQTT_TOPIC`            | Topic to subscribe to for label payloads     |
|                       | `PRINTER_IDENTIFIER`    | Brother QL USB identifier (e.g. `usb://...`) |
|                       | `PRINTER_MODEL`         | Brother QL model, defaults to `QL-700`       |

Payloads should be JSON objects. If the payload already contains
`labelItems`, they are passed straight to `print.py`. Otherwise the listener
builds a label with the product name, optional note, timestamp, and a QR code.

## Label Rendering Notes

- `printer/code/print.py` auto-creates `barcodes`, `QR`, and `output`
  directories at runtime; generated assets are ignored via `.gitignore`.
- The bundled font is `DejaVuSans-Bold.ttf`. Replace it or adjust `print.py`
  if you need a different typeface.
- `QRPrint.makeLabelAAS` supports large payloads by chunking/compressing
  before QR encoding.

## Maintenance

- To stop the stack run `./stop.sh`.
- Logs can be tailed with `docker compose logs -f mqtt_printer_listener`.
- Tests are currently manual. When making changes to `print.py` you can feed a
  sample payload with `python3 printer/code/print.py '<payload>'`.

This repository is ready to publish to GitHub at
`https://github.com/anandarupmukherjee/inventory_barcode_integration_edge.git`.
