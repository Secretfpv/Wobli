// Admin UI. Every read/write is independently authenticated by the backend.
const productForm = document.getElementById('productForm');
let adminProducts = [];
let editingProduct = null;
let productImages = [];
let imagePreviewURLs = [];
let productDirty = false;
let savingProduct = false;
const adminAttentionCounts = {adminMessagesBadge:0, adminCustomLabBadge:0, adminInstallationsBadge:0,adminOrdersBadge:0};
function updateAdminBadge(id, count, label) {
  const badge=document.getElementById(id); badge.textContent=count; badge.hidden=!count;
  badge.setAttribute('aria-label',`${count} ${label} needing attention`);
  adminAttentionCounts[id] = count;
  if (commerce.admin) updateGlobalAccountBadge(Object.values(adminAttentionCounts).reduce((total, value) => total + value, 0));
}

// Switching workspaces preserves unsaved form values in their existing panels.
function adminSection(name) {
  ['products', 'categories', 'orders', 'messages', 'custom-lab', 'installations', 'security'].forEach(section => {
    document.getElementById('admin-section-' + section).hidden = section !== name;
  });
  document.querySelectorAll('[data-admin-section]').forEach(button => {
    if (button.dataset.adminSection === name) button.setAttribute('aria-current', 'page');
    else button.removeAttribute('aria-current');
  });
  if(name==='orders')loadAdminOrders();
}
document.querySelectorAll('[data-admin-section]').forEach(button => {
  button.addEventListener('click', () => adminSection(button.dataset.adminSection));
});

