import json
import logging
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import paho.mqtt.client as mqtt
import requests
from llama_cpp import Llama

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="[llm-agent] %(asctime)s %(levelname)s: %(message)s",
)
logger = logging.getLogger("llm-agent")


@dataclass
class Settings:
    model_path: Path = Path(os.getenv("LLM_MODEL_PATH", "/models/tinyllama.gguf"))
    llm_max_tokens: int = int(os.getenv("LLM_MAX_TOKENS", "64"))
    llm_context: int = int(os.getenv("LLM_CONTEXT_SIZE", "1024"))
    llm_temperature: float = float(os.getenv("LLM_TEMPERATURE", "0.0"))
    llm_threads: Optional[int] = (
        int(os.getenv("LLM_THREADS")) if os.getenv("LLM_THREADS") else None
    )
    prompt_template: str = os.getenv(
        "LLM_PROMPT",
        ("You are an expert inventory assistant. Given the following JSON payload, "
         "return the most likely product name as a concise noun phrase. "
         "Respond with only the product name, no extra words.\n\nPayload: {payload}\n\nProduct:"),
    )
    local_host: str = os.getenv("LOCAL_MQTT_HOST", "mqtt_broker")
    local_port: int = int(os.getenv("LOCAL_MQTT_PORT", "1883"))
    local_topic: str = os.getenv("LOCAL_MQTT_TOPIC", "lobby/lift/packages")
    local_username: Optional[str] = os.getenv("LOCAL_MQTT_USERNAME")
    local_password: Optional[str] = os.getenv("LOCAL_MQTT_PASSWORD")
    remote_host: str = os.getenv("REMOTE_MQTT_HOST", "broker.hivemq.com")
    remote_port: int = int(os.getenv("REMOTE_MQTT_PORT", "1883"))
    remote_topic: str = os.getenv("REMOTE_MQTT_TOPIC", "lift/lobby/status")
    remote_username: Optional[str] = os.getenv("REMOTE_MQTT_USERNAME")
    remote_password: Optional[str] = os.getenv("REMOTE_MQTT_PASSWORD")
    ims_base: str = os.getenv("IMS_API_BASE", "https://ims.example.com")
    ims_timeout: int = int(os.getenv("IMS_TIMEOUT_SECONDS", "10"))
    ims_api_key: Optional[str] = os.getenv("IMS_API_KEY")
    ims_auth_token: Optional[str] = os.getenv("IMS_AUTH_TOKEN")


SETTINGS = Settings()


def load_llm() -> Llama:
    if not SETTINGS.model_path.exists():
        raise FileNotFoundError(
            f"LLM model not found at {SETTINGS.model_path}. Mount a GGUF model into /models."
        )

    kwargs: Dict[str, Any] = {
        "model_path": str(SETTINGS.model_path),
        "n_ctx": SETTINGS.llm_context,
        "n_threads": SETTINGS.llm_threads,
    }

    logger.info(
        "Loading LLM model from %s (ctx=%s, threads=%s)",
        SETTINGS.model_path,
        SETTINGS.llm_context,
        SETTINGS.llm_threads or "auto",
    )
    llm = Llama(**{k: v for k, v in kwargs.items() if v is not None})
    logger.info("LLM loaded")
    return llm


LLM = None


def ensure_llm() -> Llama:
    global LLM
    if LLM is None:
        LLM = load_llm()
    return LLM


def llm_extract_product(payload: Dict[str, Any]) -> str:
    llm = ensure_llm()
    prompt = SETTINGS.prompt_template.format(payload=json.dumps(payload, ensure_ascii=False))
    logger.debug("Prompting LLM with payload: %s", prompt)

    output = llm(
        prompt,
        max_tokens=SETTINGS.llm_max_tokens,
        temperature=SETTINGS.llm_temperature,
        stop=["\n"],
    )
    choice = output["choices"][0]["text"].strip()
    logger.info("LLM extracted product name: %s", choice)
    return choice


session = requests.Session()

if SETTINGS.ims_api_key:
    session.headers["x-api-key"] = SETTINGS.ims_api_key
if SETTINGS.ims_auth_token:
    session.headers["Authorization"] = SETTINGS.ims_auth_token


def query_inventory(product_name: str) -> Tuple[bool, Dict[str, Any]]:
    if not product_name:
        return False, {"reason": "empty product name"}

    url = SETTINGS.ims_base.rstrip("/") + "/items/search"
    try:
        resp = session.get(url, params={"q": product_name}, timeout=SETTINGS.ims_timeout)
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:  # broad to ensure robust logging
        logger.warning("IMS query failed: %s", exc)
        return False, {"error": str(exc)}

    items = None
    if isinstance(data, dict):
        for key in ("items", "results", "data"):
            if isinstance(data.get(key), list):
                items = data[key]
                break
    elif isinstance(data, list):
        items = data

    exists = bool(items)
    logger.info(
        "IMS lookup for '%s' -> %s (items=%s)", product_name, "FOUND" if exists else "NOT FOUND", items
    )
    return exists, {"items": items, "raw": data}


