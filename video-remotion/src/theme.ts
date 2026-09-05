// Single source of truth. Never inline a color, easing, or spring config.
//
// The palette is lifted verbatim from vendable/console/index.html, the same way
// docs/video/film.html does it, so the film and the product stay the same object.
// Amber is the merchant's spendable authority and nothing else: it is the hero
// color and it appears on at most one element per frame.
import { Easing } from "remotion";

export const theme = {
  colors: {
    ink: "#080A0E",
    ink2: "#0D1016",
    text: "#ECEEF2",
    textDim: "#8B93A1",
    textFaint: "#5A6472",
    amber: "#E0A458",
    amberSoft: "rgba(224, 164, 88, 0.14)",
    refuse: "#D6483F",
    assent: "#5FA88A",
    edge: "rgba(255, 255, 255, 0.10)",
    glow: "rgba(224, 164, 88, 0.35)",
  },
  fonts: {
    serif: '"Instrument Serif", Georgia, "Times New Roman", serif',
    sans: '"Space Grotesk", ui-sans-serif, system-ui, sans-serif',
    mono: '"JetBrains Mono", ui-monospace, "SF Mono", Menlo, monospace',
  },
  // Linear is forbidden.
  ease: {
    out: Easing.bezier(0.16, 1, 0.3, 1), // easeOutExpo, entrances
    inOut: Easing.bezier(0.83, 0, 0.17, 1), // camera moves, Ken Burns
    in: Easing.bezier(0.7, 0, 0.84, 0), // exits only
  },
  spring: {
    snappy: { damping: 14, stiffness: 160, mass: 0.6 },
    smooth: { damping: 20, stiffness: 90, mass: 1 },
    bouncy: { damping: 11, stiffness: 170, mass: 0.7 },
  },
  // The frame is 1920x1080. Content lives inside this box, centred vertically.
  // film.html anchored everything to the top-left with a fixed padding, which
  // left the bottom half of every scene empty; that is the single biggest
  // reason the first cut read as a slide deck rather than a film.
  layout: {
    marginX: 168,
    safeW: 1584,
  },
} as const;