function adminUI() {
  document.getElementById('adminTab').hidden = !commerce.admin;
  document.getElementById('accountLabel').textContent = commerce.admin ? commerce.admin.username : commerce.customer ? (commerce.customer.name || commerce.customer.username) : 'Log in';
  if (!(commerce.admin || commerce.customer)) updateGlobalAccountBadge(0);
}
function openAdminLogin() {
  if (commerce.admin) { openView('admin'); return; }
  if (commerce.customer) { showCustomerAccount(); return; }
  setAuthMode('login');
  accountModal.showModal(); document.body.style.overflow = 'hidden';
  document.getElementById('authEmail').focus();
}
function forgetAdmin() {
  ['adminMessagesBadge','adminCustomLabBadge','adminInstallationsBadge','adminOrdersBadge'].forEach(id=>updateAdminBadge(id,0,''));
  adminMessagesLoadVersion++; adminMessageThreads = []; selectedAdminClient = null; selectedAdminThread = null; adminMessageDrafts.clear();
  document.getElementById('adminQuestions').replaceChildren();
  commerce.admin = null; adminProducts = []; productDirty = false; editingProduct = null;
  document.getElementById('adminProducts').replaceChildren();
  document.getElementById('adminStats').replaceChildren();
  productForm.reset(); productImages = []; updateImagePreview(); adminUI();
  if (document.getElementById('view-admin').classList.contains('active')) openView('shop');
}
document.addEventListener('admin-session-lost', forgetAdmin);
document.getElementById('adminLogout').addEventListener('click', async () => {
  if (!confirmDiscard()) return;
  try { await api('/api/admin/logout', { method: 'POST', body: '{}' }); forgetAdmin(); }
  catch (error) { setMessage('adminStatus', error.message, true); }
});
async function restoreAdmin() {
  try { const account = (await api('/api/account/session')).account; commerce.admin = account && account.role === 'admin' ? account : null; commerce.customer = account && account.role === 'customer' ? account : null; adminUI(); await refreshAccountNotifications(); }
  catch { adminUI(); }
  finally { document.dispatchEvent(new Event('account-session-restored')); }
}
async function loadAdminProducts() {
  if (!commerce.admin) return;
  try {
    const [products, catalogue] = await Promise.all([api('/api/admin/products'), api('/api/categories')]);
    adminProducts = products.products;
    applyCategories(catalogue.categories); renderCategoryManager(catalogue.categories);
    renderAdminList();
    await Promise.all([loadQuestions(), loadInstallations(), loadCustomLabRequests(),loadAdminOrders()]);
    setMessage('adminStatus', '');
  } catch (error) { setMessage('adminStatus', error.message, true); }
}
function renderAdminList() {
  const stats = document.getElementById('adminStats'); stats.replaceChildren();
  [['Products', adminProducts.length], ['Published', adminProducts.filter(p => p.status === 'active').length], ['Drafts', adminProducts.filter(p => p.status === 'draft').length]].forEach(([label, count]) => {
    const tile = element('div', 'admin-stat'); tile.append(element('span', '', label), element('strong', '', count)); stats.append(tile);
  });
  const search = document.getElementById('adminSearch').value.toLowerCase().trim();
  const status = document.getElementById('adminFilter').value;
  const list = document.getElementById('adminProducts'); list.replaceChildren();
  const products = adminProducts.filter(p => (status === 'all' || p.status === status) && `${p.name} ${p.sku}`.toLowerCase().includes(search));
  if (!products.length) list.append(element('p', 'commerce-help', 'No matching products. Add a product or clear the search.'));
  products.forEach(product => {
    const button = actionButton('', 'admin-product-row', () => {
      if (savingProduct || !confirmDiscard()) return;
      fillProduct(product);
    });
    button.classList.toggle('selected', editingProduct && product.id === editingProduct.id);
    button.setAttribute('aria-label', `Edit ${product.name}`);
    button.append(element('strong', '', product.name), element('small', '', `${product.sku} · ${product.status === 'active' ? 'Published' : product.status} · ${product.price_cents === null ? 'No price' : money(product.price_cents)}`));
    list.append(button);
  });
  decorateButtons(list);
}
function confirmDiscard() {
  return !productDirty || window.confirm('Discard unsaved product changes?');
}
function updateImagePreview() {
  imagePreviewURLs.forEach(url => URL.revokeObjectURL(url)); imagePreviewURLs = [];
  const preview = document.getElementById('adminImagePreview'); preview.replaceChildren();
  if (!productImages.length) { preview.textContent = 'No images yet'; return; }
  productImages.forEach((source, index) => {
    const tile = element('div', 'admin-gallery-tile');
    const image = element('img');
    if (source instanceof File) { source = URL.createObjectURL(source); imagePreviewURLs.push(source); }
    image.src = source; image.alt = `Product image ${index + 1}`;
    const remove = actionButton('Remove', 'btn', () => { if (savingProduct) return; productImages.splice(index, 1); productDirty = true; updateImagePreview(); });
    const first = actionButton(index === 0 ? 'Cover image' : 'Make cover', 'btn', () => { if (savingProduct) return; productImages.unshift(productImages.splice(index, 1)[0]); productDirty = true; updateImagePreview(); });
    first.disabled = index === 0;
    tile.append(image, first, remove); preview.append(tile);
  });
  decorateButtons(preview);
}
function syncProductRequirements() {
  const availability = productForm.elements.availability.value;
  productForm.elements.price.required = availability !== 'concept';
  productForm.elements.lead_time.required = availability === 'preorder';
  productForm.elements.stock.disabled = availability !== 'stock';
}
function fillProduct(product = null) {
  editingProduct = product ? { ...product } : null;
  productForm.reset(); productImages = product ? [...(product.images || (product.image ? [product.image] : []))] : [];
  if (product) {
    ['name', 'sku', 'description', 'category', 'status', 'availability', 'lead_time', 'stock'].forEach(key => { productForm.elements[key].value = product[key]; });
    productForm.elements.admin_comment.value = product.admin_comment || '';
    productForm.elements.price.value = product.price_cents === null ? '' : (product.price_cents / 100).toFixed(2);
    productForm.querySelectorAll('[name="vehicle"]').forEach(input => { input.checked = product.vehicle.includes(input.value); });
  }
  document.getElementById('editorTitle').textContent = product ? 'Edit product' : 'Add a product';
  document.getElementById('editorRevision').textContent = product ? `Revision ${product.revision}` : 'New draft';
  document.getElementById('archiveProduct').hidden = !product || product.status === 'archived';
  productDirty = false; setMessage('productStatus', ''); syncProductRequirements(); updateImagePreview(); renderAdminList();
}
productForm.addEventListener('input', () => { productDirty = true; });
document.getElementById('productAvailability').addEventListener('change', syncProductRequirements);
document.getElementById('adminSearch').addEventListener('input', renderAdminList);
document.getElementById('adminFilter').addEventListener('change', renderAdminList);
document.getElementById('newProduct').addEventListener('click', () => { if (!savingProduct && confirmDiscard()) fillProduct(); });
document.getElementById('resetProduct').addEventListener('click', () => { if (!savingProduct && confirmDiscard()) fillProduct(editingProduct); });
document.getElementById('productImage').addEventListener('change', event => {
  const files = [...event.target.files];
  if (productImages.length + files.length > 12 || files.some(file => !['image/png', 'image/jpeg', 'image/webp'].includes(file.type) || file.size > 5 * 1024 * 1024)) {
    setMessage('productStatus', 'Choose up to 12 images, PNG/JPEG/WebP, each smaller than 5 MB.', true); event.target.value = ''; return;
  }
  productImages.push(...files); event.target.value = ''; productDirty = true; updateImagePreview();
});
document.getElementById('removeProductImage').addEventListener('click', () => {
  if (savingProduct) return;
  productImages = []; document.getElementById('productImage').value = ''; productDirty = true; updateImagePreview();
});
function productPayload() {
  const form = productForm.elements;
  const vehicle = [...productForm.querySelectorAll('[name="vehicle"]:checked')].map(input => input.value);
  if (!vehicle.length) throw new Error('Choose at least one compatible vehicle.');
  const price = form.price.value.trim();
  return {
    name: form.name.value.trim(), sku: form.sku.value.trim(), description: form.description.value.trim(),
    admin_comment: form.admin_comment.value.trim(),
    category: form.category.value, status: form.status.value, availability: form.availability.value,
    lead_time: form.lead_time.value.trim(), stock: Number(form.stock.value || 0),
    price_cents: price ? Math.round(Number(price) * 100) : null,
    images: productImages.filter(image => typeof image === 'string'), vehicle, revision: editingProduct ? editingProduct.revision : undefined,
  };
}
productForm.addEventListener('submit', async event => {
  event.preventDefault();
  if (savingProduct) return;
  let payload;
  try { payload = productPayload(); } catch (error) { setMessage('productStatus', error.message, true); return; }
  const id = editingProduct ? editingProduct.id : null;
  savingProduct = true;
  const controls = [...productForm.querySelectorAll('input,select,textarea,button')];
  controls.forEach(control => { control.dataset.wasDisabled = String(control.disabled); control.disabled = true; });
  document.getElementById('newProduct').disabled = true;
  setMessage('productStatus', 'Saving product…');
  try {
    for (let index = 0; index < productImages.length; index++) {
      const file = productImages[index];
      if (!(file instanceof File)) continue;
      const upload = await api('/api/admin/upload', { method: 'POST', headers: { 'Content-Type': file.type }, body: file });
      productImages[index] = upload.image;
    }
    payload.images = [...productImages];
    payload.image = payload.images[0] || '';
    const result = await api(id ? `/api/admin/products/${id}` : '/api/admin/products', { method: id ? 'PUT' : 'POST', body: JSON.stringify(payload) });
    productDirty = false;
    await loadAdminProducts(); fillProduct(result.product); await loadShop();
    setMessage('productStatus', result.product.status === 'active' ? 'Saved and published to the shop.' : 'Saved. This product is hidden from customers.');
  } catch (error) { setMessage('productStatus', error.message, true); }
  finally {
    savingProduct = false;
    controls.forEach(control => { control.disabled = control.dataset.wasDisabled === 'true'; delete control.dataset.wasDisabled; });
    document.getElementById('newProduct').disabled = false; syncProductRequirements();
  }
});
document.getElementById('archiveProduct').addEventListener('click', () => {
  if (!editingProduct || savingProduct) return;
  productForm.elements.status.value = 'archived'; productDirty = true; productForm.requestSubmit();
});
document.getElementById('adminPasswordForm').addEventListener('submit', async event => {
  event.preventDefault(); const form = event.currentTarget; const button = form.querySelector('button'); button.disabled = true;
  try {
    await api('/api/admin/password', { method: 'POST', body: JSON.stringify({ current: form.elements.current.value, new: form.elements.new.value }) });
    form.reset(); forgetAdmin(); openAdminLogin(); authStatus.textContent = 'Password updated. Sign in with your new password.';
  } catch (error) { document.getElementById('passwordStatus').textContent = error.message; }
  finally { button.disabled = false; form.elements.current.value = ''; form.elements.new.value = ''; }
});
window.addEventListener('beforeunload', event => { if (productDirty) { event.preventDefault(); event.returnValue = ''; } });
decorateButtons(); syncProductRequirements(); restoreAdmin();

