const http = require('http');
const fs = require('fs');
const fsp = require('fs/promises');
const path = require('path');
const crypto = require('crypto');
const { URL } = require('url');

const rootDir = path.resolve(__dirname, '..');
const publicDir = path.join(__dirname, 'public');
const configPath = path.join(__dirname, 'share-config.json');
const projectPath = path.join(rootDir, 'data', 'project.json');
const playlistPath = path.join(rootDir, 'data', 'playlist.json');
const photosDir = path.join(rootDir, 'photos-web');
const musicDir = path.join(rootDir, 'music');
const SESSION_COOKIE = 'wedding_share_session';
const SESSION_MAX_AGE = 1000 * 60 * 60 * 24 * 30;
const ASSET_MAX_AGE = 1000 * 60 * 60 * 24 * 7;

const MIME = {
  '.html': 'text/html; charset=utf-8',
  '.js': 'application/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.jpg': 'image/jpeg',
  '.jpeg': 'image/jpeg',
  '.png': 'image/png',
  '.webp': 'image/webp',
  '.svg': 'image/svg+xml',
  '.ico': 'image/x-icon',
  '.mp3': 'audio/mpeg',
  '.m4a': 'audio/mp4',
  '.aac': 'audio/aac',
  '.wav': 'audio/wav',
  '.flac': 'audio/flac',
};

function readJson(filePath) {
  return JSON.parse(fs.readFileSync(filePath, 'utf8'));
}

function getConfig() {
  const config = readJson(configPath);
  if (!config.password || !config.cookieSecret) {
    throw new Error('share-config.json 缺少 password 或 cookieSecret');
  }
  return config;
}

function sign(secret, value) {
  return crypto.createHmac('sha256', secret).update(value).digest('base64url');
}

function createSession(secret) {
  const expiresAt = Date.now() + SESSION_MAX_AGE;
  return `${expiresAt}.${sign(secret, String(expiresAt))}`;
}

function parseCookies(header) {
  if (!header) return {};
  return Object.fromEntries(
    header.split(';').map(part => {
      const idx = part.indexOf('=');
      if (idx === -1) return [part.trim(), ''];
      return [part.slice(0, idx).trim(), decodeURIComponent(part.slice(idx + 1).trim())];
    }),
  );
}

function isAuthed(req, secret) {
  const raw = parseCookies(req.headers.cookie)[SESSION_COOKIE];
  if (!raw) return false;
  const [expiresAt, digest] = raw.split('.');
  if (!expiresAt || !digest || !/^\d+$/.test(expiresAt)) return false;
  if (Number(expiresAt) < Date.now()) return false;
  return crypto.timingSafeEqual(Buffer.from(digest), Buffer.from(sign(secret, expiresAt)));
}

function signAsset(secret, pathname, expiresAt) {
  return sign(secret, `asset:${pathname}:${expiresAt}`);
}

function verifyAsset(secret, url) {
  const expiresAt = url.searchParams.get('exp');
  const sig = url.searchParams.get('sig');
  if (!expiresAt || !sig || !/^\d+$/.test(expiresAt)) return false;
  if (Number(expiresAt) < Date.now()) return false;
  const expected = signAsset(secret, url.pathname, expiresAt);
  return crypto.timingSafeEqual(Buffer.from(sig), Buffer.from(expected));
}

function json(res, code, payload) {
  const body = JSON.stringify(payload);
  res.writeHead(code, {
    'Content-Type': MIME['.json'],
    'Cache-Control': 'no-store',
    'Content-Length': Buffer.byteLength(body),
  });
  res.end(body);
}

function serveFile(res, filePath, cacheControl) {
  const ext = path.extname(filePath).toLowerCase();
  const stat = fs.statSync(filePath);
  res.writeHead(200, {
    'Content-Type': MIME[ext] || 'application/octet-stream',
    'Cache-Control': cacheControl,
    'Content-Length': stat.size,
  });
  fs.createReadStream(filePath).pipe(res);
}

function safeJoin(base, requestPath) {
  const filePath = path.normalize(path.join(base, requestPath));
  if (!filePath.startsWith(base)) return null;
  return filePath;
}

async function readBody(req) {
  const chunks = [];
  for await (const chunk of req) chunks.push(chunk);
  return Buffer.concat(chunks).toString('utf8');
}

