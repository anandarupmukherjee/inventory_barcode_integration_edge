# Inventory Label Automation System (SOA Architecture)

This repository defines a **service-oriented architecture (SOA)** for the Raspberry Pi–based inventory label automation system.  
Each component runs in its own container and communicates via well-defined APIs or MQTT topics.

---

## Overview

The system automates label creation for items using OCR text captured by a mobile app and verified against a cloud Inventory Management System (IMS).  
The Raspberry Pi acts as the **edge orchestrator**, hosting several modular services that process, query, and print labels.

---

## Services and Roles

### **Edge (Raspberry Pi)**

| Service | Purpose | Interface |
|----------|----------|------------|
| **ble-peripheral** | Exposes BLE GATT service for app connection and authentication (via QR token). | BLE characteristics (`/auth`, `/msg`, `/ack`) |
| **ble-ingress** | Converts BLE messages into MQTT payloads for downstream processing. | Subscribes to BLE; Publishes to `ingest/ocr` |
| **llm-query-builder** | Uses a lightweight LLM to extract the item name from OCR text and build IMS API query URLs. | REST: `POST /extract-and-query` |
| **print-orchestrator** | Coordinates LLM, IMS, barcode, and printer actions; decides whether to print or create new barcodes. | MQTT subscriber `ingest/ocr` / REST `/print` |
| **barcode-local** | Generates local barcode images (e.g., Code128, GS1). | REST: `POST /barcode` |
| **printer-driver** | Sends printable jobs to the Brother QL-700 printer. | REST: `POST /print-job` |
| **config-watcher** | Periodically fetches item catalogs from the IMS to refresh local cache. | Cron or REST download |
| **mosquitto** | MQTT broker used for internal decoupling of edge services. | MQTT on port 1883 |
| **telemetry** | Provides health checks, logs, and metrics. | REST: `/healthz`, `/metrics` |

---

### **Cloud (IMS)**

| Service | Purpose | Interface |
|----------|----------|------------|
| **ims-gateway** | Entry point for all edge requests, authentication, routing, rate limiting. | REST over HTTPS |
| **item-search** | Searches for existing items by name in the catalog. | `GET /items/search?q=` |
| **barcode-registry** | Creates and manages barcode–item mappings. | `POST /barcodes`, `POST /barcodes/map` |
| **catalog-exporter** | Provides downloadable item name lists for edge caching. | `GET /export/item_catalog.json` |
| **audit-log** | Records print job and mapping audit events. | `POST /events/print_job` |
| **auth** | Issues and validates tokens for Edge → Cloud communication. | OAuth2 / JWT |
| **ims-db** | Persistent store for catalog, barcodes, and logs. | PostgreSQL |

---

## Service Interactions

```mermaid
flowchart TD
  classDef box fill:#fff,stroke:#333,stroke-width:1px,rx:6,ry:6;

  %% Mobile App
  A1["Mobile App"]:::box
  A2["Scan QR (BLE token)"]:::box
  A3["Send OCR Text (BLE)"]:::box
  A1 --> A2 --> A3

  %% Edge Services
  subgraph EDGE["Edge (Raspberry Pi)"]
    B1["ble-peripheral"]:::box
    B2["ble-ingress"]:::box
    B3["llm-query-builder"]:::box
    B4["print-orchestrator"]:::box
    B5["barcode-local"]:::box
    B6["printer-driver"]:::box
    B7["mosquitto (MQTT bus)"]:::box
  end

  %% Cloud Services
  subgraph CLOUD["Cloud (IMS)"]
    C1["ims-gateway"]:::box
    C2["item-search"]:::box
    C3["barcode-registry"]:::box
    C4["ims-db"]:::box
  end

  %% Flows
  A3 -->|BLE write| B1 --> B2
  B2 -->|publish ingest/ocr| B7
  B7 -->|consume| B4
  B4 -->|query OCR text| B3
  B3 -->|return item_name| B4
  B4 -->|GET /items/search| C1 --> C2 --> C4
  C2 -->|exists?| C1
  C1 -->|exists:yes| B4
  C1 -.->|exists:no| C3 -->|create barcode| B4
  B4 -->|generate label| B5 --> B6
  B6 -->|print| A3
  B4 -->|audit| C1
```

# inventory_barcode_integration_edge

```mermaid
flowchart TD
  %% Define styles
  classDef box fill:#fff,stroke:#333,stroke-width:1px,rx:6,ry:6;

  %% --- Mobile App ---
  subgraph M["Mobile App"]
    A1["(1) Take Photo"]:::box
    A2["(2) CV + OCR Extract Text"]:::box
    A3["(3) Select Label (optional)"]:::box
    A4["(4) BLE Client - Send OCR Text"]:::box
  end

  %% --- Edge / Raspberry Pi ---
  subgraph E["Edge (Raspberry Pi)"]
    E0["BLE Peripheral & Auth"]:::box
    E1["BLE Ingress Bridge"]:::box
    E2["LLM Query Builder"]:::box
    E3["Printer Service"]:::box
    E4["Barcode Service"]:::box
  end

  %% --- Cloud / Inventory Management System ---
  subgraph C["Cloud (IMS)"]
    C1["API Gateway"]:::box
    C2["Item Search Service"]:::box
    C3["Barcode Registry"]:::box
    C4["Database"]:::box
  end

  %% --- Flow sequence ---
  A1 --> A2 --> A3 --> A4
  A4 -->|Send BLE data| E0 --> E1 --> E2
  E2 -->|Generate query| C1 --> C2 --> C4
  C2 -->|Exists? Yes/No| C1
  C1 -->|Yes: Return BC| E3
  E3 -->|Print Label| A4
  C1 -.->|No| E4 -->|Create BC| E3 -->|Print| A4
  E4 -->|Map BC to DB| C3 --> C4

```


# Sequence of Operations

```mermaid
sequenceDiagram
    autonumber
    participant APP as Mobile App
    participant QR as QR Code (token)
    participant BLE as RPi BLE Peripheral
    participant BR as BLE→Ingress Bridge
    participant LLM as LLM Query Builder
    participant G as IMS API Gateway
    participant S as Item Search Service
    participant B as Barcode Registry
    participant P as Printer

    Note over APP,QR: Onboarding
    APP->>QR: Scan QR (svc UUID, token)
    APP->>BLE: Connect + Write auth token
    BLE-->>APP: Auth OK

    Note over APP,BLE: Send OCR text (BLE)
    APP->>BLE: OCR text (chunked)
    BLE->>BR: Forward payload
    BR->>LLM: POST /extract-and-query {ocr_text}
    LLM-->>BR: {item_name, confidence, api_query}

    Note over BR,G: Check inventory
    BR->>G: GET /items/search?q=item_name
    G->>S: Search catalog
    S-->>G: {exists: true/false, item_id?, barcode?}

    alt Item exists
        G-->>BR: {exists:true, item_id, barcode}
        BR->>P: Print label {item_name, barcode, template}
        P-->>BR: printed: ok
        BR-->>APP: Ack {status:"printed", barcode}
    else Item does not exist
        G-->>BR: {exists:false}
        BR->>B: POST /barcodes (request new)
        B-->>BR: {barcode:new_code}
        BR->>G: POST /barcodes/map {item_id?, barcode}
        G-->>BR: {mapped:true}
        BR->>P: Print label {item_name, barcode:new_code}
        P-->>BR: printed: ok
        BR-->>APP: Ack {status:"printed_new", barcode:new_code}
    end

    Note over BR,G: Audit and telemetry (async)
    BR-->>G: POST /events/print_job {result, ids}

```
