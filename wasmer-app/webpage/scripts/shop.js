// The server owns product visibility, price and availability.
let shopProducts = [];
let shopLoadVersion = 0;
async function loadShop() {
  const version = ++shopLoadVersion;
  try {
    const [data, catalogue] = await Promise.all([api('/api/products'), api('/api/categories')]);
    if (version !== shopLoadVersion) return;
    applyCategories(catalogue.categories);
    shopProducts = data.products;
    renderShop();
    setMessage('shopMessage', '');
  } catch (error) {
    if (version !== shopLoadVersion) return;
    setMessage('shopMessage', error.message, true);
  }
}
function productAvailabilityKey(product) {
  return product.availability === 'concept' ? 'coming-soon' : product.availability === 'preorder' ? 'preorder' : product.stock > 0 ? 'in-stock' : 'out-of-stock';
}
function selectedShopFilters(name) {
  const checked = [...document.querySelectorAll(`[name="${name}"]:checked`)].map(input => input.value);
  return checked.includes('all') || !checked.length ? null : new Set(checked);
}
function bindShopFilter(input) {
  input.addEventListener('change', () => {
    const group = [...document.querySelectorAll(`[name="${input.name}"]`)];
    const all = group.find(option => option.value === 'all');
    if (input.value === 'all' && input.checked) group.forEach(option => { if (option !== input) option.checked = false; });
    else if (input.checked && all) all.checked = false;
    if (!group.some(option => option.checked) && all) all.checked = true;
    renderShop();
  });
}
function renderShop() {
  const categories = selectedShopFilters('shopCategory');
  const availability = selectedShopFilters('shopAvailability');
  const products = shopProducts.filter(p => (!categories || categories.has(p.category)) && (!availability || availability.has(productAvailabilityKey(p))));
  document.getElementById('shopResultsTitle').textContent = !categories && !availability ? 'All products' : 'Your selection';
  document.getElementById('shopCount').textContent = `${products.length} product${products.length === 1 ? '' : 's'}`;
  document.getElementById('shopEmpty').hidden = products.length > 0;
  const grid = document.getElementById('shopGrid');
  grid.replaceChildren();
  products.forEach(product => {
    const card = element('article', 'card shop-card');
    card.dataset.availability = productAvailabilityKey(product);
    const link = actionButton('', 'product-card-open', () => openProduct(product));
    link.setAttribute('aria-label', `View ${product.name}`);
    const images = productPhotos(product);
    const art = element('div', 'product-card-image');
    if (images.length) {
      const image = element('img', 'shop-product-image'); image.src = images[0]; image.alt = product.name; image.loading = 'lazy'; art.append(image);
      art.append(element('span', 'product-image-count', `1/${images.length}`));
    } else art.append(element('div', 'shop-product-art', 'Image coming soon'));
    const body = element('div', 'card-body');
    body.append(element('h3', '', product.name), element('span', 'product-availability', availabilityLabel(product)), element('div', 'product-price', product.price_cents === null ? 'Price coming soon' : money(product.price_cents)));
    link.append(art, body);
    const actions = element('div', 'shop-card-actions');
    const canBuy = product.availability !== 'concept' && product.price_cents !== null && (product.availability === 'preorder' || product.stock > 0);
    const buy = actionButton(canBuy ? 'Add to cart ↗' : 'Ask a question', 'btn primary', () => canBuy ? addToCart(product.id) : askProductQuestion(product));
    actions.append(buy); card.append(link, actions); grid.append(card);
  });
  decorateButtons(grid);
}
function productPhotos(product) { return product.images || (product.image ? [product.image] : []); }
function availabilityLabel(product) { return product.availability === 'concept' ? 'Coming soon' : product.availability === 'preorder' ? 'Preorder' : product.stock > 0 ? 'In stock' : 'Out of stock'; }
const productDialog = document.getElementById('productDialog');
let galleryImages = [], galleryIndex = 0, galleryName = '', productFocus = null;
function renderProductGallery() {
  const gallery = document.getElementById('productGallery'); gallery.replaceChildren();
  if (galleryImages.length) {
    const image = element('img'); image.src = galleryImages[galleryIndex]; image.alt = `${galleryName} — image ${galleryIndex + 1}`; gallery.append(image);
  } else gallery.append(element('p', 'commerce-help', 'Images coming soon'));
  document.getElementById('productImageCounter').textContent = galleryImages.length ? `${galleryIndex + 1}/${galleryImages.length}` : 'No images yet';
  document.getElementById('previousProductImage').disabled = galleryImages.length < 2;
  document.getElementById('nextProductImage').disabled = galleryImages.length < 2;
}
function moveProductImage(direction) {
  if (galleryImages.length < 2) return;
  galleryIndex = (galleryIndex + direction + galleryImages.length) % galleryImages.length; renderProductGallery();
}
function openProduct(product) {
  productFocus = document.activeElement; galleryImages = productPhotos(product); galleryIndex = 0; galleryName = product.name;
  renderProductGallery();
  const details = document.getElementById('productDetails'); details.replaceChildren();
  const title = element('h2', '', product.name); title.id = 'productDialogTitle';
  const descriptionWrap = element('div', 'product-description-wrap');
  const description = element('p', 'product-full-description', product.description || 'More details coming soon.');
  descriptionWrap.append(description);
  if (product.description) {
    descriptionWrap.classList.add('is-collapsed');
    const more = actionButton('Show full description', 'description-toggle description-more', () => {
      descriptionWrap.classList.remove('is-collapsed'); more.hidden = true; less.hidden = false; less.focus();
    });
    const less = actionButton('Show less', 'description-toggle description-less', () => {
      descriptionWrap.classList.add('is-collapsed'); less.hidden = true; more.hidden = false; more.focus();
    });
    less.hidden = true; descriptionWrap.append(more, less);
  }
  details.append(element('div', 'eyebrow', categoryNames[product.category]), title,
    element('span', 'pill', availabilityLabel(product)), element('div', 'product-price', product.price_cents === null ? 'Price coming soon' : money(product.price_cents)),
    descriptionWrap,
    element('p', 'commerce-help', `SKU: ${product.sku}`));
  if (product.availability === 'preorder') details.append(element('p', 'product-delivery', `Estimated delivery: ${product.lead_time}`));
  const canBuy = product.availability !== 'concept' && product.price_cents !== null && (product.availability === 'preorder' || product.stock > 0);
  const status = element('p', 'commerce-status'); status.setAttribute('role', 'status');
  const buy = actionButton(canBuy ? 'Add to cart ↗' : availabilityLabel(product), 'btn primary', () => {
    addToCart(product.id); status.textContent = document.getElementById('shopMessage').textContent;
    status.classList.toggle('is-error', document.getElementById('shopMessage').classList.contains('is-error'));
  });
  buy.disabled = !canBuy;
  const ask = actionButton('Ask a question', 'btn', () => askProductQuestion(product));
  const note = element('p', 'commerce-help question-login-note', commerce.admin || commerce.customer ? '' : 'You need to be logged in to ask a question.');
  const actions = element('div', 'product-detail-actions');
  if (canBuy) actions.append(buy);
  else ask.classList.add('primary');
  actions.append(ask);
  actions.classList.add('action-status-row'); actions.append(status);
  details.append(actions, note); decorateButtons(details);
  productDialog.dataset.availability = productAvailabilityKey(product);
  productDialog.showModal(); document.body.style.overflow = 'hidden';
  // Measure rendered lines after the dialog becomes visible. Character count
  // cannot detect descriptions made from many short lines.
  const descriptionBox = details.querySelector('.product-description-wrap.is-collapsed');
  if (descriptionBox) {
    const text = descriptionBox.querySelector('.product-full-description');
    if (text.scrollHeight <= text.clientHeight + 2) {
      descriptionBox.classList.remove('is-collapsed');
      descriptionBox.querySelectorAll('.description-toggle').forEach(button => button.remove());
    }
  }
}
document.getElementById('previousProductImage').onclick = () => moveProductImage(-1);
document.getElementById('nextProductImage').onclick = () => moveProductImage(1);
document.getElementById('closeProductDialog').onclick = () => productDialog.close();
productDialog.addEventListener('keydown', event => {
  if (event.key === 'ArrowLeft' || event.key === 'ArrowRight') { event.preventDefault(); moveProductImage(event.key === 'ArrowLeft' ? -1 : 1); }
});
productDialog.addEventListener('click', event => {
  if (event.target !== productDialog) return;
  const rect = productDialog.getBoundingClientRect();
  if (event.clientX < rect.left || event.clientX > rect.right || event.clientY < rect.top || event.clientY > rect.bottom) productDialog.close();
});
productDialog.addEventListener('close', () => {
  document.body.style.overflow = '';
  if (productFocus && productFocus.isConnected) productFocus.focus();
});
document.querySelectorAll('[name="shopCategory"],[name="shopAvailability"]').forEach(bindShopFilter);
document.getElementById('resetShopFilters').onclick = () => {
  for (const name of ['shopCategory','shopAvailability']) {
    document.querySelectorAll(`[name="${name}"]`).forEach(input => { input.checked = input.value === 'all'; });
  }
  renderShop();
};
loadShop();
const preorderDialog=document.getElementById("preorderDialog");
let preorderSeen=false;
try{preorderSeen=localStorage.getItem("wobli-preorder-intro-v1")==="seen"}catch{}
let preorderFocus=null;
function showPreorder(){preorderFocus=document.activeElement;if(!preorderDialog.open){preorderDialog.showModal();document.body.style.overflow="hidden"}}
function maybeShowPreorder(){if(!preorderSeen)showPreorder()}
function rememberPreorder(){preorderSeen=true;try{localStorage.setItem("wobli-preorder-intro-v1","seen")}catch{}}
// Any click on the notice or its backdrop dismisses it; button actions run first.
preorderDialog.addEventListener("click",()=>{if(preorderDialog.open)preorderDialog.close()});
preorderDialog.addEventListener("close",()=>{rememberPreorder();document.body.style.overflow="";if(document.getElementById("view-shop").classList.contains("active")&&preorderFocus)preorderFocus.focus()});
document.getElementById("closePreorder").onclick=()=>preorderDialog.close();
document.getElementById("browsePreorders").onclick=()=>preorderDialog.close();
document.getElementById("preorderInfo").onclick=showPreorder;
document.getElementById("suggestPreorder").onclick=()=>{preorderDialog.close();openView("custom");const heading=document.querySelector("#view-custom h2");heading.tabIndex=-1;heading.focus({preventScroll:true})};

