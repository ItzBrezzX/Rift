import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// GitHub Pages project sites need base = "/<repo>/".
// Set VITE_BASE_PATH in CI, or leave "/" for user/organization pages.
export default defineConfig({
  plugins: [react()],
  base: process.env.VITE_BASE_PATH || "/",
  build: {
    outDir: "dist",
    sourcemap: true,
  },
});
