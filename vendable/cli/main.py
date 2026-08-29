"""The merchant's side of Vendable.

Everything here drives the *same* `Storefront` object the MCP server exposes to buyers. That
is deliberate: a CLI that took its own code path would let the demo pass while the
agent-facing surface was broken, and the agent-facing surface is the entire product.

    vendable doctor                 is this machine set up
    vendable ingest <pdf>           read a price list into the catalog
    vendable review                 what is broken, ranked by revenue at risk
    vendable serve                  run the storefront
    vendable mandate create --cap   mint a mandate for testing
    vendable audit verify           walk the hash chain
    vendable audit tail             the last N decisions, refusals included
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from vendable.core.money import format_inr, rupees
from vendable.core.settings import settings

app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    help="Make a merchant transactable by an AI buyer, end to end.",
)
mandate_app = typer.Typer(no_args_is_help=True, help="Mint and inspect payment mandates.")
audit_app = typer.Typer(no_args_is_help=True, help="Read and verify the audit chain.")
app.add_typer(mandate_app, name="mandate")
app.add_typer(audit_app, name="audit")

console = Console()


def _storefront():
    from vendable.mcp.server import default_storefront

    return default_storefront()


# ---------------------------------------------------------------------------------


@app.command()
def doctor() -> None:
    """Check whether this machine can run everything, and say what is missing."""
    table = Table(title="vendable doctor", show_header=True, header_style="bold")
    table.add_column("check")
    table.add_column("status")
    table.add_column("detail")

    def row(name: str, ok: bool | None, detail: str) -> None:
        mark = (
            "[green]ok[/]" if ok else ("[yellow]optional[/]" if ok is None else "[red]missing[/]")
        )
        table.add_row(name, mark, detail)

    row("python", True, f"{os.sys.version.split()[0]}")

    if settings.razorpay_configured:
        row(
            "razorpay",
            settings.is_test_mode,
            "test mode"
            if settings.is_test_mode
            else "LIVE KEY -- refused. Vendable will not run against a live account.",
        )
    else:
        row("razorpay", False, "no RAZORPAY_KEY_ID / RAZORPAY_KEY_SECRET in .env")

    row(
        "webhook secret",
        bool(settings.razorpay_webhook_secret) or None,
        "set"
        if settings.razorpay_webhook_secret
        else "not set -- webhook deliveries will be refused with 503",
    )
    row(
        "llm",
        bool(settings.openai_api_key) or None,
        f"{settings.openai_model}"
        if settings.openai_api_key
        else "no OPENAI_API_KEY -- ingestion is unavailable and negotiation falls back to "
        "deterministic pricing",
    )

    key_path = Path(settings.vendable_mandate_key_path)
    row(
        "mandate key",
        True,
        f"{key_path}" if key_path.exists() else "will be generated on first use",
    )

    try:
        import playwright  # noqa: F401

        browsers = os.environ.get("PLAYWRIGHT_BROWSERS_PATH", "(default)")
        row("playwright", True, f"browsers at {browsers}")
    except ImportError:
        row("playwright", None, "not installed -- payments cannot be completed headlessly")

    db = Path(settings.vendable_db_path)
    row("database", True, f"{db} ({'exists' if db.exists() else 'will be created'})")

    console.print(table)


@app.command()
def ingest(
    pdf: Path = typer.Argument(..., help="A merchant price list, as a PDF."),
    apply: bool = typer.Option(False, "--apply", help="Write the result into the catalog."),
) -> None:
    """Extract a catalog from a messy price list.

    Prints what was found and leaves the catalog untouched unless you pass --apply, because
    a model reading a PDF is the one step here that should not happen unsupervised.
    """
    if not settings.llm_configured:
        console.print("[red]No OPENAI_API_KEY configured.[/] Ingestion needs a model.")
        raise typer.Exit(1)

    from vendable.ingest.extract import CatalogExtractor
    from vendable.negotiate.llm import OpenAICompleter

    console.print(f"reading [bold]{pdf}[/]...")
    result = CatalogExtractor(OpenAICompleter()).extract_pdf(pdf)
    if not result.ok:
        console.print(f"[red]{result.error}[/]")
        raise typer.Exit(1)

    table = Table(show_header=True, header_style="bold")
    for col in ("sku", "title", "price", "unit", "HSN", "GST", "MOQ", "note"):
        table.add_column(col)
    for p in result.products:
        table.add_row(
            p.sku,
            p.title[:34],
            f"₹{p.price_rupees}",
            p.unit or "[red]—[/]",
            p.hsn_code or "[red]—[/]",
            f"{p.gst_rate_pct}%" if p.gst_rate_pct is not None else "[red]—[/]",
            str(p.moq or "—"),
            (p.notes or "")[:40],
        )
    console.print(table)
    console.print(f"{len(result.products)} products from {result.raw_chars} characters of text")

    if result.injection and not result.injection.is_clean:
        console.print(f"[yellow]injection patterns in the source: {result.injection.summary()}[/]")
    if result.quarantined:
        console.print(f"[yellow]quarantined SKUs: {', '.join(result.quarantined)}[/]")

    if not apply:
        console.print("\n[dim]Nothing written. Re-run with --apply to update the catalog.[/]")
        return

    sf = _storefront()
    written = sf.catalog.put_many([p.to_product(source_ref=result.source) for p in result.products])
    console.print(f"[green]wrote {written} products to the catalog[/]")


@app.command()
def review() -> None:
    """What is stopping AI buyers transacting, ranked by the revenue it costs."""
    from vendable.core.models import catalog_health

    sf = _storefront()
    health, gaps = catalog_health(sf.catalog.all())

    console.print(
        f"\n[bold]{health.transactable_skus}/{health.total_skus} SKUs are transactable[/] "
        f"({health.transactable_pct:.0f}%)  ·  "
        f"{health.blocking_gaps} blocking, {health.degrading_gaps} degrading, "
        f"{health.advisory_gaps} advisory  ·  "
        f"{format_inr(health.revenue_at_risk_paise)}/yr at risk\n"
    )
    table = Table(show_header=True, header_style="bold")
    for col in ("severity", "SKU", "field", "revenue at risk", "why", "fix"):
        table.add_column(col)
    for g in gaps[:20]:
        colour = {"blocking": "red", "degrading": "yellow", "advisory": "dim"}[g.severity.value]
        table.add_row(
            f"[{colour}]{g.severity.value}[/]",
            g.sku,
            g.field,
            format_inr(g.revenue_impact_paise),
            g.why[:60],
            g.how_to_fix[:44],
        )
    console.print(table)
    if len(gaps) > 20:
        console.print(f"[dim]... and {len(gaps) - 20} more[/]")


@app.command()
def serve(port: int = typer.Option(8080, help="Port to listen on.")) -> None:
    """Run the storefront: MCP tools, discovery surfaces, and the webhook receiver."""
    import uvicorn

    from vendable.mcp.app import build

    sf = _storefront()
    console.print(f"[bold]{sf.merchant_id}[/] · {len(sf.catalog)} SKUs")
    console.print(f"  mcp        http://localhost:{port}/mcp")
    console.print(f"  discovery  http://localhost:{port}/.well-known/vendable.json")
    console.print(f"  llms.txt   http://localhost:{port}/llms.txt")
    console.print(f"  webhook    http://localhost:{port}/webhooks/razorpay")
    console.print(
        f"\n[dim]connect a stock client:[/] "
        f"claude mcp add --transport http vendable http://localhost:{port}/mcp"
    )
    uvicorn.run(build(sf), host="0.0.0.0", port=port, log_level="warning")


# --- mandate ---------------------------------------------------------------------


@mandate_app.command("create")
def mandate_create(
    cap: str = typer.Option(..., "--cap", help="Spending cap in rupees, e.g. 5000."),
    subject: str = typer.Option("buyer-agent", help="The agent this mandate empowers."),
    audience: str = typer.Option("acme-fasteners", help="The merchant it may be used with."),
    ttl: int = typer.Option(3600, help="Lifetime in seconds."),
    budget: str = typer.Option("", help="Optional cumulative budget in rupees."),
) -> None:
    """Mint an AP2-shaped mandate. In production a buyer's wallet does this, not a merchant."""
    from vendable.mandate.ap2 import AllowedPayees, AmountRange, Budget, mint

    constraints = [
        AmountRange(currency="INR", max=rupees(cap)),
        AllowedPayees(payees=[audience]),
    ]
    if budget:
        constraints.append(Budget(currency="INR", max_total=rupees(budget)))

    token = mint(
        settings.mandate_private_key(),
        issuer=settings.vendable_mandate_issuer,
        subject=subject,
        audience=audience,
        constraints=constraints,
        ttl_seconds=ttl,
    )
    console.print(
        f"[dim]cap {format_inr(rupees(cap))}"
        + (f", budget {format_inr(rupees(budget))}" if budget else "")
        + f", expires in {ttl}s, for {audience}[/]\n"
    )
    print(token)


