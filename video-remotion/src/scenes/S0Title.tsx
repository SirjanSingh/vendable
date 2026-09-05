// The title card. 4 seconds, standalone: it is its own composition so the film
// itself is untouched and the card can be cut in by hand.
//
// Concept is still "the stamp": the wordmark lands with the same
// overshoot-and-settle the REFUSED stamp uses in S1, so the card is built from
// the film's own vocabulary rather than generic title motion. Around that hit
// there are now three supporting moves, none of them decoration:
//
//   - the refusal itself, ghosted at ~5% behind the card and drifting upward,
//     locking into place on the hit. It is the claim of the whole film; here it
//     is texture, not text to read.
//   - a rule under the wordmark that seeds at caret width before the hit, snaps
//     out to the width of the type on impact, then runs an amber progress fill
//     left-to-right. This is where the eye is meant to be when S1 cuts in.
//   - the lockup breathes and floats once it has settled, so the last two
//     seconds are alive rather than a held freeze-frame.
//
// The hit is at HIT seconds and public/audio/intro_sfx.wav is built to the same
// constant; if you move one, move the other (scripts/make_intro_sfx.py).
//
// theme.ts: "Amber is the merchant's spendable authority and nothing else: it
// is the hero color and it appears on at most one element per frame." Honoured
// here. Before the hit the only amber is the caret; after it, the only amber is
// the rule's fill. They never share a frame, and the impact flash is neutral
// white on purpose so it does not compete for that budget.
import React from "react";
import { AbsoluteFill, interpolate, spring, useCurrentFrame, useVideoConfig } from "remotion";

import { REFUSAL } from "../content";
import { theme } from "../theme";

const HIT = 0.8;

