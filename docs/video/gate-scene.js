/* =========================================================================
   The gate scene: one purchase, animated, explained by motion.

   Scene 3 of the film used to be a camera panning across a static
   architecture diagram. A viewer who has never heard the words "MCP" or
   "mandate" learned nothing from it, because nothing on screen ever did
   anything. This replaces it with a sequence where a buyer travels to a
   shop, asks, is quoted, has a model's proposal deleted in front of it, and
   then tries to pay twice: once against a cap it does not fit under, once
   against one it does.

   THE ONE RULE, inherited from film.html: every visual state is a pure
   function of `p`. No CSS transitions, no requestAnimationFrame, no Date,
   no Math.random. `draw(root, 0.5)` must paint identical pixels every time
   it is called, in any order, on any machine. The renderer steps p in
   1/30s increments and screenshots each one; anything driven by wall-clock
   time drifts the frames against the voice track.

   Every number on screen is from the run captured in
   docs/video/assets/demo_run.txt:

     step 4   600 x BOLT-M8-40, list Rs 12.50 -> Rs 11.25, total Rs 6,750.00
     step 10  the same Rs 6,750.00 against a cap of Rs 50.00     -> REFUSED
     step 13  the same Rs 6,750.00 against a cap of Rs 10,000.00 -> AUTHORISED

   That pairing is why the animation works. The cart never changes size.
   The cap does. Both bars are drawn to the same scale, so "over the cap" is
   something the viewer sees rather than something the film asserts.

   Loaded as a classic script by film.html and copied into the theatre build
   by theatre/scripts/sync-run.mjs. No imports, no exports, no framework, so
   the same file drives a Playwright render and a React page.
   ========================================================================= */

