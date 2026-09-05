// Scene 6 — the seam, spoken rather than hidden. 2:51-3:06.
//
// The last four seconds hold on black so the editor has somewhere to cut to the
// live take without clipping a word.
import React from "react";
import { interpolate, useCurrentFrame, useVideoConfig } from "remotion";

import { Frame } from "../components/Frame";
import { WordReveal } from "../components/Motion";
import { theme } from "../theme";

export const S6Handoff: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const clamp = { extrapolateLeft: "clamp", extrapolateRight: "clamp" } as const;

  const out = interpolate(frame, [8.0 * fps, 10.5 * fps], [1, 0], {
    easing: theme.ease.in,
    ...clamp,
  });

  return (
    <Frame>
      <div style={{ opacity: out }}>
        <WordReveal
          text="That is the claim."
          delay={12}
          per={4}
          style={{ fontFamily: theme.fonts.serif, fontSize: 74, color: theme.colors.text }}
        />
        <WordReveal
          text="Here is me running it."
          delay={78}
          per={4}
          style={{
            fontFamily: theme.fonts.serif,
            fontSize: 74,
            color: theme.colors.amber,
            marginTop: 24,
          }}
        />
      </div>
    </Frame>
  );
};
