/* Canonical files that live outside this Vite project, copied in on every dev
 * start and every build so the two can never drift.
 *
 *   run.json        the captured run, which lives in the Python package next
 *                   to the code that produces it. Vite needs it inside
 *                   `public/` so it lands in the bundle and the built page
 *                   works even when opened straight from disk -- the fallback
 *                   if the server will not start in front of an audience.
 *
 *   gate-scene.js   the animated explainer for scene 3 of the film. The same
 *                   file has to drive a Playwright render of docs/video/film.html
 *                   and a React component here, so it is written once, as a
 *                   framework-free pure function of progress, and copied rather
 *                   than reimplemented. A second hand-maintained copy would
 *                   drift the moment either surface is re-timed.
 */
import { copyFileSync, mkdirSync, existsSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));

const COPIES = [
  {
    src: resolve(here, "../../vendable/theatre/run.json"),
    dest: resolve(here, "../public/run.json"),
    fix: "Regenerate it with: scripts/demo_buy.py --capture vendable/theatre/run.json",
  },
  {
    src: resolve(here, "../../docs/video/gate-scene.js"),
    dest: resolve(here, "../src/lib/gate-scene.js"),
    fix: "It is committed at docs/video/gate-scene.js; check the path.",
  },
];

for (const { src, dest, fix } of COPIES) {
  if (!existsSync(src)) {
    console.error(`sync-run: missing ${src}`);
    console.error(fix);
    process.exit(1);
  }
  mkdirSync(dirname(dest), { recursive: true });
  copyFileSync(src, dest);
  console.log(`sync-run: ${src} -> ${dest}`);
}
