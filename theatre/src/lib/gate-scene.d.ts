/* Types for gate-scene.js, which is copied in from docs/video/ by
 * scripts/sync-run.mjs and is deliberately framework-free: it is a classic
 * script that assigns a global, because the same file also has to load into
 * docs/video/film.html for the Playwright render, where ES modules are not
 * available. Importing it here is for the side effect of that assignment. */

export interface GateSceneApi {
  /** The scene's markup, injected once into a container. */
  MARKUP: string;
  /** Paint the scene at progress `p` in [0,1]. Pure: same p, same pixels. */
  draw(root: Element, p: number): void;
  /** How long the scene runs in the film, in seconds. */
  DUR: number;
  TOOLS: string[];
}

declare global {
  interface Window {
    GateScene: GateSceneApi;
  }
}
