"""Extraction unit tests.

The network call itself isn't exercised here — these cover the parts that are
pure logic (file sniffing, JSON tolerance, dollars-to-cents reconciliation) plus
the error path, which is where a bad experience is most likely to leak through.
"""

import io
from decimal import Decimal

import httpx
import pytest
from PIL import Image

from app import extraction
from app.extraction import (
    ExtractionError,
    _parse_json,
    _sniff_kind,
    _to_receipt,
    classify,
    extract_receipt,
)

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
JPEG_HEADER = b"\xff\xd8\xff\xe0" + b"\x00" * 32
PDF = b"%PDF-1.7\n" + b"\x00" * 32


def real_jpeg() -> bytes:
    """A genuinely decodable JPEG — the error-path tests have to get past
    image preparation before they can reach the API call."""
    buf = io.BytesIO()
    Image.new("RGB", (24, 16), "white").save(buf, format="JPEG")
    return buf.getvalue()


class TestClassify:
    @pytest.mark.parametrize("name", ["a.jpg", "a.JPEG", "a.png", "a.webp", "a.heic", "a.pdf"])
    def test_accepts_supported_types(self, name):
        assert classify(name) in {"image", "pdf"}

    @pytest.mark.parametrize("name", ["a.txt", "a.docx", "a.exe", "noextension"])
    def test_rejects_others(self, name):
        with pytest.raises(ExtractionError, match="Unsupported file type|Upload a JPG"):
            classify(name)


class TestSniff:
    def test_detects_by_content_not_extension(self):
        # A PDF renamed to .jpg is still a PDF.
        assert _sniff_kind(PDF, "receipt.jpg") == "pdf"
        assert _sniff_kind(PNG, "receipt.pdf") == "image"
        assert _sniff_kind(JPEG_HEADER, "x") == "image"

    def test_rejects_content_that_is_neither(self):
        with pytest.raises(ExtractionError, match="does not look like"):
            _sniff_kind(b"#!/bin/sh\nrm -rf /", "receipt.jpg")


class TestParseJson:
    def test_plain(self):
        assert _parse_json('{"a": 1}') == {"a": 1}

    def test_tolerates_code_fence(self):
        assert _parse_json('```json\n{"a": 1}\n```') == {"a": 1}
        assert _parse_json('```\n{"a": 1}\n```') == {"a": 1}

    def test_tolerates_surrounding_prose(self):
        assert _parse_json('Here you go:\n{"a": 1}\nHope that helps.') == {"a": 1}

    def test_floats_parse_as_decimal(self):
        # Exactness matters: 19.99 must not arrive as 19.989999999999998.
        assert _parse_json('{"total": 19.99}')["total"] == Decimal("19.99")

    def test_raises_on_garbage(self):
        with pytest.raises(ExtractionError, match="not valid JSON"):
            _parse_json("no json here at all")


class TestToReceipt:
    def test_converts_dollars_to_exact_cents(self):
        r = _to_receipt(
            {
                "merchant": "Osteria",
                "bill_date": "07/18/2026",
                "items": [{"name": "Pizza", "quantity": 1, "unit_price": 22.99, "total": 22.99}],
                "subtotal": 22.99,
                "tax": 1.15,
                "tip": 4.6,
                "fee": 0,
                "total": 28.74,
            }
        )
        assert r.merchant == "Osteria"
        assert r.bill_date.isoformat() == "2026-07-18"
        assert r.items[0].total_cents == 2299
        assert r.tax_cents == 115
        assert r.tip_cents == 460
        assert r.total_cents == 2874

    def test_derives_line_total_from_unit_price(self):
        r = _to_receipt({"items": [{"name": "Beer", "quantity": 3, "unit_price": 6.5}]})
        assert r.items[0].total_cents == 1950

    def test_derives_unit_price_from_line_total(self):
        r = _to_receipt({"items": [{"name": "Beer", "quantity": 2, "total": 13.0}]})
        assert r.items[0].unit_price_cents == 650

    def test_survives_missing_and_malformed_fields(self):
        r = _to_receipt(
            {
                "merchant": "",
                "bill_date": "not a date",
                "items": [{}, "junk", {"name": "OK", "total": "3.25"}],
            }
        )
        assert r.merchant is None
        assert r.bill_date is None
        # The junk string is skipped; the empty object still yields a row.
        assert [i.name for i in r.items] == ["Item", "OK"]
        assert r.items[1].total_cents == 325

    def test_empty_payload(self):
        r = _to_receipt({})
        assert r.items == []
        assert r.total_cents == 0