let adminMessageThreads = [];
let selectedAdminClient = null;
let selectedAdminThread = null;
const adminMessageDrafts = new Map();
let adminMessagesLoadVersion = 0;
const adminMessageNeedsAttention = thread => !thread.admin_read && (!thread.replies.length || thread.replies.at(-1).sender === 'customer');
async function loadQuestions() {
  const version = ++adminMessagesLoadVersion;
  try {
    const data = await api('/api/admin/questions');
    if (version !== adminMessagesLoadVersion || !commerce.admin) return;
    adminMessageThreads = data.questions;
    updateAdminBadge('adminMessagesBadge',adminMessageThreads.filter(adminMessageNeedsAttention).length,'message conversations');
    renderAdminMessages();
  } catch(error) { if (version === adminMessagesLoadVersion) setMessage('adminStatus', error.message, true); }
}
function renderAdminMessages() {
  const container = document.getElementById('adminQuestions'); container.replaceChildren();
  const latest = thread => Math.max(thread.created, ...thread.replies.map(reply => reply.created));
  const clients = [...new Set(adminMessageThreads.map(thread => thread.author))];
  if (!clients.includes(selectedAdminClient)) { selectedAdminClient = null; selectedAdminThread = null; }
  const threads = adminMessageThreads.filter(thread => thread.author === selectedAdminClient).sort((a,b) => latest(b)-latest(a));
  const question = threads.find(thread => thread.id === selectedAdminThread);
  if (!question) selectedAdminThread = null;
  function navigate(client, thread = null) {
    selectedAdminClient = client; selectedAdminThread = thread;
    if (thread) {
      const opened=adminMessageThreads.find(item=>item.id===thread);
      if(opened&&adminMessageNeedsAttention(opened)){opened.admin_read=true;updateAdminBadge('adminMessagesBadge',adminMessageThreads.filter(adminMessageNeedsAttention).length,'message conversations');api(`/api/admin/questions/${thread}/read`,{method:'POST',body:'{}'}).catch(()=>{opened.admin_read=false;updateAdminBadge('adminMessagesBadge',adminMessageThreads.filter(adminMessageNeedsAttention).length,'message conversations');renderAdminMessages();});}
    }
    renderAdminMessages();
    container.querySelector('button')?.focus();
  }
  function row(title, subtitle, handler, attentionCount = 0, isNew = false) {
    const button = actionButton('', 'admin-message-row', handler);
    const heading = element('span', 'admin-message-row-heading');
    heading.append(element('strong', '', title));
    if (attentionCount) {
      const badge = element('span', 'reply-badge', String(attentionCount));
      badge.setAttribute('aria-label', `${attentionCount} conversation${attentionCount === 1 ? '' : 's'} needing a reply`);
      heading.append(badge);
    }
    if (isNew) {
      const dot=element('span','new-message-dot');
      dot.setAttribute('aria-label','New message');
      heading.append(dot);
    }
    button.append(heading, element('span', 'commerce-help', subtitle), element('span', 'message-row-arrow', '↗'));
    return button;
  }
  if (!selectedAdminClient) {
    container.append(element('h3', '', 'Clients'));
    if (!clients.length) container.append(element('p', 'commerce-help', 'No customer messages yet.'));
    clients.sort((a,b) => Math.max(...adminMessageThreads.filter(t=>t.author===b).map(latest)) - Math.max(...adminMessageThreads.filter(t=>t.author===a).map(latest)));
    clients.forEach(client => {
      const items = adminMessageThreads.filter(thread => thread.author === client);
      const attentionCount = items.filter(adminMessageNeedsAttention).length;
      container.append(row(client, `${items.length} conversation${items.length === 1 ? '' : 's'} · Latest activity ${new Date(Math.max(...items.map(latest))*1000).toLocaleString()}`, () => navigate(client), attentionCount));
    });
  } else if (!question) {
    container.append(actionButton('← All clients', 'btn', () => navigate(null)), element('h3', '', selectedAdminClient));
    threads.forEach(thread => {
      const button = row(thread.product_name, `${thread.message.slice(0,120)}${thread.message.length > 120 ? '…' : ''} · ${thread.replies.length} replies`, () => navigate(selectedAdminClient, thread.id), 0, adminMessageNeedsAttention(thread));
      const dates = element('span', 'commerce-help conversation-dates', `Started ${new Date(thread.created * 1000).toLocaleString()}`);
      if (thread.replies.length) dates.append(document.createTextNode(` · Last reply ${new Date(latest(thread) * 1000).toLocaleString()}`));
      button.append(dates); container.append(button);
    });
  } else {
    container.append(actionButton('← Client messages', 'btn', () => navigate(selectedAdminClient)), element('p', 'commerce-help', selectedAdminClient));
      const item = element('article', 'admin-question');
      item.append(element('h3', '', question.product_name), element('p', 'commerce-help', `${question.author} · ${new Date(question.created * 1000).toLocaleString()}`), element('p', 'product-full-description', question.message));
      const status = element('p', 'commerce-status'); status.setAttribute('role', 'status');
      const replies = element('div', 'admin-replies');
      function showReply(reply) {
        const block = element('div', 'message-reply');
        block.classList.toggle('customer-reply', reply.sender === 'admin');
        block.append(element('strong', '', reply.sender === 'customer' ? question.author : 'Wobli'), element('p', 'commerce-help', new Date(reply.created * 1000).toLocaleString()), element('p', 'product-full-description', reply.message));
        replies.append(block);
      }
      question.replies.forEach(showReply);
      const form = element('form', 'admin-reply-form');
      const label = element('label', 'commerce-field', 'Reply to this question');
      const input = element('textarea'); input.required = true; input.maxLength = 3000; input.rows = 3;
      label.append(input);
      const send = element('button', 'btn', 'Send reply'); send.type = 'submit';
      const draft = adminMessageDrafts.get(question.id) || {text:'', id:crypto.randomUUID().replaceAll('-', '')};
      input.value = draft.text;
      let requestId = draft.id;
      form.append(label, send);
      form.addEventListener('submit', async event => {
        event.preventDefault(); if (send.disabled) return;
        send.disabled = true; input.disabled = true; status.textContent = 'Sending reply…'; status.classList.remove('is-error');
        const message = input.value;
        try {
          await api(`/api/admin/questions/${question.id}/replies`, {method:'POST', body:JSON.stringify({message, request_id:requestId})});
          const reply = {message, created:Date.now()/1000, sender:'admin'};
          question.replies.push(reply); showReply(reply); input.value = ''; requestId = crypto.randomUUID().replaceAll('-', '');
          question.admin_read=true; updateAdminBadge('adminMessagesBadge',adminMessageThreads.filter(adminMessageNeedsAttention).length,'message conversations');
          adminMessageDrafts.delete(question.id);
          status.textContent = 'Reply sent to the customer’s Messages section.';
        } catch(error) { status.textContent = error.message; status.classList.add('is-error'); }
        finally { send.disabled = false; input.disabled = false; }
      });
      input.addEventListener('input', () => { requestId = crypto.randomUUID().replaceAll('-', ''); adminMessageDrafts.set(question.id, {text:input.value, id:requestId}); });
      const remove = actionButton('Delete question', 'btn danger', async () => {
        if (!window.confirm(`Permanently delete this question about "${question.product_name}"? This cannot be undone.`)) return;
        remove.disabled = true; status.textContent = 'Deleting…';
        try {
          await api(`/api/admin/questions/${question.id}`, { method: 'DELETE' });
          adminMessageThreads = adminMessageThreads.filter(thread => thread.id !== question.id);
          updateAdminBadge('adminMessagesBadge',adminMessageThreads.filter(adminMessageNeedsAttention).length,'message conversations');
          adminMessageDrafts.delete(question.id); selectedAdminThread = null; renderAdminMessages();
        } catch (error) {
          status.textContent = error.message; status.classList.add('is-error'); remove.disabled = false;
        }
      });
      item.append(replies, form, remove, status);
      container.append(item);
  }
  decorateButtons(container);
}
document.getElementById('refreshQuestions').onclick = loadQuestions;

