import React from "react";
import { AbsoluteFill, Audio, Composition, Sequence, staticFile } from "remotion";
import { loadFont as loadSerif } from "@remotion/google-fonts/InstrumentSerif";
import { loadFont as loadSans } from "@remotion/google-fonts/SpaceGrotesk";
import { loadFont as loadMono } from "@remotion/google-fonts/JetBrainsMono";

import { Stage } from "./components/Layers";
import { CUES, TOTAL, VO_LEAD } from "./content";
import { S1Refusal } from "./scenes/S1Refusal";
import { S2Problem } from "./scenes/S2Problem";
import { S3Architecture } from "./scenes/S3Architecture";
import { S4Refusals } from "./scenes/S4Refusals";
import { S5Experiment } from "./scenes/S5Experiment";
import { S0Title } from "./scenes/S0Title";
import { S6Handoff } from "./scenes/S6Handoff";
import { theme } from "./theme";

// Fonts are bundled by Remotion rather than fetched from the Google CDN at
// render time, so a render cannot silently fall back to a system serif.
// Only the weights and subset actually used. Left unconstrained, each font
// fired ~96 network requests per frame and slowed the render badly.
const subsets = { subsets: ["latin"] as const, ignoreTooManyRequestsWarning: true };
loadSerif("normal", { weights: ["400"], ...subsets });
loadSans("normal", { weights: ["400", "500", "700"], ...subsets });
loadMono("normal", { weights: ["400", "500", "700"], ...subsets });

const FPS = 30;

const SCENES: Record<string, React.FC> = {
  s1: S1Refusal,
  s2: S2Problem,
  s3: S3Architecture,
  s4: S4Refusals,
  s5: S5Experiment,
  s6: S6Handoff,
};

export const PartOne: React.FC = () => (
  <AbsoluteFill style={{ backgroundColor: theme.colors.ink }}>
    <Stage>
      {CUES.map((cue, i) => {
        const Scene = SCENES[cue.id];
        const from = Math.round(cue.at * FPS);
        const dur = Math.round(cue.dur * FPS);
        const lead = Math.round(VO_LEAD * FPS);
        return (
          <React.Fragment key={cue.id}>
            <Sequence from={from} durationInFrames={dur} name={cue.id}>
              <Scene />
            </Sequence>
            {/* Narration, one file per cue. Bounded to the cue window on
                purpose: if a re-recorded read ever outgrows its scene the
                clipped word is obvious on the first watch, where a read
                bleeding across a cut is not. The windows in content.ts are
                sized from the measured durations, so nothing clips today. */}
            <Sequence
              from={from + lead}
              durationInFrames={dur - lead}
              name={`${cue.id}-vo`}
            >
              <Audio src={staticFile(`audio/vo_0${i + 1}.wav`)} />
            </Sequence>
          </React.Fragment>
        );
      })}
    </Stage>
  </AbsoluteFill>
);

/**
 * The title card, as its own 4s composition rather than a scene prepended to
 * PartOne. Kept separate on purpose: the card gets cut in by hand in an editor,
 * and folding it into PartOne would shift every cue by 4s and invalidate the
 * measured timings in content.ts for no gain.
 */
export const Intro: React.FC = () => (
  <AbsoluteFill style={{ backgroundColor: theme.colors.ink }}>
    <S0Title />
    <Audio src={staticFile("audio/intro_sfx.wav")} />
  </AbsoluteFill>
);

export const RemotionRoot: React.FC = () => (
  <>
    <Composition
      id="PartOne"
      component={PartOne}
      durationInFrames={Math.round(TOTAL * FPS)}
      fps={FPS}
      width={1920}
      height={1080}
    />
    <Composition
      id="Intro"
      component={Intro}
      durationInFrames={4 * FPS}
      fps={FPS}
      width={1920}
      height={1080}
    />
  </>
);
