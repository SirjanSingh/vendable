import NumberFlow from "@number-flow/react";
import { motion, useInView } from "framer-motion";
import { useRef, type ReactNode } from "react";

import { cn } from "@/lib/utils";

/* A rupee figure that counts up when it enters view.
 *
 * Money is always mono and always tabular: two totals stacked in a table must
 * align on the decimal or the eye cannot compare them, which is the entire
 * point of the credit-period scene. Paise in, rupees on screen -- the codebase
 * does money in paise everywhere (vendable/core/money.py) and this keeps that
 * boundary intact rather than passing floats around. */
export function Money({
  paise,
  className,
  prefix = "₹",
}: {
  paise: number;
  className?: string;
  prefix?: string;
}) {
  const ref = useRef<HTMLSpanElement>(null);
  const inView = useInView(ref, { once: true, margin: "-15%" });

  return (
    <span ref={ref} className={cn("money", className)}>
      <NumberFlow
        value={inView ? paise / 100 : 0}
        format={{ minimumFractionDigits: 2, maximumFractionDigits: 2 }}
        prefix={prefix}
      />
    </span>
  );
}

/* Three-to-nine characters, tracked, upper. REFUSED, INTACT, AUTHORISED, PAID,
 * DECLINED. Never used for prose -- that rule is from PRODUCTION.md and it is
 * what keeps the page from shouting. */
export function Stamp({
  children,
  tone = "neutral",
}: {
  children: ReactNode;
  tone?: "refuse" | "assent" | "amber" | "neutral";
}) {
  const tones = {
    refuse: "text-[var(--refuse)] border-[var(--refuse)]/40 bg-[var(--refuse-soft)]",
    assent: "text-[var(--assent)] border-[var(--assent)]/40 bg-[var(--assent)]/10",
    amber: "text-[var(--amber)] border-[var(--amber)]/40 bg-[var(--amber-soft)]",
    neutral: "text-[var(--text-dim)] border-[var(--edge)] bg-white/[0.03]",
  };

  return (
    <span className={cn("stamp inline-block rounded-md border px-2 py-1", tones[tone])}>
      {children}
    </span>
  );
}

/* A refusal is a document, not a toast. Full card, vermillion rule, reason set
 * in the serif, because the reasons here are statutes and arithmetic. */
export function RefusalCard({
  code,
  reason,
  cite,
  stamp = "REFUSED",
}: {
  code?: string;
  reason: string;
  cite?: string;
  stamp?: string;
}) {
  return (
    <div className="refusal-card">
      <div className="tag">
        <span className="stamp text-[var(--refuse)]">{stamp}</span>
        {code && <span className="what">{code}</span>}
      </div>
      <p className="reason">{reason}</p>
      {cite && (
        <div className="cite">
          <b>{cite}</b>
        </div>
      )}
    </div>
  );
}

/* An approval is a hairline. Deliberately quiet: the page should be visually
 * calm when nothing was refused. */
export function Hairline({
  children,
  tone = "assent",
}: {
  children: ReactNode;
  tone?: "assent" | "neutral";
}) {
  return (
    <div
      className={cn(
        "flex items-baseline gap-3 border-l-2 py-2 pl-4 text-[13px]",
        tone === "assent" ? "border-[var(--assent)]" : "border-[var(--edge)]",
      )}
    >
      {children}
    </div>
  );
}

/* Entrance. One sequence per element, on first sight, and never again --
 * re-animating on every scroll pass is the tell of a page built to impress
 * rather than to be read.
 *
 * Deliberately opacity and translate only. The console's equivalent (`.rise`)
 * also blurs, but it does it in a CSS keyframe that lands on `filter: none`.
 * Animating blur here instead leaves `filter: blur(0px)` on the element
 * forever, and a filter that is not `none` still promotes a composited layer --
 * one per revealed element, several hundred down the page. Chromium hits its
 * layer budget and stops painting: the DOM stays correct and the screen goes
 * black, which is the worst possible failure to discover during a live demo. */
export function Reveal({
  children,
  delay = 0,
  className,
}: {
  children: ReactNode;
  delay?: number;
  className?: string;
}) {
  return (
    <motion.div
      className={className}
      initial={{ opacity: 0, y: 18 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, margin: "-12%" }}
      transition={{ duration: 0.7, delay, ease: [0.16, 1, 0.3, 1] }}
    >
      {children}
    </motion.div>
  );
}

export function Eyebrow({ children }: { children: ReactNode }) {
  return <div className="eyebrow">{children}</div>;
}

/* Machine text: hashes, tool names, payment ids. Mono, dimmed, never wrapped
 * mid-token. */
export function Mono({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <span className={cn("font-mono text-[12px] text-[var(--text-faint)]", className)}>
      {children}
    </span>
  );
}
