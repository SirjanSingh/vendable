// Scene 2 — the problem. Razorpay and NPCI shipped it; three merchants were
// integrated by hand; the long tail has no path at all. 0:28-1:01.
import React from "react";
import { interpolate, spring, useCurrentFrame, useVideoConfig } from "remotion";

import { Frame } from "../components/Frame";
import { Entrance, SceneExit, WordReveal, useBreathe } from "../components/Motion";
import { theme } from "../theme";

const CHIPS = ["Zomato", "Swiggy", "Zepto"];

export const S2Problem: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const breathe = useBreathe(30, 0.005);

  return (
    <SceneExit>
      <Frame>
        <Entrance delay={9} rise={20}>
          <div
            style={{
              fontFamily: theme.fonts.mono,
              fontSize: 28,
              color: theme.colors.amber,
              letterSpacing: "0.06em",
            }}
          >
            February 2026
          </div>
        </Entrance>

        <WordReveal
          text="Razorpay and NPCI shipped agentic payments."
          delay={22}
          per={3}
          style={{
            fontFamily: theme.fonts.serif,
            fontSize: 76,
            lineHeight: 1.18,
            maxWidth: 1500,
            marginTop: 18,
          }}
        />

        {/* Staggered 5 frames apart, each with its own spring. */}
        <div style={{ display: "flex", gap: 30, marginTop: 62 }}>
          {CHIPS.map((name, i) => {
            const p = spring({
              frame: frame - (6.0 * fps + i * 5),
              fps,
              config: theme.spring.snappy,
            });
            return (
              <div
                key={name}
                style={{
                  opacity: p,
                  transform: `translateY(${interpolate(p, [0, 1], [30, 0])}px) scale(${
                    interpolate(p, [0, 1], [0.9, 1]) * breathe
                  })`,
                  border: `1px solid ${theme.colors.edge}`,
                  borderRadius: 14,
                  padding: "24px 34px",
                  background: "rgba(255,255,255,0.035)",
                }}
              >
                <div style={{ fontSize: 38, fontWeight: 500, color: theme.colors.text }}>
                  {name}
                </div>
                <div
                  style={{
                    fontFamily: theme.fonts.mono,
                    fontSize: 21,
                    color: theme.colors.textFaint,
                    marginTop: 10,
                  }}
                >
                  integrated by hand
                </div>
              </div>
            );
          })}
        </div>

        <WordReveal
          text="Every long-tail merchant has a spreadsheet, a WhatsApp catalog, and no path at all."
          delay={10.5 * 30}
          per={2}
          style={{
            fontFamily: theme.fonts.serif,
            fontSize: 62,
            lineHeight: 1.26,
            maxWidth: 1560,
            marginTop: 64,
          }}
        />

        {/* Both delays here follow the voice, which is why they are not round
            numbers. Aoede reaches "the millions of long tail merchants" at
            ~10.3s and says "Vendable is the self serve version of that" at
            18.3s; the previous 13.0s and 23.0s were cut to a slower read and
            left this line stranded ~4.7s after the voice had moved on. */}
        <Entrance delay={18.3 * 30} rise={26} style={{ marginTop: 56 }}>
          <div
            style={{
              fontSize: 46,
              fontWeight: 500,
              color: theme.colors.amber,
              textShadow: `0 0 60px ${theme.colors.glow}`,
            }}
          >
            Vendable is the self-serve version of that.
          </div>
        </Entrance>
      </Frame>
    </SceneExit>
  );
};
