// Scene 1 — the cold open. The real MSMED refusal types itself out.
// 0:00-0:28. The claim of the whole film is in this one string.
import React from "react";
import { interpolate, spring, useCurrentFrame, useVideoConfig } from "remotion";

import { Frame } from "../components/Frame";
import { Entrance, SceneExit, useFloat } from "../components/Motion";
import { REFUSAL } from "../content";
import { theme } from "../theme";

export const S1Refusal: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const clamp = { extrapolateLeft: "clamp", extrapolateRight: "clamp" } as const;

  // The type-on. film.html ran this 2.4s-11.0s and it dragged: 8.6s is a long
  // time to watch a paragraph assemble itself before anything else happens.
  // Now 1.6s-7.6s, which still finishes inside the narration's first sentence
  // ("...it refuses anyway", ending at 10.3s) rather than racing ahead of it.
  const prog = interpolate(frame, [1.6 * fps, 7.6 * fps], [0, 1], clamp);
  const shown = REFUSAL.slice(0, Math.floor(prog * REFUSAL.length));
  const typing = prog > 0 && prog < 1;
  // Blink off a floor of the frame counter, never a CSS animation, so the
  // render stays frame-for-frame reproducible.
  const caret = typing ? 1 : prog >= 1 && Math.floor(frame / fps / 0.62) % 2 === 0 ? 0.9 : 0;

  // REFUSED lands as a stamp: overshoot in, then settle. Placed on the word
  // "refuses" in the narration (9.9s), not merely after the typing stops.
  const stampP = spring({
    frame: frame - 9.9 * fps,
    fps,
    config: theme.spring.bouncy,
  });
  const float = useFloat(40, 2);

  return (
    <SceneExit>
      <Frame>
        <Entrance delay={6} rise={22}>
          <div
            style={{
              fontFamily: theme.fonts.mono,
              fontSize: 26,
              color: theme.colors.textFaint,
              letterSpacing: "0.02em",
            }}
          >
            buyer&apos;s agent &nbsp;→&nbsp; shakti-forgings &nbsp;·&nbsp; Udyam-registered small
            manufacturer
          </div>
        </Entrance>

        <Entrance delay={33} rise={22} style={{ marginTop: 16 }}>
          <div
            style={{
              fontFamily: theme.fonts.mono,
              fontSize: 30,
              color: theme.colors.amber,
            }}
          >
            request_quote &nbsp;·&nbsp; payment_terms_days = 60
          </div>
        </Entrance>

        {/* The narration says "the merchant's own limit is ninety days" at
            5.5s, and until this line existed that number appeared nowhere on
            screen: the ear got 60 and 90, the eye got 60 and 45. It is the
            whole point of the scene, so it has to be visible. shakti's own
            commercial ceiling is more generous than the statute, and the
            statute still wins.
            Provenance: fixtures/merchants/shakti-forgings/policy.json. */}
        <Entrance delay={5.3 * 30} rise={18} style={{ marginTop: 12 }}>
          <div
            style={{
              fontFamily: theme.fonts.mono,
              fontSize: 26,
              color: theme.colors.textDim,
            }}
          >
            shakti-forgings policy &nbsp;·&nbsp; max_credit_days = 90
            <span style={{ color: theme.colors.textFaint }}>
              &nbsp;&nbsp;its own ceiling, not the law&apos;s
            </span>
          </div>
        </Entrance>

        {/* The refusal itself. Fixed height so the block below it never jumps
            as the text grows line by line. */}
        <div
          style={{
            fontFamily: theme.fonts.serif,
            fontSize: 62,
            lineHeight: 1.3,
            maxWidth: 1520,
            marginTop: 58,
            minHeight: 400,
            transform: `translateY(${float}px)`,
          }}
        >
          {shown}
          <span style={{ color: theme.colors.amber, opacity: caret }}>|</span>
        </div>

        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: 34,
            marginTop: 46,
          }}
        >
          <div
            style={{
              opacity: stampP,
              transform: `scale(${interpolate(stampP, [0, 1], [1.5, 1])}) rotate(${interpolate(
                stampP,
                [0, 1],
                [-7, 0],
              )}deg)`,
              fontFamily: theme.fonts.mono,
              fontSize: 24,
              fontWeight: 700,
              letterSpacing: "0.22em",
              color: theme.colors.refuse,
              border: `2px solid ${theme.colors.refuse}`,
              borderRadius: 8,
              padding: "10px 22px",
            }}
          >
            REFUSED
          </div>

          {/* The statute citations arrive in the 2.5s of silence, so that
              "Not because of a policy. Because of a statute." (12.8s) lands
              over them rather than announcing them. */}
          <Entrance delay={11.2 * 30} rise={16}>
            <div
              style={{
                fontFamily: theme.fonts.mono,
                fontSize: 26,
                color: theme.colors.textDim,
                letterSpacing: "0.04em",
              }}
            >
              MSMED Act &nbsp;·&nbsp; s.15 &nbsp;·&nbsp; s.16 &nbsp;·&nbsp; s.43B(h)
            </div>
          </Entrance>
        </div>
      </Frame>
    </SceneExit>
  );
};
