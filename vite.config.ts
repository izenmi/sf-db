import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// GitHub Pages serves this app from https://izenmi.github.io/sf-db/,
// so every asset/data URL must be prefixed with the repo name.
export default defineConfig({
  plugins: [react()],
  base: "/sf-db/",
});
