"""Generate three realistically messy merchant price lists as PDFs, plus ground truth.

Synthesised rather than scraped, for two reasons: real supplier price lists are somebody's
commercial data, and a synthesised one can carry **hand-labelled ground truth**, which is
what turns "the extraction looked good" into a number.

The mess is deliberate and each kind of it is something that actually happens:

- **A**: a tidy tabular list, but with merged header rows, a footnote that changes the price
  of one line, and prices quoted per-box for some rows and per-piece for others.
- **B**: a WhatsApp-style flat text dump with no table at all, inconsistent separators,
  rupee symbols written four different ways, and quantities in Hindi-English mix.
- **C**: a scanned-looking two-column layout where the columns interleave when read
  linearly, plus a "revised rates" block that supersedes part of the first table.

C is the important one. Linear text extraction of a two-column PDF interleaves the columns,
which is exactly the failure mode that makes naive PDF-to-text pipelines silently wrong
rather than obviously broken.

    .venv/Scripts/python.exe scripts/make_messy_pdfs.py
"""

from __future__ import annotations

import json
from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas

OUT = Path(__file__).resolve().parents[1] / "fixtures" / "pricelists"

# Ground truth: what a correct extraction must produce. Prices in rupees as strings so no
# float ever enters the comparison.
TRUTH: dict[str, list[dict]] = {
    "merchant-a": [
        {
            "sku": "GI-CLAMP-25",
            "title": "GI saddle clamp 25mm",
            "price": "6.50",
            "unit": "piece",
            "hsn": "73269099",
            "gst_pct": 18,
            "moq": 100,
        },
        {
            "sku": "GI-CLAMP-32",
            "title": "GI saddle clamp 32mm",
            "price": "8.25",
            "unit": "piece",
            "hsn": "73269099",
            "gst_pct": 18,
            "moq": 100,
        },
        {
            "sku": "PVC-CONDUIT-20",
            "title": "PVC conduit pipe 20mm",
            "price": "42.00",
            "unit": "length",
            "hsn": "39172390",
            "gst_pct": 18,
            "moq": 20,
        },
        {
            "sku": "PVC-CONDUIT-25",
            "title": "PVC conduit pipe 25mm",
            "price": "58.00",
            "unit": "length",
            "hsn": "39172390",
            "gst_pct": 18,
            "moq": 20,
        },
        # quoted per box of 100 in the source; correct per-piece price is 3.20
        {
            "sku": "JB-4X4",
            "title": "PVC junction box 4x4",
            "price": "3.20",
            "unit": "piece",
            "hsn": "85389000",
            "gst_pct": 18,
            "moq": 100,
        },
        # the footnote revises this one from 118.00 to 109.00
        {
            "sku": "MCB-16A",
            "title": "MCB single pole 16A",
            "price": "109.00",
            "unit": "piece",
            "hsn": "85362000",
            "gst_pct": 18,
            "moq": 10,
        },
    ],
    "merchant-b": [
        {
            "sku": "WIRE-1.5",
            "title": "Copper wire 1.5 sqmm 90m",
            "price": "1180.00",
            "unit": "coil",
            "hsn": "85444999",
            "gst_pct": 18,
            "moq": 5,
        },
        {
            "sku": "WIRE-2.5",
            "title": "Copper wire 2.5 sqmm 90m",
            "price": "1890.00",
            "unit": "coil",
            "hsn": "85444999",
            "gst_pct": 18,
            "moq": 5,
        },
        {
            "sku": "SW-1WAY",
            "title": "Modular switch 1 way 6A",
            "price": "48.00",
            "unit": "piece",
            "hsn": "85365090",
            "gst_pct": 18,
            "moq": 50,
        },
        {
            "sku": "SOCK-6A",
            "title": "Modular socket 6A",
            "price": "72.00",
            "unit": "piece",
            "hsn": "85366990",
            "gst_pct": 18,
            "moq": 50,
        },
        {
            "sku": "PLATE-2M",
            "title": "Modular plate 2 module",
            "price": "95.00",
            "unit": "piece",
            "hsn": "85389000",
            "gst_pct": 18,
            "moq": 20,
        },
        {
            "sku": "LED-9W",
            "title": "LED bulb 9W cool white",
            "price": "88.00",
            "unit": "piece",
            "hsn": "94054090",
            "gst_pct": 12,
            "moq": 25,
        },
    ],
    "merchant-c": [
        {
            "sku": "PAINT-EMUL-20",
            "title": "Interior emulsion paint 20L",
            "price": "3450.00",
            "unit": "bucket",
            "hsn": "32091010",
            "gst_pct": 18,
            "moq": 2,
        },
        {
            "sku": "PAINT-PRIM-20",
            "title": "Wall primer 20L",
            "price": "2180.00",
            "unit": "bucket",
            "hsn": "32091010",
            "gst_pct": 18,
            "moq": 2,
        },
        {
            "sku": "PUTTY-40",
            "title": "Wall putty 40kg bag",
            "price": "980.00",
            "unit": "bag",
            "hsn": "32149000",
            "gst_pct": 18,
            "moq": 10,
        },
        {
            "sku": "BRUSH-4",
            "title": "Paint brush 4 inch",
            "price": "115.00",
            "unit": "piece",
            "hsn": "96032100",
            "gst_pct": 18,
            "moq": 12,
        },
        {
            "sku": "ROLLER-9",
            "title": "Paint roller 9 inch with tray",
            "price": "240.00",
            "unit": "set",
            "hsn": "96034000",
            "gst_pct": 18,
            "moq": 6,
        },
        # superseded by the "REVISED RATES" block later in the document
        {
            "sku": "THINNER-5",
            "title": "Paint thinner 5L",
            "price": "615.00",
            "unit": "can",
            "hsn": "38140010",
            "gst_pct": 18,
            "moq": 4,
        },
    ],
}


