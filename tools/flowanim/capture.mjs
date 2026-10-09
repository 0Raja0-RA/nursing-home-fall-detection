#!/usr/bin/env node
/**
 * Ambil frame dari halaman HTML beranimasi lalu rangkai jadi GIF.
 *
 *   node tools/flowanim/capture.mjs flow-detection
 *   node tools/flowanim/capture.mjs flow-api --mp4
 *   node tools/flowanim/capture.mjs flow-api --fps 10 --width 1120
 *
 * Framenya di-set satu per satu lewat window.__setFrame(n), bukan direkam
 * real-time. Jadi hasilnya deterministik: frame ke-N selalu identik, tidak
 * tergantung kecepatan mesin atau frame yang keburu terlewat.
 *
 * Perlu: puppeteer (terpasang global) dan ffmpeg di PATH.
 */

import { execFileSync } from 'node:child_process';
import { createRequire } from 'node:module';
import { mkdirSync, readFileSync, rmSync, statSync, writeFileSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const HERE = dirname(fileURLToPath(import.meta.url));
const REPO = resolve(HERE, '..', '..');
const BUILD = join(REPO, 'build', 'flowanim');
const ASSETS = join(REPO, 'docs', 'assets');

// puppeteer terpasang global, bukan sebagai dependensi repo ini.
const globalRoot = execFileSync('npm', ['root', '-g'], { encoding: 'utf8', shell: true }).trim();
const require = createRequire(pathToFileURL(join(globalRoot, 'noop.js')));
const puppeteer = require('puppeteer');

const argv = process.argv.slice(2);
const name = argv.find((a) => !a.startsWith('-'));
if (!name) {
  console.error('pakai: node tools/flowanim/capture.mjs <flow-detection|flow-api> [--mp4] [--fps N] [--width N] [--dither none|bayer] [--keep]');
  process.exit(1);
}
const flag = (k, d) => {
  const i = argv.indexOf(`--${k}`);
  return i >= 0 && argv[i + 1] && !argv[i + 1].startsWith('-') ? argv[i + 1] : d;
};
const has = (k) => argv.includes(`--${k}`);

const meta = JSON.parse(readFileSync(join(BUILD, `${name}.json`), 'utf8'));
const fps = Number(flag('fps', meta.fps));
const outWidth = Number(flag('width', meta.width));
const dither = flag('dither', 'none');
const framesDir = join(BUILD, `frames-${name}`);

rmSync(framesDir, { recursive: true, force: true });
mkdirSync(framesDir, { recursive: true });
mkdirSync(ASSETS, { recursive: true });

const pad = (n) => String(n).padStart(4, '0');

console.log(`${name}: ${meta.frames} frame @ ${meta.width}x${meta.height}`);
const t0 = Date.now();

const browser = await puppeteer.launch({
  headless: 'shell',
  args: ['--force-device-scale-factor=1', '--hide-scrollbars'],
});
const page = await browser.newPage();
await page.setViewport({ width: meta.width, height: meta.height, deviceScaleFactor: 1 });
await page.goto(`${pathToFileURL(join(BUILD, `${name}.html`)).href}?capture=1`, {
  waitUntil: 'load',
});

// Font harus siap sebelum frame pertama, kalau tidak frame awal bisa pakai
// font fallback dan ukurannya beda dengan frame sisanya.
await page.evaluate(() => document.fonts.ready);

const frameEl = await page.$('#frame');
const total = meta.frames;

for (let n = 0; n < total; n++) {
  await page.evaluate((i) => window.__setFrame(i), n);
  await frameEl.screenshot({
    path: join(framesDir, `f${pad(n)}.png`),
    type: 'png',
    optimizeForSpeed: true,
  });
  if (n % 50 === 0 || n === total - 1) {
    const pct = (((n + 1) / total) * 100).toFixed(0);
    process.stdout.write(`\r  frame ${n + 1}/${total} (${pct}%)   `);
  }
}
process.stdout.write('\n');
await browser.close();
console.log(`  capture selesai dalam ${((Date.now() - t0) / 1000).toFixed(1)} s`);

const input = join(framesDir, 'f%04d.png');
const scale = outWidth === meta.width ? '' : `scale=${outWidth}:-1:flags=lanczos,`;

// stats_mode=diff + diff_mode=rectangle: palet dan penulisan frame hanya
// memperhatikan bagian yang BERUBAH. Inilah yang membuat GIF animasi dengan
// kamera diam jadi kecil -- sebagian besar piksel identik antar frame.
const gifOut = join(ASSETS, `${name}.gif`);
const vf =
  `${scale}split[a][b];[a]palettegen=max_colors=128:stats_mode=diff[p];` +
  `[b][p]paletteuse=dither=${dither}:diff_mode=rectangle`;

console.log('  merangkai GIF...');
execFileSync(
  'ffmpeg',
  ['-y', '-v', 'error', '-framerate', String(fps), '-i', input, '-filter_complex', vf, '-loop', '0', gifOut],
  { stdio: 'inherit' },
);
const mb = (statSync(gifOut).size / 1024 / 1024).toFixed(2);
console.log(`  -> docs/assets/${name}.gif  ${mb} MB`);

if (has('mp4')) {
  const mp4Out = join(ASSETS, `${name}.mp4`);
  console.log('  merangkai MP4...');
  execFileSync(
    'ffmpeg',
    [
      '-y', '-v', 'error', '-framerate', String(fps), '-i', input,
      '-vf', `${scale}format=yuv420p`,
      '-c:v', 'libx264', '-preset', 'slow', '-crf', '20', '-movflags', '+faststart',
      mp4Out,
    ],
    { stdio: 'inherit' },
  );
  console.log(`  -> docs/assets/${name}.mp4  ${(statSync(mp4Out).size / 1024 / 1024).toFixed(2)} MB`);
}

if (!has('keep')) rmSync(framesDir, { recursive: true, force: true });

writeFileSync(
  join(BUILD, `${name}.report.json`),
  JSON.stringify({ name, fps, frames: total, outWidth, dither, gifMB: Number(mb) }, null, 2),
);
