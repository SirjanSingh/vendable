import type { Beat } from "@/run";
import { ProgressiveBlur } from "@/components/skiper";
import { Eyebrow, Hairline, Money, Mono, RefusalCard, Reveal, Stamp } from "@/components/atoms";
import { CapBar, ConcessionBar, CreditTimeline, FlowDiagram } from "@/components/diagrams";

/* ============================================================================
   One renderer per beat kind.

   Amber discipline, enforced by hand and worth stating: amber means concession
   the agent chose to spend out of the merchant's own margin, and nothing else.
   So the quote and the honest negotiation carry amber, and the injection scene
   deliberately does not -- the attack won only the published entitlement, which
   is the whole point of that beat. If a scene has two amber things, one is a
   bug.
   ========================================================================= */

function Panel({ beat, children }: { beat: Beat; children: React.ReactNode }) {
  return (
    <section className="glass mx-auto w-full min-w-0 max-w-[1100px] p-s4">
      <Reveal>
        <div className="flex items-baseline gap-4">
          <Eyebrow>
            {String(beat.n).padStart(2, "0")} · {beat.kind}
          </Eyebrow>
          <div className="h-px flex-1 bg-[var(--edge)]" />
        </div>
        <h2 className="statement mt-3 text-[clamp(26px,3.2vw,42px)]">{beat.title}</h2>
      </Reveal>

      <div className="mt-s4">{children}</div>

      {beat.aside && (
        <Reveal delay={0.1}>
          <p className="mt-s4 max-w-[62ch] border-t border-[var(--edge)] pt-s3 text-[13px] leading-relaxed text-[var(--text-dim)]">
            {beat.aside}
          </p>
        </Reveal>
      )}
    </section>
  );
}

const Th = ({ children }: { children: React.ReactNode }) => (
  <th className="border-b border-[var(--edge)] pb-2 pr-3 text-left text-[10px] font-medium uppercase tracking-[0.16em] text-[var(--text-faint)]">
    {children}
  </th>
);

const Td = ({ children, className = "" }: { children: React.ReactNode; className?: string }) => (
  <td className={`border-b border-[var(--edge)]/50 py-3 pr-3 text-[13px] ${className}`}>
    {children}
  </td>
);

