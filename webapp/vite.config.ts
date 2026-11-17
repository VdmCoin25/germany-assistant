import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// Served by FastAPI at /app-v2/; the old app at / stays untouched.
export default defineConfig({
  base: "/app-v2/",
  plugins: [react()],
  build: { outDir: "dist", target: "es2020" },
});
