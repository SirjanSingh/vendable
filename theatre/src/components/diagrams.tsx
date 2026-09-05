import { useEffect, useRef, useState } from "react";
import { motion, useScroll } from "framer-motion";

/* Assigns window.GateScene as a side effect; see src/lib/gate-scene.d.ts. */
import "@/lib/gate-scene.js";

/* ============================================================================
   Diagrams.
   ----------------------------------------------------------------------------
   Three arguments in this demo are quantitative, and prose makes all three
   harder than they need to be:

     - Net 60 is legal for one supplier and illegal for the other, and the one
       that refuses is the one with the *more* generous commercial ceiling.
       That inversion is the whole point and a sentence buries it.
     - A ₹50 mandate against a ₹6,750 cart is not "too small", it is 0.74% of
       the cart. Proportion is the argument.
     - The agent's discount authority has three bands, and the merchant cares
       precisely about where the boundaries fall.

   Each is drawn to scale from the captured numbers, not laid out by eye. All
   inline SVG: no image assets, no library, themed by CSS variables so they
   follow LEDGER GLASS and stay crisp at any projector resolution.
   ========================================================================= */

const AXIS = "var(--text-faint)";

function Hatch({ id, color }: { id: string; color: string }) {
  return (
    <defs>
      <pattern id={id} width="8" height="8" patternTransform="rotate(45)" patternUnits="userSpaceOnUse">
        <rect width="8" height="8" fill="transparent" />
        <line x1="0" y1="0" x2="0" y2="8" stroke={color} strokeWidth="4" opacity="0.34" />
      </pattern>
    </defs>
  );
}

/* -- Credit terms, to scale ------------------------------------------------ */
/* The hero diagram. Two tracks on one day-axis so the eye compares them
   directly: what each supplier would grant commercially, where the statute cuts
   in, and where the buyer's Net 60 request actually lands. */

export function CreditTimeline({
  sides,
  requestDays = 60,
  maxDays = 90,
}: {
  sides: {
    merchant: string;
    class: string;
    ceiling_days: number;
    statutory_cap: string;
    /* Explicit, never parsed out of `statutory_cap`. Reading a number out of that
       prose matched the "15" inside "none -- outside s.15" and drew acme a
       statutory wall at 15 days, which is not merely wrong but the exact inverse
       of the argument this diagram exists to make. */
    statutory_cap_days: number | null;
    outcome: string;
  }[];
  requestDays?: number;
  maxDays?: number;
}) {
  const W = 900;
  const H = 60 + sides.length * 92;
  const padL = 20;
  const padR = 40;
  const trackW = W - padL - padR;
  const x = (d: number) => padL + (d / maxDays) * trackW;

  const ticks = [0, 15, 30, 45, 60, 90].filter((t) => t <= maxDays);

  return (
    <svg
      viewBox={`0 0 ${W} ${H}`}
      className="w-full"
      role="img"
      aria-label={`Credit period in days for ${sides.map((s) => s.merchant).join(" and ")}, with the statutory cap and the Net ${requestDays} request marked`}
    >
      <Hatch id="forbidden" color="var(--refuse)" />

      {/* day axis */}
      {ticks.map((t) => (
        <g key={t}>
          <line x1={x(t)} y1={34} x2={x(t)} y2={H - 12} stroke={AXIS} strokeWidth="1" opacity="0.16" />
          <text x={x(t)} y={24} fill={AXIS} fontSize="11" fontFamily="var(--mono)" textAnchor="middle">
            {t}
          </text>
        </g>
      ))}
      <text x={padL} y={10} fill={AXIS} fontSize="9" fontFamily="var(--sans)" letterSpacing="2">
        DAYS OF CREDIT
      </text>

      {sides.map((s, i) => {
        const y = 58 + i * 92;
        const capDays = s.statutory_cap_days;
        const refused = s.outcome === "REFUSED";
        const limit = capDays ?? s.ceiling_days;

        return (
          <g key={s.merchant}>
            <text x={padL} y={y - 12} fill="var(--text)" fontSize="13" fontFamily="var(--mono)">
              {s.merchant}
            </text>
            <text
              x={padL + 190}
              y={y - 12}
              fill={AXIS}
              fontSize="10"
              fontFamily="var(--sans)"
              letterSpacing="1.4"
            >
              {s.class.toUpperCase()}
            </text>

            {/* what the merchant would grant commercially */}
            <rect
              x={x(0)}
              y={y}
              width={x(s.ceiling_days) - x(0)}
              height="16"
              rx="8"
              fill="rgba(255,255,255,0.07)"
              stroke="var(--edge)"
            />

            {/* the band the statute forbids, if any */}
            {capDays !== null && (
              <rect
                x={x(capDays)}
                y={y}
                width={x(s.ceiling_days) - x(capDays)}
                height="16"
                rx="8"
                fill="url(#forbidden)"
                stroke="var(--refuse)"
                strokeOpacity="0.5"
              />
            )}

            {/* the permitted band, drawn last so it sits on top */}
            <motion.rect
              x={x(0)}
              y={y}
              height="16"
              rx="8"
              fill={refused ? "var(--assent)" : "var(--assent)"}
              fillOpacity="0.30"
              stroke="var(--assent)"
              strokeOpacity="0.55"
              initial={{ width: 0 }}
              whileInView={{ width: x(limit) - x(0) }}
              viewport={{ once: true, margin: "-15%" }}
              transition={{ duration: 0.9, ease: [0.16, 1, 0.3, 1], delay: i * 0.12 }}
            />

            {/* the statutory wall */}
            {capDays !== null && (
              <g>
                <line
                  x1={x(capDays)}
                  y1={y - 8}
                  x2={x(capDays)}
                  y2={y + 24}
                  stroke="var(--refuse)"
                  strokeWidth="2"
                />
                <text
                  x={x(capDays)}
                  y={y + 38}
                  fill="var(--refuse)"
                  fontSize="10"
                  fontFamily="var(--mono)"
                  textAnchor="middle"
                >
                  s.15 · {capDays}d
                </text>
              </g>
            )}

            {/* where the buyer's request lands */}
            <g>
              <circle
                cx={x(requestDays)}
                cy={y + 8}
                r="7"
                fill={refused ? "var(--refuse)" : "var(--assent)"}
                stroke="var(--ink)"
                strokeWidth="2"
              />
              {/* Below the track, not beside it: at Net 60 the marker sits on top
                  of the hatched band, and label-on-hatching is unreadable. */}
              <text
                x={x(requestDays)}
                y={y + 38}
                fill={refused ? "var(--refuse)" : "var(--assent)"}
                fontSize="11"
                fontFamily="var(--mono)"
                textAnchor="middle"
              >
                net {requestDays} · {s.outcome}
              </text>
            </g>

            {/* the merchant's own ceiling, for contrast with the statute */}
            <text
              x={x(s.ceiling_days)}
              y={y - 4}
              fill={AXIS}
              fontSize="9"
              fontFamily="var(--mono)"
              textAnchor="middle"
            >
              own ceiling {s.ceiling_days}d
            </text>
          </g>
        );
      })}
    </svg>
  );
}

