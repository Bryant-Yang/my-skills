#!/usr/bin/env node
/** Local, bounded Canvas export. Dependencies are explicit; no installs or shared cache. */
import fs from 'node:fs/promises';
import path from 'node:path';
import http from 'node:http';
import { createRequire } from 'node:module';
import { pathToFileURL, fileURLToPath } from 'node:url';
import { spawn } from 'node:child_process';
import { createHash } from 'node:crypto';

const help = `Usage:
  node render-canvas.mjs --studio <html> --audio <audio> --out <mp4>
    --chrome <executable> (--dependency-root <project-dir> | --puppeteer-module <entry-or-package-dir>)
    [--resource-root <directory>] [--duration <seconds>] [--fps 24]
    [--width <even-pixels> --height <even-pixels>] [--ready-timeout <milliseconds>]
    [--overwrite] [--allow-silent-audio]

dependency-root is a project directory containing node_modules/puppeteer-core.
resource-root defaults to the HTML directory; all browser assets must stay beneath it.
Width/height default to the intrinsic dimensions of canvas#out. Audio duration is measured
after decoding to PCM. Explicit duration must match it within one video frame.
Output is published only after media verification. Existing output needs --overwrite.
Requires Node.js 18+, Python 3, ffmpeg, ffprobe, installed puppeteer-core and Chrome/Chromium.`;

function parse(argv) {
  const flags = new Set(['overwrite', 'allow-silent-audio', 'help']);
  const values = new Set(['studio', 'audio', 'out', 'chrome', 'dependency-root', 'puppeteer-module',
    'resource-root', 'duration', 'fps', 'width', 'height', 'ready-timeout']);
  const result = {};
  for (let i = 0; i < argv.length; i++) {
    const key = argv[i].startsWith('--') ? argv[i].slice(2) : '';
    if (!flags.has(key) && !values.has(key)) throw new Error(`Unknown argument: ${argv[i]}`);
    if (Object.hasOwn(result, key)) throw new Error(`Duplicate argument: --${key}`);
    if (flags.has(key)) result[key] = true;
    else {
      if (!argv[i + 1] || argv[i + 1].startsWith('--')) throw new Error(`Missing value: --${key}`);
      result[key] = argv[++i];
    }
  }
  return result;
}
function number(value, name, fallback, max = Infinity, integer = false) {
  const n = value === undefined ? fallback : Number(value);
  if (!Number.isFinite(n) || n <= 0 || n > max || (integer && !Number.isInteger(n)))
    throw new Error(`${name} must be positive${integer ? ' integer' : ''}, at most ${max}`);
  return n;
}
function inside(root, file) {
  const relative = path.relative(root, file);
  return relative === '' || (!relative.startsWith(`..${path.sep}`) && relative !== '..' && !path.isAbsolute(relative));
}
async function regularFile(file, label) {
  const resolved = await fs.realpath(path.resolve(file));
  if (!(await fs.stat(resolved)).isFile()) throw new Error(`${label} must be a regular file`);
  return resolved;
}
const aborter = new AbortController();
let interrupted = false;
function interrupt() { interrupted = true; aborter.abort(); }
process.once('SIGINT', interrupt);
process.once('SIGTERM', interrupt);
function checkAbort() { if (interrupted) throw new Error('Interrupted; unpublished temporary output will be removed'); }
async function deadline(promise, milliseconds, label) {
  let timer;
  try {
    return await Promise.race([promise, new Promise((_, reject) => {
      timer = setTimeout(() => reject(new Error(`${label} timed out after ${milliseconds} ms`)), milliseconds);
    })]);
  } finally { clearTimeout(timer); }
}
function command(binary, args) {
  checkAbort();
  return new Promise((resolve, reject) => {
    const child = spawn(binary, args, { stdio: ['ignore', 'pipe', 'pipe'], signal: aborter.signal });
    let stdout = '', stderr = '';
    child.stdout.on('data', chunk => { stdout += chunk; if (stdout.length > 4000000) stdout = stdout.slice(-4000000); });
    child.stderr.on('data', chunk => { stderr += chunk; if (stderr.length > 4000000) stderr = stderr.slice(-4000000); });
    child.on('error', reject);
    child.on('close', code => code === 0 ? resolve({ stdout, stderr })
      : reject(new Error(`${binary} failed (${code}): ${(stderr || stdout).slice(-5000)}`)));
  });
}
const mime = new Map(Object.entries({ '.html': 'text/html', '.js': 'text/javascript', '.mjs': 'text/javascript',
  '.css': 'text/css', '.json': 'application/json', '.png': 'image/png', '.jpg': 'image/jpeg',
  '.jpeg': 'image/jpeg', '.svg': 'image/svg+xml', '.webp': 'image/webp', '.gif': 'image/gif',
  '.woff': 'font/woff', '.woff2': 'font/woff2', '.ttf': 'font/ttf', '.otf': 'font/otf',
  '.wasm': 'application/wasm', '.mp3': 'audio/mpeg', '.wav': 'audio/wav', '.mp4': 'video/mp4' }));

