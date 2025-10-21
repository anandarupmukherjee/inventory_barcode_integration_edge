#!/usr/bin/env python3
import os
import sys
import json
import time
from pathlib import Path

import barcode
from barcode.writer import ImageWriter
from PIL import Image, ImageDraw, ImageFont

# --- Pillow 10 compat: reintroduce Image.ANTIALIAS constant if missing ---
try:
    _ = Image.ANTIALIAS
except AttributeError:
    if hasattr(Image, "Resampling"):
        Image.ANTIALIAS = Image.Resampling.LANCZOS  # type: ignore
    elif hasattr(Image, "LANCZOS"):
        Image.ANTIALIAS = Image.LANCZOS  # type: ignore

import brother_ql
from brother_ql.raster import BrotherQLRaster
from brother_ql.backends.helpers import send

import QRPrint  # expects /code/QRPrint.py

# ----------------------------
# Configuration (via env vars)
# ----------------------------
MODEL = os.getenv("PRINTER_MODEL", "QL-700")
TAPE = os.getenv("PRINTER_TAPE", "62")  # DK-62mm continuous
IDENTIFIER = os.getenv("PRINTER_IDENTIFIER", "usb://0x04f9:0x2042")  # your QL-700 VID:PID
QR_OVERLAY_TEXT = os.getenv("QR_OVERLAY_TEXT", "Digital Hospitals").strip()
# Note: we DON'T pass backend kwarg to send(); usb:// implies pyusb backend in your install.

# Paths (match your mounted /code)
BASE = Path(os.getenv("CODE_BASE", "/code"))
BARCODES_DIR = BASE / "barcodes"
QR_DIR = BASE / "QR"
OUTPUT_DIR = BASE / "output"
FONTS_DIR = BASE / "fonts"
FONT_PATH = FONTS_DIR / "DejaVuSans-Bold.ttf"

# QL-700 62mm tape raster width in pixels (approx 696 px)
MAX_LABEL_WIDTH = 696

def ensure_dirs():
    for p in [BARCODES_DIR, QR_DIR, OUTPUT_DIR]:
        p.mkdir(parents=True, exist_ok=True)

def log(msg: str):
    print(f"[print.py] {msg}", flush=True)

# -------------------------
# Image / label construction
# -------------------------
def create_barcode(id_str: str, output_stem: Path):
    opts = dict(
        module_height=10,
        quiet_zone=5,
        font_size=10,
        text_distance=1,
        background="white",
        foreground="black",
        center_text=False,
        format="PNG",
    )
    BC = barcode.get_barcode_class("code128")
    BC(str(id_str), writer=ImageWriter()).save(str(output_stem), opts)

def create_qr_text(value: str, output_stem: Path):
    qr = QRPrint.QRPrint()
    qr.makeLabelQR(value, str(output_stem) + ".png")