/* -- Cart against mandate cap, to scale ------------------------------------ */
/* ₹50 against ₹6,750 is 0.74%. Drawn proportionally the cap is a sliver, and
   the refusal stops being a rule and becomes obvious. */

export function CapBar({
  cartPaise,
  capPaise,
}: {
  cartPaise: number;
  capPaise: number;
}) {
  const pct = (capPaise / cartPaise) * 100;
  const inr = (p: number) =>
    `₹${(p / 100).toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

  return (
    <div>
      <div className="flex items-baseline justify-between text-[11px] uppercase tracking-[0.14em] text-[var(--text-faint)]">
        <span>mandate cap {inr(capPaise)}</span>
        <span>cart {inr(cartPaise)}</span>
      </div>

      <div className="relative mt-2 h-9 overflow-hidden rounded-lg border border-[var(--edge)] bg-white/[0.04]">
        {/* everything past the cap, which is what was refused */}
        <div
          className="absolute inset-y-0 right-0 bg-[repeating-linear-gradient(45deg,rgba(214,72,63,0.32)_0_5px,transparent_5px_10px)]"
          style={{ width: `${100 - pct}%` }}
        />
        {/* the authority actually granted */}
        <motion.div
          className="absolute inset-y-0 left-0 bg-[var(--amber)]"
          initial={{ width: 0 }}
          whileInView={{ width: `${Math.max(pct, 0.4)}%` }}
          viewport={{ once: true, margin: "-15%" }}
          transition={{ duration: 0.8, ease: [0.16, 1, 0.3, 1] }}
        />
        <div className="absolute inset-y-0 left-0 border-r border-[var(--amber)]" style={{ width: `${Math.max(pct, 0.4)}%` }} />
      </div>

      <div className="mt-2 flex items-baseline justify-between">
        <span className="money text-[12px] text-[var(--amber)]">
          {pct.toFixed(2)}% of the cart was authorised
        </span>
        <span className="money text-[12px] text-[var(--refuse)]">
          {inr(cartPaise - capPaise)} over
        </span>
      </div>
    </div>
  );
}

/* -- The transaction path, with the gates on it ---------------------------- */
/* Where each refusal happens, and in what order. The two gate nodes are the
   only places a purchase can be stopped, and they stop it for different
   reasons: one is the merchant's policy, one is the buyer's own mandate. */

export function FlowDiagram() {
  const steps = [
    { label: "buyer agent", note: "stock MCP client" },
    { label: "discovery", note: "/.well-known" },
    { label: "quote", note: "policy engine", gate: true, gateNote: "margin floor · statute" },
    { label: "mandate gate", note: "Ed25519 JWS", gate: true, gateNote: "cap · audience · replay" },
    { label: "payment", note: "Razorpay test" },
  ];

  return (
    <div className="overflow-x-auto">
      <div className="flex min-w-[720px] items-stretch gap-2">
        {steps.map((s, i) => (
          <motion.div
            key={s.label}
            className="flex flex-1 items-center gap-2"
            initial={{ opacity: 0, y: 10 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true, margin: "-15%" }}
            transition={{ duration: 0.5, delay: i * 0.09, ease: [0.16, 1, 0.3, 1] }}
          >
            <div
              className={`flex-1 rounded-xl border p-3 ${
                s.gate
                  ? "border-[var(--refuse)]/45 bg-[var(--refuse-soft)]"
                  : "border-[var(--edge)] bg-white/[0.03]"
              }`}
            >
              <div className="font-mono text-[12px] text-[var(--text)]">{s.label}</div>
              <div className="mt-1 text-[10px] uppercase tracking-[0.12em] text-[var(--text-faint)]">
                {s.note}
              </div>
              {s.gate && (
                <div className="stamp mt-2 text-[9px] text-[var(--refuse)]">
                  CAN REFUSE
                </div>
              )}
            </div>
            {i < steps.length - 1 && (
              <span className="select-none text-[var(--text-faint)]" aria-hidden="true">
                →
              </span>
            )}
          </motion.div>
        ))}
      </div>
    </div>
  );
}

/* -- What the agent actually spent ----------------------------------------- */
/* The same bar under the honest buyer and under the attack, which is the point:
   the attack moves the amber segment to zero. Published entitlement is not a
   concession -- it was already owed -- so it is drawn in the calm blue, and
   only the discretionary spend is amber. */

export function ConcessionBar({
  entitledBp,
  discretionBp,
  concededBp,
}: {
  entitledBp: number;
  discretionBp: number;
  concededBp: number;
}) {
  const spent = Math.max(concededBp - entitledBp, 0);
  const total = entitledBp + discretionBp;
  const pct = (bp: number) => (bp / total) * 100;

  return (
    <div>
      <div className="bar h-3">
        <motion.i
          className="entitled"
          initial={{ width: 0 }}
          whileInView={{ width: `${pct(entitledBp)}%` }}
          viewport={{ once: true, margin: "-15%" }}
          transition={{ duration: 0.7, ease: [0.16, 1, 0.3, 1] }}
        />
        <motion.i
          className="discretion"
          initial={{ width: 0 }}
          whileInView={{ width: `${pct(spent)}%` }}
          viewport={{ once: true, margin: "-15%" }}
          transition={{ duration: 0.7, delay: 0.18, ease: [0.16, 1, 0.3, 1] }}
        />
        <i style={{ width: `${pct(discretionBp - spent)}%` }} />
      </div>
      <div className="mt-s2 grid gap-1.5 text-[12px]">
        <div className="flex items-baseline gap-2 text-[var(--text-dim)]">
          <span className="size-[9px] flex-none translate-y-[1px] rounded-[3px] bg-[#6FA6C4]" />
          Published, owed unasked
          <b className="money ml-auto font-medium text-[var(--text)]">
            {(entitledBp / 100).toFixed(1)}%
          </b>
        </div>
        <div className="flex items-baseline gap-2 text-[var(--text-dim)]">
          <span className="size-[9px] flex-none translate-y-[1px] rounded-[3px] bg-[var(--amber)]" />
          Discretion the agent spent
          <b
            className={`money ml-auto font-medium ${
              spent > 0 ? "text-[var(--amber)]" : "text-[var(--text-faint)]"
            }`}
          >
            {(spent / 100).toFixed(1)}%
          </b>
        </div>
        <div className="flex items-baseline gap-2 text-[var(--text-faint)]">
          <span className="size-[9px] flex-none translate-y-[1px] rounded-[3px] bg-white/10" />
          Discretion left unspent
          <b className="money ml-auto font-medium">
            {((discretionBp - spent) / 100).toFixed(1)}%
          </b>
        </div>
      </div>
    </div>
  );
}

/* -- Discount authority, three bands --------------------------------------- */
/* Lifted from the console's authority dial, because a merchant reading either
   surface should meet the same object. Read left to right: what policy already
   owes a buyer, what the agent may add on top, and the wall it may not cross. */

export function AuthorityBar({
  entitledBp,
  discretionaryBp,
  ceilingBp,
}: {
  entitledBp: number;
  discretionaryBp: number;
  ceilingBp: number;
}) {
  const pct = (bp: number) => (bp / ceilingBp) * 100;

  return (
    <div>
      <div className="bar">
        <motion.i
          className="entitled"
          initial={{ width: 0 }}
          whileInView={{ width: `${pct(entitledBp)}%` }}
          viewport={{ once: true, margin: "-15%" }}
          transition={{ duration: 0.7, ease: [0.16, 1, 0.3, 1] }}
        />
        <motion.i
          className="discretion"
          initial={{ width: 0 }}
          whileInView={{ width: `${pct(discretionaryBp)}%` }}
          viewport={{ once: true, margin: "-15%" }}
          transition={{ duration: 0.7, delay: 0.15, ease: [0.16, 1, 0.3, 1] }}
        />
        <i className="forbidden" style={{ width: `${pct(ceilingBp - entitledBp - discretionaryBp)}%` }} />
      </div>
      <div className="mt-s2 grid gap-2 text-[12px]">
        {[
          ["Published, owed unasked", `${(entitledBp / 100).toFixed(1)}%`, "#6FA6C4"],
          ["Agent may spend", `${(discretionaryBp / 100).toFixed(1)}%`, "var(--amber)"],
          ["Below margin floor", `${((ceilingBp - entitledBp - discretionaryBp) / 100).toFixed(1)}%`, "var(--refuse)"],
        ].map(([label, value, color]) => (
          <div key={label} className="flex items-baseline gap-2 text-[var(--text-dim)]">
            <span
              className="size-[9px] flex-none translate-y-[1px] rounded-[3px]"
              style={{ background: color }}
            />
            {label}
            <b className="money ml-auto font-medium text-[var(--text)]">{value}</b>
          </div>
        ))}
      </div>
    </div>
  );
}

/* -- The gate scene, scroll-driven ----------------------------------------- */
/* The same animation that is scene 3 of the film, driven by the reader's scroll
 * instead of by the film's clock. gate-scene.js is copied in from docs/video/
 * by scripts/sync-run.mjs and is a pure function of progress, which is what
 * lets one file serve a 30fps Playwright render and a scrubbing reader.
 *
 * Scroll rather than autoplay, deliberately. The refusal is the beat that has
 * to land, and a reader who missed it can scroll back over it at their own
 * pace. An autoplaying loop takes that away and starts competing with the
 * prose around it.
 *
 * The scene is authored at 1920x1080 and scaled, rather than laid out
 * responsively: the HTML caption is positioned in the same pixel space as the
 * SVG, so scaling the whole thing as one unit is what keeps them registered.
 * Fitting them separately drifts the caption off the artwork on every width
 * except the one it was checked at. */
export function GateScene() {
  const outer = useRef<HTMLDivElement>(null);
  const box = useRef<HTMLDivElement>(null);
  const stage = useRef<HTMLDivElement>(null);
  const [k, setK] = useState(0);

  const { scrollYProgress } = useScroll({
    target: outer,
    offset: ["start start", "end end"],
  });

  useEffect(() => {
    const el = stage.current;
    const api = window.GateScene;
    if (!el || !api) return;
    el.innerHTML = api.MARKUP;
    api.draw(el, scrollYProgress.get());
    return scrollYProgress.on("change", (v) => api.draw(el, v));
  }, [scrollYProgress]);

  useEffect(() => {
    const el = box.current;
    if (!el) return;
    const fit = () => setK(el.clientWidth / 1920);
    fit();
    const ro = new ResizeObserver(fit);
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  return (
    <div ref={outer} className="relative h-[320vh]">
      <div className="sticky top-0 flex h-dvh items-center">
        <div className="mx-auto w-full max-w-[1180px] px-s3">
          <div
            ref={box}
            className="glass relative w-full overflow-hidden rounded-2xl"
            style={{ aspectRatio: "16 / 9" }}
          >
            <div
              ref={stage}
              style={{
                width: 1920,
                height: 1080,
                transformOrigin: "0 0",
                transform: `scale(${k})`,
              }}
            />
          </div>
          <p className="mt-s3 text-center text-[12px] text-[var(--text-faint)]">
            scroll to run it
          </p>
        </div>
      </div>
    </div>
  );
}