window.GateScene = (function () {
  "use strict";

  /* ---------- pure helpers, same shapes film.html uses ------------------ */
  const clamp = (x, a, b) => (x < a ? a : x > b ? b : x);
  /* progress through [a,b]: 0 before, 1 after */
  const pr = (t, a, b) => (b <= a ? (t >= b ? 1 : 0) : clamp((t - a) / (b - a), 0, 1));
  const ease = (x) => x * x * (3 - 2 * x);
  const out = (x) => 1 - (1 - x) * (1 - x);
  const lerp = (a, b, x) => a + (b - a) * x;
  /* a single overshoot, for something landing with weight */
  const pop = (x) => (x >= 1 ? 1 : 1 - Math.pow(1 - x, 3) * Math.cos(x * 7.2));

  /* ---------- the scene runs 35s, matching cue [3] --------------------- */
  const DUR = 35;

  /* ---------- geometry, in the SVG's own 1920x1080 ---------------------- */
  const ASK_Y = 400;   // the lane a question travels on
  const PAY_Y = 760;   // the lane money travels on
  const X_IN = 460;    // where a packet leaves the buyer
  const X_OUT = 1480;  // where it reaches the shop
  const LLM_X = 700;
  const GATE_X = 1060;

  /* Rupees to pixels. The cart, the small cap and the large cap are all
     drawn through this one number, which is what makes the comparison
     honest rather than illustrative. */
  const PX = 1 / 40;
  const CART = 6750;      // Rs 6,750.00, the cart from step 4
  const CAP_LO = 50;      // Rs 50.00, the mandate of step 10
  const CAP_HI = 10000;   // Rs 10,000.00, the mandate of step 13
  const CART_H = CART * PX;                    // 169px
  /* A Rs 50 cap is 1.25px and would read as a rendering artefact rather than
     as a cap. Floored to 9px so it is visibly a slot that is visibly too
     small, which is the true statement the 1.25px would fail to make. */
  const GAP_LO = Math.max(9, CAP_LO * PX);
  const GAP_HI = CAP_HI * PX;                  // 250px

  const TOOLS = ["search", "product", "policies", "quote", "negotiate", "reserve", "buy"];

  /* ---------- the markup, built once ----------------------------------- */
  function pills() {
    let s = "";
    for (let i = 0; i < TOOLS.length; i++) {
      const x = 560 + i * 130;
      /* y=96, not 150: at 150 the row sat on top of the policy engine's label
         and the two were unreadable together. */
      s +=
        '<g id="gs-tool-' + i + '" opacity="0">' +
        '<rect x="' + x + '" y="96" width="118" height="56" rx="12" ' +
        'fill="rgba(255,255,255,0.05)" stroke="var(--edge,rgba(255,255,255,0.10))"/>' +
        '<text class="gs-pill" x="' + (x + 59) + '" y="133" text-anchor="middle">' +
        TOOLS[i] +
        "</text></g>";
    }
    return s;
  }

  /* The four outcomes, in the order the scene produces them. Two of the
     four are refusals, and they are the same size as the approvals: the
     chain records what did not happen with the same weight as what did. */
  const CHAIN = [
    { label: "quote", kind: "ok" },
    { label: "VETO", kind: "no" },
    { label: "REFUSED", kind: "no" },
    { label: "paid", kind: "ok" },
  ];

  /* The row sits at y=846 and stops at x=990, which is not arbitrary: at the
     full width it ran under the HTML caption, and at the old y it crossed the
     mandate gate's lower bar. Both were only visible in a still. */
  function chain() {
    let s = "";
    for (let i = 0; i < CHAIN.length; i++) {
      const x = 150 + i * 220;
      if (i > 0) {
        s +=
          '<line id="gs-link-' + (i - 1) + '" x1="' + (x - 40) + '" y1="884" ' +
          'x2="' + x + '" y2="884" stroke="var(--amber,#E0A458)" ' +
          'stroke-width="3" opacity="0"/>';
      }
      const col = CHAIN[i].kind === "no" ? "var(--refuse,#D6483F)" : "var(--assent,#5FA88A)";
      s +=
        '<g id="gs-chain-' + i + '" opacity="0">' +
        '<rect x="' + x + '" y="846" width="180" height="76" rx="10" ' +
        'fill="rgba(255,255,255,0.04)" stroke="' + col + '" stroke-width="2"/>' +
        '<text class="gs-block" x="' + (x + 90) + '" y="893" text-anchor="middle" ' +
        'fill="' + col + '">' + CHAIN[i].label + "</text></g>";
    }
    return s;
  }

  const MARKUP = `
<style>
  .gs-wrap { position: absolute; inset: 0; }
  .gs-svg  { position: absolute; left: 0; top: 0; width: 100%; height: 100%; display: block; }
  .gs-svg text { font-family: var(--sans, "Space Grotesk", system-ui, sans-serif); }
  .gs-h    { font-size: 31px; font-weight: 500; fill: var(--text, #ECEEF2); }
  .gs-sub  { font-size: 24px; fill: var(--text-faint, #5A6472);
             font-family: var(--mono, "JetBrains Mono", monospace); }
  .gs-pill { font-size: 26px; fill: var(--text-dim, #8B93A1);
             font-family: var(--mono, "JetBrains Mono", monospace); }
  .gs-amt  { font-size: 30px; font-weight: 700;
             font-family: var(--mono, "JetBrains Mono", monospace); }
  .gs-cap-l{ font-size: 26px; fill: var(--amber, #E0A458);
             font-family: var(--mono, "JetBrains Mono", monospace); }
  .gs-block{ font-size: 27px; font-weight: 700; letter-spacing: 0.06em;
             font-family: var(--mono, "JetBrains Mono", monospace); }
  .gs-stampt { font-size: 34px; font-weight: 700; letter-spacing: 0.2em;
             font-family: var(--mono, "JetBrains Mono", monospace); }

  /* Captions are HTML, not SVG text, on purpose: render_film.py --pacing
     measures reading load with innerText, and keeping the prose in HTML
     keeps that check measuring the thing it claims to measure. */
  .gs-cap  { position: absolute; left: 140px; bottom: 58px; max-width: 1320px;
             font-family: var(--mono, "JetBrains Mono", monospace);
             font-size: 30px; line-height: 1.35; color: var(--amber, #E0A458); }
  .gs-line { position: absolute; left: 140px; bottom: 58px;
             font-family: var(--serif, Georgia, serif);
             font-size: 60px; color: var(--text, #ECEEF2); }
</style>

<div class="gs-wrap">
<svg class="gs-svg" viewBox="0 0 1920 1080" preserveAspectRatio="xMidYMid meet" aria-hidden="true">

  <!-- lanes -->
  <path id="gs-askpath" d="M 380 505 H 440 V 400 H 1500" fill="none"
        stroke="var(--edge,rgba(255,255,255,0.10))" stroke-width="3"/>
  <path id="gs-paypath" d="M 380 585 H 440 V 760 H 1500" fill="none"
        stroke="var(--edge,rgba(255,255,255,0.10))" stroke-width="3"/>

  <!-- the buyer -->
  <g id="gs-buyer" opacity="0">
    <rect x="110" y="470" width="270" height="140" rx="18"
          fill="rgba(255,255,255,0.04)" stroke="var(--edge,rgba(255,255,255,0.10))"/>
    <circle id="gs-buyerdot" cx="152" cy="512" r="9" fill="var(--amber,#E0A458)"/>
    <text class="gs-h"   x="178" y="522">AI buyer</text>
    <text class="gs-sub" x="140" y="568">has never seen</text>
    <text class="gs-sub" x="140" y="596">this merchant</text>
  </g>

  <!-- the shop -->
  <g id="gs-shop" opacity="0">
    <rect x="1510" y="300" width="300" height="520" rx="14"
          fill="rgba(255,255,255,0.04)" stroke="var(--edge,rgba(255,255,255,0.10))"/>
    <path d="M 1510 372 H 1810" stroke="var(--edge,rgba(255,255,255,0.10))" stroke-width="3"/>
    <text class="gs-h"   x="1660" y="345" text-anchor="middle">the merchant</text>
    <text class="gs-sub" x="1660" y="430" text-anchor="middle">a spreadsheet</text>
    <text class="gs-sub" x="1660" y="462" text-anchor="middle">and a price list</text>
    <text class="gs-sub" x="1660" y="494" text-anchor="middle">until today</text>
  </g>

  <!-- the seven tools -->
  ${pills()}

  <!-- the model, on the asking lane only -->
  <g id="gs-llm" opacity="0">
    <circle id="gs-llmring" cx="${LLM_X}" cy="${ASK_Y}" r="62" fill="none"
            stroke="var(--amber,#E0A458)" stroke-width="2" opacity="0"/>
    <circle cx="${LLM_X}" cy="${ASK_Y}" r="46" fill="rgba(224,164,88,0.14)"
            stroke="var(--amber,#E0A458)" stroke-width="2"/>
    <text class="gs-sub" x="${LLM_X}" y="${ASK_Y + 10}" text-anchor="middle"
          fill="var(--amber,#E0A458)">LLM</text>
    <text class="gs-sub" x="${LLM_X}" y="${ASK_Y + 108}" text-anchor="middle">proposes only</text>
  </g>

  <!-- the policy gate: bars that close across the asking lane -->
  <g id="gs-pgate" opacity="0">
    <rect x="${GATE_X - 14}" y="240" width="28" height="320" rx="6"
          fill="rgba(214,72,63,0.10)"/>
    <rect id="gs-pgate-top" x="${GATE_X - 14}" y="240" width="28" height="0"
          rx="6" fill="var(--refuse,#D6483F)"/>
    <rect id="gs-pgate-bot" x="${GATE_X - 14}" y="560" width="28" height="0"
          rx="6" fill="var(--refuse,#D6483F)"/>
    <text class="gs-sub" x="${GATE_X}" y="215" text-anchor="middle">policy engine</text>
  </g>

  <!-- the mandate gate: the opening IS the cap, drawn to scale.
       The faint jamb is what makes it read as a gate. Without it, a wide cap
       leaves two short amber chips floating in the dark and the shape stops
       meaning anything. Both labels sit ABOVE the band: below it they landed
       on top of the audit chain in beat 5. -->
  <g id="gs-mgate" opacity="0">
    <rect x="${GATE_X - 14}" y="600" width="28" height="320" rx="6"
          fill="rgba(224,164,88,0.10)"/>
    <rect id="gs-mgate-top" x="${GATE_X - 14}" y="600" width="28" height="0"
          rx="6" fill="var(--amber,#E0A458)"/>
    <rect id="gs-mgate-bot" x="${GATE_X - 14}" y="920" width="28" height="0"
          rx="6" fill="var(--amber,#E0A458)"/>
    <text class="gs-sub" x="${GATE_X + 30}" y="540">mandate gate</text>
    <text class="gs-sub" x="${GATE_X + 30}" y="572">no model here</text>
    <text id="gs-caplabel" class="gs-cap-l" x="${GATE_X + 40}" y="${PAY_Y + 9}"
          opacity="0">cap</text>
  </g>

  <!-- a question travelling out -->
  <g id="gs-req" opacity="0">
    <rect x="-70" y="-26" width="140" height="52" rx="10"
          fill="rgba(255,255,255,0.06)" stroke="var(--text-dim,#8B93A1)"/>
    <text class="gs-sub" x="0" y="9" text-anchor="middle"
          fill="var(--text,#ECEEF2)">600 units</text>
  </g>

  <!-- the price coming back, and then dropping -->
  <g id="gs-tag" opacity="0">
    <rect x="-108" y="-34" width="216" height="68" rx="10"
          fill="rgba(255,255,255,0.06)" stroke="var(--text-dim,#8B93A1)"/>
    <text id="gs-tagv" class="gs-amt" x="0" y="10" text-anchor="middle"
          fill="var(--text,#ECEEF2)">Rs 12.50</text>
    <text id="gs-tagoff" class="gs-cap-l" x="0" y="66" text-anchor="middle"
          opacity="0">10% volume break, unasked</text>
  </g>

  <!-- the ask that goes too far -->
  <g id="gs-ask2" opacity="0">
    <rect x="-124" y="-26" width="248" height="52" rx="10"
          fill="rgba(224,164,88,0.14)" stroke="var(--amber,#E0A458)"/>
    <text class="gs-sub" x="0" y="9" text-anchor="middle"
          fill="var(--amber,#E0A458)">give me more off</text>
  </g>

  <!-- what the model proposed, before it was deleted -->
  <g id="gs-ghost" opacity="0">
    <rect x="-104" y="-26" width="208" height="52" rx="10" fill="none"
          stroke="var(--amber,#E0A458)" stroke-width="2" stroke-dasharray="9 7"/>
    <text class="gs-sub" x="0" y="9" text-anchor="middle"
          fill="var(--amber,#E0A458)">95% off?</text>
  </g>

  <!-- the cart, as a bar whose height is what it costs -->
  <g id="gs-coin" opacity="0">
    <rect id="gs-coinr" x="-84" y="${-CART_H / 2}" width="168" height="${CART_H}"
          rx="10" fill="rgba(95,168,138,0.16)" stroke="var(--assent,#5FA88A)" stroke-width="2"/>
    <text id="gs-coint" class="gs-amt" x="0" y="10" text-anchor="middle"
          fill="var(--assent,#5FA88A)">Rs 6,750</text>
  </g>

  <!-- The verdict, left of the gate. It used to sit at x=1240, where the
       AUTHORISED line ran straight across the merchant's box. -->
  <g id="gs-stamp" opacity="0">
    <text id="gs-stampt" class="gs-stampt" x="512" y="${PAY_Y - 150}">REFUSED</text>
    <text id="gs-stampw" class="gs-sub" x="512" y="${PAY_Y - 108}">over by Rs 6,700.00</text>
  </g>

  <!-- the veto stamp on the asking lane -->
  <g id="gs-veto" opacity="0">
    <text class="gs-stampt" x="1120" y="${ASK_Y - 90}" fill="var(--refuse,#D6483F)">VETO</text>
  </g>

  <!-- the record -->
  ${chain()}

</svg>

<div class="gs-cap"></div>
<div class="gs-line"></div>
</div>`;

  /* ---------- drawing ---------------------------------------------------- */

  /* One cache per root element. Querying 30 nodes 5,400 times is the kind of
     thing that turns a 4 minute render into a 15 minute one. */
  function cache(root) {
    if (root.__gs) return root.__gs;
    const c = { el: {}, len: {} };
    const grab = (id) => (c.el[id] = root.querySelector("#" + id));
    [
      "gs-buyer", "gs-shop", "gs-llm", "gs-llmring", "gs-pgate", "gs-pgate-top",
      "gs-pgate-bot", "gs-mgate", "gs-mgate-top", "gs-mgate-bot", "gs-caplabel",
      "gs-req", "gs-tag", "gs-tagv", "gs-tagoff", "gs-ask2", "gs-ghost",
      "gs-coin", "gs-coinr", "gs-coint", "gs-stamp", "gs-stampt", "gs-stampw",
      "gs-veto", "gs-askpath", "gs-paypath",
    ].forEach(grab);
    for (let i = 0; i < TOOLS.length; i++) grab("gs-tool-" + i);
    for (let i = 0; i < CHAIN.length; i++) grab("gs-chain-" + i);
    for (let i = 0; i < CHAIN.length - 1; i++) grab("gs-link-" + i);
    c.cap = root.querySelector(".gs-cap");
    c.line = root.querySelector(".gs-line");
    /* Path lengths are fixed geometry, so measuring once is not state. */
    c.len.ask = c.el["gs-askpath"].getTotalLength();
    c.len.pay = c.el["gs-paypath"].getTotalLength();
    root.__gs = c;
    return c;
  }

  const show = (el, v) => { el.style.opacity = v; };
  const at = (el, x, y, s) =>
    (el.setAttribute(
      "transform",
      "translate(" + x.toFixed(2) + "," + y.toFixed(2) + ")" +
        (s === undefined ? "" : " scale(" + s.toFixed(4) + ")")
    ));

  /* The caption is one element whose text changes, so only one line of prose
     is ever in the DOM. That keeps --pacing's word count honest and keeps the
     screen under the twelve-word rule in PRODUCTION.md. */
  const CAPTIONS = [
    { at: 0.9,  s: "A stock client connects, knowing only a URL." },
    { at: 3.0,  s: "It is handed seven tools." },
    { at: 5.9,  s: "It asks for 600 units." },
    { at: 8.0,  s: "Quoted, with the volume break already applied." },
    { at: 11.0, s: "It pushes for more. The model proposes." },
    { at: 13.4, s: "The engine deletes the proposal." },
    { at: 17.4, s: "Now it tries to pay. The mandate has a cap." },
    { at: 19.5, s: "The cart does not fit. Refused, and it says by how much." },
    { at: 22.9, s: "Same cart, a mandate that allows it. Through." },
    { at: 26.4, s: "Every outcome is written down. Refusals included." },
    /* Cleared early so the closing line is the last thing that appears and
       still gets its 4 seconds of dwell before the cut. `--pacing` measures
       exactly this and flagged 3.0s the first time round. */
    { at: 30.0, s: "" },
  ];

  function caption(c, t) {
    let s = "";
    for (let i = 0; i < CAPTIONS.length; i++) if (t >= CAPTIONS[i].at) s = CAPTIONS[i].s;
    if (c.cap.textContent !== s) c.cap.textContent = s;
    /* fade in over the 0.4s after whichever caption is current */
    let a = 0;
    for (let i = 0; i < CAPTIONS.length; i++) {
      if (t >= CAPTIONS[i].at) a = ease(pr(t, CAPTIONS[i].at, CAPTIONS[i].at + 0.4));
    }
    c.cap.style.opacity = s === "" ? 0 : a;
  }

  function draw(root, p) {
    const c = cache(root);
    const t = clamp(p, 0, 1) * DUR;

    /* ---- beat 1: it connects, and is handed seven tools --------------- */
    const bIn = ease(pr(t, 0.2, 1.7));
    show(c.el["gs-buyer"], bIn);
    at(c.el["gs-buyer"], lerp(-330, 0, bIn), 0);
    show(c.el["gs-shop"], ease(pr(t, 0.0, 1.0)));

    const dAsk = ease(pr(t, 1.4, 2.7));
    const dPay = ease(pr(t, 1.7, 3.0));
    c.el["gs-askpath"].setAttribute("stroke-dasharray", c.len.ask);
    c.el["gs-askpath"].setAttribute("stroke-dashoffset", (c.len.ask * (1 - dAsk)).toFixed(2));
    c.el["gs-paypath"].setAttribute("stroke-dasharray", c.len.pay);
    c.el["gs-paypath"].setAttribute("stroke-dashoffset", (c.len.pay * (1 - dPay)).toFixed(2));

    for (let i = 0; i < TOOLS.length; i++) {
      const v = pop(pr(t, 2.4 + i * 0.17, 2.85 + i * 0.17));
      const el = c.el["gs-tool-" + i];
      show(el, clamp(v, 0, 1));
      at(el, 0, lerp(-22, 0, clamp(v, 0, 1)));
    }

    /* ---- beat 2: it asks, and is quoted ------------------------------- */
    const reqGo = pr(t, 4.3, 5.9);
    show(c.el["gs-req"], ease(pr(t, 4.1, 4.5)) * (1 - ease(pr(t, 5.7, 6.1))));
    at(c.el["gs-req"], lerp(X_IN, X_OUT, ease(reqGo)), ASK_Y);

    const tagGo = pr(t, 6.4, 7.8);
    show(c.el["gs-tag"], ease(pr(t, 6.3, 6.7)) * (1 - ease(pr(t, 9.4, 9.9))));
    at(c.el["gs-tag"], lerp(X_OUT, 640, ease(tagGo)), ASK_Y);
    /* the price drops once the tag has landed, not while it is moving */
    const cut = t >= 8.1;
    const want = cut ? "Rs 11.25" : "Rs 12.50";
    if (c.el["gs-tagv"].textContent !== want) c.el["gs-tagv"].textContent = want;
    c.el["gs-tagv"].setAttribute("fill", cut ? "var(--assent,#5FA88A)" : "var(--text,#ECEEF2)");
    show(c.el["gs-tagoff"], ease(pr(t, 8.3, 8.9)));

    /* ---- beat 3: the model proposes, the engine deletes it ------------ */
    const askGo = pr(t, 9.9, 11.0);
    show(c.el["gs-ask2"], ease(pr(t, 9.7, 10.1)) * (1 - ease(pr(t, 11.0, 11.3))));
    at(c.el["gs-ask2"], lerp(X_IN, LLM_X, ease(askGo)), ASK_Y);

    show(c.el["gs-llm"], ease(pr(t, 9.6, 10.2)) * (1 - 0.62 * ease(pr(t, 15.8, 16.8))));
    /* the model thinking: a ring expanding out of it, twice, from t alone */
    const think = pr(t, 11.0, 11.9);
    c.el["gs-llmring"].setAttribute("r", (46 + out(think) * 46).toFixed(2));
    show(c.el["gs-llmring"], (1 - think) * 0.9);

    const ghostGo = pr(t, 11.7, 13.0);
    const ghostDies = ease(pr(t, 13.0, 13.35));
    show(c.el["gs-ghost"], ease(pr(t, 11.6, 12.0)) * (1 - ghostDies));
    at(
      c.el["gs-ghost"],
      lerp(LLM_X + 60, GATE_X - 118, ease(ghostGo)),
      ASK_Y,
      lerp(1, 0.55, ghostDies)
    );

    /* the gate slams: 0.3s, the fastest movement in the scene */
    const slam = out(pr(t, 12.75, 13.05));
    c.el["gs-pgate-top"].setAttribute("height", (slam * 160).toFixed(2));
    c.el["gs-pgate-bot"].setAttribute("y", (560 - slam * 160).toFixed(2));
    c.el["gs-pgate-bot"].setAttribute("height", (slam * 160).toFixed(2));

    /* The asking lane recedes once the money beat starts. It stays on screen,
       because the gate really does stay shut, but at full strength a closed red
       gate and a live VETO stamp compete with the refusal happening below them
       and the eye goes to the wrong half of the frame. */
    const recede = 1 - 0.62 * ease(pr(t, 15.8, 16.8));
    show(c.el["gs-pgate"], ease(pr(t, 11.4, 12.0)) * recede);
    show(c.el["gs-veto"], pop(pr(t, 13.2, 13.7)) * (1 - ease(pr(t, 15.6, 16.4))));

    /* ---- beat 4: the money, twice ------------------------------------- */
    show(c.el["gs-mgate"], ease(pr(t, 16.4, 17.1)));
    /* The opening is the cap, to scale. It starts at Rs 50 and is replaced by
       Rs 10,000 after the refusal: the cart never resizes, the cap does. */
    const wide = ease(pr(t, 20.9, 21.6));
    const gap = lerp(GAP_LO, GAP_HI, wide);
    c.el["gs-mgate-top"].setAttribute("height", (PAY_Y - gap / 2 - 600).toFixed(2));
    c.el["gs-mgate-bot"].setAttribute("y", (PAY_Y + gap / 2).toFixed(2));
    c.el["gs-mgate-bot"].setAttribute("height", (920 - PAY_Y - gap / 2).toFixed(2));
    const capTxt = wide > 0.5 ? "cap Rs 10,000" : "cap Rs 50";
    if (c.el["gs-caplabel"].textContent !== capTxt) c.el["gs-caplabel"].textContent = capTxt;
    show(c.el["gs-caplabel"], ease(pr(t, 17.0, 17.6)));

    /* first attempt: out to the gate, stopped, thrown back */
    const goA = ease(pr(t, 17.6, 19.1));
    const backA = ease(pr(t, 19.35, 20.5));
    /* second attempt: the identical bar, through the widened gate */
    const goB = ease(pr(t, 21.9, 23.3));
    const thru = ease(pr(t, 23.3, 24.4));

    /* it stops with its leading edge just short of the gate, not on it */
    const STOP_X = GATE_X - 100;
    let cx, cvis;
    if (t < 20.9) {
      cx = lerp(X_IN, STOP_X, goA) - backA * (STOP_X - X_IN + 260);
      cvis = ease(pr(t, 17.4, 17.8)) * (1 - ease(pr(t, 20.2, 20.7)));
    } else {
      cx = lerp(X_IN, STOP_X, goB) + thru * (X_OUT - STOP_X);
      cvis = ease(pr(t, 21.7, 22.1)) * (1 - ease(pr(t, 24.2, 24.7)));
    }
    show(c.el["gs-coin"], cvis);
    /* a shove backwards reads as rejection; a small lift sells the bounce */
    const lift = backA > 0 && backA < 1 ? Math.sin(backA * Math.PI) * -34 : 0;
    at(c.el["gs-coin"], cx, PAY_Y + lift);
    const hit = t >= 19.1 && t < 20.9;
    c.el["gs-coinr"].setAttribute("stroke", hit ? "var(--refuse,#D6483F)" : "var(--assent,#5FA88A)");
    c.el["gs-coinr"].setAttribute("fill", hit ? "rgba(214,72,63,0.16)" : "rgba(95,168,138,0.16)");
    c.el["gs-coint"].setAttribute("fill", hit ? "var(--refuse,#D6483F)" : "var(--assent,#5FA88A)");

    /* the verdict, refused then authorised, same element */
    const refused = t < 21.0;
    const st = c.el["gs-stampt"], sw = c.el["gs-stampw"];
    const stTxt = refused ? "REFUSED" : "AUTHORISED";
    if (st.textContent !== stTxt) st.textContent = stTxt;
    const swTxt = refused ? "over the cap by Rs 6,700.00" : "Rs 6,750.00 against cap Rs 10,000.00";
    if (sw.textContent !== swTxt) sw.textContent = swTxt;
    const col = refused ? "var(--refuse,#D6483F)" : "var(--assent,#5FA88A)";
    st.setAttribute("fill", col);
    sw.setAttribute("fill", col);
    show(
      c.el["gs-stamp"],
      refused
        ? pop(pr(t, 19.2, 19.7)) * (1 - ease(pr(t, 20.6, 21.0)))
        : pop(pr(t, 23.6, 24.1)) * (1 - ease(pr(t, 31.2, 31.7)))
    );

    /* ---- beat 5: all four go on the record ---------------------------- */
    for (let i = 0; i < CHAIN.length; i++) {
      const a = 25.9 + i * 0.9;
      const v = pop(pr(t, a, a + 0.55));
      const el = c.el["gs-chain-" + i];
      show(el, clamp(v, 0, 1));
      at(el, 0, lerp(-46, 0, clamp(v, 0, 1)));
      if (i < CHAIN.length - 1) show(c.el["gs-link-" + i], ease(pr(t, a + 0.6, a + 1.0)));
    }

    /* ---- beat 6: the line --------------------------------------------- */
    caption(c, t);
    const lineOn = ease(pr(t, 30.5, 31.3));
    const lineTxt = "The LLM proposes. The engine disposes.";
    if (c.line.textContent !== (t >= 30.5 ? lineTxt : "")) {
      c.line.textContent = t >= 30.5 ? lineTxt : "";
    }
    c.line.style.opacity = lineOn;
    c.line.style.transform = "translateY(" + ((1 - lineOn) * 18).toFixed(2) + "px)";
  }

  return { MARKUP, draw, DUR, TOOLS };
})();
