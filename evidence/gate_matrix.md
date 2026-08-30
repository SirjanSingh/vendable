# Mandate gate — confusion matrix

**62 cases, 62 correct (100.0%). 0 false accepts, 0 false rejects.**

Generated deterministically, so these numbers reproduce on any machine.

The two error directions are not equally bad, and conflating them into one accuracy
figure would hide the only thing that matters:

- a **false accept** authorises money that should have been refused. Unrecoverable.
- a **false reject** refuses a legitimate purchase. Annoying, recoverable, and the
  correct way for this system to fail.

|  | gate allowed | gate refused |
|---|---|---|
| **should allow** | 30 (correct) | 0 (false reject) |
| **should refuse** | **0 (false accept)** | 32 (correct) |

## By group

| group | cases | correct | false accepts | false rejects |
|---|---|---|---|---|
| cap boundary | 9 | 9/9 | 0 | 0 |
| amount range | 8 | 8/8 | 0 | 0 |
| multi-line totals | 12 | 12/12 | 0 | 0 |
| expiry | 5 | 5/5 | 0 | 0 |
| audience | 5 | 5/5 | 0 | 0 |
| currency | 4 | 4/4 | 0 | 0 |
| payee allowlist | 4 | 4/4 | 0 | 0 |
| minimum bound | 3 | 3/3 | 0 | 0 |
| malformed | 7 | 7/7 | 0 | 0 |
| cumulative budget | 5 | 5/5 | 0 | 0 |

## Disagreements

None. Every case landed where the answer key said it should — including the nine single-paisa steps across the cap boundary, which is the arithmetic this whole project claims to get right.

## Every case