function appendAdminServiceReplies(card, request, endpoint, onSent) {
  const replies=element('div','admin-replies');
  const show=reply=>{const block=element('div','message-reply');block.classList.toggle('customer-reply',reply.sender==='admin');block.append(element('strong','',reply.sender==='customer'?request.email:'Wobli'),element('p','commerce-help',new Date(reply.created*1000).toLocaleString()),element('p','product-full-description',reply.message));replies.append(block);};
  request.replies.forEach(show);
  const form=element('form','admin-reply-form'),field=element('label','commerce-field','Reply to this request'),input=element('textarea');input.required=true;input.maxLength=3000;input.rows=3;field.append(input);
  const send=element('button','btn','Send reply');send.type='submit';form.append(field,send);
  form.onsubmit=async event=>{event.preventDefault();send.disabled=true;input.disabled=true;const message=input.value,requestId=crypto.randomUUID().replaceAll('-','');try{await api(`${endpoint}/${request.id}/replies`,{method:'POST',body:JSON.stringify({message,request_id:requestId})});const reply={id:requestId,message,created:Date.now()/1000,sender:'admin',is_read:0};request.replies.push(reply);show(reply);input.value='';if(request.status==='new')request.status='contacted';onSent();}catch(error){window.alert(error.message);}finally{send.disabled=false;input.disabled=false;}};
  card.append(replies,form);
}

