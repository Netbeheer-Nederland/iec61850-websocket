import { readdir, stat } from "node:fs/promises";
import path from "node:path";
import { spawn } from "node:child_process";

const rootDir = new URL("..", import.meta.url).pathname;
const targets = [path.join(rootDir, "static")];

async function collectJsFiles(dir) {
  const entries = await readdir(dir, { withFileTypes: true });
  const files = [];
  for (const entry of entries) {
    const fullPath = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      files.push(...await collectJsFiles(fullPath));
    } else if (entry.isFile() && fullPath.endsWith(".js")) {
      files.push(fullPath);
    }
  }
  return files;
}

async function ensureTargetsExist(paths) {
  for (const target of paths) {
    await stat(target);
  }
}

function runNodeCheck(file) {
  return new Promise((resolve, reject) => {
    const child = spawn(process.execPath, ["--check", file], { stdio: "inherit" });
    child.on("exit", (code) => (code === 0 ? resolve() : reject(new Error(`Syntax check failed for ${file}`))));
  });
}

await ensureTargetsExist(targets);
const files = [];
for (const target of targets) {
  files.push(...await collectJsFiles(target));
}

for (const file of files) {
  await runNodeCheck(file);
}

console.log(`Checked ${files.length} JavaScript files.`);
