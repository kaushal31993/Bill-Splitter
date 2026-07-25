"""Receipt extraction.

An uploaded photo or PDF is sent to a Claude vision model, which returns the
line items as structured JSON. This is deliberately *not* traditional OCR:
receipts are exactly the case where glyph-level OCR struggles — multi-column
layouts, abbreviated item names, prices detached from the names they belong to —
and a vision model does well, because it reads the layout rather than the pixels.

Extraction is never trusted blindly. The caller lands on a review screen with
every extracted item editable, and the running subtotal compared against the
extracted total. A failure here is recoverable: the bill is still created, empty,
and the user falls back to manual entry rather than losing the upload.
"""

from __future__ import annotations

import base64
import datetime as dt
import io
import json
import logging
import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation

from .config import get_settings
from .money import to_cents

log = logging.getLogger(__name__)

# Claude's supported image types. HEIC (the iPhone default) is not among them,
# so it is converted to JPEG on the way in.
IMAGE_MEDIA_TYPES = {
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "png": "image/png",
    "gif": "image/gif",
    "webp": "image/webp",
}
HEIC_EXTENSIONS = {"heic", "heif"}
PDF_EXTENSIONS = {"pdf"}

SUPPORTED_EXTENSIONS = set(IMAGE_MEDIA_TYPES) | HEIC_EXTENSIONS | PDF_EXTENSIONS

# Claude Opus 5 sits in the high-resolution vision tier: 2576px on the long
# edge. Anything larger costs tokens without adding readable detail.
MAX_IMAGE_EDGE = 2576

RECEIPT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "merchant",
        "bill_date",
        "items",
        "subtotal",
        "tax",
        "tip",
        "fee",
        "discount",
        "total",
    ],
    "properties": {
        "merchant": {
            "type": "string",
            "description": "Merchant or restaurant name. Empty string if not visible.",
        },
        "bill_date": {
            "type": "string",
            "description": "Date on the receipt as MM/DD/YYYY. Empty string if not visible.",
        },
        "items": {
            "type": "array",
            "description": "Every purchased line item, in the order printed on the receipt. "
            "Do not include subtotal, tax, tip, discount, or total rows here.",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["name", "quantity", "unit_price", "total"],
                "properties": {
                    "name": {"type": "string", "description": "Item name as printed."},
                    "quantity": {
                        "type": "number",
                        "description": "Quantity. Use 1 when the receipt does not show one.",
                    },
                    "unit_price": {
                        "type": "number",
                        "description": "Price for a single unit, in dollars.",
                    },
                    "total": {
                        "type": "number",
                        "description": "Line total in dollars (quantity x unit price).",
                    },
                },
            },
        },
        "subtotal": {"type": "number", "description": "Subtotal before tax and tip. 0 if absent."},
        "tax": {"type": "number", "description": "Total tax. 0 if absent."},
        "tip": {"type": "number", "description": "Tip or gratuity. 0 if absent."},
        "fee": {
            "type": "number",
            "description": "Service charges, delivery or other fees, combined. 0 if absent.",
        },
        "discount": {
            "type": "number",
            "description": "Total discounts, savings, coupons, or credits, as a POSITIVE "
            "number. 0 if absent.",
        },
        "total": {"type": "number", "description": "Grand total charged. 0 if absent."},
    },
}

SYSTEM_PROMPT = """You transcribe receipts and invoices into structured data.

Rules:
- Transcribe only what is actually printed. Never invent an item, a price, or a date.
- List every purchased line item in printed order. Exclude subtotal, tax, tip,
  discount, and total rows from the items array — those have their own fields.
- Amounts are in US dollars as plain numbers: 12.99, not "$12.99".
- Item prices are what was actually charged. If the receipt shows a regular
  price struck through next to a lower price, use the lower one.
- Put savings, coupons, and credits in `discount` as a positive number — never
  as a negative line item.
- The line items plus tax, tip, and fees, minus the discount, should equal the
  printed total. If they don't, re-read the receipt before answering.
- If a value is unreadable or absent, use 0 for numbers and "" for strings rather
  than guessing.
- A modifier printed under an item with its own price (extra cheese, add bacon)
  is its own line item.
- If the receipt shows a quantity greater than 1, set quantity and unit_price so
  that quantity x unit_price equals the line total."""


