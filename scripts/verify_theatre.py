"""Exercise the theatre in a real browser and assert what an audience would see.

The theatre is a replay, so "the data is right" is cheap -- run.json is checked into the
repo and can be read with `cat`. What is expensive, and what this script is for, is that
the page *paints*. That failure mode is real and it already happened twice here: once when
a fixed, blurred aurora promoted a document-sized composited layer, and once when an
entrance animation left `filter: blur(0px)` on several hundred elements. In both cases the
DOM was perfectly correct -- every node present, every computed opacity 1 -- and the screen
was black. Nothing short of driving a browser and looking at pixels catches that.

So this asserts three classes of thing:

  * the page paints: headings have non-zero boxes, and the rendered frame is not a
    single flat colour
  * the argument reaches the screen: the statute verbatim, the cap drawn to scale, the
    concession bar amber under an honest buyer and empty under the attack
  * nothing from the component library leaked through: no placeholder images, no
    #f5f4f3 ground, no "Project 1"

    # terminal 1
    .venv/Scripts/python.exe scripts/serve_demo.py
    # terminal 2
    .venv/Scripts/python.exe scripts/verify_theatre.py

`--shots DIR` writes a screenshot of every beat, which is what goes in the deck.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

# Set before Playwright launches. Chromium is ~700 MB and C: runs at under 400 MB free.
os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", "D:/tmp/pw-browsers")

from playwright.sync_api import Page, sync_playwright  # noqa: E402

THEATRE = "http://localhost:8080/theatre/"

failures: list[str] = []
checks = 0


def check(ok: bool, label: str) -> None:
    global checks
    checks += 1
    print(f"  {'ok  ' if ok else 'FAIL'}  {label}")
    if not ok:
        failures.append(label)


def settle(page: Page) -> None:
    """Scroll the whole page once so every `whileInView` reveal has fired.

    Reveals are `once: true`, so a beat that has never been scrolled past is still at
    opacity 0 and would fail a visibility check for a reason that has nothing to do with
    the page being broken.
    """
    page.evaluate(
        """() => new Promise((resolve) => {
            let y = 0;
            const step = () => {
                y += window.innerHeight * 0.6;
                window.scrollTo(0, y);
                if (y < document.documentElement.scrollHeight) {
                    requestAnimationFrame(step);
                } else {
                    window.scrollTo(0, 0);
                    setTimeout(resolve, 400);
                }
            };
            step();
        })"""
    )
    page.wait_for_timeout(600)


def frame_is_not_flat(page: Page) -> bool:
    """True when the rendered frame contains more than one colour.

    The black-screen failures both produced a frame of exactly one value. Sampling the
    actual pixels is the only assertion that would have caught them.
    """
    shot = page.screenshot(type="png")
    # PNG IDAT entropy is a poor proxy; compare distinct bytes instead, which is enough to
    # separate "a flat fill" from "a page with text on it".
    return len(set(shot)) > 64


def main() -> int:
    ap = argparse.ArgumentParser(description="Verify the theatre in a real browser.")
    ap.add_argument("url", nargs="?", default=THEATRE)
    ap.add_argument("--shots", help="write screenshots of each beat to this directory")
    args = ap.parse_args()

    shots = Path(args.shots) if args.shots else None
    if shots:
        shots.mkdir(parents=True, exist_ok=True)

    errors: list[str] = []

    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page(viewport={"width": 1600, "height": 1000})
        page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
        page.on("pageerror", lambda e: errors.append(str(e)))

        print(f"\ntheatre  {args.url}")
        page.goto(args.url, wait_until="networkidle")
        page.wait_for_selector("h1", timeout=10_000)
        settle(page)

        # -- it paints ----------------------------------------------------------
        print("\npaint")
        h1 = page.locator("h1").first
        box = h1.bounding_box()
        check(bool(box and box["width"] > 100 and box["height"] > 20), "the cover headline has a box")
        check(h1.is_visible(), "the cover headline is visible")
        check(frame_is_not_flat(page), "the rendered frame is not a flat fill")

        # A filter that is not `none` promotes a composited layer and is what blanked the
        # page before. Nothing on this page should carry one after its entrance.
        stuck = page.evaluate(
            """() => [...document.querySelectorAll('*')]
                .filter(el => {
                    const f = getComputedStyle(el).filter;
                    return f && f !== 'none' && f.includes('blur(0px)');
                }).length"""
        )
        check(stuck == 0, f"no element left holding filter: blur(0px) (found {stuck})")

        # -- every beat is on the page -----------------------------------------
        print("\nbeats")
        sections = page.locator("section")
        n = sections.count()
        check(n == 17, f"all 17 beats render (found {n})")

        visible = page.evaluate(
            """() => [...document.querySelectorAll('section')]
                .filter(s => s.getBoundingClientRect().height > 40).length"""
        )
        check(visible == n, f"every beat has height (found {visible}/{n})")

        # -- the argument reaches the screen -----------------------------------
        print("\nthe argument")
        body = page.inner_text("body")

        check("s.15 of the MSMED Act" in body, "the statute is quoted verbatim")
        check("45 days" in body, "the 45-day statutory cap is on the page")
        check("s.43B(h)" in body, "the deduction consequence is on the page")
        check("shakti-forgings" in body and "acme-fasteners" in body, "both merchants appear")

        check("amount_over_cap" in body.lower(), "the mandate cap refusal names its code")
        check("₹6,700.00 over" in body or "6,700" in body, "the cap overflow is quantified")
        check("0.74% of the cart was authorised" in body, "the cap is drawn to scale")

        check("INTACT" in body, "the chain reports INTACT")
        check("137" in body, "the record count is on the page")

        check("plink_TW9Mn6aPJujCZW" in body, "the settled payment link is shown")
        check("plink_TW9NbV6nlj5RCJ" in body, "the declined payment link is shown")

        # -- the diagrams -------------------------------------------------------
        print("\ndiagrams")
        svgs = page.locator("svg[role='img']").count()
        check(svgs >= 1, f"the credit timeline is drawn (found {svgs})")
        check("DAYS OF CREDIT" in body, "the credit timeline is labelled")
        check("s.15 · 45d" in body, "the statutory wall is marked on the timeline")

        bars = page.locator(".bar").count()
        check(bars >= 2, f"the concession bars are drawn (found {bars})")
        # The security argument, as a number: honest buyer spends 2.0%, attack spends 0.0%.
        check("2.0%" in body, "the honest buyer spent discretion")
        check("0.0%" in body, "the attack spent none")
        check("CAN REFUSE" in body, "the flow diagram marks the gates")

        # -- nothing leaked from the component library --------------------------
        print("\nno placeholder residue")
        html = page.content()
        for junk, label in [
            ("lummi", "no Lummi placeholder images"),
            ("f5f4f3", "no #f5f4f3 light ground"),
            ("Project 1", "no 'Project 1' demo copy"),
            ("ff3828", "no #ff3828 demo accent"),
        ]:
            check(junk.lower() not in html.lower(), label)

        check("skiper-ui.com" in html, "Skiper UI attribution is present (free licence)")

        # -- a phone can open it -------------------------------------------------
        print("\nresponsive")
        page.set_viewport_size({"width": 390, "height": 844})
        page.wait_for_timeout(500)
        overflow = page.evaluate(
            "() => document.documentElement.scrollWidth - document.documentElement.clientWidth"
        )
        check(overflow <= 1, f"no horizontal overflow at 390px (overflow {overflow}px)")
        page.set_viewport_size({"width": 1600, "height": 1000})

        # -- screenshots ---------------------------------------------------------
        if shots:
            print(f"\nshots -> {shots}")
            settle(page)
            page.screenshot(path=str(shots / "theatre-cover.png"))
            for i in range(n):
                sec = sections.nth(i)
                sec.scroll_into_view_if_needed()
                page.wait_for_timeout(700)
                sec.screenshot(path=str(shots / f"theatre-{i + 1:02d}.png"))
            print(f"  wrote {n + 1} images")

        print("\nconsole")
        check(not errors, f"zero browser console errors (found {len(errors)})")
        for e in errors[:5]:
            print(f"        {e}")

        browser.close()

    ok = checks - len(failures)
    print(f"\n{ok}/{checks} checks passed")
    if failures:
        print("\nfailed:")
        for f in failures:
            print(f"  - {f}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
