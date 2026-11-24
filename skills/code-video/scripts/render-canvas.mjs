#!/usr/bin/env node
/** Local, bounded Canvas keyframe & video export. Explicit dependencies; no installs or shared cache. */
import fs from 'node:fs/promises';
import path from 'node:path';
import http from 'node:http';
import { createRequire } from 'node:module';
import { pathToFileURL, fileURLToPath } from 'node:url';
import { spawn } from 'node:child_process';
import { createHash } from 'node:crypto';

const help = `Usage:
  Video export:
    node render-canvas.mjs --studio <html> --audio <audio> --out <mp4>
      --chrome <executable> (--dependency-root <project-dir> | --puppeteer-module <entry-or-package-dir>)
      [--resource-root <directory>] [--selector <css>] [--workers <1..8>] [--chapters <ffmeta>]
      [--duration <seconds>] [--fps 24] [--width <even-pixels> --height <even-pixels>]
      [--ready-timeout <milliseconds>] [--overwrite] [--allow-silent-audio]

  Keyframe inspection (no audio required):
    node render-canvas.mjs --studio <html> --keyframes <t1,t2,...> --out-dir <directory>
      --chrome <executable> (--dependency-root <project-dir> | --puppeteer-module <entry-or-package-dir>)
      [--resource-root <directory>] [--selector <css>]
      [--width <even-pixels> --height <even-pixels>] [--ready-timeout <milliseconds>] [--overwrite]

dependency-root is a project directory containing node_modules/puppeteer-core.
resource-root defaults to the HTML directory; all browser assets must stay beneath it.
selector defaults to canvas#out, canvas#film, or the sole <canvas> element on the page.
Width/height default to the intrinsic dimensions of the selected canvas.
Audio duration is measured after decoding to PCM; explicit duration must match within one video frame.
Pages may push layout overflow diagnostics into window.__layoutWarnings during renderAt(t).
Output is published only after verification. Existing outputs require --overwrite.`;

