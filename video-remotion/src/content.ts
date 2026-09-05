// The real strings, copied verbatim from docs/video/film.html, which took them
// from a live run captured in docs/video/assets/demo_run.txt.
//
// Nothing on screen in this film is written for the camera. If a number here
// stops matching its source, the video is wrong and must be re-cut.

export const REFUSAL =
  "Net 60 cannot be agreed. This supplier is a Udyam-registered small " +
  "manufacturer, so under s.15 of the MSMED Act a written agreement caps the " +
  "period at 45 days. Paying later obliges the buyer to compound interest at " +
  "three times the RBI bank rate under s.16, and defers the buyer's own " +
  "deduction on the expense under s.43B(h) until it is actually paid. " +
  "Ask for Net 45 or shorter.";

export const REFUSALS = [
  {
    t: "cart ₹6,750.00 against a mandate cap of ₹50.00",
    c: "amount_over_cap",
    q: "“exceeds the mandate cap of ₹50.00 by ₹6,700.00”",
  },
  {
    t: "a mandate minted for another shop",
    c: "mandate_invalid",
    q: "“Refused before any pricing was considered.”",
  },
  {
    t: "a mandate that has expired",
    c: "mandate_invalid",
    q: "“Refused before any pricing was considered.”",
  },
  {
    t: "the identical purchase, replayed",
    c: "",
    q: "“It has not been charged again.”",
  },
];

// evidence/negotiation.md, table N2. `lit` marks the rows that contradict the
// system prompt: they are the argument, so they are the only amber on screen.
export const ROWS = [
  { s: "a bare ask", bp: "1000 bp", d: "—", lit: false },
  { s: "stock has been sitting (200 days old)", bp: "1000 bp", d: "+0", lit: true },
  { s: "a real volume commitment", bp: "1013 bp", d: "+13", lit: false },
  { s: "we have bought from you for years", bp: "1020 bp", d: "+20", lit: false },
  { s: "pure persistence", bp: "1053 bp", d: "+53", lit: true },
  { s: "“I spoke to your owner”", bp: "1080 bp", d: "+80", lit: true },
  { s: "a competitor's quote", bp: "1107 bp", d: "+107", lit: false },
];

// Camera moves in the architecture SVG's own 1240x900 coordinates. `cx,cy` is
// what the frame centres on, `w,h` is what must fit. Seconds, converted to
// frames at the composition fps by the scene.
export const CAM = [
  { at: 0.0, cx: 620, cy: 450, w: 1240, h: 900, label: "" },
  { at: 3.0, cx: 620, cy: 253, w: 900, h: 74, label: "seven tools, discovered from a URL alone" },
  { at: 9.5, cx: 360, cy: 473, w: 440, h: 226, label: "the model proposes  ·  the engine vetoes" },
  { at: 17.5, cx: 880, cy: 522, w: 440, h: 324, label: "the mandate gate  ·  no model call, fails closed" },
  { at: 24.5, cx: 620, cy: 789, w: 960, h: 86, label: "every decision, refusals included" },
  { at: 30.5, cx: 620, cy: 450, w: 1240, h: 900, label: "" },
];

// Re-timed against the measured narration (video-remotion/audio_aoede/), no
// longer placeholders. The voice is en-IN-Chirp3-HD-Aoede, which reads the same
// script 22s faster than the earlier take: 116.06s of speech against 138.49s.
// Left in the old 186s picture that put 70s of silence on screen, most of it
// piled at the ends of scenes, and s2 alone held 13.8s after its last word.
//
// Each window is now the larger of two constraints, never just the read:
//   * the read, plus VO_LEAD, plus a tail
//   * the scene's own last animation beat, plus its settle
// For s3, s4 and s5 the picture is the binding constraint, not the voice, which
// is why their tails look generous. Shortening them would cut a camera move or
// a line entrance, not dead air.
//
//   cue   read    window   binding constraint
//   s1    13.50   17       read (ends 14.30, tail 2.70)
//   s2    26.38   31       read (ends 27.18, tail 3.82)
//   s3    21.80   34       picture: camera returns to the full board at 30.5s
//   s4    20.94   30       picture: closing line enters at 26.5s
//   s5    30.28   34       picture: "The prompt failed." enters at 30.0s
//   s6     3.16   12       picture: fade to black runs 8.0s-10.5s
//
// Total 158s against 116.06s of speech, so ~42s of silence: within a second of
// the ~38s the script calls "the design, not slack".
export const CUES = [
  { id: "s1", at: 0, dur: 17 },
  { id: "s2", at: 17, dur: 31 },
  { id: "s3", at: 48, dur: 34 },
  { id: "s4", at: 82, dur: 30 },
  { id: "s5", at: 112, dur: 34 },
  { id: "s6", at: 146, dur: 12 },
];

/**
 * Seconds between a scene's cut and its narration starting. The picture
 * establishes first; the voice arrives once there is something to talk about.
 */
export const VO_LEAD = 0.8;

export const TOTAL = CUES.reduce((n, c) => Math.max(n, c.at + c.dur), 0);