function buildProjectPayload(secret) {
  const project = readJson(projectPath);
  const expiresAt = String(Date.now() + ASSET_MAX_AGE);
  const photos = (project.photos || []).map(src => {
    const pathname = `/${src}`;
    const sig = signAsset(secret, pathname, expiresAt);
    return {
      src: `${pathname}?exp=${expiresAt}&sig=${encodeURIComponent(sig)}`,
    };
  });
  return {
    title: project.title || '婚礼相册',
    subtitle: project.subtitle || '',
    theme: project.theme || 'starry',
    total: photos.length,
    photos,
  };
}

function buildPlaylistPayload(secret) {
  const playlist = readJson(playlistPath);
  const expiresAt = String(Date.now() + ASSET_MAX_AGE);
  const tracks = (playlist.tracks || []).map(src => {
    const pathname = `/${src}`;
    const sig = signAsset(secret, pathname, expiresAt);
    return { src: `${pathname}?exp=${expiresAt}&sig=${encodeURIComponent(sig)}` };
  });
  return { total: tracks.length, tracks };
}

const server = http.createServer(async (req, res) => {
  try {
    const config = getConfig();
    const url = new URL(req.url, `http://${req.headers.host}`);
    const authed = isAuthed(req, config.cookieSecret);

    if (url.pathname === '/health') {
      return json(res, 200, { ok: true });
    }

    if (url.pathname === '/api/session') {
      return json(res, 200, { authenticated: authed });
    }

    if (url.pathname === '/api/login' && req.method === 'POST') {
      const body = JSON.parse((await readBody(req)) || '{}');
      if (String(body.password || '') !== config.password) {
        return json(res, 401, { ok: false, message: '密码不正确' });
      }
      const session = createSession(config.cookieSecret);
      res.writeHead(200, {
        'Content-Type': MIME['.json'],
        'Cache-Control': 'no-store',
        'Set-Cookie': `${SESSION_COOKIE}=${session}; Max-Age=${SESSION_MAX_AGE / 1000}; Path=/; HttpOnly; SameSite=Lax`,
      });
      return res.end(JSON.stringify({ ok: true }));
    }

    if (url.pathname === '/api/project') {
      if (!authed) return json(res, 401, { authenticated: false });
      return json(res, 200, buildProjectPayload(config.cookieSecret));
    }

    if (url.pathname === '/api/playlist') {
      if (!authed) return json(res, 401, { authenticated: false });
      return json(res, 200, buildPlaylistPayload(config.cookieSecret));
    }

    if (url.pathname === '/' || url.pathname === '/album' || url.pathname === '/album.html') {
      return serveFile(res, path.join(publicDir, 'share.html'), 'no-store');
    }

    if (url.pathname === '/favicon.ico') {
      res.writeHead(204);
      return res.end();
    }

    if (url.pathname.startsWith('/photos-web/')) {
      if (!authed && !verifyAsset(config.cookieSecret, url)) return json(res, 401, { authenticated: false });
      const reqPath = decodeURIComponent(url.pathname.replace(/^\/photos-web\//, ''));
      const filePath = safeJoin(photosDir, reqPath);
      if (!filePath || !fs.existsSync(filePath)) return json(res, 404, { message: 'photo not found' });
      return serveFile(res, filePath, 'private, max-age=604800');
    }

    if (url.pathname.startsWith('/music/')) {
      if (!authed && !verifyAsset(config.cookieSecret, url)) return json(res, 401, { authenticated: false });
      const reqPath = decodeURIComponent(url.pathname.replace(/^\/music\//, ''));
      const filePath = safeJoin(musicDir, reqPath);
      if (!filePath || !fs.existsSync(filePath)) return json(res, 404, { message: 'track not found' });
      return serveFile(res, filePath, 'private, max-age=604800');
    }

    const fallback = safeJoin(publicDir, decodeURIComponent(url.pathname.replace(/^\//, '')));
    if (fallback && fs.existsSync(fallback) && fs.statSync(fallback).isFile()) {
      return serveFile(res, fallback, 'no-store');
    }

    res.writeHead(404, { 'Content-Type': 'text/plain; charset=utf-8' });
    res.end('Not Found');
  } catch (error) {
    res.writeHead(500, { 'Content-Type': 'text/plain; charset=utf-8' });
    res.end(`Server Error: ${error.message}`);
  }
});

const config = getConfig();
server.listen(config.port, config.host, () => {
  console.log(`share server listening on http://${config.host}:${config.port}`);
});
