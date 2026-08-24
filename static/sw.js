const CACHE_NAME = 'namsuong-v1';

// Cài đặt Service Worker
self.addEventListener('install', event => {
    console.log('Service Worker: Đã cài đặt');
    self.skipWaiting();
});

// Kích hoạt và dọn dẹp cache cũ
self.addEventListener('activate', event => {
    console.log('Service Worker: Đã kích hoạt');
});

// Lắng nghe các yêu cầu mạng (Fetch)
self.addEventListener('fetch', event => {
    // Phiên bản cơ bản: luôn tải dữ liệu mới từ mạng
    event.respondWith(fetch(event.request));
});