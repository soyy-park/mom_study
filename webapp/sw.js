const CACHE_NAME = "quiz-review-v1";
const SHELL_FILES = [
  "./",
  "./index.html",
  "./style.css",
  "./app.js",
  "./firebase-config.js",
  "./profile-config.js",
  "./manifest.json",
  "./icons/icon-192.png",
  "./icons/icon-512.png",
];
const SDK_PREFIX = "https://www.gstatic.com/firebasejs/";
// 홈 화면 목업이 쓰는 CDN (Tailwind + 구글 폰트) — 버전 고정이 아니라서 캐시 우선이 아니라
// 네트워크 우선으로 캐싱해야 업데이트가 반영되면서도 오프라인일 때 마지막 버전을 쓸 수 있다.
const NETWORK_FIRST_HOSTS = ["cdn.tailwindcss.com", "fonts.googleapis.com", "fonts.gstatic.com"];

self.addEventListener("install", (event) => {
  event.waitUntil(caches.open(CACHE_NAME).then((cache) => cache.addAll(SHELL_FILES)));
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE_NAME).map((k) => caches.delete(k)))
    )
  );
  self.clients.claim();
});

// 같은 출처(앱 셸): 네트워크 우선 -> 재배포가 바로 반영되고, 오프라인이면 캐시 사용.
async function networkFirst(request) {
  const cache = await caches.open(CACHE_NAME);
  try {
    const response = await fetch(request);
    if (response.ok) cache.put(request, response.clone());
    return response;
  } catch (err) {
    const cached = await cache.match(request);
    if (cached) return cached;
    if (request.mode === "navigate") return cache.match("./index.html");
    throw err;
  }
}

// Firebase SDK(CDN): 주소에 버전이 박혀 있어 불변이므로 캐시 우선.
async function cacheFirst(request) {
  const cache = await caches.open(CACHE_NAME);
  const cached = await cache.match(request);
  if (cached) return cached;
  const response = await fetch(request);
  if (response.ok) cache.put(request, response.clone());
  return response;
}

self.addEventListener("fetch", (event) => {
  const { request } = event;
  if (request.method !== "GET") return;
  const url = new URL(request.url);

  if (url.origin === self.location.origin) {
    event.respondWith(networkFirst(request));
  } else if (request.url.startsWith(SDK_PREFIX)) {
    event.respondWith(cacheFirst(request));
  } else if (NETWORK_FIRST_HOSTS.includes(url.hostname)) {
    event.respondWith(networkFirst(request));
  }
  // 그 외(Firestore 통신 등)는 건드리지 않는다 — SDK 자체 오프라인 캐시가 담당.
});