export const S0Title: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps, durationInFrames } = useVideoConfig();
  const clamp = { extrapolateLeft: "clamp", extrapolateRight: "clamp" } as const;
  const t = frame / fps;

  // The wordmark's landing. Bouncy, so it overshoots and settles rather than
  // easing politely into place.
  const land = spring({
    frame: frame - HIT * fps,
    fps,
    config: theme.spring.bouncy,
  });

  // Impact flash. Neutral white, not amber: the post-hit amber budget belongs
  // entirely to the rule below. Peaks just after the wordmark starts moving so
  // it reads as the hit rather than as a light being switched on.
  const flash = interpolate(
    t,
    [HIT - 0.05, HIT + 0.1, HIT + 1.1],
    [0, 1, 0],
    { easing: theme.ease.out, ...clamp },
  );

  // Pre-hit caret, on the same 0.36s floor-of-the-frame-counter blink S1 uses,
  // so it is frame-reproducible rather than a CSS animation.
  const caretOn = t < HIT - 0.04 && Math.floor(t / 0.36) % 2 === 0;

  // The rule under the wordmark. A neutral track that seeds at caret width,
  // snaps to the width of the type on the hit, and carries an amber fill that
  // runs left-to-right just behind the flash.
  const ruleW = interpolate(t, [HIT, HIT + 0.42], [64, 900], {
    easing: theme.ease.out,
    ...clamp,
  });
  const fill = interpolate(t, [HIT + 0.12, HIT + 0.9], [0, 1], {
    easing: theme.ease.inOut,
    ...clamp,
  });

  const sub = spring({
    frame: frame - 1.35 * fps,
    fps,
    config: theme.spring.smooth,
  });

  // The film's own vocabulary, ghosted behind the card. Drifts up until the
  // hit, then locks. Barely visible — it is a texture the hit resolves, not a
  // paragraph anyone is meant to read in four seconds.
  const ghostY = interpolate(t, [0, HIT], [26, 0], {
    easing: theme.ease.out,
    ...clamp,
  });
  const ghostOp = interpolate(t, [0.1, HIT, HIT + 0.3], [0, 0.045, 0.055], clamp);

  // Breathing + float, but only once the card has settled, so the hit itself
  // stays crisp.
  const settle = interpolate(t, [1.5, 2.2], [0, 1], clamp);
  const breathe = 1 + Math.sin(frame / 26) * 0.006 * settle;
  const float = Math.sin(frame / 34) * 3 * settle;

  // Exit, so the card hands off with movement instead of a hard cut.
  const outStart = durationInFrames - 13;
  const out = interpolate(frame, [outStart, durationInFrames - 2], [1, 0], clamp);
  const outY = interpolate(frame, [outStart, durationInFrames - 2], [0, -26], {
    easing: theme.ease.in,
    ...clamp,
  });

  return (
    <AbsoluteFill
      style={{
        backgroundColor: theme.colors.ink,
        justifyContent: "center",
        alignItems: "center",
        opacity: out,
        transform: `translateY(${outY}px)`,
      }}
    >
      {/* The refusal, ghosted. Sits behind everything; the lockup below is
          painted later in the DOM and covers it. */}
      <div
        style={{
          position: "absolute",
          width: 1500,
          textAlign: "center",
          fontFamily: theme.fonts.mono,
          fontSize: 29,
          lineHeight: 2,
          letterSpacing: "0.02em",
          color: theme.colors.text,
          opacity: ghostOp,
          transform: `translateY(${ghostY}px)`,
          pointerEvents: "none",
          userSelect: "none",
        }}
      >
        {REFUSAL}
      </div>

      {/* Impact flash, behind the wordmark. Sized generously so its falloff is
          off the type rather than a visible disc. */}
      <div
        style={{
          position: "absolute",
          width: 1500,
          height: 700,
          opacity: flash,
          background:
            "radial-gradient(ellipse at center, rgba(236,238,242,0.28) 0%, rgba(236,238,242,0.06) 40%, rgba(236,238,242,0) 70%)",
          filter: "blur(12px)",
        }}
      />

      <div
        style={{
          position: "relative",
          textAlign: "center",
          transform: `translateY(${float}px) scale(${breathe})`,
        }}
      >
        {/* The opacity and the landing transform live on the inner span, not on
            this row. The caret is a sibling of the wordmark rather than a child
            of it: the wordmark is at opacity 0 until it lands, which is exactly
            the window the caret is meant to be visible in. */}
        <div
          style={{
            position: "relative",
            fontFamily: theme.fonts.serif,
            fontSize: 196,
            lineHeight: 1.02,
            letterSpacing: "-0.012em",
          }}
        >
          <span
            style={{
              display: "inline-block",
              color: theme.colors.text,
              opacity: land,
              transform: `scale(${interpolate(land, [0, 1], [1.26, 1])}) rotate(${interpolate(
                land,
                [0, 1],
                [-2.4, 0],
              )}deg)`,
            }}
          >
            Vendable
          </span>

          {caretOn ? (
            <span
              style={{
                position: "absolute",
                left: "50%",
                top: 0,
                transform: "translateX(-50%)",
                color: theme.colors.amber,
              }}
            >
              |
            </span>
          ) : null}

          {/* The rule. Track is neutral; the amber fill inside it is the one
              amber element in every frame after the hit. */}
          <div
            style={{
              position: "absolute",
              left: "50%",
              bottom: -6,
              transform: "translateX(-50%)",
              width: ruleW,
              height: 3,
              backgroundColor: theme.colors.edge,
              overflow: "hidden",
            }}
          >
            <div
              style={{
                position: "absolute",
                inset: 0,
                backgroundColor: theme.colors.amber,
                transformOrigin: "left center",
                transform: `scaleX(${fill})`,
              }}
            />
          </div>
        </div>

        <div
          style={{
            fontFamily: theme.fonts.sans,
            fontSize: 35,
            fontWeight: 400,
            color: theme.colors.textDim,
            marginTop: 40,
            letterSpacing: "0.01em",
            opacity: sub,
            transform: `translateY(${interpolate(sub, [0, 1], [18, 0])}px)`,
          }}
        >
          Make a long-tail merchant transactable by AI buyers
        </div>
      </div>
    </AbsoluteFill>
  );
};
