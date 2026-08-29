"""Headless completion of a Razorpay hosted payment page.

This module is the honest part of the system, and it is worth saying why it exists rather
than hiding it behind a nicer abstraction.

Everything upstream of here is agent-native: the buyer's agent speaks MCP, presents a signed
mandate, gets a gated decision, and receives a payment link. Then the rail runs out. Razorpay
exposes no agent-facing way to *complete* a payment -- S2S is not routed on a default account,
UPI is disabled on ours, and the card flow is defended by hCaptcha, which exists precisely to
stop software from doing this. So the last mile is crossed by driving a page built for a human
thumb.

The route that works, found by probing rather than by reading:

    Payment Link -> hosted checkout -> contact -> Netbanking -> a bank
      -> https://api.razorpay.com/v1/gateway/mocksharp/payment  ->  [Success] [Failure]

`mocksharp` is Razorpay's own test simulator. Two buttons, no captcha, no OTP. It also makes
**failure reproducible on demand**, which is where the Phase 5 declined-payment evidence comes
from -- a genuine gift, since a payment that fails only sometimes cannot be put in a table.

None of this touches live money: `RazorpayClient` refuses to construct on a non-test key.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from enum import Enum

from playwright.sync_api import Page, TimeoutError as PWTimeout, sync_playwright

# Set before Playwright launches. Chromium is ~700 MB and C: runs at under 400 MB free.
os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", "D:/tmp/pw-browsers")

CHECKOUT_FRAME_MARKER = "checkout/public"
SIMULATOR_MARKER = "mocksharp"

# A throwaway contact. Razorpay's checkout demands one before showing payment methods; it
# never reaches a real person in test mode.
TEST_CONTACT = "9000090000"

# Banks seen on this test account, in preference order. The first one present is used --
# Razorpay reorders and occasionally marks one "Facing issues", so pinning a single bank
# makes the driver fail for a reason that has nothing to do with our code.
BANK_PREFERENCE = ("Canara Bank", "PNB", "IDBI", "BOB")


class Outcome(str, Enum):
    SUCCESS = "success"
    FAILURE = "failure"


@dataclass(slots=True)
class CheckoutResult:
    completed: bool
    outcome: Outcome | None = None
    reason: str = ""
    steps: list[str] = field(default_factory=list)
    """Every step attempted, so a failure says how far it got rather than just 'timeout'."""


class HostedCheckoutDriver:
    """Drives one payment link to a chosen outcome.

    Deliberately synchronous and single-purpose. It is called once per purchase, takes tens
    of seconds, and its failure mode must be legible -- so it records a step trail rather
    than retrying cleverly.
    """

    def __init__(self, *, headless: bool = True, slow_ms: int = 0, timeout_ms: int = 45_000):
        self.headless = headless
        self.slow_ms = slow_ms
        self.timeout_ms = timeout_ms

    def pay(self, payment_link_url: str, outcome: Outcome = Outcome.SUCCESS) -> CheckoutResult:
        steps: list[str] = []

        def note(s: str) -> None:
            steps.append(s)

        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=self.headless, slow_mo=self.slow_ms)
                ctx = browser.new_context()
                # The simulator is reached by redirect, but Razorpay has been known to open
                # it in a second tab. Track every page so either shape works.
                pages: list[Page] = []
                ctx.on("page", lambda pg: pages.append(pg))
                page = ctx.new_page()
                pages.append(page)

                try:
                    page.goto(payment_link_url, wait_until="domcontentloaded", timeout=60_000)
                    page.wait_for_timeout(6_000)
                    note("opened payment link")

                    frame = self._checkout_frame(page)
                    frame.locator("input[name=contact]").fill(TEST_CONTACT)
                    self._checkout_frame(page).get_by_role("button", name="Continue").click()
                    page.wait_for_timeout(5_000)
                    note("submitted contact")

                    self._checkout_frame(page).get_by_text("Netbanking", exact=True).first.click()
                    page.wait_for_timeout(4_000)
                    note("chose netbanking")

                    bank = self._pick_bank(page)
                    if bank is None:
                        return CheckoutResult(
                            False,
                            reason=(
                                "No known test bank was offered on the netbanking screen. "
                                f"Expected one of: {', '.join(BANK_PREFERENCE)}."
                            ),
                            steps=steps,
                        )
                    note(f"selected bank: {bank}")
                    # Selecting a bank submits immediately -- there is no Continue to press,
                    # and clicking one is what made the first attempts hang on an overlay.

                    sim = self._await_simulator(page, pages)
                    if sim is None:
                        return CheckoutResult(
                            False,
                            reason=(
                                "The bank simulator never appeared. The payment was created "
                                "but not completed; it will expire unpaid."
                            ),
                            steps=steps,
                        )
                    note("reached the mocksharp simulator")

                    label = "Success" if outcome is Outcome.SUCCESS else "Failure"
                    sim.get_by_role("button", name=label).click()
                    page.wait_for_timeout(8_000)
                    note(f"clicked {label}")

                    return CheckoutResult(True, outcome=outcome, steps=steps)

                finally:
                    browser.close()

        except PWTimeout as exc:
            return CheckoutResult(
                False, reason=f"Checkout timed out: {str(exc)[:200]}", steps=steps
            )
        except Exception as exc:  # a broken page shape must not take the server down
            return CheckoutResult(
                False, reason=f"Checkout failed: {type(exc).__name__}: {exc}", steps=steps
            )

    # -- page plumbing -------------------------------------------------------------

    def _checkout_frame(self, page: Page):
        """Re-resolve the checkout iframe every time.

        It is re-created between steps, so a frame handle captured earlier goes stale and
        throws in a way that reads like a selector bug. Look it up fresh, always.
        """
        for frame in page.frames:
            if CHECKOUT_FRAME_MARKER in frame.url:
                return frame
        raise RuntimeError("Razorpay checkout iframe not found on the page")

    def _pick_bank(self, page: Page) -> str | None:
        frame = self._checkout_frame(page)
        for name in BANK_PREFERENCE:
            loc = frame.get_by_text(name, exact=True)
            if loc.count():
                loc.first.click()
                return name
        return None

    def _await_simulator(self, page: Page, pages: list[Page]) -> Page | None:
        deadline = self.timeout_ms
        waited = 0
        while waited < deadline:
            page.wait_for_timeout(2_000)
            waited += 2_000
            for candidate in list(pages):
                try:
                    if SIMULATOR_MARKER in candidate.url:
                        return candidate
                except Exception:
                    continue
        return None


__all__ = ["CheckoutResult", "HostedCheckoutDriver", "Outcome"]
