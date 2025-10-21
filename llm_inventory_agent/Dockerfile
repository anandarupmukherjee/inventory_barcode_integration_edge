FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends \
      build-essential \
      cmake \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py /app/app.py

ENV LLM_MODEL_PATH=/models/tinyllama.gguf \
    LOCAL_MQTT_HOST=mqtt_broker \
    LOCAL_MQTT_PORT=1883 \
    LOCAL_MQTT_TOPIC=lobby/lift/packages \
    REMOTE_MQTT_HOST=broker.hivemq.com \
    REMOTE_MQTT_PORT=1883 \
    REMOTE_MQTT_TOPIC=lift/lobby/status \
    IMS_API_BASE=https://ims.example.com \
    IMS_TIMEOUT_SECONDS=10 \
    LLM_MAX_TOKENS=64 \
    LLM_CONTEXT_SIZE=1024

CMD ["python3", "/app/app.py"]