async function serve(root) {
  const server = http.createServer(async (request, response) => {
    try {
      const url = new URL(request.url, 'http://localhost');
      if (url.pathname === '/favicon.ico') { response.writeHead(204); response.end(); return; }
      if (request.method !== 'GET' && request.method !== 'HEAD') { response.writeHead(405); response.end(); return; }
      const requested = path.resolve(root, `.${decodeURIComponent(url.pathname)}`);
      if (!inside(root, requested)) throw new Error('Outside resource root');
      const file = await fs.realpath(requested);
      if (!inside(root, file) || !(await fs.stat(file)).isFile()) throw new Error('Outside resource root or non-file');
      const data = await fs.readFile(file);
      response.writeHead(200, { 'Content-Type': mime.get(path.extname(file).toLowerCase()) || 'application/octet-stream',
        'Content-Length': data.length, 'Cache-Control': 'no-store' });
      response.end(request.method === 'HEAD' ? undefined : data);
    } catch {
      response.writeHead(404); response.end('Local resource unavailable');
    }
  });
  await new Promise((resolve, reject) => { server.once('error', reject); server.listen(0, '127.0.0.1', resolve); });
  return { server, origin: `http://127.0.0.1:${server.address().port}` };
}
function pngBuffer(data) {
  if (typeof data !== 'string' || !data.startsWith('data:image/png;base64,'))
    throw new Error('renderAt(t, "image/png", 1) must return a PNG data URL');
  const buffer = Buffer.from(data.slice('data:image/png;base64,'.length), 'base64');
  if (buffer.length < 24 || buffer.subarray(0, 8).toString('hex') !== '89504e470d0a1a0a')
    throw new Error('renderAt returned invalid PNG data');
  return buffer;
}

