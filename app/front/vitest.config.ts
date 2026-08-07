import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

// Component tests only. The pure state/API suites keep running under `npm test`
// (tsc + node), so this runner is restricted to *.test.tsx to avoid executing
// the .mjs suites twice under a different module resolution.
export default defineConfig({
  plugins: [react()],
  test: {
    environment: "jsdom",
    // Testing Library only registers its afterEach unmount when globals exist;
    // without this, renders leak across tests.
    globals: true,
    include: ["src/**/*.test.tsx"],
    restoreMocks: true,
  },
});
