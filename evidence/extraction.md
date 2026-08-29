# Catalog extraction accuracy

Three synthesised merchant price lists, hand-labelled ground truth, scored field by
field. Synthesised rather than scraped because a real supplier's price list is
somebody's commercial data and cannot carry a public answer key.

Extraction is the one place a language model is used for judgement. Everything
downstream of it -- gap validation, pricing, the mandate gate -- is deterministic.

Model: `gpt-5`. Input is naive linear PDF text, the same
interleaved mess a merchant's own tooling would produce.

| merchant | SKUs found | SKU recall | price/unit/HSN/GST/MOQ | all fields | traps |
|---|---|---|---|---|---|
| merchant-a | 6/6 | 100% | 100.0% (30/30) | 100.0% (36/36) | 2/2 |
| merchant-b | 6/6 | 100% | 100.0% (30/30) | 91.7% (33/36) | 2/2 |
| merchant-c | 6/6 | 100% | 100.0% (30/30) | 94.4% (34/36) | 2/2 |

**Every field that affects money: 100.0% correct (90/90). All fields including titles: 95.4% (103/108). 6/6 planted ambiguities resolved correctly.**

## Two corrections to this scorer, both of which flattered nobody

The first run scored **64.8%** and gave merchant-b 0% recall. The extractor was not
at fault. That document is a WhatsApp-style message containing no product codes at
all, so the model used product names as identifiers -- the only reasonable answer --
and the scorer marked all six SKUs missing for failing to guess codes I had invented
for the answer key. Matching now falls back to title overlap where the source carries
no codes.

The second run scored 96.3%, and **all four remaining misses were the `title` field,**
where in every case the model was *more faithful to the source document than my
ground truth was*: it returned "Copper wire 1.5 sqmm 90 mtr coil", which is what the
page literally says, against my paraphrase "90m". So titles are now reported
separately from the five fields where being wrong changes an invoice.

Both corrections are left in the record rather than quietly folded into a better
number, because an evaluation that has never been wrong is usually one nobody
checked. The headline figure moved from 64.8% to 96.3% without the extractor
changing at all -- which is a fact about my measurement, not about the model.

## The planted ambiguities

These are the only genuinely hard part. A parser gets all of them wrong.

| merchant | SKU | field | why it is hard | resolved |
|---|---|---|---|---|
| merchant-a | JB-4X4 | price | rate quoted per box of 100; must be converted to per-piece | yes |
| merchant-a | MCB-16A | price | footnote 2 revises the table's 118.00 | yes |
| merchant-b | LED-9W | gst_pct | 12% GST while every other line on the page is 18% | yes |
| merchant-b | WIRE-2.5 | price | no table; price written inline in a sentence | yes |
| merchant-c | THINNER-5 | price | REVISED RATES block supersedes the table's 680.00 | yes |
| merchant-c | BRUSH-4 | price | right-hand column; interleaves under linear extraction | yes |

## Every miss

### merchant-b

| SKU | field | expected | extracted | planted trap |
|---|---|---|---|---|
| WIRE-1.5 | title | `copper wire 1.5 sqmm 90m` | `copper wire 1.5 sqmm 90 m coil` | no |
| WIRE-2.5 | title | `copper wire 2.5 sqmm 90m` | `copper wire 2.5 sqmm 90 m coil` | no |
| SW-1WAY | title | `modular switch 1 way 6a` | `modular switch 1-way 6a` | no |

### merchant-c

| SKU | field | expected | extracted | planted trap |
|---|---|---|---|---|
| PAINT-EMUL-20 | title | `interior emulsion paint 20l` | `interior emulsion 20l` | no |
| ROLLER-9 | title | `paint roller 9 inch with tray` | `roller 9 inch + tray` | no |