def merchant_a(c: canvas.Canvas) -> None:
    """A tidy table -- undermined by a unit switch and a footnote that revises a price."""
    c.setFont("Helvetica-Bold", 15)
    c.drawString(20 * mm, 275 * mm, "SHREE ELECTRICALS & HARDWARE")
    c.setFont("Helvetica", 8)
    c.drawString(
        20 * mm, 270 * mm, "Peenya Industrial Area, Bengaluru 560058  |  GSTIN 29AABCS1429B1ZQ"
    )
    c.setFont("Helvetica-Bold", 10)
    c.drawString(20 * mm, 261 * mm, "PRICE LIST — EFFECTIVE 01 APR 2026")
    c.setFont("Helvetica", 7)
    c.drawString(
        20 * mm, 256 * mm, "All rates exclusive of freight. Rates subject to change without notice."
    )

    y = 245 * mm
    c.setFont("Helvetica-Bold", 8)
    for x, head in [
        (20, "CODE"),
        (55, "DESCRIPTION"),
        (120, "HSN"),
        (140, "GST"),
        (155, "RATE"),
        (178, "MOQ"),
    ]:
        c.drawString(x * mm, y, head)
    c.line(20 * mm, y - 1.5 * mm, 190 * mm, y - 1.5 * mm)

    rows = [
        ("GI-CLAMP-25", "GI saddle clamp 25mm", "73269099", "18%", "6.50", "100 nos"),
        ("GI-CLAMP-32", "GI saddle clamp 32mm", "73269099", "18%", "8.25", "100 nos"),
        (
            "PVC-CONDUIT-20",
            "PVC conduit pipe 20mm (3 mtr)",
            "39172390",
            "18%",
            "42.00",
            "20 lengths",
        ),
        (
            "PVC-CONDUIT-25",
            "PVC conduit pipe 25mm (3 mtr)",
            "39172390",
            "18%",
            "58.00",
            "20 lengths",
        ),
        # the trap: rate is per box of 100, not per piece
        ("JB-4X4", "PVC junction box 4x4  *per box of 100*", "85389000", "18%", "320.00", "1 box"),
        ("MCB-16A", "MCB single pole 16A  (see note 2)", "85362000", "18%", "118.00", "10 nos"),
    ]
    y -= 7 * mm
    c.setFont("Helvetica", 8)
    for code, desc, hsn, gst, rate, moq in rows:
        c.drawString(20 * mm, y, code)
        c.drawString(55 * mm, y, desc)
        c.drawString(120 * mm, y, hsn)
        c.drawString(140 * mm, y, gst)
        c.drawRightString(172 * mm, y, rate)
        c.drawString(178 * mm, y, moq)
        y -= 6 * mm

    y -= 6 * mm
    c.setFont("Helvetica-Oblique", 7)
    c.drawString(20 * mm, y, "Note 1: Junction box rate quoted per box of 100 pcs.")
    c.drawString(
        20 * mm,
        y - 4 * mm,
        "Note 2: MCB 16A revised to Rs 109.00 per pc w.e.f. 15 Apr 2026, superseding table above.",
    )