let adminInstallationRequests = [];
let selectedInstallationClient = null;
let selectedInstallationRequest = null;
async function loadInstallations() {
  if (!commerce.admin) return;
  const container = document.getElementById('adminInstallations');
  try { adminInstallationRequests = (await api('/api/admin/installations')).installations; updateAdminBadge('adminInstallationsBadge',adminInstallationRequests.filter(request=>!request.admin_read).length,'installation requests'); renderAdminInstallations(); }
  catch(error) { container.textContent = error.message; }
}
function renderAdminInstallations() {
  const container = document.getElementById('adminInstallations'); container.replaceChildren();
  const clients = [...new Set(adminInstallationRequests.map(request => request.email))];
  if (!clients.includes(selectedInstallationClient)) { selectedInstallationClient = null; selectedInstallationRequest = null; }
  const requests = adminInstallationRequests.filter(request => request.email === selectedInstallationClient);
  const request = requests.find(item => item.id === selectedInstallationRequest);
  function navigate(client, id = null) { selectedInstallationClient = client; selectedInstallationRequest = id;if(id){const opened=adminInstallationRequests.find(item=>item.id===id);if(opened&&!opened.admin_read){opened.admin_read=true;updateAdminBadge('adminInstallationsBadge',adminInstallationRequests.filter(item=>!item.admin_read).length,'installation requests');api(`/api/admin/installations/${id}/read`,{method:'POST',body:'{}'}).catch(()=>{opened.admin_read=false;updateAdminBadge('adminInstallationsBadge',adminInstallationRequests.filter(item=>!item.admin_read).length,'installation requests');renderAdminInstallations();});}}renderAdminInstallations(); }
  function requestRow(item) {
    const button = actionButton('', 'admin-message-row', () => navigate(item.email, item.id));
    const heading=element('span','admin-message-row-heading');heading.append(element('strong','',item.product_name));if(!item.admin_read)heading.append(element('span','new-message-dot'));
    button.append(heading, element('span', 'commerce-help', `${vehicleNames[item.vehicle_type]} · ${item.vehicle_model} · ${item.vehicle_year} · ${new Date(item.created*1000).toLocaleString()} · ${item.status}`), element('span', 'message-row-arrow', '↗'));
    return button;
  }
  if (!selectedInstallationClient) {
    container.append(element('h3', '', 'Clients'));
    if (!clients.length) container.append(element('p', 'commerce-help', 'No installation requests yet.'));
    clients.forEach(client => {
      const items = adminInstallationRequests.filter(item => item.email === client);
      const button = actionButton('', 'admin-message-row', () => navigate(client));
      const heading=element('span','admin-message-row-heading');heading.append(element('strong','',client));const count=items.filter(item=>!item.admin_read).length;if(count)heading.append(element('span','reply-badge',String(count)));
      button.append(heading, element('span', 'commerce-help', `${items.length} request${items.length === 1 ? '' : 's'} · Latest ${new Date(Math.max(...items.map(item=>item.created))*1000).toLocaleString()}`), element('span', 'message-row-arrow', '↗'));
      container.append(button);
    });
  } else if (!request) {
    container.append(actionButton('← All clients', 'btn', () => navigate(null)), element('h3', '', selectedInstallationClient));
    requests.forEach(item => container.append(requestRow(item)));
  } else {
    const card = element('article', 'installation-card');
    const list = document.createElement('dl');
    [['Product',request.product_name],['Vehicle',`${vehicleNames[request.vehicle_type]} · ${request.vehicle_model} · ${request.vehicle_year}`],['Email',request.email],['Submitted',new Date(request.created*1000).toLocaleString()],['Mounting comment',request.comment || 'No comment']].forEach(([term,value]) => list.append(element('dt','',term),element('dd','',value)));
    const label = element('label','commerce-field','Status'); const select = document.createElement('select');
    [['new','New'],['contacted','Contacted'],['scheduled','Scheduled'],['completed','Completed'],['cancelled','Cancelled']].forEach(([value,text]) => { const option=new Option(text,value);select.append(option); }); select.value=request.status; label.append(select);
    const status=element('p','commerce-status');
    select.onchange=async()=>{ select.disabled=true; try { await api(`/api/admin/installations/${request.id}`,{method:'PUT',body:JSON.stringify({status:select.value})});request.status=select.value;updateAdminBadge('adminInstallationsBadge',adminInstallationRequests.filter(item=>!item.admin_read).length,'installation requests');status.textContent='Status updated.'; } catch(error){status.textContent=error.message;select.value=request.status;} finally{select.disabled=false;} };
    const remove=actionButton('Delete request','btn danger',async()=>{if(!confirm('Permanently delete this installation request?'))return;remove.disabled=true;try{await api(`/api/admin/installations/${request.id}`,{method:'DELETE'});adminInstallationRequests=adminInstallationRequests.filter(item=>item.id!==request.id);updateAdminBadge('adminInstallationsBadge',adminInstallationRequests.filter(item=>!item.admin_read).length,'installation requests');navigate(selectedInstallationClient);}catch(error){status.textContent=error.message;remove.disabled=false;}});
    card.append(element('h3','',request.product_name),list,label);
    appendAdminServiceReplies(card,request,'/api/admin/installations',()=>{select.value=request.status;updateAdminBadge('adminInstallationsBadge',adminInstallationRequests.filter(item=>!item.admin_read).length,'installation requests');});
    card.append(remove,status);
    container.append(actionButton('← Client requests','btn',()=>navigate(selectedInstallationClient)),card);
  }
  decorateButtons(container);
}
document.getElementById('refreshInstallations').onclick = loadInstallations;

