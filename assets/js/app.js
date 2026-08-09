const PAGE_SIZE = 24;

let allProducts = [];
let catalogItems = [];
let filteredItems = [];
let renderedCount = 0;
let activeModalItem = null;
let toastTimer = null;
let catalogMeta = null;

let currentFilters = {
  size: '',
  pcd: '',
  category: '',
  search: '',
};

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', init);
} else {
  init();
}

async function init() {
  try {
    allProducts = await loadProducts();
    catalogItems = groupProducts(allProducts);

    document.getElementById('modelCount').textContent = new Set(allProducts.map((item) => item.model)).size;
    document.getElementById('specCount').textContent = allProducts.length;

    renderFilterButtons();
    readFiltersFromUrl();
    syncFilterControls();
    initUIEvents();
    initInfiniteScroll();
    applyFilters();
    showSourceStatus();
  } catch (error) {
    console.error('型錄載入失敗:', error);
    showLoadError();
  } finally {
    document.getElementById('loader')?.classList.add('hidden');
  }
}

async function loadProducts() {
  try {
    const response = await fetch('/api/catalog', { cache: 'no-cache' });
    if (!response.ok) throw new Error(`本機型錄 API HTTP ${response.status}`);
    const payload = await response.json();
    if (!Array.isArray(payload.products)) throw new Error('商品 API 格式錯誤');
    catalogMeta = payload.meta || null;
    return payload.products;
  } catch (catalogError) {
    console.warn('本機圖片索引暫時無法載入，改用專案內的基礎型錄。', catalogError);
    const fallbackResponse = await fetch('./data/products.json', { cache: 'no-cache' });
    if (!fallbackResponse.ok) throw new Error(`Fallback HTTP ${fallbackResponse.status}`);
    const products = await fallbackResponse.json();
    if (!Array.isArray(products)) throw new Error('商品資料格式錯誤');
    catalogMeta = {
      source: 'static-fallback',
      warnings: ['本機圖片索引暫時無法載入，目前顯示基礎型錄。'],
    };
    return products;
  }
}

function groupProducts(products) {
  const groups = new Map();

  products.forEach((product) => {
    const key = JSON.stringify([product.model, product.look, product.category]);
    if (!groups.has(key)) {
      groups.set(key, {
        model: product.model,
        look: product.look,
        category: product.category,
        image: product.image,
        imageUrl: product.imageUrl || '',
        variants: [],
      });
    }

    const group = groups.get(key);
    if (!group.image && product.image) group.image = product.image;
    if (!group.imageUrl && product.imageUrl) group.imageUrl = product.imageUrl;

    const specKey = JSON.stringify(product.spec);
    if (!group.variants.some((variant) => JSON.stringify(variant) === specKey)) {
      group.variants.push(product.spec);
    }
  });

  return [...groups.values()]
    .map((item) => ({ ...item, variants: sortVariants(item.variants) }))
    .sort((a, b) => a.model.localeCompare(b.model, 'zh-Hant', { numeric: true }));
}

function sortVariants(variants) {
  return [...variants].sort((a, b) => (
    Number(a['吋']) - Number(b['吋']) ||
    a['孔徑'].localeCompare(b['孔徑'], 'zh-Hant', { numeric: true }) ||
    Number(a['J值']) - Number(b['J值']) ||
    Number(a['ET值']) - Number(b['ET值'])
  ));
}

function renderFilterButtons() {
  const sizes = uniqueSorted(allProducts.map((item) => item.spec?.['吋']), true);
  const pcds = uniqueSorted(allProducts.map((item) => item.spec?.['孔徑']));
  const categories = ['鑄造', '旋壓', '鍛造'].filter((category) => (
    allProducts.some((item) => item.category === category)
  ));

  renderChips('filterSizes', sizes, 'size', (value) => `${value} 吋`);
  renderChips('filterPCD', pcds, 'pcd');
  renderChips('filterCategories', categories, 'category');
}

function renderChips(containerId, values, type, labeler = (value) => value) {
  const container = document.getElementById(containerId);
  if (!container) return;

  values.forEach((value) => {
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'chip';
    button.dataset.type = type;
    button.dataset.value = value;
    button.textContent = labeler(value);
    container.appendChild(button);
  });
}