class ExtractionError(Exception):
    """Extraction could not produce usable data. Recoverable — the caller falls
    back to manual entry."""


@dataclass
class ExtractedItem:
    name: str
    quantity: int
    unit_price_cents: int
    total_cents: int


@dataclass
class ExtractedReceipt:
    merchant: str | None = None
    bill_date: dt.date | None = None
    items: list[ExtractedItem] = field(default_factory=list)
    subtotal_cents: int = 0
    tax_cents: int = 0
    tip_cents: int = 0
    fee_cents: int = 0
    discount_cents: int = 0
    total_cents: int = 0


def classify(filename: str) -> str:
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext in PDF_EXTENSIONS:
        return "pdf"
    if ext in HEIC_EXTENSIONS or ext in IMAGE_MEDIA_TYPES:
        return "image"
    raise ExtractionError(
        f"Unsupported file type '.{ext}'. Upload a JPG, PNG, WEBP, GIF, HEIC, or PDF."
    )


def _sniff_kind(data: bytes, filename: str) -> str:
    """Validate by content, not by extension — a .png that is really a PDF
    should be treated as a PDF, and an executable renamed to .jpg rejected."""
    if data[:5] == b"%PDF-":
        return "pdf"
    if data[:3] == b"\xff\xd8\xff":
        return "image"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image"
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return "image"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image"
    if data[4:12] in (b"ftypheic", b"ftypheix", b"ftyphevc", b"ftypmif1", b"ftypmsf1"):
        return "image"
    raise ExtractionError(
        "That file does not look like an image or a PDF. Upload a photo or PDF of the receipt."
    )


def _prepare_image(data: bytes) -> tuple[str, str]:
    """Normalize any supported image to a base64 JPEG/PNG Claude can read.

    Applies EXIF orientation — phone photos are routinely stored sideways with a
    rotation flag, and a sideways receipt extracts badly — and downscales to the
    model's high-resolution ceiling.
    """
    from PIL import Image, ImageOps

    try:
        import pillow_heif

        pillow_heif.register_heif_opener()
    except Exception:  # pragma: no cover - HEIC support is best effort
        log.warning("pillow-heif unavailable; HEIC uploads will fail")

    try:
        img = Image.open(io.BytesIO(data))
        img = ImageOps.exif_transpose(img)
        if img.mode not in ("RGB", "L"):
            img = img.convert("RGB")
        if max(img.size) > MAX_IMAGE_EDGE:
            img.thumbnail((MAX_IMAGE_EDGE, MAX_IMAGE_EDGE), Image.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=90)
    except ExtractionError:
        raise
    except Exception as exc:
        raise ExtractionError(f"Could not read that image: {exc}") from exc

    return base64.standard_b64encode(buf.getvalue()).decode("ascii"), "image/jpeg"


MAX_TEXT_CHARS = 120_000
MIN_TEXT_LAYER_CHARS = 200


def pdf_text_layer(data: bytes) -> str | None:
    """Return a digitally generated PDF's embedded text, or None.

    This is the single biggest cost lever. Sent as a `document` block, a PDF is
    rasterised page-by-page and billed as images; the same receipt sent as text
    costs roughly an order of magnitude less. Emailed and app-generated receipts
    (Instacart, Amazon, most invoices) all carry a clean text layer. Scans do
    not, and fall through to the vision path.
    """
    try:
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(data))
        pages = [(page.extract_text() or "") for page in reader.pages[:50]]
    except Exception as exc:  # pragma: no cover - malformed PDFs fall back
        log.info("No usable PDF text layer (%s); falling back to vision", exc)
        return None

    text = "\n".join(pages).strip()
    if len(text) < MIN_TEXT_LAYER_CHARS:
        return None
    # A text layer with no digits is not a receipt we can read.
    if not any(ch.isdigit() for ch in text):
        return None
    return text[:MAX_TEXT_CHARS]