const questionDialog = document.getElementById('questionDialog');
const questionForm = document.getElementById('questionForm');
let questionProduct = null, questionRequestId = null, questionSending = false;
let questionThanksTimer;
function finishQuestionThanks() {
  if (questionDialog.open && questionDialog.classList.contains('question-success')) questionDialog.close();
}
function flashQuestionLock() {
  if (!questionDialog.open || !questionDialog.classList.contains('question-success') || questionDialog.classList.contains('question-lock')) return;
  clearTimeout(questionThanksTimer);
  questionDialog.classList.add('question-lock');
  questionThanksTimer = setTimeout(finishQuestionThanks, 1500);
}
questionDialog.addEventListener('animationend', event => {
  if (event.target !== questionDialog || event.pseudoElement !== '::before') return;
  if (event.animationName === 'sectionLedSweep') flashQuestionLock();
  if (event.animationName === 'questionLockFlash') finishQuestionThanks();
});
questionDialog.addEventListener('close', () => {
  clearTimeout(questionThanksTimer);
  questionDialog.classList.remove('question-success', 'question-lock');
});
function askProductQuestion(product) {
  const resume = () => {
    questionDialog.dataset.availability = productAvailabilityKey(product);
    if (!productDialog.open) openProduct(product);
    const note = document.querySelector('.question-login-note'); if (note) note.textContent = '';
    if (!questionProduct || questionProduct.id !== product.id) { questionForm.reset(); questionRequestId = crypto.randomUUID(); }
    questionProduct = product;
    questionForm.hidden = false;
    document.getElementById('questionThanks').hidden = true;
    document.getElementById('questionEyebrow').hidden = false;
    document.getElementById('questionProductName').hidden = false;
    document.getElementById('questionTitle').textContent = 'Ask us about it.';
    document.getElementById('questionProductName').textContent = product.name;
    setMessage('questionStatus', ''); questionDialog.showModal(); document.body.style.overflow = 'hidden';
    document.getElementById('questionMessage').focus();
  };
  if (!commerce.admin && !commerce.customer) loginForQuestion(resume); else resume();
}
document.getElementById('closeQuestion').onclick = () => { if (!questionSending) questionDialog.close(); };
questionDialog.addEventListener('cancel', event => { if (questionSending) event.preventDefault(); });
questionDialog.addEventListener('close', () => { document.body.style.overflow = document.querySelector('dialog[open]') ? 'hidden' : ''; });
questionForm.addEventListener('submit', async event => {
  event.preventDefault(); if (questionSending || !questionProduct) return;
  const message = document.getElementById('questionMessage').value.trim();
  if (!message) { setMessage('questionStatus', 'Please write your question.', true); return; }
  const button = document.getElementById('sendQuestion'); questionSending = true; button.disabled = true;
  setMessage('questionStatus', 'Sending your question…');
  try {
    await api('/api/questions', {method:'POST',body:JSON.stringify({product_id:questionProduct.id,message,request_id:questionRequestId})});
    questionForm.hidden = true;
    document.getElementById('questionEyebrow').hidden = true;
    document.getElementById('questionProductName').hidden = true;
    document.getElementById('questionTitle').textContent = 'Thank you!';
    document.getElementById('questionThanks').hidden = false;
    document.getElementById('questionTitle').focus();
    questionDialog.classList.add('question-success');
    // Fallback advances the sequence if animation events are unavailable.
    questionThanksTimer = setTimeout(flashQuestionLock, 2100);
    questionForm.reset(); questionRequestId = crypto.randomUUID();
  } catch(error) {
    if (error.status === 403) {
      commerce.customer=null; commerce.admin=null; adminUI();
      questionDialog.addEventListener('close', () => loginForQuestion(() => askProductQuestion(questionProduct)), {once:true}); questionDialog.close();
    } else setMessage('questionStatus', error.message, true);
  } finally { questionSending=false; button.disabled=false; }
});
