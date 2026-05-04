import { copyFile, mkdir } from "node:fs/promises";
import path from "node:path";

const rootDir = new URL("..", import.meta.url).pathname;
const source = path.join(rootDir, "static", "app", "main.js");
const outputDir = path.join(rootDir, "static", "dist");
const output = path.join(outputDir, "main.js");

await mkdir(outputDir, { recursive: true });
await copyFile(source, output);

console.log(`Copied ${source} -> ${output}`);