def _build_content(data: bytes, filename: str) -> tuple[list[dict], str]:
    """Returns the message content plus the path taken, for logging."""
    kind = _sniff_kind(data, filename)
    instruction = {
        "type": "text",
        "text": "Transcribe this receipt into the required structure.",
    }

    if kind == "pdf":
        if get_settings().prefer_pdf_text_layer:
            text = pdf_text_layer(data)
            if text:
                return (
                    [
                        {
                            "type": "text",
                            "text": "Text extracted from the receipt PDF:\n\n<receipt>\n"
                            f"{text}\n</receipt>",
                        },
                        instruction,
                    ],
                    "pdf-text",
                )

        # Scanned or image-only PDF: Claude reads these natively, no separate
        # rasterisation step needed.
        return (
            [
                {
                    "type": "document",
                    "source": {
                        "type": "base64",
                        "media_type": "application/pdf",
                        "data": base64.standard_b64encode(data).decode("ascii"),
                    },
                },
                instruction,
            ],
            "pdf-vision",
        )

    b64, media_type = _prepare_image(data)
    return (
        [
            {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": b64}},
            instruction,
        ],
        "image",
    )


# Published per-million-token rates, for the cost line in the logs. A model
# that isn't listed simply logs token counts without a dollar estimate.
PRICING = {
    "claude-haiku-4-5": (1.00, 5.00),
    "claude-sonnet-5": (3.00, 15.00),
    "claude-sonnet-4-6": (3.00, 15.00),
    "claude-opus-5": (5.00, 25.00),
    "claude-opus-4-8": (5.00, 25.00),
    "claude-opus-4-7": (5.00, 25.00),
}


def _log_usage(model: str, path: str, usage) -> None:
    if usage is None:
        return
    inp = getattr(usage, "input_tokens", 0) or 0
    out = getattr(usage, "output_tokens", 0) or 0
    rates = PRICING.get(model)
    if rates:
        cost = (inp / 1_000_000) * rates[0] + (out / 1_000_000) * rates[1]
        log.info(
            "Extraction via %s [%s]: %d in / %d out tokens ≈ $%.4f",
            model, path, inp, out, cost,
        )
    else:
        log.info("Extraction via %s [%s]: %d in / %d out tokens", model, path, inp, out)


def _supports_effort(model: str) -> bool:
    """`effort` is rejected by the 4.5-generation models."""
    return "haiku-4-5" not in model and "sonnet-4-5" not in model


# Server-side refusal fallbacks exist only on the frontier models; every other
# model rejects the parameter outright with a 400.
FALLBACK_MODELS = ("claude-opus-5", "claude-fable-5", "claude-mythos-5")


def _supports_fallbacks(model: str) -> bool:
    return model in FALLBACK_MODELS


def _first_text(response) -> str:
    for block in response.content:
        if getattr(block, "type", None) == "text":
            return block.text
    raise ExtractionError("The model returned no readable text.")


def _parse_json(text: str) -> dict:
    """Parse the model's JSON, tolerating a stray code fence.

    ``parse_float=Decimal`` matters: it keeps 19.99 exact all the way to the
    cents conversion instead of routing it through a binary float.
    """
    candidate = text.strip()
    fence = re.match(r"^```(?:json)?\s*(.*?)\s*```$", candidate, re.DOTALL)
    if fence:
        candidate = fence.group(1)
    try:
        return json.loads(candidate, parse_float=Decimal)
    except json.JSONDecodeError:
        start, end = candidate.find("{"), candidate.rfind("}")
        if start != -1 and end > start:
            try:
                return json.loads(candidate[start : end + 1], parse_float=Decimal)
            except json.JSONDecodeError:
                pass
    raise ExtractionError("The model's response was not valid JSON.")


def _money(value) -> int:
    if value in (None, ""):
        return 0
    try:
        return to_cents(value)
    except (ValueError, InvalidOperation):
        return 0


def _parse_date(value: str) -> dt.date | None:
    value = (value or "").strip()
    if not value:
        return None
    for fmt in ("%m/%d/%Y", "%Y-%m-%d", "%m/%d/%y", "%m-%d-%Y"):
        try:
            return dt.datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    return None


def _to_receipt(payload: dict) -> ExtractedReceipt:
    items: list[ExtractedItem] = []
    for raw in payload.get("items") or []:
        if not isinstance(raw, dict):
            continue
        name = str(raw.get("name") or "").strip() or "Item"
        try:
            quantity = max(1, int(Decimal(str(raw.get("quantity") or 1))))
        except (ValueError, InvalidOperation):
            quantity = 1
        unit = _money(raw.get("unit_price"))
        total = _money(raw.get("total"))
        # Reconcile the two: whichever is missing is derived from the other.
        if total == 0 and unit != 0:
            total = unit * quantity
        if unit == 0 and total != 0 and quantity:
            unit = total // quantity
        items.append(
            ExtractedItem(
                name=name[:300], quantity=quantity, unit_price_cents=unit, total_cents=total
            )
        )

    return ExtractedReceipt(
        merchant=(str(payload.get("merchant") or "").strip() or None),
        bill_date=_parse_date(str(payload.get("bill_date") or "")),
        items=items,
        subtotal_cents=_money(payload.get("subtotal")),
        tax_cents=_money(payload.get("tax")),
        tip_cents=_money(payload.get("tip")),
        fee_cents=_money(payload.get("fee")),
        discount_cents=abs(_money(payload.get("discount"))),
        total_cents=_money(payload.get("total")),
    )


def extract_receipt(data: bytes, filename: str) -> ExtractedReceipt:
    """Extract a receipt. Raises ExtractionError on any recoverable failure."""
    settings = get_settings()
    if not settings.extraction_enabled:
        raise ExtractionError(
            "Automatic extraction is off because ANTHROPIC_API_KEY is not set. "
            "Add the items by hand, or set the key and re-upload."
        )

    classify(filename)  # rejects obviously wrong extensions early
    content, path = _build_content(data, filename)

    import anthropic

    client = anthropic.Anthropic(api_key=settings.anthropic_api_key, max_retries=2, timeout=180.0)

    model = settings.extraction_model

    output_config: dict = {"format": {"type": "json_schema", "schema": RECEIPT_SCHEMA}}
    if settings.extraction_effort and _supports_effort(model):
        output_config["effort"] = settings.extraction_effort

    extra: dict = {}
    if _supports_fallbacks(model):
        # Safety classifiers can decline a request; "default" re-serves it on
        # Anthropic's recommended fallback model rather than failing outright.
        extra["betas"] = ["server-side-fallback-2026-07-01"]
        extra["fallbacks"] = "default"

    try:
        response = client.beta.messages.create(
            model=model,
            max_tokens=16000,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": content}],
            output_config=output_config,
            **extra,
        )
    except anthropic.APIStatusError as exc:
        # Surface the API's own message. A bare status code sends the user
        # hunting through logs for something the response already explained
        # (an expired key, an exhausted credit balance, a rate limit).
        detail = ""
        body = getattr(exc, "body", None)
        if isinstance(body, dict):
            detail = str((body.get("error") or {}).get("message") or "").strip()
        log.error(
            "Extraction API error %s (request_id=%s): %s",
            exc.status_code,
            getattr(exc, "request_id", None),
            detail or exc,
        )

        if exc.status_code == 401:
            raise ExtractionError(
                "The extraction service rejected ANTHROPIC_API_KEY. Check the key in .env."
            ) from exc
        if exc.status_code == 429:
            raise ExtractionError(
                "Rate limited by the extraction service. Wait a moment and re-upload."
            ) from exc
        raise ExtractionError(
            detail or f"Extraction service error ({exc.status_code})."
        ) from exc
    except anthropic.APIConnectionError as exc:
        log.error("Extraction connection error: %s", exc)
        raise ExtractionError(
            "Could not reach the extraction service. Check this machine's network access."
        ) from exc

    _log_usage(settings.extraction_model, path, getattr(response, "usage", None))

    if response.stop_reason == "refusal":
        raise ExtractionError("The extraction service declined to process that file.")
    if response.stop_reason == "max_tokens":
        raise ExtractionError("That receipt was too long to transcribe in one pass.")

    return _to_receipt(_parse_json(_first_text(response)))