function uniqueSorted(values, numeric = false) {
  const unique = [...new Set(values.filter(Boolean))];
  return unique.sort((a, b) => numeric
    ? Number(a) - Number(b)
    : a.localeCompare(b, 'zh-Hant', { numeric: true }));
}

function readFiltersFromUrl() {
  const params = new URLSearchParams(window.location.search);
  currentFilters = {
    size: params.get('size') || '',
    pcd: params.get('pcd') || '',
    category: params.get('category') || '',
    search: params.get('search') || '',
  };
}

function syncFilterControls() {
  const searchInput = document.getElementById('searchInput');
  if (searchInput) searchInput.value = currentFilters.search;

  document.querySelectorAll('.chip').forEach((chip) => {
    chip.classList.toggle('active', currentFilters[chip.dataset.type] === chip.dataset.value);
  });
}

function applyFilters() {
  filteredItems = catalogItems.flatMap((item) => {
    const searchTarget = `${item.model} ${item.look} ${item.category}`.toLowerCase();
    const matchesSearch = !currentFilters.search || searchTarget.includes(currentFilters.search.toLowerCase());
    const matchesCategory = !currentFilters.category || item.category === currentFilters.category;
    if (!matchesSearch || !matchesCategory) return [];

    const matchingVariants = item.variants.filter((spec) => (
      (!currentFilters.size || spec['吋'] === currentFilters.size) &&
      (!currentFilters.pcd || spec['孔徑'] === currentFilters.pcd)
    ));

    return matchingVariants.length ? [{ ...item, visibleVariants: matchingVariants }] : [];
  });

  renderedCount = 0;
  document.getElementById('grid')?.replaceChildren();

  const visibleSpecs = filteredItems.reduce((total, item) => total + item.visibleVariants.length, 0);
  const resultCounter = document.getElementById('resultCounter');
  if (resultCounter) resultCounter.textContent = `共 ${filteredItems.length} 款 / ${visibleSpecs} 種規格`;

  const emptyState = document.getElementById('emptyState');
  emptyState?.classList.toggle('hidden', filteredItems.length > 0);

  renderActiveFilters();
  updateFilterBadge();
  updateUrl();
  revealNextPage();
}

function revealNextPage() {
  if (renderedCount >= filteredItems.length) return;

  const page = filteredItems.slice(renderedCount, renderedCount + PAGE_SIZE);
  const fragment = document.createDocumentFragment();
  page.forEach((item) => fragment.appendChild(createProductCard(item)));
  document.getElementById('grid')?.appendChild(fragment);
  renderedCount += page.length;
}

