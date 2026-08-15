import assert from "node:assert/strict";
import fs from "node:fs";

const html = fs.readFileSync(new URL("../index.html", import.meta.url), "utf8");

assert.match(html, /<!doctype html>/i, "index.html must be a complete document");
assert.match(html, /<meta name="viewport"/i, "mobile viewport is required");
assert.doesNotMatch(html, /claude\.ai|claudeusercontent\.com|__FRAME_PREAMBLE/, "Claude wrapper references must not ship");

const scripts = [...html.matchAll(/<script(?:\s[^>]*)?>([\s\S]*?)<\/script>/gi)];
assert.equal(scripts.length, 1, "the standalone app should contain one inline application script");
new Function(scripts[0][1]);

const markers = [
  "const BOXES=",
  "const ATTACKS=",
  "const STUDIES=",
  "function openRoom",
  "function openArena",
  "function renderStudies",
  "function renderBadges",
  "function setPrompt",
  "id=\"roomTerm\"",
  "id=\"rtMin\"",
  "id=\"termFab\"",
  "id=\"profile\"",
  "id=\"arena\"",
  "id=\"forum\""
];

for (const marker of markers) {
  assert.ok(html.includes(marker), `missing NIGHTRANGE feature marker: ${marker}`);
}

const boxIds = [...html.matchAll(/id:\s*['"](?:NET|PEN|BK|FE)-\d+['"]/g)];
assert.equal(boxIds.length, 21, "all 21 playable boxes must be present");

console.log("NIGHTRANGE standalone source parsed successfully; all major feature markers are present.");

