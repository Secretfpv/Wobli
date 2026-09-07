// Shared local API helpers. Credentials remain in HttpOnly server cookies.
const commerce = { admin: null, customer: null };
const vehicleNames = { car: 'Car', moto: 'Motorcycle', scooter: 'Scooter / Vespa', escooter: 'E-scooter', bike: 'Bike / E-bike', other: 'Other' };
const categoryNames = { mounts: 'Mounts & adapters', electronics: 'Power & electronics', storage: 'Storage & utility', care: 'Detailing & care' };
const money = cents => new Intl.NumberFormat('en-CH', { style: 'currency', currency: 'CHF' }).format(cents / 100);

async function api(path, options = {}) {
  const headers = new Headers(options.headers || {});
  if (options.body && !(options.body instanceof Blob)) headers.set('Content-Type', 'application/json');
  const account = commerce.admin || commerce.customer;
  if (account && options.method && options.method !== 'GET') headers.set('X-CSRF-Token', account.csrf);
  let response;
  try { response = await fetch(path, { ...options, headers, credentials: 'same-origin', cache: 'no-store' }); }
  catch { throw new Error('The shop server is unavailable. Start the local shop server and try again.'); }
  let data;
  try { data = await response.json(); }
  catch { throw new Error('Open this website through the shop server on port 8082.'); }
  if (!response.ok) {
    const error = new Error(data.error || 'The request could not be completed.');
    error.status = response.status;
    if (response.status === 403 && commerce.admin && path.startsWith('/api/admin/') &&
        ['Sign in as an administrator first.', 'Security token expired. Sign in again.'].includes(data.error)) {
      commerce.admin = null;
      document.dispatchEvent(new Event('admin-session-lost'));
    }
    throw error;
  }
  return data;
}

function element(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}
function decorateButtons(root = document) {
  root.querySelectorAll('button:not(.led-button):not(.product-card-open)').forEach(button => {
    if (button.closest('footer') || button.classList.contains('cart-product-link') || button.classList.contains('description-toggle')) return;
    if (['forgotPassword', 'togglePassword', 'adminAccess'].includes(button.id)) return;
    button.classList.add('led-button');
    ['button-led-halo', 'button-led-core'].forEach(name => {
      const span = element('span', name); span.setAttribute('aria-hidden', 'true'); button.append(span);
    });
  });
}
function actionButton(text, className, handler) {
  const button = element('button', className, text); button.type = 'button';
  button.addEventListener('click', handler); return button;
}
function setMessage(id, message, error = false) {
  const node = document.getElementById(id); node.textContent = message; node.classList.toggle('is-error', error);
}

function updateGlobalAccountBadge(count = 0) {
  const badge = document.getElementById('globalAccountBadge');
  const total = Number.isInteger(count) && count > 0 ? count : 0;
  badge.textContent = total;
  badge.hidden = !(commerce.admin || commerce.customer) || !total;
  badge.setAttribute('aria-label', `${total} notification${total === 1 ? '' : 's'} waiting`);
}

async function refreshAccountNotifications() {
  if (!(commerce.admin || commerce.customer)) { updateGlobalAccountBadge(0); return; }
  try {
    const data = await api('/api/account/notifications');
    if (commerce.admin || commerce.customer) updateGlobalAccountBadge(data.total);
  } catch { /* Keep the current count during a temporary connection problem. */ }
}

setInterval(() => { if (!document.hidden) refreshAccountNotifications(); }, 30000);

function alignFormStatus(status) {
  if (!status || status.closest('.action-status-row')) return;
  const previous = status.previousElementSibling;
  if (!previous) return;
  if (previous.matches('button')) {
    const row = element('div', 'action-status-row');
    previous.before(row); row.append(previous, status);
  } else if (previous.matches('.actions,.editor-actions')) {
    previous.classList.add('action-status-row'); previous.append(status);
  }
}
document.querySelectorAll('form > .commerce-status,form > [role="status"]').forEach(alignFormStatus);