class InventoryAgent:
    def __init__(self) -> None:
        self.remote_client = mqtt.Client(client_id="llm-agent-remote")
        if SETTINGS.remote_username:
            self.remote_client.username_pw_set(SETTINGS.remote_username, SETTINGS.remote_password)

        self.remote_client.on_connect = self._on_remote_connect
        self.remote_client.on_disconnect = self._on_remote_disconnect

        self.local_client = mqtt.Client(client_id="llm-agent-local")
        if SETTINGS.local_username:
            self.local_client.username_pw_set(SETTINGS.local_username, SETTINGS.local_password)

        self.local_client.on_connect = self._on_local_connect
        self.local_client.on_message = self._on_local_message
        self.local_client.on_disconnect = self._on_local_disconnect

    def start(self) -> None:
        self._connect_remote()
        self.remote_client.loop_start()
        self._connect_local()
        self.local_client.loop_forever()

    # --- MQTT callbacks ---
    def _connect_remote(self) -> None:
        while True:
            try:
                self.remote_client.connect(SETTINGS.remote_host, SETTINGS.remote_port, keepalive=60)
                logger.info("Connected to remote MQTT %s:%s", SETTINGS.remote_host, SETTINGS.remote_port)
                return
            except Exception as exc:
                logger.warning("Remote MQTT connect failed: %s", exc)
                time.sleep(5)

    def _connect_local(self) -> None:
        while True:
            try:
                self.local_client.connect(SETTINGS.local_host, SETTINGS.local_port, keepalive=60)
                logger.info("Connected to local MQTT %s:%s", SETTINGS.local_host, SETTINGS.local_port)
                return
            except Exception as exc:
                logger.warning("Local MQTT connect failed: %s", exc)
                time.sleep(3)

    @staticmethod
    def _on_remote_connect(client: mqtt.Client, _userdata, flags, rc):
        logger.info("Remote MQTT connected rc=%s", rc)

    @staticmethod
    def _on_remote_disconnect(client: mqtt.Client, userdata, rc):
        logger.warning("Remote MQTT disconnected rc=%s", rc)

    def _on_local_connect(self, client: mqtt.Client, _userdata, flags, rc):
        if rc == 0:
            logger.info("Subscribed to local topic %s", SETTINGS.local_topic)
            client.subscribe(SETTINGS.local_topic)
        else:
            logger.error("Local MQTT connect failed rc=%s", rc)

    def _on_local_disconnect(self, client: mqtt.Client, userdata, rc):
        logger.warning("Local MQTT disconnected rc=%s", rc)

    def _on_local_message(self, client: mqtt.Client, _userdata, msg: mqtt.MQTTMessage):
        payload_text = msg.payload.decode(errors="ignore").strip()
        logger.info("Message received on %s: %s", msg.topic, payload_text[:200])
        try:
            payload = json.loads(payload_text) if payload_text else {}
        except json.JSONDecodeError:
            payload = {"raw": payload_text}

        try:
            product_name = llm_extract_product(payload)
        except Exception as exc:
            logger.error("LLM extraction failed: %s", exc)
            product_name = fallback_product_name(payload)
            logger.info("Fallback product name: %s", product_name)

        exists, metadata = query_inventory(product_name)
        status_message = {
            "product": product_name,
            "exists": exists,
            "items": metadata.get("items"),
        }
        status_payload = json.dumps(status_message)
        result = self.remote_client.publish(
            SETTINGS.remote_topic,
            payload=status_payload,
            qos=1,
            retain=False,
        )
        if result.rc == mqtt.MQTT_ERR_SUCCESS:
            logger.info(
                "Published status '%s' to remote topic %s",
                "found product" if exists else "no product",
                SETTINGS.remote_topic,
            )
        else:
            logger.error("Failed to publish to remote broker rc=%s", result.rc)


def fallback_product_name(payload: Dict[str, Any]) -> str:
    """Fallback string heuristics when the LLM is unavailable."""
    if isinstance(payload, dict):
        for key in ("product_name", "productName", "name", "title"):
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        if "labelItems" in payload and isinstance(payload["labelItems"], list):
            for item in payload["labelItems"]:
                if (
                    isinstance(item, dict)
                    and item.get("labelType") == "text"
                    and isinstance(item.get("labelValue"), str)
                    and item["labelValue"].strip()
                ):
                    return item["labelValue"].strip()
    if isinstance(payload, str) and payload.strip():
        return payload.strip()
    return ""


def main() -> None:
    try:
        ensure_llm()
    except FileNotFoundError as exc:
        logger.error(exc)
        raise SystemExit(1)

    agent = InventoryAgent()
    agent.start()


if __name__ == "__main__":
    main()
