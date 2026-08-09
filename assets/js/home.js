if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', loadHomepageImages);
} else {
  loadHomepageImages();
}

async function loadHomepageImages() {
  const targets = [...document.querySelectorAll('img[data-product-model]')];
  if (!targets.length) return;

  try {
    const response = await fetch('/api/catalog', { cache: 'no-cache' });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const payload = await response.json();
    if (!Array.isArray(payload.products)) throw new Error('商品 API 格式錯誤');

    targets.forEach((image) => {
      const model = normalizeProductKey(image.dataset.productModel);
      const look = normalizeProductKey(image.dataset.productLook);
      const match = payload.products.find((product) => (
        normalizeProductKey(product.model || product.name) === model &&
        (!look || normalizeProductKey(product.look).includes(look)) &&
        product.imageUrl
      ));

      if (match?.imageUrl) {
        const originalSource = image.getAttribute('src');
        image.addEventListener('error', () => {
          if (originalSource) image.src = originalSource;
        }, { once: true });
        image.src = match.imageUrl;
      }
    });
  } catch (error) {
    console.warn('本機型錄圖片暫時無法取得，保留原有圖片。', error);
  }
}

function normalizeProductKey(value = '') {
  return String(value)
    .normalize('NFKC')
    .toUpperCase()
    .replaceAll('電渡', '電鍍')
    .replace(/(旋壓|鍛造|鑄造|色)/g, '')
    .replace(/[^0-9A-Z\u4E00-\u9FFF]+/g, '');
}
