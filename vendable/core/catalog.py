"""Catalog persistence and search.

Search here is deterministic keyword matching, not embeddings, and that is a deliberate
choice rather than a shortcut. A buying agent asking for "M8 galvanised bolt" needs the
result set to be explainable and stable: the same query must return the same SKUs in the
same order every run, or the extraction-accuracy and negotiation evidence in Phase 5 cannot
reproduce. Semantic search would rank better on paper and make every downstream number a
moving target.

It is also one of the places worth naming in the README's "where I chose not to use an LLM":
the model's judgement belongs in reading a messy PDF, not in deciding which of forty SKUs a
literal query matched.
"""

from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path

from vendable.core.models import Availability, Product

_SCHEMA = """
CREATE TABLE IF NOT EXISTS products (
    sku          TEXT PRIMARY KEY,
    merchant_id  TEXT NOT NULL,
    body         TEXT NOT NULL,
    search_blob  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS products_merchant ON products(merchant_id);
"""

_TOKEN_RE = re.compile(r"[a-z0-9]+")

# Words that match everything and therefore rank nothing.
_STOPWORDS = frozenset(
    {
        "a",
        "an",
        "the",
        "of",
        "for",
        "with",
        "and",
        "or",
        "in",
        "on",
        "to",
        "i",
        "me",
        "need",
        "want",
        "buy",
        "some",
        "any",
        "please",
        "looking",
        "get",
        "find",
        "show",
    }
)


def _tokens(text: str) -> list[str]:
    return [t for t in _TOKEN_RE.findall(text.lower()) if t not in _STOPWORDS]


class Catalog:
    """A merchant's SKUs. One SQLite file, shared with the rest of the local stores."""

    def __init__(self, db_path: Path | str = ":memory:", *, merchant_id: str = "") -> None:
        self.db_path = str(db_path)
        self.merchant_id = merchant_id
        if self.db_path != ":memory:":
            Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        if self.db_path != ":memory:":
            self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    # -- writing -------------------------------------------------------------------

    def put(self, product: Product, *, merchant_id: str | None = None) -> None:
        blob = " ".join(
            [
                product.sku,
                product.title,
                product.description,
                product.brand,
                product.category,
                product.unit,
                product.hsn_code,
            ]
        ).lower()
        self._conn.execute(
            "INSERT OR REPLACE INTO products (sku, merchant_id, body, search_blob)"
            " VALUES (?,?,?,?)",
            (product.sku, merchant_id or self.merchant_id, product.model_dump_json(), blob),
        )
        self._conn.commit()

    def put_many(self, products: list[Product], *, merchant_id: str | None = None) -> int:
        for p in products:
            self.put(p, merchant_id=merchant_id)
        return len(products)

    def set_stock(self, sku: str, qty: int) -> None:
        p = self.get(sku)
        if p is None:
            return
        p.stock_qty = qty
        if qty <= 0:
            p.availability = Availability.OUT_OF_STOCK
        self.put(p)

    # -- reading -------------------------------------------------------------------

    def get(self, sku: str) -> Product | None:
        row = self._conn.execute("SELECT body FROM products WHERE sku = ?", (sku,)).fetchone()
        return Product.model_validate_json(row["body"]) if row else None

    def all(self) -> list[Product]:
        rows = self._conn.execute("SELECT body FROM products ORDER BY sku")
        return [Product.model_validate_json(r["body"]) for r in rows]

    def stock_map(self) -> dict[str, int]:
        return {p.sku: p.stock_qty for p in self.all()}

    def __len__(self) -> int:
        return int(self._conn.execute("SELECT COUNT(*) FROM products").fetchone()[0])

    # -- search --------------------------------------------------------------------

    def search(self, query: str, *, limit: int = 10, in_stock_only: bool = False) -> list[Product]:
        """Rank by how many query tokens a SKU matches, then by price, then by SKU.

        Ties break on price ascending and then SKU alphabetically so the ordering is total.
        Without a total order, two SKUs matching equally well can swap places between runs
        and quietly change an evidence table.
        """
        terms = _tokens(query)
        if not terms:
            results = self.all()
        else:
            rows = self._conn.execute("SELECT sku, body, search_blob FROM products")
            scored: list[tuple[int, Product]] = []
            for row in rows:
                blob = row["search_blob"]
                score = sum(1 for t in terms if t in blob)
                # An exact SKU match beats everything -- an agent quoting a SKU back at us
                # means it, and burying that under fuzzy title matches is infuriating.
                if row["sku"].lower() == query.strip().lower():
                    score += 100
                if score:
                    scored.append((score, Product.model_validate_json(row["body"])))
            scored.sort(key=lambda pair: (-pair[0], pair[1].list_price_paise, pair[1].sku))
            results = [p for _, p in scored]

        if in_stock_only:
            results = [p for p in results if p.is_sellable]
        return results[:limit]

    def close(self) -> None:
        self._conn.close()


def load_seed(path: Path | str) -> list[Product]:
    """Read a JSON array of products from disk. Used by fixtures and the CLI."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return [Product.model_validate(item) for item in data]


__all__ = ["Catalog", "load_seed"]
