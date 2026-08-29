"""Catalog extraction: the one job in this system a language model is genuinely better at.

A merchant's price list is a PDF that was a spreadsheet that was a WhatsApp message. Rates
are quoted per box on one line and per piece on the next. A footnote three inches below the
table revises a price. Two columns interleave the moment anything reads them linearly. There
is no parser for this, and writing one would be a career.

So the model reads it. What the model is **not** allowed to do is decide whether the result
is usable — that is `validate_product`, which is arithmetic, runs afterwards, and has no
model in it. The division is the point:

    model      -> "what does this document say?"      (judgement, ambiguity, layout)
    validator  -> "is this SKU sellable?"             (facts, arithmetic, no judgement)

Extraction output is also treated as **untrusted**. A price list is a file someone sent the
merchant, and a supplier who writes an instruction into a product description is attacking
the negotiation agent through the merchant's own catalog. Everything extracted is scanned
before it is stored.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from vendable.core.models import Product
from vendable.core.money import rupees
from vendable.firewall.fencing import Risk, ScanResult, fence, fenced_prompt_note, scan
from vendable.negotiate.agent import Completer

SYSTEM = """You extract structured product data from Indian merchant price lists.

The documents are messy: inconsistent layouts, footnotes that revise prices, rates quoted per
box on one line and per piece on the next, two-column pages whose columns interleave when read
linearly, and GST rates stated once for a whole section with one exception buried in a note.

Read the WHOLE document before deciding any value. Specifically:
- If a footnote or a "revised rates" block contradicts a table, THE LATER REVISION WINS.
- If a rate is quoted per box or per pack, convert it to a per-unit price and say so.
- If a section states a GST rate but one line overrides it, use the override for that line.
- Indian GST rates are only ever 0, 0.25, 3, 5, 12, 18 or 28 percent.
- HSN codes are 4, 6 or 8 digits.

For every field you are not confident about, leave it null rather than guessing. A null is a
gap the merchant can fix; a confident wrong number is an invoice that fails.

Return ONLY a JSON object of this exact shape:
{"products": [{
  "sku": "string",
  "title": "string",
  "description": "string or null",
  "price_rupees": "string, e.g. \\"3.20\\", per single unit",
  "unit": "piece|box|coil|bag|length|set|can|bucket|cartridge|pack or null",
  "hsn_code": "string or null",
  "gst_rate_pct": number or null,
  "moq": integer or null,
  "notes": "string or null - say here if you converted a price or applied a revision"
}]}
"""


@dataclass(slots=True)
class ExtractedProduct:
    sku: str
    title: str
    price_rupees: str
    description: str = ""
    unit: str = ""
    hsn_code: str = ""
    gst_rate_pct: float | None = None
    moq: int | None = None
    notes: str = ""

    def to_product(self, *, source_ref: str = "") -> Product:
        return Product(
            sku=self.sku,
            title=self.title,
            description=self.description or "",
            list_price_paise=rupees(self.price_rupees),
            hsn_code=self.hsn_code or "",
            gst_rate_bp=int(round((self.gst_rate_pct or 0) * 100)),
            unit=self.unit or "",
            moq=self.moq or 1,
            source_ref=source_ref,
        )


@dataclass(slots=True)
class ExtractionResult:
    source: str
    products: list[ExtractedProduct] = field(default_factory=list)
    injection: ScanResult | None = None
    quarantined: list[str] = field(default_factory=list)
    """SKUs dropped because their own text carried an injection attempt."""
    raw_chars: int = 0
    error: str = ""

    @property
    def ok(self) -> bool:
        return not self.error


def read_pdf_text(path: Path | str) -> str:
    """Linear text extraction. Deliberately naive, because that is the realistic input.

    A better PDF parser would reduce the mess and make the extraction look easier than it is.
    The interleaved two-column output this produces is exactly what a merchant's own tooling
    would hand a model, so it is what the model is given.
    """
    from pypdf import PdfReader

    reader = PdfReader(str(path))
    return "\n".join(page.extract_text() or "" for page in reader.pages)


class CatalogExtractor:
    def __init__(self, completer: Completer) -> None:
        self.completer = completer

    def extract_text(self, text: str, *, source: str = "") -> ExtractionResult:
        if not text.strip():
            return ExtractionResult(source=source, error="the document contained no text")

        probe = scan(text)
        user = "\n".join(
            [
                fenced_prompt_note("PRICE_LIST"),
                fence(text, label="PRICE_LIST"),
                "",
                "Extract every product you can find. Return only the JSON object.",
            ]
        )
        raw = self.completer.complete(SYSTEM, user)
        parsed = _parse(raw)
        if parsed is None:
            return ExtractionResult(
                source=source,
                injection=probe,
                raw_chars=len(text),
                error=f"model did not return usable JSON (got {len(raw)} chars)",
            )

        products: list[ExtractedProduct] = []
        quarantined: list[str] = []
        for item in parsed:
            extracted = _coerce(item)
            if extracted is None:
                continue
            # Quarantine per-SKU: one poisoned description must not discard a whole catalog.
            own_text = f"{extracted.title} {extracted.description} {extracted.notes}"
            if scan(own_text).risk is Risk.HOSTILE:
                quarantined.append(extracted.sku)
                continue
            products.append(extracted)

        return ExtractionResult(
            source=source,
            products=products,
            injection=probe,
            quarantined=quarantined,
            raw_chars=len(text),
        )

    def extract_pdf(self, path: Path | str) -> ExtractionResult:
        path = Path(path)
        try:
            text = read_pdf_text(path)
        except Exception as exc:  # noqa: BLE001 -- a corrupt PDF is a data problem, not a crash
            return ExtractionResult(source=path.name, error=f"could not read the PDF: {exc}")
        return self.extract_text(text, source=path.name)


def _parse(raw: str) -> list[dict[str, Any]] | None:
    text = (raw or "").strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:]
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        return None
    try:
        obj = json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return None
    items = obj.get("products") if isinstance(obj, dict) else None
    return items if isinstance(items, list) else None


def _coerce(item: Any) -> ExtractedProduct | None:
    """Turn one model-produced dict into a typed row, or drop it.

    Every field is defended, because the model is allowed to be wrong here and the cost of a
    malformed row must be one missing SKU rather than an exception halfway through a catalog.
    """
    if not isinstance(item, dict):
        return None
    sku = str(item.get("sku") or "").strip()
    title = str(item.get("title") or "").strip()
    price = item.get("price_rupees")
    if not sku or price in (None, ""):
        return None
    try:
        rupees(str(price))  # parseable as money, or it is not a price
    except Exception:  # noqa: BLE001
        return None

    gst = item.get("gst_rate_pct")
    try:
        gst_val = float(gst) if gst is not None else None
    except (TypeError, ValueError):
        gst_val = None

    moq = item.get("moq")
    try:
        moq_val = int(moq) if moq is not None else None
    except (TypeError, ValueError):
        moq_val = None

    return ExtractedProduct(
        sku=sku,
        title=title,
        price_rupees=str(price),
        description=str(item.get("description") or "").strip(),
        unit=str(item.get("unit") or "").strip(),
        hsn_code=str(item.get("hsn_code") or "").strip(),
        gst_rate_pct=gst_val,
        moq=moq_val,
        notes=str(item.get("notes") or "").strip(),
    )


__all__ = ["CatalogExtractor", "ExtractedProduct", "ExtractionResult", "read_pdf_text"]
