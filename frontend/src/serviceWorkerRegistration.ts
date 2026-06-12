export function register() {
  if ('serviceWorker' in navigator) {
    window.addEventListener('load', () => {
      const swUrl = '/sw.js';
      navigator.serviceWorker
        .register(swUrl)
        .then((registration) => {
          console.log('[SW] ServiceWorker registered successfully with scope:', registration.scope);
        })
        .catch((error) => {
          console.error('[SW] ServiceWorker registration failed:', error);
        });
    });
  }
}

export function unregister() {
  if ('serviceWorker' in navigator) {
    navigator.serviceWorker.ready
      .then((registration) => {
        registration.unregister();
        console.log('[SW] ServiceWorker unregistered.');
      })
      .catch((error) => {
        console.error(error.message);
      });
  }
}