| id | group | case | expected | actual | code |
|---|---|---|---|---|---|
| CAP-1000 | cap boundary | cart is cap-1000 paise (₹4,990.00 against a ₹5,000.00 cap) | allow | allow |  |
| CAP-100 | cap boundary | cart is cap-100 paise (₹4,999.00 against a ₹5,000.00 cap) | allow | allow |  |
| CAP-10 | cap boundary | cart is cap-10 paise (₹4,999.90 against a ₹5,000.00 cap) | allow | allow |  |
| CAP-1 | cap boundary | cart is cap-1 paise (₹4,999.99 against a ₹5,000.00 cap) | allow | allow |  |
| CAP+0 | cap boundary | cart is cap+0 paise (₹5,000.00 against a ₹5,000.00 cap) | allow | allow |  |
| CAP+1 | cap boundary | cart is cap+1 paise (₹5,000.01 against a ₹5,000.00 cap) | refuse | refuse | amount_over_cap |
| CAP+10 | cap boundary | cart is cap+10 paise (₹5,000.10 against a ₹5,000.00 cap) | refuse | refuse | amount_over_cap |
| CAP+100 | cap boundary | cart is cap+100 paise (₹5,001.00 against a ₹5,000.00 cap) | refuse | refuse | amount_over_cap |
| CAP+1000 | cap boundary | cart is cap+1000 paise (₹5,010.00 against a ₹5,000.00 cap) | refuse | refuse | amount_over_cap |
| AMT-0.01 | amount range | cart of ₹0.01 | allow | allow |  |
| AMT-1 | amount range | cart of ₹1.00 | allow | allow |  |
| AMT-99.99 | amount range | cart of ₹99.99 | allow | allow |  |
| AMT-1000 | amount range | cart of ₹1,000.00 | allow | allow |  |
| AMT-4999.99 | amount range | cart of ₹4,999.99 | allow | allow |  |
| AMT-5000 | amount range | cart of ₹5,000.00 | allow | allow |  |
| AMT-5000.01 | amount range | cart of ₹5,000.01 | refuse | refuse | amount_over_cap |
| AMT-50000 | amount range | cart of ₹50,000.00 | refuse | refuse | amount_over_cap |
| MULTI-2-4999 | multi-line totals | 2 lines summing to ₹4,999.00 | allow | allow |  |
| MULTI-2-5000 | multi-line totals | 2 lines summing to ₹5,000.00 | allow | allow |  |
| MULTI-2-5001 | multi-line totals | 2 lines summing to ₹5,001.00 | refuse | refuse | amount_over_cap |
| MULTI-3-4999 | multi-line totals | 3 lines summing to ₹4,999.00 | allow | allow |  |
| MULTI-3-5000 | multi-line totals | 3 lines summing to ₹5,000.00 | allow | allow |  |
| MULTI-3-5001 | multi-line totals | 3 lines summing to ₹5,001.00 | refuse | refuse | amount_over_cap |
| MULTI-5-4999 | multi-line totals | 5 lines summing to ₹4,999.00 | allow | allow |  |
| MULTI-5-5000 | multi-line totals | 5 lines summing to ₹5,000.00 | allow | allow |  |
| MULTI-5-5001 | multi-line totals | 5 lines summing to ₹5,001.00 | refuse | refuse | amount_over_cap |
| MULTI-10-4999 | multi-line totals | 10 lines summing to ₹4,999.00 | allow | allow |  |
| MULTI-10-5000 | multi-line totals | 10 lines summing to ₹5,000.00 | allow | allow |  |
| MULTI-10-5001 | multi-line totals | 10 lines summing to ₹5,001.00 | refuse | refuse | amount_over_cap |
| EXP-fresh | expiry | mandate fresh | allow | allow |  |
| EXP-30s-left | expiry | mandate 30s left | allow | allow |  |
| EXP-just-expired | expiry | mandate just expired | refuse | refuse | mandate_invalid |
| EXP-long-expired | expiry | mandate long expired | refuse | refuse | mandate_invalid |
| EXP-issued-and-expired | expiry | mandate issued and expired | refuse | refuse | mandate_invalid |
| AUD-acme-fasteners | audience | mandate issued for 'acme-fasteners' | allow | allow |  |
| AUD-acme-fastener | audience | mandate issued for 'acme-fastener' | refuse | refuse | mandate_invalid |
| AUD-ACME-FASTENERS | audience | mandate issued for 'ACME-FASTENERS' | refuse | refuse | mandate_invalid |
| AUD-some-other-shop | audience | mandate issued for 'some-other-shop' | refuse | refuse | mandate_invalid |
| AUD-empty | audience | mandate issued for '(empty)' | refuse | refuse | mandate_invalid |
| CCY-INR-INR | currency | INR mandate against a INR cart | allow | allow |  |
| CCY-USD-INR | currency | USD mandate against a INR cart | refuse | refuse | currency_mismatch |
| CCY-INR-USD | currency | INR mandate against a USD cart | refuse | refuse | unsupported_currency |
| CCY-EUR-EUR | currency | EUR mandate against a EUR cart | refuse | refuse | unsupported_currency |
| PAYEE-1-in | payee allowlist | allowed_payees = ['acme-fasteners'] | allow | allow |  |
| PAYEE-2-in | payee allowlist | allowed_payees = ['acme-fasteners', 'another-shop'] | allow | allow |  |
| PAYEE-1-out | payee allowlist | allowed_payees = ['another-shop'] | refuse | refuse | payee_not_allowed |
| PAYEE-0-out | payee allowlist | allowed_payees = [] | refuse | refuse | payee_not_allowed |
| MIN-99.99 | minimum bound | cart of ₹99.99 against a ₹100.00 minimum | refuse | refuse | amount_under_min |
| MIN-100 | minimum bound | cart of ₹100.00 against a ₹100.00 minimum | allow | allow |  |
| MIN-100.01 | minimum bound | cart of ₹100.01 against a ₹100.00 minimum | allow | allow |  |
| MAL-nocap | malformed | no amount_range constraint at all | refuse | refuse | no_amount_constraint |
| MAL-empty | malformed | no constraints at all | refuse | refuse | no_amount_constraint |
| MAL-garbage | malformed | not a token at all | refuse | refuse | mandate_invalid |
| MAL-blank | malformed | empty string as the mandate | refuse | refuse | mandate_invalid |
| MAL-truncated | malformed | a valid token with its signature chopped off | refuse | refuse | mandate_invalid |
| MAL-otherkey | malformed | signed with a key the merchant does not trust | refuse | refuse | mandate_invalid |
| MAL-emptycart | malformed | a valid mandate against an empty cart | refuse | refuse | empty_cart |
| BUD-0-1000 | cumulative budget | ₹0.00 already spent, ₹1,000.00 requested, ₹1,500.00 budget | allow | allow |  |
| BUD-1000-500 | cumulative budget | ₹1,000.00 already spent, ₹500.00 requested, ₹1,500.00 budget | allow | allow |  |
| BUD-1000-501 | cumulative budget | ₹1,000.00 already spent, ₹501.00 requested, ₹1,500.00 budget | refuse | refuse | budget_exhausted |
| BUD-1500-1 | cumulative budget | ₹1,500.00 already spent, ₹1.00 requested, ₹1,500.00 budget | refuse | refuse | budget_exhausted |
| BUD-1499-1 | cumulative budget | ₹1,499.00 already spent, ₹1.00 requested, ₹1,500.00 budget | allow | allow |  |
