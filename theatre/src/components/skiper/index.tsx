/* ============================================================================
   Skiper UI primitives, de-styled.
   ----------------------------------------------------------------------------
   Adapted from Skiper UI (https://skiper-ui.com) free components:
     skiper16  StickyCard_001   -> StickyCard
     skiper41  ProgressiveBlur  -> ProgressiveBlur
     skiper89  Skiper89         -> ScrollProgressRing


   Each shipped with a demo wrapper: a #f5f4f3 ground, placeholder Lummi images,
   a #ff3828 accent, and in one case a draggable widget. All of that is removed.
   What is kept is the mechanism -- the scroll transform, the mask geometry, the
   mask geometry -- restyled against LEDGER GLASS tokens and generalised
   to take children rather than an <img>.

   Attribution is required by the free licence and is rendered in the footer.
   ========================================================================= */

import {
  motion,
  useMotionValueEvent,
  useScroll,
  useTransform,
  type MotionValue,
} from "framer-motion";
import { useRef, useState, type ReactNode } from "react";
import NumberFlow from "@number-flow/react";

import { cn } from "@/lib/utils";

/* -- ProgressiveBlur ------------------------------------------------------ */
/* A masked backdrop-blur band. Used to fade the top and bottom of the ledger
   scroll region so rows dissolve rather than being guillotined by an edge. */

type ProgressiveBlurProps = {
  className?: string;
  backgroundColor?: string;
  position?: "top" | "bottom";
  height?: string;
  blurAmount?: string;
};

export const ProgressiveBlur = ({
  className = "",
  backgroundColor = "var(--ink)",
  position = "top",
  height = "120px",
  blurAmount = "4px",
}: ProgressiveBlurProps) => {
  const isTop = position === "top";

  return (
    <div
      className={cn("pointer-events-none absolute left-0 w-full select-none", className)}
      style={{
        [isTop ? "top" : "bottom"]: 0,
        height,
        background: isTop
          ? `linear-gradient(to top, transparent, ${backgroundColor})`
          : `linear-gradient(to bottom, transparent, ${backgroundColor})`,
        maskImage: isTop
          ? `linear-gradient(to bottom, ${backgroundColor} 50%, transparent)`
          : `linear-gradient(to top, ${backgroundColor} 50%, transparent)`,
        WebkitBackdropFilter: `blur(${blurAmount})`,
        backdropFilter: `blur(${blurAmount})`,
        WebkitUserSelect: "none",
        userSelect: "none",
      }}
    />
  );
};

/* -- StickyCard ----------------------------------------------------------- */
/* The spine of the page. Each beat sticks at the top and scales down as the
   next one rides over it, so the sequence reads as a deck being laid out
   rather than a list being scrolled past. Takes children, not an image. */

export const StickyCard = ({
  i,
  progress,
  range,
  targetScale,
  children,
}: {
  i: number;
  progress: MotionValue<number>;
  range: [number, number];
  targetScale: number;
  children: ReactNode;
}) => {
  const container = useRef<HTMLDivElement>(null);
  const scale = useTransform(progress, range, [1, targetScale]);

  return (
    <div ref={container} className="sticky top-0 flex min-h-dvh items-center justify-center">
      <motion.div
        style={{ scale, top: `${i * 14}px` }}
        className="deck relative w-full origin-top"
      >
        {children}
      </motion.div>
    </div>
  );
};

/* -- ScrollProgressRing --------------------------------------------------- */
/* Kept because it earns a second job here: the ring is scroll position and the
   number beside it is the audit-chain sequence, so progress through the page
   and progress through the ledger are the same object. The original was
   draggable; a widget that wanders during a demo is a liability, so it is
   pinned. */

export const ScrollProgressRing = ({
  from,
  to,
  label = "seq",
}: {
  from: number;
  to: number;
  label?: string;
}) => {
  const { scrollYProgress } = useScroll();
  const [seq, setSeq] = useState(from);

  const clamped = useTransform(scrollYProgress, (v) => Math.min(Math.max(v, 0), 1));
  const asSeq = useTransform(clamped, (v) => Math.round(from + v * (to - from)));

  useMotionValueEvent(asSeq, "change", (v) => setSeq(v));

  const r = 18;
  const circumference = 2 * Math.PI * r;

  return (
    <div className="fixed bottom-5 right-5 z-50 flex items-center gap-3">
      <div className="text-right">
        <div className="eyebrow">{label}</div>
        <NumberFlow
          value={seq}
          className="money text-[15px] text-[var(--text)]"
        />
      </div>
      <div className="glass flex size-12 items-center justify-center rounded-2xl">
        <svg className="size-9 text-[var(--text-dim)]" viewBox="0 0 48 48" role="presentation">
          <circle
            cx="24"
            cy="24"
            r={r}
            stroke="currentColor"
            strokeWidth="2"
            className="opacity-25"
            fill="none"
          />
          <motion.circle
            cx="24"
            cy="24"
            r={r}
            stroke="var(--assent)"
            strokeWidth="2"
            fill="none"
            strokeLinecap="round"
            strokeDasharray={`${circumference}`}
            style={{
              pathLength: clamped,
              rotate: -90,
              transformOrigin: "50% 50%",
            }}
          />
        </svg>
      </div>
    </div>
  );
};

/* CharReveal (skiper31) was installed and then removed. Per-character reveal
   turns a paragraph into hundreds of inline-block spans that cannot wrap: the
   statute rendered as one unbreakable 3,581px line, overflowed every phone,
   and could not be selected or read by a screen reader. The statute is the most
   important text on this page, so it is set plainly instead. Noted rather than
   deleted silently, because "why is there no text animation" is a fair question. */
