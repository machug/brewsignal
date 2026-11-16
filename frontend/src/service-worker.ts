/// <reference types="@sveltejs/kit" />
/// <reference lib="webworker" />

// Web Push only (tilt_ui-91a). No offline caching.
const sw = self as unknown as ServiceWorkerGlobalScope;

sw.addEventListener('install', () => sw.skipWaiting());
sw.addEventListener('activate', (event) => event.waitUntil(sw.clients.claim()));

sw.addEventListener('push', (event) => {
	const data = event.data?.json() ?? {};
	event.waitUntil(
		sw.registration.showNotification(data.title || 'BrewSignal', {
			body: data.body,
			icon: '/icon-512.png',
			badge: '/icon-512.png',
			data: { url: data.url || '/' }
		})
	);
});

sw.addEventListener('notificationclick', (event) => {
	event.notification.close();
	const url = new URL(event.notification.data?.url || '/', sw.location.origin).href;
	event.waitUntil(
		sw.clients.matchAll({ type: 'window', includeUncontrolled: true }).then((clients) => {
			const open = clients.find((c) => 'focus' in c);
			if (open) {
				open.focus();
				return 'navigate' in open ? open.navigate(url) : undefined;
			}
			return sw.clients.openWindow(url);
		})
	);
});
