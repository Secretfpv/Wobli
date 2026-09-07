// Only product IDs and quantities are kept locally. Totals always come from the server.
const CART_KEY = 'wobli-cart-v1';
let cart = [];
try {
  const value = JSON.parse(localStorage.getItem(CART_KEY) || '[]');
  if (Array.isArray(value)) {
    const unique = new Map();
    value.slice(0, 100).forEach(item => {
      if (item && /^[a-f0-9]{32}$/.test(item.id) && Number.isInteger(item.quantity) && item.quantity >= 1 && item.quantity <= 99) unique.set(item.id, { id: item.id, quantity: item.quantity });
    });
    cart = [...unique.values()];
  }
} catch { /* A blocked or invalid local store must not break the shop. */ }
let quoteVersion = 0;
function saveCart() {
  try { localStorage.setItem(CART_KEY, JSON.stringify(cart)); } catch { /* The cart still works for this visit. */ }
  document.getElementById('cartBadge').textContent = cart.reduce((count, item) => count + item.quantity, 0);
}
function addToCart(id) {
  const product = shopProducts.find(p => p.id === id);
  if (!product || product.availability === 'concept' || product.price_cents === null) return;
  const existing = cart.find(item => item.id === id);
  const quantity = existing ? existing.quantity + 1 : 1;
  if (quantity > 99 || (product.availability === 'stock' && quantity > product.stock)) {
    setMessage('shopMessage', 'You have reached the available quantity for this item.', true); return;
  }
  if (!existing && cart.length >= 100) { setMessage('shopMessage', 'The cart is full. Remove an item before adding another.', true); return; }
  if (existing) existing.quantity = quantity;
  else cart.push({ id, quantity });
  saveCart();
  setMessage('shopMessage', `${product.name} added to your cart.`);
}
function removeCartItem(id) {
  cart = cart.filter(item => item.id !== id); saveCart(); renderCart();
}
async function renderCart() {
  const version = ++quoteVersion;
  const container = document.getElementById('cartItems');
  if (!cart.length) {
    container.replaceChildren();
    const empty = element('div', 'cart-empty');
    empty.append(element('h3', '', 'Your next build starts here.'), element('p', '', 'Your cart is empty. Explore the collection to add an upgrade.'), actionButton('Explore the shop ↗', 'btn primary', () => openView('shop')));
    container.append(empty); decorateButtons(container);
    document.getElementById('cartTotal').textContent = money(0); setMessage('cartStatus', '');
    if(typeof setCheckoutQuote==='function')setCheckoutQuote(null);return;
  }
  setMessage('cartStatus', 'Checking current prices and availability…');
  document.getElementById('cartTotal').textContent = '—';
  try {
    const quote = await api('/api/cart/quote', { method: 'POST', body: JSON.stringify({ items: cart }) });
    if (version !== quoteVersion) return;
    container.replaceChildren();
    quote.lines.forEach(line => {
      const product = line.product;
      const row = element('article', 'cart-line');
      const image = product && product.image ? element('img', 'cart-thumb') : element('div', 'cart-thumb');
      if (product && product.image) { image.src = product.image; image.alt = product.name; }
      const details = element('div');
      const heading = element('h3');
      let thumbnail = image;
      if (product) {
        const open = () => openProduct(product);
        const imageButton = actionButton('', 'cart-product-link cart-image-link', open);
        imageButton.setAttribute('aria-label', `View ${product.name}`);
        imageButton.append(image); thumbnail = imageButton;
        heading.append(actionButton(product.name, 'cart-product-link cart-name-link', open));
      } else heading.textContent = 'Unavailable product';
      details.append(heading);
      if (product && product.price_cents !== null) details.append(element('p', '', `${money(product.price_cents)} each`));
      if (product && product.availability === 'preorder') details.append(element('p', 'product-delivery', `Preorder · ${product.lead_time}`));
      if (line.issue) details.append(element('p', 'is-error', line.issue));
      const controls = element('div', 'cart-controls');
      const label = element('label', 'commerce-field', 'Quantity');
      const quantity = element('input', 'cart-quantity');
      quantity.type = 'number'; quantity.min = '1'; quantity.max = '99'; quantity.step = '1'; quantity.value = line.quantity;
      quantity.setAttribute('aria-label', `Quantity for ${product ? product.name : 'unavailable product'}`);
      quantity.addEventListener('input', () => {
        const value = Number(quantity.value);
        if (!Number.isInteger(value) || value < 1 || value > 99) return;
        const item = cart.find(item => item.id === line.id);
        if (item) item.quantity = value;
        saveCart();
        document.getElementById('cartTotal').textContent = '—';
        setMessage('cartStatus', 'Finish editing quantity to refresh the subtotal.');
      });
      quantity.addEventListener('change', () => renderCart());
      label.append(quantity); controls.append(label, actionButton('Remove', 'cart-remove', () => removeCartItem(line.id)));
      details.append(controls); row.append(thumbnail, details, element('strong', '', line.issue ? '—' : money(line.line_total_cents))); container.append(row);
    });
    document.getElementById('cartTotal').textContent = money(quote.subtotal_cents);
    setMessage('cartStatus', quote.lines.some(line => line.issue) ? 'Some items need attention and are excluded from the subtotal.' : 'Prices and availability are up to date.', quote.lines.some(line => line.issue));
    if(typeof setCheckoutQuote==='function')setCheckoutQuote(quote);
    decorateButtons(container);
  } catch (error) {
    if (version !== quoteVersion) return;
    container.replaceChildren(element('p', 'commerce-help', 'Your items remain saved on this device. Reconnect to the shop server to see the current cart.'));
    setMessage('cartStatus', error.message, true);
    if(typeof setCheckoutQuote==='function')setCheckoutQuote(null);
  }
}
saveCart();
window.addEventListener('storage', event => {
  if (event.key === CART_KEY) location.reload();
});