function parse(argv) {
  const flags = new Set(['overwrite', 'allow-silent-audio', 'help']);
  const values = new Set([
    'studio', 'audio', 'out', 'keyframes', 'out-dir', 'chrome',
    'dependency-root', 'puppeteer-module', 'resource-root', 'selector',
    'workers', 'chapters', 'duration', 'fps', 'width', 'height', 'ready-timeout',
  ]);
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

function parseKeyframeTimes(spec) {
  const parts = String(spec).split(',').map(s => s.trim()).filter(Boolean);
  if (!parts.length || parts.length > 64)
    throw new Error('keyframes must contain between 1 and 64 comma-separated non-negative timestamps');
  return parts.map(raw => {
    const t = Number(raw);
    if (!Number.isFinite(t) || t < 0 || t > 3600)
      throw new Error(`Invalid keyframe timestamp: ${raw}`);
    return t;
  });
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

const mime = new Map(Object.entries({
  '.html': 'text/html', '.js': 'text/javascript', '.mjs': 'text/javascript',
  '.css': 'text/css', '.json': 'application/json', '.png': 'image/png', '.jpg': 'image/jpeg',
  '.jpeg': 'image/jpeg', '.svg': 'image/svg+xml', '.webp': 'image/webp', '.gif': 'image/gif',
  '.woff': 'font/woff', '.woff2': 'font/woff2', '.ttf': 'font/ttf', '.otf': 'font/otf',
  '.wasm': 'application/wasm', '.mp3': 'audio/mpeg', '.wav': 'audio/wav', '.mp4': 'video/mp4',
}));

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
      response.writeHead(200, {
        'Content-Type': mime.get(path.extname(file).toLowerCase()) || 'application/octet-stream',
        'Content-Length': data.length,
        'Cache-Control': 'no-store',
      });
      response.end(request.method === 'HEAD' ? undefined : data);
    } catch {
      response.writeHead(404);
      response.end('Local resource unavailable');
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
  for (const key of ['studio', 'chrome']) if (!args[key]) throw new Error(`Required: --${key}`);
  if (Boolean(args['dependency-root']) === Boolean(args['puppeteer-module']))
    throw new Error('Provide exactly one of --dependency-root or --puppeteer-module');
  if (Boolean(args.width) !== Boolean(args.height))
    throw new Error('Provide both --width and --height, or neither');

  const keyframeMode = args.keyframes !== undefined || args['out-dir'] !== undefined;
  if (keyframeMode) {
    if (!args.keyframes || !args['out-dir'])
      throw new Error('Keyframe mode requires both --keyframes and --out-dir');
    for (const forbidden of ['audio', 'out', 'duration', 'fps', 'workers', 'chapters', 'allow-silent-audio']) {
      if (args[forbidden] !== undefined)
        throw new Error(`--${forbidden} cannot be combined with --keyframes`);
    }
  } else {
    for (const key of ['audio', 'out']) if (!args[key]) throw new Error(`Required: --${key}`);
  }

  const readyTimeout = number(args['ready-timeout'], 'ready-timeout', 30000, 300000, true);
  let width = args.width ? number(args.width, 'width', undefined, 8192, true) : undefined;
  let height = args.height ? number(args.height, 'height', undefined, 8192, true) : undefined;
  const selector = args.selector || null;
  const studio = await regularFile(args.studio, 'studio');
  const chrome = await regularFile(args.chrome, 'chrome');
  const resourceRoot = await fs.realpath(path.resolve(args['resource-root'] || path.dirname(studio)));
  if (!(await fs.stat(resourceRoot)).isDirectory() || !inside(resourceRoot, studio))
    throw new Error('resource-root must be a directory containing studio');

  const resolver = createRequire(import.meta.url);
  const dependencyDirectory = args['dependency-root']
    ? await fs.realpath(path.join(path.resolve(args['dependency-root']), 'node_modules', 'puppeteer-core')) : undefined;
  const modulePath = resolver.resolve(dependencyDirectory || path.resolve(args['puppeteer-module']));
  const imported = await import(pathToFileURL(modulePath).href);
  const puppeteer = imported.default || imported;
  if (typeof puppeteer.launch !== 'function') throw new Error('Dependency does not expose puppeteer.launch');

  let browser, local, temporary;
  const errors = [];
  const layoutWarnings = [];
  const seenWarnings = new Set();
  function checkErrors() { checkAbort(); if (errors.length) throw new Error(errors.join('\n')); }
  function recordWarnings(items) {
    if (!Array.isArray(items)) return;
    for (const item of items) {
      const text = typeof item === 'string' ? item : JSON.stringify(item);
      if (!seenWarnings.has(text) && layoutWarnings.length < 100) {
        seenWarnings.add(text);
        layoutWarnings.push(item);
      }
    }
  }

  async function openStudioPage(studioUrl, viewportW, viewportH) {
    const page = await browser.newPage();
    await page.setViewport({ width: viewportW, height: viewportH, deviceScaleFactor: 1 });
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
    checkErrors();
    return page;
  }

  async function renderPng(target, time, expectedW, expectedH) {
    checkErrors();
    const payload = await deadline(target.evaluate(async t => {
      if (Array.isArray(window.__layoutWarnings)) window.__layoutWarnings.length = 0;
      const data = await window.renderAt(t, 'image/png', 1);
      const warnings = Array.isArray(window.__layoutWarnings) ? [...window.__layoutWarnings] : [];
      return { data, warnings };
    }, time), readyTimeout, `renderAt(${time})`);
    checkErrors();
    recordWarnings(payload.warnings);
    const buffer = pngBuffer(payload.data);
    if (buffer.readUInt32BE(16) !== expectedW || buffer.readUInt32BE(20) !== expectedH)
      throw new Error('renderAt PNG dimensions do not match canvas');
    return buffer;
  }

  async function resolveCanvasSize(page) {
    return page.evaluate(customSelector => {
      let canvas = null;
      if (customSelector) {
        canvas = document.querySelector(customSelector);
        if (!canvas || canvas.tagName?.toLowerCase() !== 'canvas')
          throw new Error(`Expected <canvas> matching selector: ${customSelector}`);
      } else {
        canvas = document.querySelector('canvas#out') || document.querySelector('canvas#film');
        if (!canvas) {
          const all = document.querySelectorAll('canvas');
          if (all.length === 1) canvas = all[0];
          else throw new Error('Expected canvas#out, canvas#film, or a single <canvas> (use --selector to disambiguate)');
        }
      }
      return { width: canvas.width, height: canvas.height };
    }, selector);
  }

  if (keyframeMode) {
    const times = parseKeyframeTimes(args.keyframes);
    const outDir = path.resolve(args['out-dir']);
    try {
      const stat = await fs.lstat(outDir);
      if (!stat.isDirectory()) throw new Error('out-dir must be a directory');
    } catch (error) { if (error.code !== 'ENOENT') throw error; }
    await fs.mkdir(outDir, { recursive: true });
    const outDirReal = await fs.realpath(outDir);
    const plannedNames = times.map((t, i) => `kf_${String(i + 1).padStart(3, '0')}_${String(t).replace('.', '_')}s.png`);
    if (!args.overwrite) {
      for (const name of plannedNames) {
        try {
          await fs.lstat(path.join(outDirReal, name));
          throw new Error(`Keyframe output already exists (${name}); use --overwrite to replace it`);
        } catch (error) { if (error.code !== 'ENOENT') throw error; }
      }
    }
    temporary = await fs.mkdtemp(path.join(outDirReal, '.code-video-kf-'));
    try {
      local = await serve(resourceRoot);
      const studioUrl = `${local.origin}/${path.relative(resourceRoot, studio).split(path.sep).map(encodeURIComponent).join('/')}?render`;
      browser = await puppeteer.launch({
        executablePath: chrome,
        headless: true,
        timeout: readyTimeout,
        args: ['--disable-background-networking', '--disable-default-apps', '--no-first-run'],
      });
      const probePage = await openStudioPage(studioUrl, width || 1280, height || 720);
      const size = await resolveCanvasSize(probePage);
      width ??= size.width;
      height ??= size.height;
      if (width !== size.width || height !== size.height || width % 2 || height % 2 || width > 8192 || height > 8192 || width <= 0 || height <= 0)
        throw new Error('Canvas intrinsic dimensions must match requested positive even dimensions, at most 8192');
      await probePage.setViewport({ width, height, deviceScaleFactor: 1 });
      await probePage.reload({ waitUntil: 'networkidle0', timeout: readyTimeout });
      await probePage.waitForFunction('window.ready === true && typeof window.renderAt === "function"', { timeout: readyTimeout });
      await deadline(probePage.evaluate(async () => {
        await document.fonts.ready;
        await Promise.all([...document.images].map(image => image.decode()));
      }), readyTimeout, 'Font and image readiness');

      const hash = buffer => createHash('sha256').update(buffer).digest('hex');
      const uniqueTimes = [...new Set(times)];
      const buffersByTime = new Map();
      const hashes = new Map();
      for (const t of uniqueTimes) {
        const buf = await renderPng(probePage, t, width, height);
        buffersByTime.set(t, buf);
        hashes.set(t, hash(buf));
      }
      for (const t of [...uniqueTimes].reverse()) {
        if (hash(await renderPng(probePage, t, width, height)) !== hashes.get(t))
          throw new Error(`Forward/reverse seek mismatch at ${t}`);
      }
      const coldSamples = uniqueTimes.length <= 3 ? uniqueTimes : [uniqueTimes[0], uniqueTimes[Math.floor(uniqueTimes.length / 2)], uniqueTimes.at(-1)];
      for (const t of coldSamples) {
        const cold = await openStudioPage(studioUrl, width, height);
        if (hash(await renderPng(cold, t, width, height)) !== hashes.get(t))
          throw new Error(`Cold/warm seek mismatch at ${t}`);
        await cold.close();
      }
      const written = [];
      for (let i = 0; i < times.length; i++) {
        const name = plannedNames[i];
        const stage = path.join(temporary, name);
        const target = path.join(outDirReal, name);
        await fs.writeFile(stage, buffersByTime.get(times[i]));
        if (args.overwrite) {
          try { if (!(await fs.lstat(target)).isFile()) throw new Error(`Existing keyframe target is not a regular file: ${name}`); }
          catch (error) { if (error.code !== 'ENOENT') throw error; }
          await fs.rename(stage, target);
        } else {
          await fs.link(stage, target);
          await fs.unlink(stage);
        }
        written.push({ time: times[i], file: target });
      }
      console.log(JSON.stringify({
        passed: true,
        mode: 'keyframes',
        width,
        height,
        keyframes: written,
        seek_checks: ['forward/reverse PNG equality', 'cold/warm PNG equality'],
        layout_warnings: layoutWarnings,
      }, null, 2));
    } finally {
      if (browser) {
        try { await deadline(browser.close(), 5000, 'Owned browser cleanup'); }
        catch { browser.process()?.kill('SIGKILL'); }
      }
      if (local) { local.server.closeAllConnections?.(); await new Promise(resolve => local.server.close(resolve)); }
      if (temporary) await fs.rm(temporary, { recursive: true, force: true });
    }
    return;
  }

  // Full video export mode
  const fps = number(args.fps, 'fps', 24, 120);
  const requestedDuration = args.duration ? number(args.duration, 'duration', undefined, 3600) : undefined;
  const explicitWorkers = args.workers !== undefined ? number(args.workers, 'workers', 1, 8, true) : undefined;
  const audio = await regularFile(args.audio, 'audio');
  const chapters = args.chapters ? await regularFile(args.chapters, 'chapters') : null;
  const out = path.resolve(args.out);
  if (out === audio || out === studio || (chapters && out === chapters))
    throw new Error('Output must be different from source audio and HTML');
  try {
    const existingOutput = await fs.realpath(out);
    if (existingOutput === audio || existingOutput === studio || (chapters && existingOutput === chapters))
      throw new Error('Output must be different from source audio and HTML');
  } catch (error) { if (error.code !== 'ENOENT') throw error; }
  if (path.extname(out).toLowerCase() !== '.mp4') throw new Error('out must end with .mp4');
  try {
    await fs.lstat(out);
    if (!args.overwrite) throw new Error('Output already exists; use --overwrite to replace it');
    if (!(await fs.lstat(out)).isFile()) throw new Error('Existing output must be a regular file, not a directory or symlink');
  } catch (error) { if (error.code !== 'ENOENT') throw error; }

  await command('ffmpeg', ['-version']);
  await command('ffprobe', ['-version']);
  await command('python3', ['--version']);
  await fs.mkdir(path.dirname(out), { recursive: true });
  temporary = await fs.mkdtemp(path.join(path.dirname(out), '.code-video-'));
  try {
    const pcm = path.join(temporary, 'audio.wav');
    await command('ffmpeg', ['-nostdin', '-v', 'error', '-xerror', '-i', audio, '-map', '0:a:0',
      '-vn', '-ar', '48000', '-c:a', 'pcm_s16le', pcm]);
    const audioData = JSON.parse((await command('ffprobe', ['-v', 'error', '-show_streams', '-of', 'json', pcm])).stdout);
    const audioStream = audioData.streams.find(s => s.codec_type === 'audio');
    if (!audioStream || ![1, 2].includes(audioStream.channels)) throw new Error('Audio must have one or two channels');
    const ticks = Number(audioStream.duration_ts);
    const [timeNumerator, timeDenominator] = String(audioStream.time_base).split('/').map(Number);
    if (![ticks, timeNumerator, timeDenominator].every(value => Number.isSafeInteger(value) && value > 0))
      throw new Error('Decoded PCM requires positive integer duration_ts and time_base');
    const duration = number(ticks * timeNumerator / timeDenominator, 'decoded audio duration', undefined, 3600);
    if (requestedDuration !== undefined && Math.abs(requestedDuration - duration) > 1 / fps + 0.001)
      throw new Error('Explicit duration differs from decoded audio by more than one frame; edit audio first');
    const frameCount = Math.ceil(duration * fps - 1e-8);
    const workerCount = explicitWorkers ?? Math.min(4, Math.max(1, Math.floor(frameCount / 48)));

    local = await serve(resourceRoot);
    const studioUrl = `${local.origin}/${path.relative(resourceRoot, studio).split(path.sep).map(encodeURIComponent).join('/')}?render`;
    browser = await puppeteer.launch({
      executablePath: chrome,
      headless: true,
      timeout: readyTimeout,
      args: ['--disable-background-networking', '--disable-default-apps', '--no-first-run'],
    });

    const page = await openStudioPage(studioUrl, width || 1280, height || 720);
    const size = await resolveCanvasSize(page);
    width ??= size.width;
    height ??= size.height;
    if (width !== size.width || height !== size.height || width % 2 || height % 2 || width > 8192 || height > 8192 || width <= 0 || height <= 0)
      throw new Error('Canvas intrinsic dimensions must match requested positive even dimensions, at most 8192');
    await page.setViewport({ width, height, deviceScaleFactor: 1 });
    await page.reload({ waitUntil: 'networkidle0', timeout: readyTimeout });
    await page.waitForFunction('window.ready === true && typeof window.renderAt === "function"', { timeout: readyTimeout });
    await deadline(page.evaluate(async () => {
      await document.fonts.ready;
      await Promise.all([...document.images].map(image => image.decode()));
    }), readyTimeout, 'Font and image readiness');

    const samples = [...new Set([0, Math.floor(frameCount / 2) / fps, (frameCount - 1) / fps])];
    const hashes = new Map();
    const hash = buffer => createHash('sha256').update(buffer).digest('hex');
    for (const time of samples) hashes.set(time, hash(await renderPng(page, time, width, height)));
    for (const time of [...samples].reverse()) {
      if (hash(await renderPng(page, time, width, height)) !== hashes.get(time))
        throw new Error(`Forward/reverse seek mismatch at ${time}`);
    }
    for (const time of samples) {
      const cold = await openStudioPage(studioUrl, width, height);
      if (hash(await renderPng(cold, time, width, height)) !== hashes.get(time))
        throw new Error(`Cold/warm seek mismatch at ${time}`);
      await cold.close();
    }

    const frames = path.join(temporary, 'frames');
    await fs.mkdir(frames);
    const pages = [page];
    for (let w = 1; w < workerCount; w++) {
      pages.push(await openStudioPage(studioUrl, width, height));
    }
    let nextIndex = 0;
    let completed = 0;
    const reportStep = Math.max(1, Math.ceil(frameCount / 10));
    await Promise.all(pages.map(async workerPage => {
      while (true) {
        const index = nextIndex++;
        if (index >= frameCount) break;
        const buf = await renderPng(workerPage, index / fps, width, height);
        await fs.writeFile(path.join(frames, `${String(index).padStart(8, '0')}.png`), buf);
        completed++;
        if (completed % reportStep === 0 || completed === frameCount)
          console.error(`Rendered ${completed}/${frameCount} frames`);
      }
    }));
    checkErrors();

    const pending = path.join(temporary, 'pending.mp4');
    const ffmpegArgs = [
      '-nostdin', '-v', 'error', '-xerror',
      '-framerate', String(fps), '-start_number', '0', '-i', path.join(frames, '%08d.png'),
      '-i', pcm,
    ];
    if (chapters) ffmpegArgs.push('-i', chapters);
    ffmpegArgs.push('-map', '0:v:0', '-map', '1:a:0');
    if (chapters) ffmpegArgs.push('-map_metadata', '2', '-map_chapters', '2');
    ffmpegArgs.push(
      '-c:v', 'libx264', '-crf', '18', '-preset', 'medium',
      '-pix_fmt', 'yuv420p', '-fps_mode', 'cfr', '-c:a', 'aac', '-b:a', '192k',
      '-movflags', '+faststart', pending,
    );
    await command('ffmpeg', ffmpegArgs);

    const verifier = fileURLToPath(new URL('./verify-video.py', import.meta.url));
    const validation = ['python3', [
      verifier, pending, '--width', String(width), '--height', String(height),
      '--fps', String(fps), '--frames', String(frameCount), '--duration', String(duration),
      '--channels', String(audioStream.channels),
    ]];
    if (args['allow-silent-audio']) validation[1].push('--allow-silent-audio');
    const verification = JSON.parse((await command(...validation)).stdout);
    checkErrors();

    if (args.overwrite) {
      try { if (!(await fs.lstat(out)).isFile()) throw new Error('Output became a directory or symlink'); }
      catch (error) { if (error.code !== 'ENOENT') throw error; }
      await fs.rename(pending, out);
    } else {
      await fs.link(pending, out);
      await fs.unlink(pending);
    }
    console.log(JSON.stringify({
      passed: true,
      out,
      workers: workerCount,
      source_seek_samples: samples,
      seek_checks: ['forward/reverse PNG equality', 'cold/warm PNG equality'],
      layout_warnings: layoutWarnings,
      verification,
    }, null, 2));
  } finally {
    if (browser) {
      try { await deadline(browser.close(), 5000, 'Owned browser cleanup'); }
      catch { browser.process()?.kill('SIGKILL'); }
    }
    if (local) { local.server.closeAllConnections?.(); await new Promise(resolve => local.server.close(resolve)); }
    if (temporary) await fs.rm(temporary, { recursive: true, force: true });
  }
}

main().catch(error => { console.error(error.message); process.exitCode = interrupted ? 130 : 1; });
