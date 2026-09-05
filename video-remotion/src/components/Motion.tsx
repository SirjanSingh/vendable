// Entrances, exits, and breathing.
//
// film.html had exactly one entrance (opacity + a 16px rise, smoothstep) applied
// to everything, nothing ever exited, and nothing moved once it had landed. That
// combination is what makes a cut feel static even when the timing is correct.
import React from "react";
import {
  interpolate,
  spring,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";

import { theme } from "../theme";

/** Entrance: opacity + rise + scale, three properties, spring-driven. */
export const Entrance: React.FC<{
  delay?: number;
  rise?: number;
  config?: { damping: number; stiffness: number; mass: number };
  style?: React.CSSProperties;
  children: React.ReactNode;
}> = ({ delay = 0, rise = 34, config = theme.spring.smooth, style, children }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const p = spring({ frame: frame - delay, fps, config });

  return (
    <div
      style={{
        opacity: p,
        transform: `translateY(${interpolate(p, [0, 1], [rise, 0])}px) scale(${interpolate(
          p,
          [0, 1],
          [0.965, 1],
        )})`,
        ...style,
      }}
    >
      {children}
    </div>
  );
};

/**
 * Scene-level exit. Faster than any entrance (12 frames vs ~20) and applied to a
 * whole scene wrapper, so a cut lands on movement rather than on a crossfade.
 */
export const SceneExit: React.FC<{
  children: React.ReactNode;
  style?: React.CSSProperties;
}> = ({ children, style }) => {
  const frame = useCurrentFrame();
  const { durationInFrames } = useVideoConfig();
  const a = durationInFrames - 13;
  const b = durationInFrames - 3;
  const clamp = { extrapolateLeft: "clamp", extrapolateRight: "clamp" } as const;

  const y = interpolate(frame, [a, b], [0, -38], {
    easing: theme.ease.in,
    ...clamp,
  });
  const o = interpolate(frame, [a, b], [1, 0], clamp);

  return (
    <div style={{ opacity: o, transform: `translateY(${y}px)`, ...style }}>
      {children}
    </div>
  );
};

/**
 * Word-by-word reveal for the display lines. 3-frame stagger.
 * `gap` is in px on purpose: an em gap resolves against the parent font-size,
 * not the 58px type, and collapses to nothing.
 */
export const WordReveal: React.FC<{
  text: string;
  delay?: number;
  per?: number;
  style?: React.CSSProperties;
  wordStyle?: (i: number) => React.CSSProperties;
}> = ({ text, delay = 0, per = 3, style, wordStyle }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  return (
    <div style={{ display: "flex", flexWrap: "wrap", ...style }}>
      {text.split(" ").map((word, i) => {
        const p = spring({
          frame: frame - delay - i * per,
          fps,
          config: theme.spring.snappy,
        });
        return (
          <span
            key={i}
            style={{
              display: "inline-block",
              marginRight: "0.28em",
              opacity: p,
              transform: `translateY(${interpolate(p, [0, 1], [26, 0])}px)`,
              ...(wordStyle ? wordStyle(i) : {}),
            }}
          >
            {word}
          </span>
        );
      })}
    </div>
  );
};

/** Micro-motion for anything that sits on screen longer than two seconds. */
export const useBreathe = (period = 26, amount = 0.006) => {
  const frame = useCurrentFrame();
  return 1 + Math.sin(frame / period) * amount;
};

export const useFloat = (period = 34, px = 3) => {
  const frame = useCurrentFrame();
  return Math.sin(frame / period) * px;
};
