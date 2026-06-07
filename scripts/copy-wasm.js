#!/usr/bin/env node
// Copies rnnoise WASM + JS glue from node_modules into web_static so Flask/Electron can serve them.
const fs   = require("fs");
const path = require("path");

const ROOT = path.join(__dirname, "..");
const SRC  = path.join(ROOT, "node_modules", "@jitsi", "rnnoise-wasm", "dist");
const DEST = path.join(ROOT, "src", "ui", "web_static");

const FILES = ["rnnoise.js", "rnnoise.wasm"];
let ok = true;

for (const file of FILES) {
  const src = path.join(SRC, file);
  if (!fs.existsSync(src)) {
    console.error(`Missing: ${src}  — run: npm install`);
    ok = false;
    continue;
  }
  fs.copyFileSync(src, path.join(DEST, file));
  console.log(`Copied ${file} → web_static/`);
}

process.exit(ok ? 0 : 1);
