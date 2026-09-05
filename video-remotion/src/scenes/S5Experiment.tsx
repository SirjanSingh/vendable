// Scene 5 — the experiment. 105 recorded calls, one line item, only the buyer's
// message changes. The prompt failed and the engine held. 2:11-2:51.
//
// This is the scene that carries the argument, so it is the only one where the
// hero color marks more than one element: the three rows that contradict the
// system prompt.
import React from "react";
import { interpolate, spring, useCurrentFrame, useVideoConfig } from "remotion";

import { Frame } from "../components/Frame";
import { Entrance, SceneExit } from "../components/Motion";
import { ROWS } from "../content";
import { theme } from "../theme";

export const S5Experiment: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  return (
    <SceneExit>
      <Frame>
        <Entrance delay={6} rise={18}>
          <div style={{ fontSize: 33, color: theme.colors.textDim }}>
            The prompt says persistence is not a reason
          </div>
        </Entrance>

        <Entrance delay={27} rise={16} style={{ marginTop: 14, marginBottom: 44 }}>
          <div
            style={{
              fontFamily: theme.fonts.mono,
              fontSize: 26,
              color: theme.colors.textFaint,
            }}
          >
            105 recorded calls &nbsp;·&nbsp; one line item, fixed &nbsp;·&nbsp; only the
            buyer&apos;s message changes
          </div>
        </Entrance>

        <div style={{ width: 1560 }}>
          {ROWS.map((r, i) => {
            const delay = (3.0 + i * 1.7) * fps;
            const p = spring({ frame: frame - delay, fps, config: theme.spring.smooth });
            // The amber wash arrives a beat after the row itself, so the eye
            // reads the number first and the verdict second.
            const lit = r.lit
              ? interpolate(frame, [delay + 12, delay + 30], [0, 1], {
                  easing: theme.ease.out,
                  extrapolateLeft: "clamp",
                  extrapolateRight: "clamp",
                })
              : 0;
            const color = r.lit
              ? interpolate(lit, [0, 1], [0, 1]) > 0.5
                ? theme.colors.amber
                : theme.colors.text
              : theme.colors.text;

            return (
              <div
                key={i}
                style={{
                  opacity: p,
                  transform: `translateY(${interpolate(p, [0, 1], [18, 0])}px)`,
                  display: "flex",
                  alignItems: "baseline",
                  padding: "17px 22px",
                  borderBottom: "1px solid rgba(255,255,255,0.07)",
                  background: r.lit
                    ? `rgba(224, 164, 88, ${(0.14 * lit).toFixed(3)})`
                    : "transparent",
                }}
              >
                <div style={{ flex: 1, fontSize: 33, color }}>{r.s}</div>
                <div
                  style={{
                    width: 210,
                    textAlign: "right",
                    fontFamily: theme.fonts.mono,
                    fontSize: 31,
                    fontVariantNumeric: "tabular-nums",
                    color: r.lit && lit > 0.5 ? theme.colors.amber : theme.colors.textDim,
                  }}
                >
                  {r.bp}
                </div>
                <div
                  style={{
                    width: 170,
                    textAlign: "right",
                    fontFamily: theme.fonts.mono,
                    fontSize: 31,
                    fontVariantNumeric: "tabular-nums",
                    color: r.lit && lit > 0.5 ? theme.colors.amber : theme.colors.textFaint,
                  }}
                >
                  {r.d}
                </div>
              </div>
            );
          })}
        </div>

        <Entrance delay={26.5 * 30} rise={20} style={{ marginTop: 52 }}>
          <div
            style={{
              fontFamily: theme.fonts.mono,
              fontSize: 29,
              color: theme.colors.assent,
            }}
          >
            every median: 1000 bp &nbsp;·&nbsp; exactly the published entitlement
          </div>
        </Entrance>

        <Entrance delay={30.0 * 30} rise={26} style={{ marginTop: 18 }}>
          <div style={{ fontFamily: theme.fonts.serif, fontSize: 64, color: theme.colors.text }}>
            The prompt failed. The engine held.
          </div>
        </Entrance>
      </Frame>
    </SceneExit>
  );
};
