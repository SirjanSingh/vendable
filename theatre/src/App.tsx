import { useEffect, useRef, useState } from "react";
import { useScroll } from "framer-motion";
import ReactLenis from "lenis/react";

import { loadRun, type Run } from "@/run";
import { Scene } from "@/scenes";
import { ScrollProgressRing, StickyCard } from "@/components/skiper";
import { Eyebrow, Mono, Reveal } from "@/components/atoms";
import { GateScene } from "@/components/diagrams";

/* The three consecutive mandate refusals -- too small, wrong merchant, expired
 * -- are the one place a card stack earns its keep. They are uniform objects
 * and the effect says the thing the beats say: refusal after refusal, each on a
 * different ground, none of them negotiable. Everything else scrolls normally,
 * because this is a document about evidence and stacking dense panels would
 * cost more in legibility than it returns. */
function RefusalDeck({ run }: { run: Run }) {
  const container = useRef<HTMLDivElement>(null);
  const { scrollYProgress } = useScroll({
    target: container,
    offset: ["start start", "end end"],
  });

  const deck = run.beats.filter((b) => ["cap", "audience", "expired"].includes(b.id));

  return (
    <div ref={container} className="relative">
      {deck.map((beat, i) => (
        <StickyCard
          key={beat.id}
          i={i}
          progress={scrollYProgress}
          range={[i * (1 / deck.length), 1]}
          targetScale={1 - (deck.length - i) * 0.035}
        >
          <Scene beat={beat} />
        </StickyCard>
      ))}
    </div>
  );
}

function Cover({ run }: { run: Run }) {
  return (
    <header className="mx-auto flex min-h-dvh w-full max-w-[1100px] flex-col justify-center px-s3">
      <Reveal>
        <Eyebrow>Vendable · a captured run, replayed</Eyebrow>
      </Reveal>
      <Reveal delay={0.08}>
        <h1 className="statement mt-s3 max-w-[16ch] text-[clamp(44px,8vw,104px)]">
          What it refuses is the product.
        </h1>
      </Reveal>
      <Reveal delay={0.16}>
        <p className="mt-s4 max-w-[54ch] text-[15px] leading-relaxed text-[var(--text-dim)]">
          A buyer agent that has never seen this merchant shops, is quoted, negotiates, is refused
          on four different grounds, buys, and pays. Every figure below is transcribed from a real
          run against two live servers on Razorpay test mode.
        </p>
      </Reveal>
      <Reveal delay={0.24}>
        <div className="mt-s5 flex flex-wrap gap-s4 border-t border-[var(--edge)] pt-s3">
          <div>
            <Eyebrow>chain</Eyebrow>
            <Mono className="text-[var(--text)]">
              {run.provenance.chain_records} records · {run.provenance.chain_state}
            </Mono>
          </div>
          <div>
            <Eyebrow>source</Eyebrow>
            <Mono className="text-[var(--text)]">{run.provenance.source}</Mono>
          </div>
        </div>
      </Reveal>
      <Reveal delay={0.34}>
        <div className="mt-s5 text-[11px] uppercase tracking-[0.22em] text-[var(--text-faint)]">
          scroll
        </div>
      </Reveal>
    </header>
  );
}

export default function App() {
  const [run, setRun] = useState<Run | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    loadRun().then(setRun).catch((e) => setError(String(e)));
  }, []);

  if (error) {
    return (
      <main className="mx-auto max-w-[62ch] p-s5">
        <h1 className="statement text-[32px]">The run could not be loaded.</h1>
        <p className="mt-s3 text-[var(--text-dim)]">{error}</p>
        <p className="mt-s3 text-[13px] text-[var(--text-faint)]">
          Expected run.json alongside this page. It is served from{" "}
          <span className="font-mono">vendable/theatre/run.json</span>.
        </p>
      </main>
    );
  }

  if (!run) return <main className="min-h-dvh" aria-busy="true" />;

  const inDeck = new Set(["cap", "audience", "expired"]);
  const before = run.beats.filter((b) => b.n < 10);
  const after = run.beats.filter((b) => b.n >= 10 && !inDeck.has(b.id));

  return (
    <ReactLenis root>
      <ScrollProgressRing from={115} to={run.provenance.chain_records} />

      <Cover run={run} />

      <main className="mx-auto grid w-full min-w-0 max-w-[1180px] gap-s5 px-s3 pb-s5">
        {before.map((b) => (
          <Scene key={b.id} beat={b} />
        ))}
      </main>

      {/* The mechanism, in motion, before the evidence for it. A reader who has
          watched a cart bounce off a cap reads the three refusal cards below as
          three instances of a thing they have already seen, rather than as
          three assertions they have to take on trust. */}
      <GateScene />

      <RefusalDeck run={run} />

      <main className="mx-auto grid w-full min-w-0 max-w-[1180px] gap-s5 px-s3 pb-s5 pt-s5">
        {after.map((b) => (
          <Scene key={b.id} beat={b} />
        ))}
      </main>

      <footer className="mx-auto w-full max-w-[1180px] px-s3 pb-s5">
        <div className="border-t border-[var(--edge)] pt-s3 text-[12px] leading-relaxed text-[var(--text-faint)]">
          <p className="max-w-[70ch]">{run.provenance.note}</p>
          <p className="mt-s2">
            Scroll and reveal components adapted from{" "}
            <a
              className="text-[var(--text-dim)] underline underline-offset-2"
              href="https://skiper-ui.com"
              target="_blank"
              rel="noreferrer noopener"
            >
              Skiper UI
            </a>
            .
          </p>
        </div>
      </footer>
    </ReactLenis>
  );
}