def overlay_text_on_qr(image: Image.Image, text: str) -> Image.Image:
    text = (text or "").strip()
    if not text:
        return image
    if image.mode != "RGB":
        image = image.convert("RGB")

    try:
        font_size = max(12, int(image.width * 0.08))
        font = ImageFont.truetype(str(FONT_PATH), font_size)
    except Exception:
        font = ImageFont.load_default()
        font_size = getattr(font, 'size', 12)

    dummy = Image.new("RGB", (image.width, image.height), "white")
    drawer = ImageDraw.Draw(dummy)
    if hasattr(drawer, "textbbox"):
        bbox = drawer.textbbox((0, 0), text, font=font)
        text_w = bbox[2] - bbox[0]
        text_h = bbox[3] - bbox[1]
    else:
        text_w, text_h = drawer.textsize(text, font=font)

    pad_y = max(6, int(font_size * 0.4))
    pad_x = max(4, int(font_size * 0.2))
    caption_height = text_h + pad_y * 2

    new_height = image.height + caption_height
    output = Image.new("RGB", (image.width, new_height), "white")
    output.paste(image, (0, 0))

    draw = ImageDraw.Draw(output)
    text_x = max(pad_x, (image.width - text_w) // 2)
    text_y = image.height + pad_y
    draw.text((text_x, text_y), text, fill="black", font=font)
    return output

def create_qr_aas(value: str, output_stem: Path):
    qr = QRPrint.QRPrint()
    qr.makeLabelAAS(value, str(output_stem) + ".png")

# --- constants for spacing ---
TOP_PAD = 8
LINE_GAP = 8
BOTTOM_PAD = 8
MAX_LABEL_WIDTH = 696  # QL-700 62mm

def create_label(barcode_items, text_items, qr_items, output_path: Path):
    log("Composing label image...")

    # load images
    barcode_imgs, qr_imgs = [], []
    max_barcode_w = 0
    max_qr_w = 0

    for it in barcode_items:
        img = Image.open(f"{it['imgPath']}.png")
        barcode_imgs.append(img)
        max_barcode_w = max(max_barcode_w, img.width)

    for it in qr_items:
        img = Image.open(f"{it['imgPath']}.png")
        img = overlay_text_on_qr(img, QR_OVERLAY_TEXT)
        qr_imgs.append(img)
        max_qr_w = max(max_qr_w, img.width)

    label_w = max(500, max_barcode_w, max_qr_w)
    label_w = min(label_w, MAX_LABEL_WIDTH)

    # fonts
    try:
        key_font = ImageFont.truetype(str(FONT_PATH), max(12, int(label_w / 10)))
        val_font = ImageFont.truetype(str(FONT_PATH), max(10, int(label_w / 18)))
    except Exception:
        key_font = ImageFont.load_default()
        val_font = ImageFont.load_default()

    # rough height estimate (we'll crop later anyway)
    def estimate_text_height():
        total = 0
        line_height = max(1, int(val_font.size * 1.2))
        for item in text_items:
            key = str(item.get("labelKey", "") or "").strip()
            val = str(item.get("labelValue", "") or "").strip()
            if not key and not val:
                continue
            if key:
                total += key_font.size
            if val:
                lines = val.splitlines() or [val]
                total += line_height * len(lines)
            if key or val:
                total += LINE_GAP
        return total

    text_block_h = estimate_text_height()
    est_h = text_block_h + sum(img.height + LINE_GAP for img in barcode_imgs + qr_imgs) + TOP_PAD + BOTTOM_PAD
    est_h = max(est_h, 200)

    # make canvas
    label = Image.new("RGB", (label_w, est_h), "white")
    draw = ImageDraw.Draw(label)

    # render
    y = TOP_PAD
    line_height = max(1, int(val_font.size * 1.2))

    for t in text_items:
        key = str(t.get("labelKey", "") or "").strip()
        val = str(t.get("labelValue", "") or "").strip()
        if not key and not val:
            continue
        if key:
            draw.text((10, y), key, fill="black", font=key_font)
            y += key_font.size
        if val:
            lines = val.splitlines() or [val]
            for line in lines:
                draw.text((10, y), line, fill="black", font=val_font)
                y += line_height
        if key or val:
            y += LINE_GAP

    def paste_center(img):
        nonlocal y
        # scale down if wider than tape
        if img.width > MAX_LABEL_WIDTH:
            r = MAX_LABEL_WIDTH / img.width
            img = img.resize((MAX_LABEL_WIDTH, max(1, int(img.height * r))), Image.ANTIALIAS)
        x = (label_w - img.width) // 2
        label.paste(img, (x, y))
        y += img.height + LINE_GAP

    for img in barcode_imgs:
        paste_center(img)
    for img in qr_imgs:
        paste_center(img)

    # hard crop to used content height
    used_h = min(y - LINE_GAP + BOTTOM_PAD, label.height)
    label = label.crop((0, 0, label_w, used_h))

    # final safety: ensure width <= MAX_LABEL_WIDTH
    if label.width > MAX_LABEL_WIDTH:
        r = MAX_LABEL_WIDTH / label.width
        label = label.resize((MAX_LABEL_WIDTH, max(1, int(label.height * r))), Image.ANTIALIAS)

    label.save(output_path)
    log(f"Label saved: {output_path} (w={label.width}, h={label.height})")

def send_to_printer(image_path: Path):
    """
    Convert PNG to Brother raster and send to printer.
    We don't pass backend=...; usb:// implies pyusb in your install.
    """
    printer = BrotherQLRaster(MODEL)
    log(f"Converting for model={MODEL}, tape={TAPE}, id={IDENTIFIER}")
    instructions = brother_ql.brother_ql_create.convert(
        printer,
        [str(image_path)],
        TAPE,
        dither=True,
        cut=True,          # request cut after each label
        rotate='auto'      # auto-rotate if needed
    )
    send(instructions, IDENTIFIER)
    log("Print sent")


# -------------------------
# Payload handling
# -------------------------
def process_payload(payload: dict):
    ensure_dirs()

    items = payload.get("labelItems", [])
    qty = int(payload.get("qty", 1))

    barcode_items, text_items, qr_items = [], [], []

    for it in items:
        ltype = it.get("labelType")
        key = str(it.get("labelKey", ""))
        val = str(it.get("labelValue", ""))

        if ltype == "barcode":
            stem = BARCODES_DIR / f"barcode-{key}-{val}"
            create_barcode(val, stem)
            it["imgPath"] = str(stem)
            barcode_items.append(it)
            log(f"Barcode created: {stem}.png")

        elif ltype == "QR":
            stem = QR_DIR / f"QR-{key}"
            create_qr_text(val, stem)
            it["imgPath"] = str(stem)
            qr_items.append(it)
            log(f"QR created: {stem}.png")

        elif ltype == "QRAAS":
            stem = QR_DIR / f"QR-{key}"
            create_qr_aas(val, stem)
            it["imgPath"] = str(stem)
            qr_items.append(it)
            log(f"AAS QR created: {stem}.png")

        elif ltype == "text":
            text_items.append(it)
            log(f"Text added: {key or '[text]'} -> {val}")

    label_png = OUTPUT_DIR / "label.png"
    create_label(barcode_items, text_items, qr_items, label_png)

    for i in range(qty):
        log(f"Printing copy {i+1}/{qty}")
        send_to_printer(label_png)
        time.sleep(0.4)

# -------------------------
# Main
# -------------------------
def read_payload_arg_or_stdin():
    if len(sys.argv) >= 2 and sys.argv[1].strip():
        return sys.argv[1]
    if not sys.stdin.isatty():
        return sys.stdin.read()
    print("Usage: python3 print.py '<json_payload>'", file=sys.stderr)
    sys.exit(1)

def main():
    try:
        raw = read_payload_arg_or_stdin()
        payload = json.loads(raw)
        log(f"Payload received: {str(payload)[:400]}")
        process_payload(payload)
    except json.JSONDecodeError as e:
        log(f"JSON error: {e}")
        sys.exit(2)
    except Exception as e:
        log(f"Error: {e}")
        sys.exit(3)

if __name__ == "__main__":
    main()
