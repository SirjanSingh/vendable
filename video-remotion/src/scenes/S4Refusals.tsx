// Scene 4 — every money action, gated. Four real refusals. 1:36-2:11.
import React from "react";
import { interpolate, spring, useCurrentFrame, useVideoConfig } from "remotion";

import { Frame } from "../components/Frame";
import { Entrance, SceneExit } from "../components/Motion";
import { REFUSALS } from "../content";
import { theme } from "../theme";

// Held from film.html: each row lands as the narration reaches it.
const AT = [1.0, 7.5, 13.5, 19.5];

export const S4Refusals: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  return (
    <SceneExit>
      <Frame>
        <Entrance delay={6} rise={18}>
          <div
            style={{
              fontSize: 33,
              color: theme.colors.textDim,
              letterSpacing: "0.01em",
              marginBottom: 48,
            }}
          >
            Every money action, gated
          </div>
        </Entrance>

        <div style={{ display: "flex", flexDirection: "column", gap: 40 }}>
          {REFUSALS.map((r, i) => {
            const p = spring({
              frame: frame - AT[i] * fps,
              fps,
              config: theme.spring.smooth,
            });
            // A rule sweeps in with each row: it gives the eye an edge to track
            // down the list, which four free-floating text blocks did not.
            const rule = interpolate(p, [0, 1], [0, 1]);

            return (
              <div
                key={i}
                style={{
                  opacity: p,
                  transform: `translateY(${interpolate(p, [0, 1], [26, 0])}px)`,
                  display: "flex",
                  gap: 28,
                  maxWidth: 1560,
                }}
              >
                <div
                  style={{
                    width: 3,
                    alignSelf: "stretch",
                    transformOrigin: "50% 0%",
                    transform: `scaleY(${rule})`,
                    background: r.c ? theme.colors.refuse : theme.colors.assent,
                    opacity: 0.55,
                    borderRadius: 3,
                  }}
                />
                <div>
                  <div style={{ fontSize: 34, fontWeight: 500, color: theme.colors.text }}>
                    {r.t}
                  </div>
                  {r.c ? (
                    <div
                      style={{
                        fontFamily: theme.fonts.mono,
                        fontSize: 24,
                        color: theme.colors.refuse,
                        marginTop: 9,
                        letterSpacing: "0.04em",
                      }}
                    >
                      {r.c}
                    </div>
                  ) : null}
                  <div
                    style={{
                      fontFamily: theme.fonts.serif,
                      fontSize: 38,
                      color: theme.colors.textDim,
                      marginTop: 11,
                    }}
                  >
                    {r.q}
                  </div>
                </div>
              </div>
            );
          })}
        </div>

        <Entrance delay={26.5 * 30} rise={24} style={{ marginTop: 58 }}>
          <div
            style={{
              fontSize: 40,
              fontWeight: 500,
              color: theme.colors.amber,
              textShadow: `0 0 60px ${theme.colors.glow}`,
            }}
          >
            Every refusal carries the reason that makes it actionable.
          </div>
        </Entrance>
      </Frame>
    </SceneExit>
  );
};
