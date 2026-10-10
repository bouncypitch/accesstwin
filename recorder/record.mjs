// Renders a director-mode tour page frame by frame and encodes it (with narration) to MP4.
//   node recorder/record.mjs out/04_tour/explainer [--fps 30] [--size 1920x1080] [--from 0 --to 20]
import { chromium } from "playwright";
import { spawn } from "node:child_process";
import { readFileSync, existsSync } from "node:fs";
import { resolve, join } from "node:path";

const args = process.argv.slice(2);
const dir = resolve(args[0]);
const opt = (k, d) => { const i = args.indexOf(k); return i >= 0 ? args[i + 1] : d; };
const fps = Number(opt("--fps", 30));
const [W, H] = opt("--size", "1920x1080").split("x").map(Number);
const tour = JSON.parse(readFileSync(join(dir, "tour.json"), "utf8"));
const from = Number(opt("--from", 0)), to = Math.min(Number(opt("--to", tour.duration)), tour.duration);
const out = opt("--out", join(dir, "video.mp4"));

// Narration: each clip delayed to its segment start, mixed into one track.
const clips = tour.segments.filter(s => s.audio && s.t0 < to && s.t0 + s.dur > from);
const ffArgs = ["-y", "-f", "image2pipe", "-framerate", String(fps), "-c:v", "mjpeg", "-i", "-"];
for (const c of clips) ffArgs.push("-i", join(dir, c.audio));
if (clips.length) {
  const parts = clips.map((c, i) => `[${i + 1}:a]adelay=${Math.max(0, Math.round((c.t0 - from + 0.25) * 1000))}:all=1[a${i}]`);
  ffArgs.push("-filter_complex", parts.join(";") + ";" + clips.map((_, i) => `[a${i}]`).join("") + `amix=inputs=${clips.length}:normalize=0[aout]`,
    "-map", "0:v", "-map", "[aout]", "-c:a", "aac", "-b:a", "160k");
}
ffArgs.push("-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p", "-movflags", "+faststart",
  "-t", String(to - from), out);
const ff = spawn("ffmpeg", ffArgs, { stdio: ["pipe", "ignore", "inherit"] });

const browser = await chromium.launch({ channel: "chrome", headless: true,
  args: ["--use-angle=metal", "--ignore-gpu-blocklist", "--enable-gpu-rasterization", "--disable-background-timer-throttling"] });
const page = await browser.newPage({ viewport: { width: W, height: H }, deviceScaleFactor: 1 });
page.on("pageerror", e => console.error("page error:", e.message));
await page.goto("file://" + join(dir, "tour.html") + "?record=1");
await page.waitForFunction(() => typeof window.renderAt === "function", null, { timeout: 60000 });
await page.evaluate(() => document.fonts.ready);

const n = Math.round((to - from) * fps), t0 = Date.now();
for (let f = 0; f < n; f++) {
  await page.evaluate(t => window.renderAt(t), from + f / fps);
  const jpg = await page.screenshot({ type: "jpeg", quality: 90 });
  if (!ff.stdin.write(jpg)) await new Promise(r => ff.stdin.once("drain", r));
  if (f % (fps * 10) === 0) process.stdout.write(`\r${(f / fps).toFixed(0)}s / ${(n / fps).toFixed(0)}s  (${((Date.now() - t0) / Math.max(1, f)).toFixed(0)} ms/frame)   `);
}
ff.stdin.end();
await new Promise(r => ff.on("close", r));
await browser.close();
console.log(`\nwrote ${out} (${n} frames in ${((Date.now() - t0) / 1000).toFixed(0)} s)`);
