import { existsSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";
import { spawnSync } from "node:child_process";

const scriptDir = dirname(fileURLToPath(import.meta.url));
const projectRoot = resolve(scriptDir, "..");
const vitestEntry = resolve(projectRoot, "node_modules", "vitest", "vitest.mjs");

if (!existsSync(vitestEntry)) {
  console.log("component tests skipped: vitest is not installed in app/front");
  process.exit(0);
}

const result = spawnSync(process.execPath, [vitestEntry, "run"], {
  cwd: projectRoot,
  stdio: "inherit",
});

process.exit(result.status ?? 1);