@mandate_app.command("inspect")
def mandate_inspect(token: str = typer.Argument(..., help="A compact JWS mandate.")) -> None:
    """Decode a mandate WITHOUT verifying it, to see what it claims."""
    import base64

    try:
        payload = token.split(".")[1]
        claims = json.loads(base64.urlsafe_b64decode(payload + "=="))
    except Exception:
        console.print("[red]Not a decodable token.[/]")
        raise typer.Exit(1) from None

    console.print("[yellow]Decoded without verification — these are claims, not facts.[/]\n")
    console.print_json(json.dumps(claims))


# --- audit -----------------------------------------------------------------------


@audit_app.command("verify")
def audit_verify() -> None:
    """Walk the hash chain and report any break."""
    sf = _storefront()
    breaks = sf.audit.verify()
    if not breaks:
        console.print(
            f"[green]chain intact[/] · {len(sf.audit)} records · head {sf.audit.head[:16]}..."
        )
        return
    console.print(f"[red]{len(breaks)} break(s) found[/]")
    for b in breaks:
        console.print(f"  record {b.seq}: {b.reason}")
    raise typer.Exit(1)


@audit_app.command("tail")
def audit_tail(n: int = typer.Option(20, "-n", help="How many records.")) -> None:
    """The last N decisions, refusals included."""
    sf = _storefront()
    records = list(sf.audit)[-n:]
    table = Table(show_header=True, header_style="bold")
    for col in ("seq", "actor", "action", "subject", "detail"):
        table.add_column(col)
    for r in records:
        colour = "red" if "refus" in r.action.value or "fail" in r.action.value else ""
        detail = ", ".join(f"{k}={v}" for k, v in list(r.payload.items())[:3])
        table.add_row(
            str(r.seq),
            r.actor,
            f"[{colour}]{r.action.value}[/]" if colour else r.action.value,
            r.subject[:22],
            detail[:64],
        )
    console.print(table)


if __name__ == "__main__":
    app()