class TestErrorSurfacing:
    """A status code alone sends the user hunting through logs for something
    the API response already explained."""

    def _run_with_error(self, monkeypatch, status: int, message: str) -> str:
        import anthropic

        class Settings:
            extraction_enabled = True
            anthropic_api_key = "sk-test"
            extraction_model = "claude-opus-5"
            extraction_effort = "low"
            prefer_pdf_text_layer = True

        monkeypatch.setattr(extraction, "get_settings", lambda: Settings())

        request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
        body = {"type": "error", "error": {"type": "invalid_request_error", "message": message}}
        response = httpx.Response(status, request=request, json=body)

        class FakeMessages:
            def create(self, **_kwargs):
                raise anthropic.APIStatusError(message, response=response, body=body)

        class FakeClient:
            def __init__(self, **_kwargs):
                self.beta = type("Beta", (), {"messages": FakeMessages()})()

        monkeypatch.setattr(anthropic, "Anthropic", FakeClient)

        with pytest.raises(ExtractionError) as exc:
            extract_receipt(real_jpeg(), "receipt.jpg")
        return str(exc.value)

    def test_passes_through_the_api_message(self, monkeypatch):
        detail = "Your credit balance is too low to access the Anthropic API."
        assert detail in self._run_with_error(monkeypatch, 400, detail)

    def test_names_the_key_on_401(self, monkeypatch):
        assert "ANTHROPIC_API_KEY" in self._run_with_error(monkeypatch, 401, "authentication_error")

    def test_explains_rate_limiting_on_429(self, monkeypatch):
        assert "Rate limited" in self._run_with_error(monkeypatch, 429, "rate_limit_error")


class TestDisabled:
    def test_says_why_when_no_key_is_configured(self, monkeypatch):
        class Settings:
            extraction_enabled = False
            anthropic_api_key = ""
            extraction_model = "claude-opus-5"
            extraction_effort = "low"
            prefer_pdf_text_layer = True

        monkeypatch.setattr(extraction, "get_settings", lambda: Settings())
        with pytest.raises(ExtractionError, match="ANTHROPIC_API_KEY is not set"):
            extract_receipt(real_jpeg(), "receipt.jpg")


class TestPdfTextLayer:
    """Reading a digital PDF's text layer instead of shipping page images is
    the difference between cents and fractions of a cent per receipt."""

    def test_returns_none_for_a_pdf_with_no_text_layer(self):
        assert extraction.pdf_text_layer(PDF) is None

    def test_returns_none_for_garbage(self):
        assert extraction.pdf_text_layer(b"not a pdf at all") is None

    def test_requires_digits_to_look_like_a_receipt(self, monkeypatch):
        class FakePage:
            def extract_text(self):
                return "lorem ipsum " * 40  # long, but no digits

        class FakeReader:
            def __init__(self, _stream):
                self.pages = [FakePage()]

        import pypdf

        monkeypatch.setattr(pypdf, "PdfReader", FakeReader)
        assert extraction.pdf_text_layer(PDF) is None

    def test_uses_the_text_layer_when_present(self, monkeypatch):
        class FakePage:
            def extract_text(self):
                return "WALMART\nBananas 1.29\nMilk 3.49\nSubtotal 4.78\nTax 0.34\n" * 6

        class FakeReader:
            def __init__(self, _stream):
                self.pages = [FakePage()]

        import pypdf

        monkeypatch.setattr(pypdf, "PdfReader", FakeReader)
        text = extraction.pdf_text_layer(PDF)
        assert text is not None and "Bananas 1.29" in text

    def test_build_content_prefers_text_over_images(self, monkeypatch):
        class Settings:
            prefer_pdf_text_layer = True

        monkeypatch.setattr(extraction, "get_settings", lambda: Settings())
        monkeypatch.setattr(extraction, "pdf_text_layer", lambda _d: "WALMART\nMilk 3.49\n")

        content, path = extraction._build_content(PDF, "receipt.pdf")
        assert path == "pdf-text"
        assert all(block["type"] == "text" for block in content)
        assert "Milk 3.49" in content[0]["text"]

    def test_build_content_falls_back_to_the_document_block(self, monkeypatch):
        class Settings:
            prefer_pdf_text_layer = True

        monkeypatch.setattr(extraction, "get_settings", lambda: Settings())
        monkeypatch.setattr(extraction, "pdf_text_layer", lambda _d: None)

        content, path = extraction._build_content(PDF, "scan.pdf")
        assert path == "pdf-vision"
        assert content[0]["type"] == "document"


class TestEffortGating:
    @pytest.mark.parametrize(
        "model,expected",
        [
            ("claude-opus-5", True),
            ("claude-sonnet-5", True),
            ("claude-haiku-4-5", False),
            ("claude-sonnet-4-5", False),
        ],
    )
    def test_effort_is_only_sent_to_models_that_accept_it(self, model, expected):
        # The 4.5 generation rejects `effort` outright, so sending it there
        # would turn a cost optimisation into a hard 400.
        assert extraction._supports_effort(model) is expected


class TestFallbackGating:
    @pytest.mark.parametrize(
        "model,expected",
        [
            ("claude-opus-5", True),
            ("claude-fable-5", True),
            ("claude-haiku-4-5", False),
            ("claude-sonnet-5", False),
            ("claude-opus-4-8", False),
        ],
    )
    def test_fallbacks_only_go_to_models_that_accept_them(self, model, expected):
        # Sending `fallbacks` to a model that doesn't support it is a hard 400,
        # so a cheaper-model swap would break extraction outright.
        assert extraction._supports_fallbacks(model) is expected
