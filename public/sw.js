// Service worker mínimo: permite instalar como aplicativo. Os dados offline ficam no cache do Firestore.
self.addEventListener('install',()=>self.skipWaiting());self.addEventListener('activate',e=>e.waitUntil(self.clients.claim()));
self.addEventListener('fetch',()=>{});
