/**
 * 拾光 · Lumen — Service Worker
 *
 * 策略：
 * - 导航请求 (HTML): network-first → 永远拿最新 index.html，断网时回退缓存
 * - 静态资源 (JS/CSS/字体/图片): cache-first → Vite 内容哈希，安全长期缓存
 * - API (/api/*) & WebSocket: 不拦截，直通网络
 *
 * 自动更新机制：
 * - install 时 skipWaiting() → 新 SW 立即激活
 * - activate 时清理旧缓存 + clients.claim() → 立即接管页面
 * - 页面端监听 controllerchange → 自动刷新一次
 */

const CACHE_NAME = 'lumen-v1';

// 静态资源后缀（Vite hash 后的文件，安全缓存）
const STATIC_ASSET_RE = /\.(?:js|css|woff2?|ttf|eot|png|jpg|jpeg|svg|ico|webp|avif)$/i;

// ── Install: 立即激活 ──────────────────────────────────────────────────────
self.addEventListener('install', (event) => {
  self.skipWaiting();
});

// ── Activate: 清理旧缓存 + 接管页面 ────────────────────────────────────────
self.addEventListener('activate', (event) => {
  event.waitUntil(
    (async () => {
      const names = await caches.keys();
      await Promise.all(
        names
          .filter((n) => n !== CACHE_NAME)
          .map((n) => caches.delete(n)),
      );
      await self.clients.claim();
    })(),
  );
});

// ── Fetch: 分策略缓存 ───────────────────────────────────────────────────────
self.addEventListener('fetch', (event) => {
  const { request } = event;

  // 只处理 GET
  if (request.method !== 'GET') return;

  const url = new URL(request.url);

  // API 和 WebSocket 直通
  if (url.pathname.startsWith('/api/')) return;

  // 导航请求: network-first
  if (request.mode === 'navigate') {
    event.respondWith(
      (async () => {
        try {
          const resp = await fetch(request);
          const cache = await caches.open(CACHE_NAME);
          cache.put(request, resp.clone());
          return resp;
        } catch {
          // 断网：回退缓存的 index.html
          const cached = await caches.match(request);
          if (cached) return cached;
          return caches.match('/');
        }
      })(),
    );
    return;
  }

  // 同源静态资源: cache-first
  if (url.origin === self.location.origin && STATIC_ASSET_RE.test(url.pathname)) {
    event.respondWith(
      (async () => {
        const cached = await caches.match(request);
        if (cached) return cached;
        try {
          const resp = await fetch(request);
          // 只缓存成功的响应
          if (resp.ok) {
            const cache = await caches.open(CACHE_NAME);
            cache.put(request, resp.clone());
          }
          return resp;
        } catch {
          return new Response('', { status: 504, statusText: 'Offline' });
        }
      })(),
    );
  }
});
