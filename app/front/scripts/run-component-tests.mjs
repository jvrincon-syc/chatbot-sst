import { existsSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";
import { spawnSync } from "node:child_process";
import { createRequire } from "node:module";

const scriptDir = dirname(fileURLToPath(import.meta.url));
const projectRoot = resolve(scriptDir, "..");
const requireFromProject = createRequire(resolve(projectRoot, "package.json"));
let vitestEntry;

try {
  const vitestPackageJson = requireFromProject.resolve("vitest/package.json");
  vitestEntry = resolve(dirname(vitestPackageJson), "vitest.mjs");
} catch (error) {
  const message =
    error instanceof Error ? error.message : "Unable to resolve vitest from the repo root.";
  console.error(`component tests failed: ${message}`);
  process.exit(1);
}

const result = spawnSync(process.execPath, [vitestEntry, "run"], {
  cwd: projectRoot,
  stdio: "inherit",
});

if (result.error) {
  throw result.error;
}

process.exit(result.status ?? 1);
