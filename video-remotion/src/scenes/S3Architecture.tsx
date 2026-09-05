// Scene 3 — the architecture diagram, under a camera. 1:01-1:36.
//
// The diagram is drawn at its native 1240x900 and moved by a camera rather than
// fitted to the frame. Fitting it put its 12.5px body text at ~11px on a 1080p
// frame: under the legibility floor and precisely what YouTube's encoder throws
// away. Pushing in keeps the smallest text on screen at 22px and the parts that
// carry the argument over 40px.
import React from "react";
import {
  AbsoluteFill,
  Img,
  interpolate,
  staticFile,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";

import { SceneExit } from "../components/Motion";
import { CAM } from "../content";
import { theme } from "../theme";

const FIT_W = 1700;
const FIT_H = 800;
const S_MAX = 3.4;

const clampN = (x: number, a: number, b: number) => (x < a ? a : x > b ? b : x);
const camScale = (c: (typeof CAM)[number]) =>
  clampN(Math.min(FIT_W / c.w, FIT_H / c.h), 1.0, S_MAX);

export const S3Architecture: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const s = frame / fps;
  const clamp = { extrapolateLeft: "clamp", extrapolateRight: "clamp" } as const;

  const appear = interpolate(frame, [6, 72], [0, 1], {
    easing: theme.ease.out,
    ...clamp,
  });

  let i = 0;
  for (let k = 0; k < CAM.length; k++) if (s >= CAM[k].at) i = k;
  const cur = CAM[i];
  const prev = i > 0 ? CAM[i - 1] : CAM[0];

  // Eased camera move, 1.1s. film.html used smoothstep; easeInOutQuint gives the
  // move a heavier start and a softer arrival, which reads as a camera rather
  // than as a tween.
  const move = interpolate(frame, [cur.at * fps, (cur.at + 1.1) * fps], [0, 1], {
    easing: theme.ease.inOut,
    ...clamp,
  });

  // A slow continuous drift on top of the cut-to-cut moves, so the frame is
  // never completely locked off. This is the Ken Burns rule applied to a still.
  const drift = Math.sin(frame / 150) * 5;
  const driftScale = 1 + Math.sin(frame / 190) * 0.006;

  const sc = interpolate(move, [0, 1], [camScale(prev), camScale(cur)]) * driftScale;
  const cx = interpolate(move, [0, 1], [prev.cx, cur.cx]);
  const cy = interpolate(move, [0, 1], [prev.cy, cur.cy]);

  const left = 960 - cx * sc + drift;
  const top = 540 - cy * sc;

  const capShown = cur.label
    ? interpolate(frame, [(cur.at + 0.35) * fps, (cur.at + 1.15) * fps], [0, 1], {
        easing: theme.ease.out,
        ...clamp,
      })
    : 0;

  return (
    <SceneExit>
      <AbsoluteFill>
        <div
          style={{
            position: "absolute",
            left: 0,
            top: 0,
            width: 1240,
            height: 900,
            transformOrigin: "0 0",
            transform: `translate(${left.toFixed(2)}px, ${top.toFixed(2)}px) scale(${sc.toFixed(4)})`,
            opacity: appear,
          }}
        >
          <Img
            src={staticFile("architecture.svg")}
            style={{ width: 1240, height: 900, display: "block" }}
          />
        </div>

        {/* A floor under the caption so it never sits on a diagram box. */}
        <div
          style={{
            position: "absolute",
            left: 0,
            right: 0,
            bottom: 0,
            height: 220,
            opacity: capShown,
            background: `linear-gradient(180deg, transparent, ${theme.colors.ink} 52%)`,
          }}
        />
        <div
          style={{
            position: "absolute",
            left: theme.layout.marginX,
            bottom: 72,
            // Absolutely positioned with no definite width, this collapsed to
            // min-content and stacked one word per line over the diagram.
            whiteSpace: "nowrap",
            opacity: capShown,
            transform: `translateY(${interpolate(capShown, [0, 1], [16, 0])}px)`,
            fontFamily: theme.fonts.mono,
            fontSize: 33,
            color: theme.colors.amber,
          }}
        >
          {cur.label}
        </div>
      </AbsoluteFill>
    </SceneExit>
  );
};