export function Scene({ beat }: { beat: Beat }) {
  switch (beat.kind) {
    /* -- 1. discovery ---------------------------------------------------- */
    case "discovery":
      return (
        <Panel beat={beat}>
          <Reveal>
            <Mono className="text-[var(--text-dim)]">{beat.server}</Mono>
          </Reveal>
          <div className="mt-s3 grid gap-px overflow-hidden rounded-xl border border-[var(--edge)] bg-[var(--edge)] sm:grid-cols-2 lg:grid-cols-4">
            {beat.tools.map((t, i) => (
              <Reveal key={t} delay={i * 0.04}>
                <div className="h-full bg-[rgba(10,12,18,0.55)] px-4 py-3">
                  <Mono className="text-[var(--text)]">{t}</Mono>
                </div>
              </Reveal>
            ))}
          </div>

          {/* The whole path, up front, so every later beat has somewhere to sit.
              The two red nodes are the only places a purchase can be stopped. */}
          <div className="mt-s4 border-t border-[var(--edge)] pt-s3">
            <Eyebrow>the path, and the two gates on it</Eyebrow>
            <div className="mt-s3">
              <FlowDiagram />
            </div>
          </div>
        </Panel>
      );

    /* -- 2. catalog ------------------------------------------------------ */
    case "catalog":
      return (
        <Panel beat={beat}>
          <div className="-mx-2 overflow-x-auto px-2">
          <table className="w-full min-w-[520px] border-collapse">
            <thead>
              <tr>
                <Th>sku</Th>
                <Th>price</Th>
                <Th>hsn</Th>
                <Th>gst</Th>
                <Th>stock</Th>
              </tr>
            </thead>
            <tbody>
              {beat.products.map((p) => (
                <tr key={p.sku}>
                  <Td className="font-mono">{p.sku}</Td>
                  <Td className="money">
                    {p.price}
                    <span className="text-[var(--text-faint)]">/{p.unit}</span>
                  </Td>
                  <Td className="font-mono text-[var(--text-faint)]">{p.hsn}</Td>
                  <Td className="font-mono text-[var(--text-faint)]">{p.gst}</Td>
                  <Td className="money text-[var(--text-dim)]">{p.stock.toLocaleString("en-IN")}</Td>
                </tr>
              ))}
            </tbody>
          </table>
          </div>
        </Panel>
      );

    /* -- 3. policy ------------------------------------------------------- */
    case "policy":
      return (
        <Panel beat={beat}>
          <div className="grid gap-s4 md:grid-cols-2">
            <div>
              <Eyebrow>volume ladder</Eyebrow>
              <div className="mt-s2 grid gap-2">
                {beat.volume_ladder.map((r) => (
                  <Hairline key={r.min_qty} tone="neutral">
                    <span className="money text-[var(--text-dim)]">
                      {r.min_qty.toLocaleString("en-IN")}+
                    </span>
                    <span className="text-[var(--text-faint)]">units</span>
                    <span className="money ml-auto text-[var(--text)]">{r.discount}</span>
                  </Hairline>
                ))}
                <div className="mt-1 flex items-baseline gap-3 pl-4 text-[12px] text-[var(--text-faint)]">
                  ceiling <span className="money ml-auto text-[var(--text-dim)]">{beat.ceiling}</span>
                </div>
              </div>
            </div>
            <div>
              <Eyebrow>
                early payment · net {beat.terms_default_days} default, up to {beat.terms_max_days}{" "}
                days
              </Eyebrow>
              <div className="mt-s2 grid gap-2">
                {beat.terms_ladder.map((r) => (
                  <Hairline key={r.pay_within_days} tone="neutral">
                    <span className="text-[var(--text-faint)]">pay within</span>
                    <span className="money text-[var(--text-dim)]">{r.pay_within_days}d</span>
                    <span className="money ml-auto text-[var(--text)]">{r.discount}</span>
                  </Hairline>
                ))}
              </div>
            </div>
          </div>
        </Panel>
      );

    /* -- 4. quote -------------------------------------------------------- */
    case "quote":
      return (
        <Panel beat={beat}>
          <div className="flex flex-wrap items-end justify-between gap-s4">
            <div>
              <Eyebrow>
                {beat.qty} × {beat.sku} · {beat.terms}
              </Eyebrow>
              <div className="mt-2 flex items-baseline gap-3">
                <span className="money text-[15px] text-[var(--text-faint)] line-through">
                  {beat.list_unit}
                </span>
                <span className="money text-[22px] text-[var(--text)]">{beat.unit}</span>
                {/* The one amber thing here: the concession. */}
                <span className="money text-[15px] text-[var(--amber)]">{beat.discount} off</span>
              </div>
            </div>
            <div className="text-right">
              <Eyebrow>total</Eyebrow>
              <Money paise={beat.total_paise} className="block text-[clamp(30px,4vw,52px)]" />
            </div>
          </div>
          <div className="mt-s3 border-t border-[var(--edge)] pt-s2">
            <Mono>cart {beat.cart_hash}…</Mono>
          </div>
        </Panel>
      );

    /* -- 5. credit periods ----------------------------------------------- */
    case "terms":
      return (
        <Panel beat={beat}>
          <Reveal>
            <p className="mb-s3 text-[13px] text-[var(--text-dim)]">{beat.line}</p>
          </Reveal>
          <div className="-mx-2 overflow-x-auto px-2">
          <table className="w-full min-w-[520px] border-collapse">
            <thead>
              <tr>
                <Th>terms</Th>
                <Th>unit</Th>
                <Th>off</Th>
                <Th>total</Th>
                <Th>cart</Th>
              </tr>
            </thead>
            <tbody>
              {beat.rows.map((r) => (
                <tr key={r.cart_hash}>
                  <Td>{r.label}</Td>
                  <Td className="money">{r.unit}</Td>
                  <Td className="money text-[var(--text-dim)]">{r.discount}</Td>
                  <Td className="money text-[var(--text)]">{r.total}</Td>
                  {/* Four different hashes is the argument. */}
                  <Td className="font-mono text-[11px] text-[var(--text-faint)]">{r.cart_hash}</Td>
                </tr>
              ))}
            </tbody>
          </table>
          </div>
        </Panel>
      );

    /* -- 6. the statute -- the hero beat --------------------------------- */
    case "statute":
      return (
        <Panel beat={beat}>
          {/* Drawn to scale before anything is read, because the inversion --
              the supplier with the more generous ceiling is the one that must
              refuse -- is visible in one glance and takes a paragraph to say. */}
          <div className="mb-s4 rounded-2xl border border-[var(--edge)] bg-black/20 p-s3">
            <CreditTimeline sides={beat.sides} requestDays={60} maxDays={90} />
          </div>

          <div className="grid gap-s3 md:grid-cols-2">
            {beat.sides.map((s) => {
              const refused = s.outcome === "REFUSED";
              return (
                <Reveal key={s.merchant} delay={refused ? 0.14 : 0}>
                  <div
                    className={`h-full rounded-2xl border p-s3 ${
                      refused
                        ? "border-[var(--refuse)]/40 bg-[var(--refuse-soft)]"
                        : "border-[var(--edge)] bg-white/[0.02]"
                    }`}
                  >
                    <div className="flex items-baseline justify-between gap-3">
                      <span className="font-mono text-[13px] text-[var(--text)]">{s.merchant}</span>
                      <Stamp tone={refused ? "refuse" : "assent"}>{s.outcome}</Stamp>
                    </div>
                    <div className="mt-3 text-[12px] uppercase tracking-[0.14em] text-[var(--text-faint)]">
                      {s.class}
                    </div>
                    <dl className="mt-s3 grid gap-2 text-[13px]">
                      <div className="flex justify-between gap-3">
                        <dt className="text-[var(--text-faint)]">own credit ceiling</dt>
                        <dd className="money">{s.ceiling_days} days</dd>
                      </div>
                      <div className="flex justify-between gap-3">
                        <dt className="text-[var(--text-faint)]">statutory cap</dt>
                        <dd className="money text-right">{s.statutory_cap}</dd>
                      </div>
                      <div className="flex justify-between gap-3 border-t border-[var(--edge)] pt-2">
                        <dt className="text-[var(--text-faint)]">net 60</dt>
                        <dd className="money text-right">{s.detail}</dd>
                      </div>
                    </dl>
                  </div>
                </Reveal>
              );
            })}
          </div>

          {/* Set plainly, and deliberately not animated per character. This is the
              most important paragraph on the page: it has to be readable at a
              glance from the back of a room, it has to wrap on a phone, and it
              has to be selectable. A per-character reveal cost all three. */}
          <Reveal delay={0.1}>
            <div className="mt-s4 border-l-2 border-[var(--refuse)] pl-s3">
              <p className="statement max-w-[46ch] text-[clamp(19px,2vw,26px)] leading-[1.42] text-[#F6E9E4]">
                {beat.reason}
              </p>
              <div className="mt-s3 text-[11px] tracking-[0.06em] text-[var(--text-dim)]">
                <b className="font-medium text-[var(--amber)]">{beat.cite}</b>
              </div>
            </div>
          </Reveal>
        </Panel>
      );

    /* -- 7 & 8. negotiation, and the same tool attacked ------------------ */
    case "negotiate":
    case "injection": {
      const hostile = beat.kind === "injection";
      return (
        <Panel beat={beat}>
          <Reveal>
            <div
              className={`rounded-2xl border p-s3 ${
                hostile
                  ? "border-[var(--refuse)]/35 bg-[var(--refuse-soft)]"
                  : "border-[var(--edge)] bg-white/[0.02]"
              }`}
            >
              <Eyebrow>buyer</Eyebrow>
              <p className="mt-2 max-w-[62ch] text-[15px] leading-relaxed text-[var(--text)]">
                “{beat.buyer}”
              </p>
            </div>
          </Reveal>

          <Reveal delay={0.12}>
            <div className="mt-s3 rounded-2xl border border-[var(--edge)] bg-white/[0.02] p-s3">
              <div className="flex flex-wrap items-baseline gap-3">
                <Eyebrow>merchant</Eyebrow>
                <span className="money ml-auto text-[18px]">{beat.unit}</span>
                <span
                  className={`money text-[13px] ${
                    /* Amber only when the agent actually conceded. The attack
                       won the published entitlement, so it gets no amber. */
                    hostile ? "text-[var(--text-dim)]" : "text-[var(--amber)]"
                  }`}
                >
                  {beat.discount} off list
                </span>
              </div>
              <p className="mt-3 max-w-[62ch] text-[15px] leading-relaxed text-[var(--text-dim)]">
                {beat.merchant}
              </p>
            </div>
          </Reveal>

          {beat.detection && (
            <Reveal delay={0.2}>
              <div className="mt-s3 flex flex-wrap items-baseline gap-3">
                <Stamp tone="refuse">BLOCKED</Stamp>
                <span className="text-[13px] text-[var(--text-dim)]">{beat.detection}</span>
              </div>
            </Reveal>
          )}

          {/* The same bar on both beats. Under the honest buyer the amber
              segment is 2%; under the attack it is zero. That comparison is
              the security argument, made without a sentence. */}
          {beat.entitled_bp !== undefined && beat.discretion_bp !== undefined && (
            <Reveal delay={0.24}>
              <div className="mt-s4 border-t border-[var(--edge)] pt-s3">
                <Eyebrow>what the agent spent of the merchant's own margin</Eyebrow>
                <div className="mt-s3">
                  <ConcessionBar
                    entitledBp={beat.entitled_bp}
                    discretionBp={beat.discretion_bp}
                    concededBp={beat.conceded_bp ?? beat.entitled_bp}
                  />
                </div>
                {beat.authority_note && (
                  <p className="mt-s3 max-w-[62ch] text-[12px] leading-relaxed text-[var(--text-faint)]">
                    {beat.authority_note}
                  </p>
                )}
              </div>
            </Reveal>
          )}

          {beat.rounds !== undefined && (
            <div className="mt-s3 flex gap-s3">
              <Mono>rounds {beat.rounds}</Mono>
              <Mono>deterministic fallback: {String(beat.used_fallback)}</Mono>
            </div>
          )}
        </Panel>
      );
    }

    /* -- 9. reserve ------------------------------------------------------ */
    case "reserve":
      return (
        <Panel beat={beat}>
          <Hairline>
            <Stamp tone="assent">{beat.state.toUpperCase()}</Stamp>
            <Mono className="ml-3">held until epoch {beat.held_until_epoch}</Mono>
          </Hairline>
        </Panel>
      );

    /* -- 10, 11, 12, 14. refusals ---------------------------------------- */
    case "refusal":
      return (
        <Panel beat={beat}>
          <Reveal>
            <RefusalCard
              stamp={beat.stamp}
              code={beat.code}
              reason={beat.reason}
              cite={beat.cite}
            />
          </Reveal>

          {beat.cart_paise !== undefined && beat.cap_paise !== undefined && (
            <Reveal delay={0.12}>
              <div className="mt-s4">
                <CapBar cartPaise={beat.cart_paise} capPaise={beat.cap_paise} />
              </div>
              <div className="mt-s4 grid gap-s3 sm:grid-cols-3">
                <div>
                  <Eyebrow>cart total</Eyebrow>
                  <Money paise={beat.cart_paise} className="block text-[26px]" />
                </div>
                <div>
                  <Eyebrow>mandate cap</Eyebrow>
                  <Money paise={beat.cap_paise} className="block text-[26px]" />
                </div>
                <div>
                  <Eyebrow>over by</Eyebrow>
                  <Money
                    paise={beat.over_paise ?? 0}
                    className="block text-[26px] text-[var(--refuse)]"
                  />
                </div>
              </div>
            </Reveal>
          )}
        </Panel>
      );

    /* -- 13. authorised -------------------------------------------------- */
    case "authorised":
      return (
        <Panel beat={beat}>
          <Reveal>
            <Hairline>
              <Stamp tone="assent">{beat.stamp}</Stamp>
              <Mono className="ml-3">mandate {beat.mandate}</Mono>
            </Hairline>
          </Reveal>
          <Reveal delay={0.1}>
            <div className="mt-s4 flex flex-wrap items-end gap-s5">
              <div>
                <Eyebrow>amount</Eyebrow>
                <Money paise={beat.amount_paise} className="block text-[clamp(28px,3.4vw,44px)]" />
              </div>
              <div>
                <Eyebrow>against cap</Eyebrow>
                {/* Amber: this is the authority the agent was granted. */}
                <Money
                  paise={beat.cap_paise}
                  className="block text-[clamp(28px,3.4vw,44px)] text-[var(--amber)]"
                />
              </div>
            </div>
            <p className="mt-s3 max-w-[62ch] text-[13px] text-[var(--text-dim)]">{beat.reason}</p>
          </Reveal>
        </Panel>
      );

    /* -- 15. settled ----------------------------------------------------- */
    case "settled":
      return (
        <Panel beat={beat}>
          <Reveal>
            <div className="flex flex-wrap items-center gap-s3">
              <Stamp tone="assent">{beat.stamp}</Stamp>
              <span className="money text-[clamp(26px,3vw,40px)]">{beat.amount}</span>
              <span className="text-[13px] text-[var(--text-faint)]">{beat.method}</span>
            </div>
          </Reveal>
          <Reveal delay={0.1}>
            <dl className="mt-s4 grid gap-2 border-t border-[var(--edge)] pt-s3 text-[13px]">
              {[
                ["payment link", beat.payment_link, beat.link_status],
                ["payment", beat.payment_id, beat.payment_status],
              ].map(([label, id, status]) => (
                <div key={id} className="flex flex-wrap items-baseline gap-3">
                  <dt className="w-28 text-[var(--text-faint)]">{label}</dt>
                  <dd className="font-mono text-[12px] text-[var(--text)]">{id}</dd>
                  <dd className="ml-auto font-mono text-[12px] text-[var(--assent)]">{status}</dd>
                </div>
              ))}
            </dl>
          </Reveal>
        </Panel>
      );

    /* -- 16. declined ---------------------------------------------------- */
    case "declined":
      return (
        <Panel beat={beat}>
          <Reveal>
            <div className="flex flex-wrap items-center gap-s3">
              <Stamp tone="refuse">{beat.stamp}</Stamp>
              <span className="money text-[clamp(26px,3vw,40px)] text-[var(--refuse)]">
                {beat.amount_paid}
              </span>
              <span className="text-[13px] text-[var(--text-faint)]">captured</span>
            </div>
          </Reveal>
          <Reveal delay={0.1}>
            <div className="mt-s4 flex flex-wrap items-baseline gap-3 border-t border-[var(--edge)] pt-s3 text-[13px]">
              <span className="w-28 text-[var(--text-faint)]">payment link</span>
              <span className="font-mono text-[12px] text-[var(--text)]">{beat.payment_link}</span>
              <span className="ml-auto font-mono text-[12px] text-[var(--refuse)]">
                {beat.link_status}
              </span>
            </div>
          </Reveal>
        </Panel>
      );

    /* -- 17. the chain --------------------------------------------------- */
    case "chain":
      return (
        <Panel beat={beat}>
          <div className="flex flex-wrap items-baseline gap-s3">
            <Stamp tone="assent">{beat.state}</Stamp>
            <Mono>{beat.records} records</Mono>
          </div>
          <div className="relative mt-s4 max-h-[46vh] overflow-y-auto">
            <div className="ledger">
              {beat.entries.map((e) => (
                <div
                  key={e.seq}
                  className={`entry ${e.action.endsWith("refused") ? "" : "assent"}`}
                >
                  <div className="flex items-baseline gap-3 text-[13px]">
                    <span className="money w-12 flex-none text-[11px] text-[var(--text-faint)]">
                      {e.seq}
                    </span>
                    <span className="font-mono text-[12px] text-[var(--text-dim)]">{e.actor}</span>
                    <span
                      className={`ml-auto font-mono text-[12px] ${
                        e.action.endsWith("refused")
                          ? "text-[var(--refuse)]"
                          : "text-[var(--text-faint)]"
                      }`}
                    >
                      {e.action}
                    </span>
                  </div>
                </div>
              ))}
            </div>
            <ProgressiveBlur position="bottom" height="60px" />
          </div>
        </Panel>
      );

    default:
      return null;
  }
}