function createProductCard(item) {
  const card = document.createElement('button');
  card.type = 'button';
  card.className = 'product-card';
  card.setAttribute('aria-label', `查看 ${item.model} ${item.look || ''} 規格`);

  const media = document.createElement('div');
  media.className = 'product-card__media';

  const badge = document.createElement('span');
  badge.className = 'product-card__badge';
  badge.textContent = item.category || '鋁圈';
  media.appendChild(badge);
  setProductImage(media, getProductImageSource(item), `${item.model} ${item.look || ''}`, item.model);

  const sizes = uniqueSorted(item.visibleVariants.map((spec) => spec['吋']), true);
  const pcds = uniqueSorted(item.visibleVariants.map((spec) => spec['孔徑']));

  const body = document.createElement('div');
  body.className = 'product-card__body';
  body.innerHTML = `
    <div class="product-card__heading">
      <h2>${escapeHtml(item.model)}</h2>
      <span>${item.visibleVariants.length} 種規格</span>
    </div>
    <p class="product-card__finish">${escapeHtml(item.look || '表面處理待確認')}</p>
    <div class="product-card__specs">
      <div><small>SIZE</small><strong>${escapeHtml(sizes.map((size) => `${size}"`).join(' / '))}</strong></div>
      <div><small>PCD</small><strong>${escapeHtml(pcds.join(' / '))}</strong></div>
    </div>
  `;

  card.append(media, body);
  card.addEventListener('click', () => openModal(item));
  return card;
}

function getProductImageSource(item) {
  if (item.imageUrl) return item.imageUrl;
  const firstVariant = item.visibleVariants?.[0] || item.variants?.[0];
  const size = firstVariant?.['吋'];
  return item.image && size
    ? `./public/images/wheels/${encodeURIComponent(size)}/${encodeURIComponent(item.image)}`
    : '';
}

function setProductImage(container, imageSource, alt, model) {
  container.querySelectorAll('img, .product-card__placeholder').forEach((element) => element.remove());

  if (!imageSource) {
    appendPlaceholder(container, model);
    return;
  }

  const image = document.createElement('img');
  image.loading = 'lazy';
  image.alt = alt;
  image.src = imageSource;
  image.addEventListener('error', () => {
    image.remove();
    appendPlaceholder(container, model);
  }, { once: true });
  container.appendChild(image);
}

function appendPlaceholder(container, model) {
  if (container.querySelector('.product-card__placeholder')) return;
  const placeholder = document.createElement('div');
  placeholder.className = 'product-card__placeholder';
  const title = document.createElement('strong');
  title.textContent = model;
  const label = document.createElement('span');
  label.textContent = 'IMAGE PENDING';
  placeholder.append(title, label);
  container.appendChild(placeholder);
}

function openModal(item) {
  activeModalItem = item;
  const modal = document.getElementById('detailModal');
  if (!modal) return;

  document.getElementById('modalCategory').textContent = item.category || 'ALLOY WHEEL';
  document.getElementById('modalTitle').textContent = item.model;
  document.getElementById('modalSubtitle').textContent = item.look || '表面處理待確認';
  document.getElementById('modalVariantCount').textContent = `共 ${item.visibleVariants.length} 種`;

  const modalMedia = document.getElementById('modalMedia');
  setProductImage(modalMedia, getProductImageSource(item), `${item.model} ${item.look || ''}`, item.model);

  const tbody = document.getElementById('modalVariants');
  tbody.replaceChildren();
  sortVariants(item.visibleVariants).forEach((spec) => {
    const row = document.createElement('tr');
    row.innerHTML = `
      <td>${escapeHtml(spec['吋'])}"</td>
      <td>${escapeHtml(spec['孔徑'])}</td>
      <td>${escapeHtml(spec['J值'])}J</td>
      <td>ET ${escapeHtml(spec['ET值'])}</td>
      <td>${escapeHtml(spec['中心孔'])}</td>
    `;
    tbody.appendChild(row);
  });

  modal.showModal();
}

async function copyInquiryInformation() {
  if (!activeModalItem) return;

  const variants = sortVariants(activeModalItem.visibleVariants);
  const lines = variants.slice(0, 12).map((spec) => (
    `${spec['吋']}吋 / PCD ${spec['孔徑']} / ${spec['J值']}J / ET ${spec['ET值']} / 中心孔 ${spec['中心孔']}`
  ));
  if (variants.length > 12) lines.push(`其他 ${variants.length - 12} 種規格請由門市確認`);

  const text = [
    '北德文鋁圈｜門市詢價',
    `型號：${activeModalItem.model}`,
    `表面處理：${activeModalItem.look || '待確認'}`,
    `製程：${activeModalItem.category || '待確認'}`,
    '可選規格：',
    ...lines,
    '',
    '車型／年份：（請填寫）',
    '現有輪胎規格：（請填寫）',
  ].join('\n');

  try {
    await navigator.clipboard.writeText(text);
  } catch {
    fallbackCopy(text);
  }
  showToast('已複製詢價資訊');
}

function fallbackCopy(text) {
  const textarea = document.createElement('textarea');
  textarea.value = text;
  textarea.setAttribute('readonly', '');
  textarea.style.position = 'fixed';
  textarea.style.opacity = '0';
  document.body.appendChild(textarea);
  textarea.select();
  document.execCommand('copy');
  textarea.remove();
}

function showToast(message) {
  const toast = document.getElementById('toast');
  if (!toast) return;
  toast.textContent = message;
  toast.classList.add('show');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => toast.classList.remove('show'), 2200);
}

function showSourceStatus() {
  if (!catalogMeta) return;
  const warnings = Array.isArray(catalogMeta.warnings) ? catalogMeta.warnings : [];
  warnings.forEach((warning) => console.warn(warning));

  if (catalogMeta.source === 'static-fallback') {
    showToast('本機圖片索引暫時無法載入，已顯示基礎型錄');
    return;
  }

  if (catalogMeta.stock?.error) {
    showToast('庫存 Excel 暫時無法取得，商品型錄仍可瀏覽');
  }
}

function setDrawer(open) {
  const drawer = document.getElementById('filterDrawer');
  const backdrop = document.getElementById('drawerBackdrop');
  const trigger = document.getElementById('filterTrigger');
  drawer?.classList.toggle('open', open);
  drawer?.setAttribute('aria-hidden', String(!open));
  backdrop?.classList.toggle('hidden', !open);
  trigger?.setAttribute('aria-expanded', String(open));
}

function clearFilters() {
  currentFilters = { size: '', pcd: '', category: '', search: '' };
  syncFilterControls();
  applyFilters();
}

function renderActiveFilters() {
  const container = document.getElementById('activeFilters');
  if (!container) return;
  container.replaceChildren();

  const labels = {
    search: `搜尋：${currentFilters.search}`,
    size: `${currentFilters.size} 吋`,
    pcd: `PCD ${currentFilters.pcd}`,
    category: currentFilters.category,
  };

  Object.entries(currentFilters).forEach(([type, value]) => {
    if (!value) return;
    const tag = document.createElement('span');
    tag.className = 'active-filter';
    tag.append(document.createTextNode(labels[type]));

    const remove = document.createElement('button');
    remove.type = 'button';
    remove.setAttribute('aria-label', `移除${labels[type]}條件`);
    remove.textContent = '×';
    remove.addEventListener('click', () => {
      currentFilters[type] = '';
      syncFilterControls();
      applyFilters();
    });
    tag.appendChild(remove);
    container.appendChild(tag);
  });
}

function updateFilterBadge() {
  const count = ['size', 'pcd', 'category'].filter((key) => currentFilters[key]).length;
  const badge = document.getElementById('activeFilterCount');
  if (!badge) return;
  badge.textContent = count;
  badge.classList.toggle('hidden', count === 0);
}

function updateUrl() {
  const params = new URLSearchParams();
  Object.entries(currentFilters).forEach(([key, value]) => {
    if (value) params.set(key, value);
  });
  const query = params.toString();
  history.replaceState(null, '', `${window.location.pathname}${query ? `?${query}` : ''}`);
}

function initUIEvents() {
  const modal = document.getElementById('detailModal');

  document.getElementById('filterTrigger')?.addEventListener('click', () => setDrawer(true));
  document.getElementById('filterClose')?.addEventListener('click', () => setDrawer(false));
  document.getElementById('filterApply')?.addEventListener('click', () => setDrawer(false));
  document.getElementById('drawerBackdrop')?.addEventListener('click', () => setDrawer(false));
  document.getElementById('filterClear')?.addEventListener('click', clearFilters);
  document.getElementById('emptyClear')?.addEventListener('click', clearFilters);
  document.getElementById('copyInquiry')?.addEventListener('click', copyInquiryInformation);
  document.querySelector('.modal-close')?.addEventListener('click', () => modal?.close());

  modal?.addEventListener('click', (event) => {
    if (event.target === modal) modal.close();
  });

  document.getElementById('searchInput')?.addEventListener('input', (event) => {
    currentFilters.search = event.target.value.trim();
    applyFilters();
  });

  document.addEventListener('click', (event) => {
    const chip = event.target.closest('.chip');
    if (!chip) return;
    const { type, value } = chip.dataset;
    currentFilters[type] = currentFilters[type] === value ? '' : value;
    syncFilterControls();
    applyFilters();
  });
}

function initInfiniteScroll() {
  const sentinel = document.getElementById('sentinel');
  if (!sentinel || !('IntersectionObserver' in window)) return;
  new IntersectionObserver((entries) => {
    if (entries[0].isIntersecting) revealNextPage();
  }, { rootMargin: '500px' }).observe(sentinel);
}

function showLoadError() {
  const resultCounter = document.getElementById('resultCounter');
  if (resultCounter) resultCounter.textContent = '型錄載入失敗';

  const grid = document.getElementById('grid');
  if (!grid) return;
  const error = document.createElement('div');
  error.className = 'empty-state';
  error.innerHTML = '<span>LOAD ERROR</span><h2>無法載入商品型錄</h2><p>請透過網站伺服器開啟頁面，或稍後重新整理。</p>';
  grid.appendChild(error);
}

function escapeHtml(value) {
  return String(value ?? '')
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#039;');
}
