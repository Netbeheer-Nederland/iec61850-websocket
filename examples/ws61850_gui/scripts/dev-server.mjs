import { spawn } from "node:child_process";
import { watch } from "node:fs";
import path from "node:path";

const rootDir = new URL("..", import.meta.url).pathname;
const appPath = path.join(rootDir, "app.py");
const staticDir = path.join(rootDir, "static");

function startFlask() {
  return spawn("python", [appPath], {
    cwd: rootDir,
    stdio: "inherit",
    env: { ...process.env, FLASK_ENV: "development" },
  });
}

let flask = startFlask();

watch(staticDir, { recursive: true }, (_eventType, filename) => {
  if (!filename) return;
  console.log(`[dev-server] static changed: ${filename}`);
});

process.on("SIGINT", () => {
  flask.kill("SIGINT");
  process.exit(0);
});
