FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends \
      libusb-1.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY app.py /app/app.py

# libs needed by your print.py stack
RUN pip install --no-cache-dir \
    paho-mqtt \
    brother_ql \
    python-barcode \
    Pillow==9.5.0 \
    qrcode \
    pyusb


CMD ["python3", "/app/app.py"]
