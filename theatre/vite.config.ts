import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import path from "node:path";

const here = import.meta.dirname;

// The build lands inside the Python package, so `pip install vendable` ships the
// page and Starlette can mount it as plain static files. Source stays out here:
// node_modules never goes anywhere near the wheel.
//
// `base` must match the mount point or every asset 404s -- the page loads, the
// bundle does not, and the screen is black with no error anyone can see.
export default defineConfig({
  base: "/theatre/",
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: { "@": path.resolve(here, "./src") },
  },
  build: {
    outDir: path.resolve(here, "../vendable/theatre/static"),
    emptyOutDir: true,
    // One file each. The whole point of this surface is that it opens instantly
    // in front of a judge; chunk waterfalls are not worth the caching win here.
    rollupOptions: {
      output: {
        entryFileNames: "assets/[name].js",
        chunkFileNames: "assets/[name].js",
        assetFileNames: "assets/[name].[ext]",
      },
    },
  },
});
