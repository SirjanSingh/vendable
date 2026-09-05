// The five-layer stack every scene sits inside:
//   background mesh -> content -> grade -> grain -> vignette
//
// film.html painted a flat #080A0E with one static radial wash. Flat backgrounds
// are the tell that separates "rendered slide" from "film", and they band badly
// under YouTube's encoder at this bit depth.
import React from "react";
import { AbsoluteFill, useCurrentFrame } from "remotion";

import { theme } from "../theme";

export const BgMesh: React.FC = () => {
  const frame = useCurrentFrame();
  // Slow, wide drift. Everything here is a pure function of `frame`, so the
  // render stays reproducible in the same way film.html's seek(t) was.
  const d1 = Math.sin(frame / 210) * 60;
  const d2 = Math.cos(frame / 260) * 48;

  return (
    <AbsoluteFill style={{ background: theme.colors.ink }}>
      <div
        style={{
          position: "absolute",
          width: 1700,
          height: 1700,
          borderRadius: "50%",
          top: -680 + d2 * 0.4,
          left: -280 + d1,
          filter: "blur(60px)",
          background: `radial-gradient(circle, ${theme.colors.amber}1F, transparent 62%)`,
        }}
      />
      <div
        style={{
          position: "absolute",
          width: 1300,
          height: 1300,
          borderRadius: "50%",
          bottom: -620,
          right: -320 - d2,
          filter: "blur(80px)",
          background: `radial-gradient(circle, ${theme.colors.assent}14, transparent 66%)`,
        }}
      />
    </AbsoluteFill>
  );
};

export const Grade: React.FC = () => (
  <AbsoluteFill style={{ pointerEvents: "none" }}>
    <AbsoluteFill
      style={{
        backgroundColor: theme.colors.amber,
        mixBlendMode: "soft-light",
        opacity: 0.16,
      }}
    />
    <AbsoluteFill
      style={{
        background:
          "linear-gradient(180deg, rgba(0,0,0,0.16), transparent 26%, transparent 70%, rgba(0,0,0,0.26))",
      }}
    />
  </AbsoluteFill>
);

export const Grain: React.FC = () => {
  const frame = useCurrentFrame();
  const noise = `url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='220' height='220'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='2'/%3E%3C/filter%3E%3Crect width='220' height='220' filter='url(%23n)' opacity='0.5'/%3E%3C/svg%3E")`;
  return (
    <AbsoluteFill
      style={{
        pointerEvents: "none",
        backgroundImage: noise,
        backgroundSize: "220px",
        // Shifting the tile per frame is what reads as film grain rather than
        // as a fixed dirty overlay.
        backgroundPosition: `${(frame * 7) % 220}px ${(frame * 13) % 220}px`,
        opacity: 0.055,
        mixBlendMode: "overlay",
      }}
    />
  );
};

export const Vignette: React.FC = () => (
  <AbsoluteFill
    style={{
      pointerEvents: "none",
      background:
        "radial-gradient(ellipse at center, transparent 54%, rgba(0,0,0,0.30) 100%)",
    }}
  />
);

/** Wraps scene content in the full stack. Content goes in as children. */
export const Stage: React.FC<{ children: React.ReactNode }> = ({ children }) => (
  <AbsoluteFill style={{ backgroundColor: theme.colors.ink }}>
    <BgMesh />
    <AbsoluteFill>{children}</AbsoluteFill>
    <Grade />
    <Grain />
    <Vignette />
  </AbsoluteFill>
);