let adminCustomLabRequests=[],selectedCustomLabClient=null,selectedCustomLabRequest=null;
async function loadCustomLabRequests(){if(!commerce.admin)return;try{adminCustomLabRequests=(await api('/api/admin/custom-lab')).requests;updateAdminBadge('adminCustomLabBadge',adminCustomLabRequests.filter(request=>!request.admin_read).length,'Custom Lab requests');renderAdminCustomLab();}catch(error){document.getElementById('adminCustomLab').textContent=error.message;}}
function renderAdminCustomLab(){
 const container=document.getElementById('adminCustomLab');container.replaceChildren();const clients=[...new Set(adminCustomLabRequests.map(item=>item.email))];
 if(!clients.includes(selectedCustomLabClient)){selectedCustomLabClient=null;selectedCustomLabRequest=null;}
 const requests=adminCustomLabRequests.filter(item=>item.email===selectedCustomLabClient),request=requests.find(item=>item.id===selectedCustomLabRequest);
 const navigate=(client,id=null)=>{selectedCustomLabClient=client;selectedCustomLabRequest=id;if(id){const opened=adminCustomLabRequests.find(item=>item.id===id);if(opened&&!opened.admin_read){opened.admin_read=true;updateAdminBadge('adminCustomLabBadge',adminCustomLabRequests.filter(item=>!item.admin_read).length,'Custom Lab requests');api(`/api/admin/custom-lab/${id}/read`,{method:'POST',body:'{}'}).catch(()=>{opened.admin_read=false;updateAdminBadge('adminCustomLabBadge',adminCustomLabRequests.filter(item=>!item.admin_read).length,'Custom Lab requests');renderAdminCustomLab();});}}renderAdminCustomLab();};
 const label=item=>item.request_type==='new_product'?(item.product_name||'New product idea'):`Custom product · ${item.vehicle_model}`;
 const row=item=>{const button=actionButton('','admin-message-row',()=>navigate(item.email,item.id)),heading=element('span','admin-message-row-heading');heading.append(element('strong','',label(item)));if(!item.admin_read)heading.append(element('span','new-message-dot'));button.append(heading,element('span','commerce-help',`${item.request_type==='new_product'?'New product suggestion':'Custom product request'} · ${new Date(item.created*1000).toLocaleString()} · ${item.status}`),element('span','message-row-arrow','↗'));return button;};
 if(!selectedCustomLabClient){container.append(element('h3','','Clients'));if(!clients.length)container.append(element('p','commerce-help','No Custom Lab requests yet.'));clients.forEach(client=>{const items=adminCustomLabRequests.filter(item=>item.email===client),button=actionButton('','admin-message-row',()=>navigate(client)),heading=element('span','admin-message-row-heading');heading.append(element('strong','',client));const count=items.filter(item=>!item.admin_read).length;if(count)heading.append(element('span','reply-badge',String(count)));button.append(heading,element('span','commerce-help',`${items.length} request${items.length===1?'':'s'} · Latest ${new Date(Math.max(...items.map(item=>item.created))*1000).toLocaleString()}`),element('span','message-row-arrow','↗'));container.append(button);});}
 else if(!request){container.append(actionButton('← All clients','btn',()=>navigate(null)),element('h3','',selectedCustomLabClient));requests.forEach(item=>container.append(row(item)));}
 else{const card=element('article','installation-card'),list=document.createElement('dl');const details=[['Type',request.request_type==='new_product'?'New product suggestion':'Custom product request'],['Email',request.email],['Submitted',new Date(request.created*1000).toLocaleString()]];if(request.request_type==='new_product')details.push(['Product idea',request.product_name]);else details.push(['Vehicle',`${vehicleNames[request.vehicle_type]} · ${request.vehicle_model} · ${request.vehicle_year}`],['Budget',request.budget]);details.push(['Description',request.description]);details.forEach(([term,value])=>list.append(element('dt','',term),element('dd','',value)));const status=element('p','commerce-status'),field=element('label','commerce-field','Status'),select=document.createElement('select');[['new','New'],['reviewing','Reviewing'],['contacted','Contacted'],['accepted','Accepted'],['completed','Completed'],['declined','Declined']].forEach(([value,text])=>select.append(new Option(text,value)));select.value=request.status;field.append(select);select.onchange=async()=>{select.disabled=true;try{await api(`/api/admin/custom-lab/${request.id}`,{method:'PUT',body:JSON.stringify({status:select.value})});request.status=select.value;updateAdminBadge('adminCustomLabBadge',adminCustomLabRequests.filter(item=>!item.admin_read).length,'Custom Lab requests');status.textContent='Status updated.';}catch(error){status.textContent=error.message;select.value=request.status;}finally{select.disabled=false;}};const remove=actionButton('Delete request','btn danger',async()=>{if(!confirm('Permanently delete this Custom Lab request?'))return;remove.disabled=true;try{await api(`/api/admin/custom-lab/${request.id}`,{method:'DELETE'});adminCustomLabRequests=adminCustomLabRequests.filter(item=>item.id!==request.id);updateAdminBadge('adminCustomLabBadge',adminCustomLabRequests.filter(item=>!item.admin_read).length,'Custom Lab requests');navigate(selectedCustomLabClient);}catch(error){status.textContent=error.message;remove.disabled=false;}});card.append(element('h3','',label(request)),list,field);appendAdminServiceReplies(card,request,'/api/admin/custom-lab',()=>{select.value=request.status;updateAdminBadge('adminCustomLabBadge',adminCustomLabRequests.filter(item=>!item.admin_read).length,'Custom Lab requests');});card.append(remove,status);container.append(actionButton('← Client requests','btn',()=>navigate(selectedCustomLabClient)),card);}
 decorateButtons(container);
}
document.getElementById('refreshCustomLab').onclick=loadCustomLabRequests;

