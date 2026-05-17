// Service Worker disabled — using direct serving for development
// This file intentionally unregisters any existing service worker

self.addEventListener('install', () => self.skipWaiting());
self.addEventListener('activate', (e) => {
  e.waitUntil(
    caches.keys().then(keys => Promise.all(keys.map(k => caches.delete(k))))
      .then(() => self.clients.claim())
      .then(() => {
        // Tell all clients to reload
        self.clients.matchAll().then(clients => {
          clients.forEach(client => client.navigate(client.url));
        });
      })
  );
});