def merchant_b(c: canvas.Canvas) -> None:
    """No table at all. A message someone typed on a phone and had printed."""
    c.setFont("Helvetica-Bold", 13)
    c.drawString(20 * mm, 275 * mm, "M/s NATIONAL ELECTRIC STORES")
    c.setFont("Helvetica", 8)
    c.drawString(
        20 * mm, 270 * mm, "Chickpet, Bengaluru  -  Mob 98450 xxxxx  -  GSTIN 29AAFCN2837D1Z5"
    )

    lines = [
        "",
        "Sir, updated rate list as discussed. All rates GST extra unless mentioned.",
        "",
        "Copper wire 1.5 sqmm 90 mtr coil ....... Rs.1180/- per coil (min 5 coil)",
        "copper wire 2.5sqmm 90mtr - 1890 rs coil, minimum 5 coils",
        "HSN for both wire items 85444999, gst 18%",
        "",
        "Modular switch 1 way 6A  =  48/- pc     (50 pcs min) hsn 85365090",
        "Modular socket 6A ........ Rs 72 per pc, same min qty, hsn 85366990",
        "Modular plate 2 module — ₹95/pc, moq 20 nos, HSN 85389000, GST 18 percent",
        "",
        "LED bulb 9W cool white  Rs.88.00 each  min 25 nos",
        "  ^ this item GST is 12% only (hsn 94054090)",
        "",
        "switch/socket/plate all 18% gst.",
        "Delivery 2-3 days. Payment 30 days.",
    ]
    y = 258 * mm
    c.setFont("Helvetica", 9)
    for line in lines:
        c.drawString(20 * mm, y, line)
        y -= 5.5 * mm


def merchant_c(c: canvas.Canvas) -> None:
    """Two columns that interleave under linear extraction, plus a revised-rates block."""
    c.setFont("Helvetica-Bold", 14)
    c.drawString(20 * mm, 275 * mm, "COLOURWORKS PAINTS & SUPPLIES")
    c.setFont("Helvetica", 8)
    c.drawString(20 * mm, 270 * mm, "Mysore Road, Bengaluru  |  GSTIN 29AACCC4471E1ZP  |  Q2 2026")

    left = [
        ("PAINT-EMUL-20", "Interior emulsion 20L", "3450.00"),
        ("PAINT-PRIM-20", "Wall primer 20L", "2180.00"),
        ("PUTTY-40", "Wall putty 40kg", "980.00"),
    ]
    right = [
        ("BRUSH-4", "Paint brush 4 inch", "115.00"),
        ("ROLLER-9", "Roller 9 inch + tray", "240.00"),
        ("THINNER-5", "Paint thinner 5L", "680.00"),
    ]

    y0 = 255 * mm
    c.setFont("Helvetica-Bold", 9)
    c.drawString(20 * mm, y0 + 8 * mm, "BULK / SITE ITEMS")
    c.drawString(110 * mm, y0 + 8 * mm, "TOOLS & SUNDRIES")
    c.setFont("Helvetica", 8)

    for i in range(3):
        y = y0 - i * 12 * mm
        code, desc, rate = left[i]
        c.drawString(20 * mm, y, code)
        c.drawString(20 * mm, y - 4 * mm, desc)
        c.drawRightString(95 * mm, y - 4 * mm, f"Rs {rate}")
        code, desc, rate = right[i]
        c.drawString(110 * mm, y, code)
        c.drawString(110 * mm, y - 4 * mm, desc)
        c.drawRightString(185 * mm, y - 4 * mm, f"Rs {rate}")

    y = y0 - 45 * mm
    c.setFont("Helvetica", 7)
    c.drawString(
        20 * mm,
        y,
        "MOQ: emulsion/primer 2 buckets, putty 10 bags, brush 12 nos, roller 6 sets, thinner 4 cans.",
    )
    c.drawString(
        20 * mm,
        y - 4 * mm,
        "HSN: 32091010 paints & primer / 32149000 putty / 96032100 brush / 96034000 roller / 38140010 thinner.",
    )
    c.drawString(20 * mm, y - 8 * mm, "GST 18% on all lines above.")

    y -= 22 * mm
    c.setFont("Helvetica-Bold", 10)
    c.drawString(20 * mm, y, "REVISED RATES  (supersedes the table above)")
    c.setFont("Helvetica", 8)
    c.drawString(
        20 * mm,
        y - 6 * mm,
        "THINNER-5   Paint thinner 5L   Rs 615.00 per can   — reduced, effective immediately",
    )


BUILDERS = {"merchant-a": merchant_a, "merchant-b": merchant_b, "merchant-c": merchant_c}


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for name, build in BUILDERS.items():
        path = OUT / f"{name}.pdf"
        c = canvas.Canvas(str(path), pagesize=A4)
        build(c)
        c.showPage()
        c.save()
        print(f"wrote {path.name}  ({len(TRUTH[name])} SKUs in ground truth)")

    truth_path = OUT / "ground_truth.json"
    truth_path.write_text(json.dumps(TRUTH, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"wrote {truth_path.name}")
    print("\ntraps planted:")
    print("  A: JB-4X4 quoted per box of 100 (Rs 320) -> correct unit price Rs 3.20")
    print("  A: MCB-16A table says 118.00, footnote 2 revises to 109.00")
    print("  B: no table at all; LED GST is 12% while everything else is 18%")
    print("  C: two columns interleave under linear extraction")
    print("  C: THINNER-5 table says 680.00, REVISED RATES block says 615.00")


if __name__ == "__main__":
    main()