async function main() {
  const args = parse(process.argv.slice(2));
  if (args.help) { console.log(help); return; }
  for (const key of ['studio', 'audio', 'out', 'chrome']) if (!args[key]) throw new Error(`Required: --${key}`);
  if (Boolean(args['dependency-root']) === Boolean(args['puppeteer-module']))
    throw new Error('Provide exactly one of --dependency-root or --puppeteer-module');
  if (Boolean(args.width) !== Boolean(args.height)) throw new Error('Provide both --width and --height, or neither');
  const fps = number(args.fps, 'fps', 24, 120);
  const readyTimeout = number(args['ready-timeout'], 'ready-timeout', 30000, 300000, true);
  let width = args.width ? number(args.width, 'width', undefined, 8192, true) : undefined;
  let height = args.height ? number(args.height, 'height', undefined, 8192, true) : undefined;
  const requestedDuration = args.duration ? number(args.duration, 'duration', undefined, 3600) : undefined;
  const studio = await regularFile(args.studio, 'studio');
  const audio = await regularFile(args.audio, 'audio');
  const chrome = await regularFile(args.chrome, 'chrome');
  const out = path.resolve(args.out);
  if (out === audio || out === studio) throw new Error('Output must be different from source audio and HTML');
  try {
    const existingOutput = await fs.realpath(out);
    if (existingOutput === audio || existingOutput === studio)
      throw new Error('Output must be different from source audio and HTML');
  } catch (error) { if (error.code !== 'ENOENT') throw error; }
  if (path.extname(out).toLowerCase() !== '.mp4') throw new Error('out must end with .mp4');
  const resourceRoot = await fs.realpath(path.resolve(args['resource-root'] || path.dirname(studio)));
  if (!(await fs.stat(resourceRoot)).isDirectory() || !inside(resourceRoot, studio))
    throw new Error('resource-root must be a directory containing studio');
  try {
    await fs.lstat(out);
    if (!args.overwrite) throw new Error('Output already exists; use --overwrite to replace it');
    if (!(await fs.lstat(out)).isFile()) throw new Error('Existing output must be a regular file, not a directory or symlink');
  } catch (error) { if (error.code !== 'ENOENT') throw error; }
  const resolver = createRequire(import.meta.url);
  const dependencyDirectory = args['dependency-root']
    ? await fs.realpath(path.join(path.resolve(args['dependency-root']), 'node_modules', 'puppeteer-core')) : undefined;
  const modulePath = resolver.resolve(dependencyDirectory || path.resolve(args['puppeteer-module']));
  const imported = await import(pathToFileURL(modulePath).href);
  const puppeteer = imported.default || imported;
  if (typeof puppeteer.launch !== 'function') throw new Error('Dependency does not expose puppeteer.launch');
  await command('ffmpeg', ['-version']); await command('ffprobe', ['-version']); await command('python3', ['--version']);
  await fs.mkdir(path.dirname(out), { recursive: true });
  const temporary = await fs.mkdtemp(path.join(path.dirname(out), '.code-video-'));
  let browser, local;
  const errors = [];
  function checkErrors() { checkAbort(); if (errors.length) throw new Error(errors.join('\n')); }
  try {
    const pcm = path.join(temporary, 'audio.wav');
    await command('ffmpeg', ['-nostdin', '-v', 'error', '-xerror', '-i', audio, '-map', '0:a:0',
      '-vn', '-ar', '48000', '-c:a', 'pcm_s16le', pcm]);
    const audioData = JSON.parse((await command('ffprobe', ['-v', 'error', '-show_streams', '-of', 'json', pcm])).stdout);
    const audioStream = audioData.streams.find(s => s.codec_type === 'audio');
    if (!audioStream || ![1, 2].includes(audioStream.channels)) throw new Error('Audio must have one or two channels');
    // WAV duration is rounded to six decimal places by ffprobe. Integer PCM ticks
    // preserve exact frame-aligned sample counts before taking the frame ceiling.
    const ticks = Number(audioStream.duration_ts);
    const [timeNumerator, timeDenominator] = String(audioStream.time_base).split('/').map(Number);
    if (![ticks, timeNumerator, timeDenominator].every(value => Number.isSafeInteger(value) && value > 0))
      throw new Error('Decoded PCM requires positive integer duration_ts and time_base');
    const duration = number(ticks * timeNumerator / timeDenominator, 'decoded audio duration', undefined, 3600);
    if (requestedDuration !== undefined && Math.abs(requestedDuration - duration) > 1 / fps + 0.001)
      throw new Error('Explicit duration differs from decoded audio by more than one frame; edit audio first');
    const frameCount = Math.ceil(duration * fps - 1e-8);
    local = await serve(resourceRoot);
    const studioUrl = `${local.origin}/${path.relative(resourceRoot, studio).split(path.sep).map(encodeURIComponent).join('/')}?render`;
    browser = await puppeteer.launch({ executablePath: chrome, headless: true, timeout: readyTimeout,
      args: ['--disable-background-networking', '--disable-default-apps', '--no-first-run'] });
    async function makePage() {
      const page = await browser.newPage();
      await page.setViewport({ width: width || 1280, height: height || 720, deviceScaleFactor: 1 });
      await page.setRequestInterception(true);
      page.on('request', request => {
        const url = request.url();
        if (url.startsWith(`${local.origin}/`) || /^(data:|blob:|about:)/.test(url))
          request.continue().catch(error => errors.push(`Request interception: ${error.message}`));
        else { errors.push(`External browser resource blocked: ${url}`); request.abort().catch(() => {}); }
      });
      page.on('requestfailed', request => errors.push(`Resource failed: ${request.url()} (${request.failure()?.errorText})`));
      page.on('response', response => { if (response.status() >= 400) errors.push(`Resource HTTP ${response.status()}: ${response.url()}`); });
      page.on('pageerror', error => errors.push(`Page error: ${error.message}`));
      page.on('console', message => { if (message.type() === 'error') errors.push(`Console error: ${message.text()}`); });
      await page.goto(studioUrl, { waitUntil: 'networkidle0', timeout: readyTimeout });
      await page.waitForFunction('window.ready === true && typeof window.renderAt === "function"', { timeout: readyTimeout });
      await deadline(page.evaluate(async () => {
        await document.fonts.ready;
        await Promise.all([...document.images].map(image => image.decode()));
      }), readyTimeout, 'Font and image readiness');
      checkErrors(); return page;
    }
    const page = await makePage();
    const size = await page.evaluate(() => {
      const canvas = document.querySelector('canvas#out');
      if (!canvas) throw new Error('Expected canvas#out');
      return { width: canvas.width, height: canvas.height };
    });
    width ??= size.width; height ??= size.height;
    if (width !== size.width || height !== size.height || width % 2 || height % 2 || width > 8192 || height > 8192 || width <= 0 || height <= 0)
      throw new Error('Canvas intrinsic dimensions must match requested positive even dimensions, at most 8192');
    await page.setViewport({ width, height, deviceScaleFactor: 1 });
    // Reinitialize after adopting intrinsic dimensions so cold pages use the same viewport.
    await page.reload({ waitUntil: 'networkidle0', timeout: readyTimeout });
    await page.waitForFunction('window.ready === true && typeof window.renderAt === "function"', { timeout: readyTimeout });
    await deadline(page.evaluate(async () => { await document.fonts.ready; await Promise.all([...document.images].map(image => image.decode())); }), readyTimeout, 'Font and image readiness');
    async function frame(target, time) {
      checkErrors();
      const data = await deadline(target.evaluate(async t => await window.renderAt(t, 'image/png', 1), time), readyTimeout, `renderAt(${time})`);
      checkErrors();
      const buffer = pngBuffer(data);
      if (buffer.readUInt32BE(16) !== width || buffer.readUInt32BE(20) !== height)
        throw new Error('renderAt PNG dimensions do not match canvas');
      return buffer;
    }
    const samples = [...new Set([0, Math.floor(frameCount / 2) / fps, (frameCount - 1) / fps])];
    const hashes = new Map();
    const hash = buffer => createHash('sha256').update(buffer).digest('hex');
    for (const time of samples) hashes.set(time, hash(await frame(page, time)));
    for (const time of [...samples].reverse()) {
      if (hash(await frame(page, time)) !== hashes.get(time)) throw new Error(`Forward/reverse seek mismatch at ${time}`);
    }
    for (const time of samples) {
      const cold = await makePage();
      if (hash(await frame(cold, time)) !== hashes.get(time)) throw new Error(`Cold/warm seek mismatch at ${time}`);
      await cold.close();
    }
    const frames = path.join(temporary, 'frames'); await fs.mkdir(frames);
    for (let index = 0; index < frameCount; index++) {
      await fs.writeFile(path.join(frames, `${String(index).padStart(8, '0')}.png`), await frame(page, index / fps));
      if (index % Math.max(1, Math.ceil(frameCount / 10)) === 0) console.error(`Rendered ${index + 1}/${frameCount} frames`);
    }
    checkErrors();
    // No -shortest: preserve every decoded audio sample. Video may extend by less than one frame.
    const pending = path.join(temporary, 'pending.mp4');
    await command('ffmpeg', ['-nostdin', '-v', 'error', '-xerror', '-framerate', String(fps),
      '-start_number', '0', '-i', path.join(frames, '%08d.png'), '-i', pcm,
      '-map', '0:v:0', '-map', '1:a:0', '-c:v', 'libx264', '-crf', '18', '-preset', 'medium',
      '-pix_fmt', 'yuv420p', '-fps_mode', 'cfr', '-c:a', 'aac', '-b:a', '192k',
      '-movflags', '+faststart', pending]);
    const verifier = fileURLToPath(new URL('./verify-video.py', import.meta.url));
    const validation = ['python3', [verifier, pending, '--width', String(width), '--height', String(height),
      '--fps', String(fps), '--frames', String(frameCount), '--duration', String(duration),
      '--channels', String(audioStream.channels)]];
    if (args['allow-silent-audio']) validation[1].push('--allow-silent-audio');
    const verification = JSON.parse((await command(...validation)).stdout);
    checkErrors();
    // link is an atomic no-clobber publication; rename is an explicitly allowed replacement.
    if (args.overwrite) {
      try { if (!(await fs.lstat(out)).isFile()) throw new Error('Output became a directory or symlink'); }
      catch (error) { if (error.code !== 'ENOENT') throw error; }
      await fs.rename(pending, out);
    } else { await fs.link(pending, out); await fs.unlink(pending); }
    console.log(JSON.stringify({ passed: true, out, source_seek_samples: samples,
      seek_checks: ['forward/reverse PNG equality', 'cold/warm PNG equality'],
      verification }, null, 2));
  } finally {
    if (browser) {
      try { await deadline(browser.close(), 5000, 'Owned browser cleanup'); }
      catch { browser.process()?.kill('SIGKILL'); }
    }
    if (local) { local.server.closeAllConnections?.(); await new Promise(resolve => local.server.close(resolve)); }
    await fs.rm(temporary, { recursive: true, force: true });
  }
}
main().catch(error => { console.error(error.message); process.exitCode = interrupted ? 130 : 1; });