let adminOrders=[];
const orderStatusNames={ordered:'Ordered',in_preparation:'In preparation',ready_to_send:'Ready to send',sent:'Sent',cancelled:'Cancelled'};
async function loadAdminOrders(){
 if(!commerce.admin)return;
 const status=document.getElementById('adminOrdersStatus');status.textContent='Loading orders…';
 try{adminOrders=(await api('/api/admin/orders')).orders;updateAdminBadge('adminOrdersBadge',adminOrders.filter(order=>!order.admin_read).length,'new orders');renderAdminOrders();status.textContent=adminOrders.length?`${adminOrders.length} paid order${adminOrders.length===1?'':'s'}.`:'No paid orders yet.';}catch(error){status.textContent=error.message;}
}
function renderAdminOrders(){
 const container=document.getElementById('adminOrders');container.replaceChildren();
 adminOrders.forEach(order=>{
  const card=element('details','admin-order'),summary=element('summary','admin-order-summary'),heading=element('strong','',order.public_id);if(!order.admin_read)heading.append(element('span','new-message-dot'));
  card.classList.toggle('is-cancelled',order.fulfillment_status==='cancelled');
  summary.append(heading,element('span','',`${order.shipping.name} ${order.shipping.surname}`),element('span',`order-status order-status-${order.fulfillment_status}`,orderStatusNames[order.fulfillment_status]||order.fulfillment_status),element('span','commerce-help',new Date(order.created*1000).toLocaleString()));card.append(summary);
  const body=element('div','admin-order-body'),list=document.createElement('dl');
  [['Order ID',order.public_id],['Email',order.customer_email],['Customer',`${order.shipping.name} ${order.shipping.surname}`],['Telephone',order.shipping.phone],['Address',[order.shipping.address,order.shipping.address_extra,`${order.shipping.postal_code} ${order.shipping.city}`,order.shipping.country].filter(Boolean).join(', ')],['Payment','Paid'],['Total',money(order.amount_cents)],['Policies accepted',order.policy_version?`Version ${order.policy_version} · ${new Date(order.policy_accepted_at*1000).toLocaleString()}`:'Legacy order — no recorded version']].forEach(([term,value])=>list.append(element('dt','',term),element('dd','',value)));
  const products=element('div','admin-order-products');products.append(element('h4','','Products'));order.items.forEach(item=>products.append(element('p','',`${item.quantity} × ${item.name} · ${money(item.unit_amount*item.quantity)}`)));
  const field=element('label','commerce-field','Order status'),select=document.createElement('select');Object.entries(orderStatusNames).forEach(([value,label])=>select.append(new Option(label,value)));select.value=order.fulfillment_status;field.append(select);const update=element('p','commerce-status');
  select.onchange=async()=>{const previous=order.fulfillment_status;select.disabled=true;update.textContent='Updating…';try{await api(`/api/admin/orders/${order.id}`,{method:'PUT',body:JSON.stringify({status:select.value})});order.fulfillment_status=select.value;const badge=summary.querySelector('.order-status');badge.textContent=orderStatusNames[select.value];badge.className=`order-status order-status-${select.value}`;card.classList.toggle('is-cancelled',select.value==='cancelled');update.textContent='Status updated. The customer has been notified.';}catch(error){select.value=previous;update.textContent=error.message;}finally{select.disabled=false;}};
  card.addEventListener('toggle',()=>{if(card.open&&!order.admin_read){order.admin_read=1;heading.querySelector('.new-message-dot')?.remove();updateAdminBadge('adminOrdersBadge',adminOrders.filter(item=>!item.admin_read).length,'new orders');api(`/api/admin/orders/${order.id}/read`,{method:'POST',body:'{}'}).catch(()=>{order.admin_read=0;renderAdminOrders();});}});
  body.append(list,products,field,update);card.append(body);container.append(card);
 });decorateButtons(container);
}
document.getElementById('refreshOrders').onclick=loadAdminOrders;
