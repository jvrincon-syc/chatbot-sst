import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";
import { build } from "vite";
import { spawnSync } from "node:child_process";

const scriptDir = dirname(fileURLToPath(import.meta.url));
const projectRoot = resolve(scriptDir, "..");

const typecheck = spawnSync(
  process.execPath,
  ["node_modules/typescript/bin/tsc", "-p", "tsconfig.build.json", "--noEmit"],
  {
    cwd: projectRoot,
    stdio: "inherit",
  },
);

if ((typecheck.status ?? 1) !== 0) {
  process.exit(typecheck.status ?? 1);
}

await build({
  root: projectRoot,
  configFile: resolve(projectRoot, "vite.config.mjs"),
});
