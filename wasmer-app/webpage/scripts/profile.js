// Customer profile: personal data is read/written only through the authenticated API.
let profileLoadingVersion = 0;
let unreadReplyIds = [];
let unreadInstallationReplyIds = [];
let unreadCustomLabReplyIds = [];
let unreadOrderUpdates = 0;
let activeProfileOrder = null;
let currentProfileOrders = [];
const customerReplyDrafts = new Map();
let sendingCustomerReply = false;
function updateReplyBadge() {
  const badge = document.getElementById('messageBadge');
  badge.textContent = unreadReplyIds.length;
  badge.hidden = !unreadReplyIds.length;
  badge.setAttribute('aria-label', `${unreadReplyIds.length} unread replies`);
  const installationBadge=document.getElementById('profileInstallationsBadge');installationBadge.textContent=unreadInstallationReplyIds.length;installationBadge.hidden=!unreadInstallationReplyIds.length;installationBadge.setAttribute('aria-label',`${unreadInstallationReplyIds.length} unread installation replies`);
  const customBadge=document.getElementById('profileCustomLabBadge');customBadge.textContent=unreadCustomLabReplyIds.length;customBadge.hidden=!unreadCustomLabReplyIds.length;customBadge.setAttribute('aria-label',`${unreadCustomLabReplyIds.length} unread Custom Lab replies`);
  const orderBadge=document.getElementById('profileOrdersBadge');orderBadge.textContent=unreadOrderUpdates;orderBadge.hidden=!unreadOrderUpdates;orderBadge.setAttribute('aria-label',`${unreadOrderUpdates} updated orders`);
  if (commerce.customer) updateGlobalAccountBadge(unreadReplyIds.length + unreadInstallationReplyIds.length + unreadCustomLabReplyIds.length + unreadOrderUpdates);
}
async function markRepliesRead(section = 'messages') {
  const version = profileLoadingVersion;
  const source = section === 'installations' ? unreadInstallationReplyIds : section === 'custom-lab' ? unreadCustomLabReplyIds : unreadReplyIds;
  const ids = [...source];
  if (!ids.length || !commerce.customer) return;
  try {
    for (let i = 0; i < ids.length; i += 500) {
      await api('/api/account/replies/read', {method:'POST', body:JSON.stringify({ids:ids.slice(i, i + 500)})});
    }
    if (version !== profileLoadingVersion) return;
    if(section==='installations')unreadInstallationReplyIds=unreadInstallationReplyIds.filter(id=>!ids.includes(id));
    else if(section==='custom-lab')unreadCustomLabReplyIds=unreadCustomLabReplyIds.filter(id=>!ids.includes(id));
    else unreadReplyIds=unreadReplyIds.filter(id=>!ids.includes(id));
    updateReplyBadge();
  } catch(error) { if (version === profileLoadingVersion) setMessage('profileMessagesStatus', error.message, true); }
}
async function markServiceRequestRead(ids,section) {
  if(!ids.length||!commerce.customer)return;
  try{
    for(let i=0;i<ids.length;i+=500)await api('/api/account/replies/read',{method:'POST',body:JSON.stringify({ids:ids.slice(i,i+500)})});
    if(section==='installations')unreadInstallationReplyIds=unreadInstallationReplyIds.filter(id=>!ids.includes(id));
    else unreadCustomLabReplyIds=unreadCustomLabReplyIds.filter(id=>!ids.includes(id));
    updateReplyBadge();
  }catch{ /* The next profile refresh will retry the unread state. */ }
}
const detailsForm = document.getElementById('profileDetailsForm');
function profileSection(name) {
  ['home', 'orders', 'messages', 'installations', 'custom-lab', 'personal', 'settings'].forEach(section => { document.getElementById('profile-' + section).hidden = section !== name; });
  document.querySelectorAll('.profile-navigation [data-profile]').forEach(button => {
    if (button.dataset.profile === name) button.setAttribute('aria-current', 'page'); else button.removeAttribute('aria-current');
  });
  if (name === 'messages') markRepliesRead(name);
  if(name==='orders'&&unreadOrderUpdates){api('/api/account/orders/read',{method:'POST',body:'{}'}).then(()=>{unreadOrderUpdates=0;updateReplyBadge();}).catch(()=>{});}
}
document.querySelectorAll('[data-profile]').forEach(button => button.addEventListener('click', () => profileSection(button.dataset.profile)));
function displayProfileMessages(profile) {
  unreadReplyIds = profile.messages.flatMap(message => message.replies.filter(reply => reply.sender === 'admin' && !reply.is_read).map(reply => reply.id));
  updateReplyBadge();
  const messages = document.getElementById('profileMessages');
  messages.replaceChildren();
  document.getElementById('profileMessagesStatus').textContent = profile.messages.length ? `${profile.messages.length} message${profile.messages.length === 1 ? '' : 's'} sent.` : 'You haven’t sent any product questions yet.';
  profile.messages.forEach(message => {
    const item = document.createElement('article');
    item.className = 'profile-message';
    const heading = document.createElement('h4'); heading.textContent = message.product_name;
    const date = document.createElement('time');
    date.dateTime = new Date(message.created * 1000).toISOString();
    date.textContent = `Sent · ${new Date(message.created * 1000).toLocaleString()}`;
    const body = document.createElement('p'); body.textContent = message.message;
    item.append(heading, date, body); messages.append(item);
    message.replies.forEach(reply => {
      const response = element('div', 'message-reply');
      response.classList.toggle('customer-reply', reply.sender === 'customer');
      response.append(element('strong', '', reply.sender === 'customer' ? 'You' : 'Wobli'), element('p', 'commerce-help', new Date(reply.created * 1000).toLocaleString()), element('p', '', reply.message));
      item.append(response);
    });
    if (!message.replies.length) item.append(element('p', 'commerce-help', 'Waiting for a reply.'));
    const form = element('form', 'customer-reply-form');
    const label = element('label', 'commerce-field', 'Your reply');
    const input = element('textarea'); input.required = true; input.maxLength = 3000; input.rows = 3;
    const draft = customerReplyDrafts.get(message.id) || {text:'', id:crypto.randomUUID().replaceAll('-', '')};
    input.value = draft.text;
    input.addEventListener('input', () => {
      draft.text = input.value; draft.id = crypto.randomUUID().replaceAll('-', ''); customerReplyDrafts.set(message.id, draft);
    });
    label.append(input);
    const send = element('button', 'btn', 'Send reply'); send.type = 'submit';
    const status = element('p', 'commerce-status'); status.setAttribute('role', 'status');
    form.append(label, send, status); item.append(form);
    form.addEventListener('submit', async event => {
      event.preventDefault(); if (sendingCustomerReply) return;
      sendingCustomerReply = true; send.disabled = true; input.disabled = true;
      const version = profileLoadingVersion;
      status.textContent = 'Sending…';
      try {
        await api(`/api/account/questions/${message.id}/replies`, {method:'POST', body:JSON.stringify({message:input.value, request_id:draft.id})});
        customerReplyDrafts.delete(message.id);
        if (version !== profileLoadingVersion) return;
        input.value = ''; draft.text = ''; draft.id = crypto.randomUUID().replaceAll('-', '');
        status.textContent = 'Reply sent.';
        const data = await api('/api/account/profile');
        if (version === profileLoadingVersion && commerce.customer) displayProfileMessages(data.profile);
      } catch(error) { if (version === profileLoadingVersion) status.textContent = error.message; }
      finally { sendingCustomerReply = false; send.disabled = false; input.disabled = false; }
    });
  });
  decorateButtons(messages);
  if (!document.getElementById('profile-messages').hidden) markRepliesRead();
}
function customerServiceCard(request,section,title,appendDetails) {
  const card=element('details','installation-card customer-service-card');
  const summary=element('summary','customer-service-summary'),heading=element('span','customer-service-title',title),meta=element('span','commerce-help',`${new Date(request.created*1000).toLocaleString()} · ${request.status[0].toUpperCase()+request.status.slice(1)}`);
  const unread=request.replies.filter(reply=>reply.sender==='admin'&&!reply.is_read).map(reply=>reply.id);
  if(unread.length){const dot=element('span','new-message-dot');dot.setAttribute('aria-label','New reply');heading.append(dot);}
  summary.append(heading,meta);card.append(summary);
  const content=element('div','customer-service-content');appendDetails(content);
  const replies=element('div','customer-service-replies');
  const showReply=reply=>{const block=element('div','message-reply');block.classList.toggle('customer-reply',reply.sender==='customer');block.append(element('strong','',reply.sender==='customer'?'You':'Wobli'),element('p','commerce-help',new Date(reply.created*1000).toLocaleString()),element('p','',reply.message));replies.append(block);};
  request.replies.forEach(showReply);content.append(replies);
  const form=element('form','customer-reply-form'),field=element('label','commerce-field','Your reply'),input=element('textarea');input.required=true;input.maxLength=3000;input.rows=3;field.append(input);const send=element('button','btn','Send reply');send.type='submit';const status=element('p','commerce-status');status.setAttribute('role','status');form.append(field,send,status);content.append(form);card.append(content);
  card.addEventListener('toggle',()=>{if(card.open&&unread.length){markServiceRequestRead(unread,section);heading.querySelector('.new-message-dot')?.remove();}});
  form.addEventListener('submit',async event=>{event.preventDefault();if(send.disabled)return;send.disabled=true;input.disabled=true;status.textContent='Sending…';const message=input.value,requestId=crypto.randomUUID().replaceAll('-','');try{await api(`/api/account/${section}/${request.id}/replies`,{method:'POST',body:JSON.stringify({message,request_id:requestId})});const reply={id:requestId,message,created:Date.now()/1000,sender:'customer',is_read:1};request.replies.push(reply);showReply(reply);input.value='';status.textContent='Reply sent.';}catch(error){status.textContent=error.message;}finally{send.disabled=false;input.disabled=false;}});
  decorateButtons(card);return card;
}
function displayProfile(profile) {
  if (commerce.customer) { commerce.customer.name = profile.details.name.trim(); adminUI(); }
  displayProfileMessages(profile);
  displayProfileOrders(profile.orders || []);
  const installations = document.getElementById('profileInstallations'); installations.replaceChildren();
  unreadInstallationReplyIds=profile.installations.flatMap(request=>request.replies.filter(reply=>reply.sender==='admin'&&!reply.is_read).map(reply=>reply.id));
  document.getElementById('profileInstallationsStatus').textContent = profile.installations.length ? `${profile.installations.length} installation request${profile.installations.length === 1 ? '' : 's'}.` : 'You have no installation requests from this account.';
  profile.installations.forEach(request=>installations.append(customerServiceCard(request,'installations',request.product_name,container=>{container.append(element('p','commerce-help',`${vehicleNames[request.vehicle_type]} · ${request.vehicle_model} · ${request.vehicle_year}`));if(request.comment)container.append(element('p','',request.comment));})));
  const customLab=document.getElementById('profileCustomLab');customLab.replaceChildren();
  unreadCustomLabReplyIds=profile.custom_lab.flatMap(request=>request.replies.filter(reply=>reply.sender==='admin'&&!reply.is_read).map(reply=>reply.id));
  document.getElementById('profileCustomLabStatus').textContent=profile.custom_lab.length?`${profile.custom_lab.length} Custom Lab request${profile.custom_lab.length===1?'':'s'}.`:'You have no Custom Lab requests from this account.';
  profile.custom_lab.forEach(request=>{const title=request.request_type==='new_product'?(request.product_name||'New product idea'):`Custom product · ${request.vehicle_model} · ${request.vehicle_year}`;customLab.append(customerServiceCard(request,'custom-lab',title,container=>container.append(element('p','',request.description))));});
  updateReplyBadge();
  document.getElementById('profileEmail').textContent = profile.email;
  document.getElementById('profileWelcome').textContent = profile.details.name ? `Welcome, ${profile.details.name}.` : 'Your space.';
  document.getElementById('profileDetailsSummary').textContent = [profile.details.name, profile.details.surname, profile.details.city].filter(Boolean).join(' · ') || 'Add your details for future deliveries.';
  Object.entries(profile.details).forEach(([key, value]) => { const input = detailsForm.elements.namedItem(key); if (input) input.value = value; });
  document.getElementById('profileEmailForm').elements.email.value = profile.email;
}
function displayProfileOrders(orders) {
  currentProfileOrders=orders;
  const container=document.getElementById('profileOrders');container.replaceChildren();
  document.getElementById('profileOrdersStatus').textContent=orders.length?`${orders.length} order${orders.length===1?'':'s'}.`:'You have no orders yet.';
  unreadOrderUpdates=orders.filter(order=>!order.status_read).length;updateReplyBadge();
  const statusNames={ordered:'Ordered',in_preparation:'In preparation',ready_to_send:'Ready to send',sent:'Sent',cancelled:'Cancelled'};
  orders.forEach(order=>{
    const card=element('article','profile-order');
    card.tabIndex=0;card.setAttribute('role','button');card.setAttribute('aria-label',`Open order ${order.public_id}`);
    const header=element('div','profile-order-header');
    const title=element('div'),heading=element('h4','',order.public_id||`WOBLI-${order.id.toUpperCase()}`);if(!order.status_read)heading.append(element('span','new-message-dot'));title.append(heading,element('time','',new Date(order.created*1000).toLocaleString()));
    const state=element('span',`order-status order-status-${order.fulfillment_status}`,statusNames[order.fulfillment_status]||order.fulfillment_status);header.append(title,state);card.append(header);
    const items=element('div','profile-order-items');
    order.items.forEach(item=>{const row=element('div','profile-order-item');row.append(element('span','',`${item.quantity} × ${item.name}`),element('strong','',money(item.unit_amount*item.quantity)));items.append(row);});
    const total=element('div','profile-order-total');total.append(element('span','','Total'),element('strong','',money(order.amount_cents)));card.append(items,total);container.append(card);
    card.addEventListener('click',()=>openOrderDetails(order));
    card.addEventListener('keydown',event=>{if(event.key==='Enter'||event.key===' '){event.preventDefault();openOrderDetails(order);}});
  });
  if(!document.getElementById('profile-orders').hidden&&unreadOrderUpdates){api('/api/account/orders/read',{method:'POST',body:'{}'}).then(()=>{unreadOrderUpdates=0;updateReplyBadge();}).catch(()=>{});}
}
function openOrderDetails(order){
  activeProfileOrder=order;
  const dialog=document.getElementById('orderDetailsDialog'),content=document.getElementById('orderDetailsContent'),shipping=order.shipping||{};
  document.getElementById('orderDetailsTitle').textContent=order.public_id;
  content.replaceChildren();
  const list=document.createElement('dl');list.className='order-details-list';
  const statusNames={ordered:'Ordered',in_preparation:'In preparation',ready_to_send:'Ready to send',sent:'Sent',cancelled:'Cancelled'};
  [['Status',statusNames[order.fulfillment_status]||order.fulfillment_status],['Order date',new Date(order.created*1000).toLocaleString()],['Customer',[shipping.name,shipping.surname].filter(Boolean).join(' ')],['Email',commerce.customer.username],['Telephone',shipping.phone||''],['Delivery address',[shipping.address,shipping.address_extra,`${shipping.postal_code||''} ${shipping.city||''}`.trim(),shipping.country].filter(Boolean).join(', ')],['Total',money(order.amount_cents)]].forEach(([term,value])=>list.append(element('dt','',term),element('dd','',value)));
  const products=element('div','order-details-products');products.append(element('h3','','Products'));
  order.items.forEach(item=>{
    const row=element('button','order-details-product');row.type='button';row.setAttribute('aria-label',`Open ${item.name} in the shop`);
    row.append(element('span','',`${item.quantity} × ${item.name}`),element('strong','',money(item.quantity*item.unit_amount)));products.append(row);
    row.addEventListener('click',async()=>{
      closeOrderDetails();openView('shop');await loadShop();
      const product=shopProducts.find(entry=>entry.id===item.id);
      if(product)openProduct(product);
      else window.alert('This product is no longer available in the current shop catalogue.');
    });
  });
  content.append(list,products);
  const cancel=document.getElementById('cancelCustomerOrder');cancel.hidden=['sent','cancelled'].includes(order.fulfillment_status);cancel.disabled=false;
  document.getElementById('cancelOrderStatus').textContent=order.fulfillment_status==='cancelled'?'This order is cancelled.':order.fulfillment_status==='sent'?'This order has already been sent.':'';
  if(!dialog.open)dialog.showModal();document.body.style.overflow='hidden';
}
function closeOrderDetails(){const dialog=document.getElementById('orderDetailsDialog');if(dialog.open)dialog.close();activeProfileOrder=null;document.body.style.overflow=document.querySelector('dialog[open]')?'hidden':'';}
document.getElementById('closeOrderDetails').addEventListener('click',closeOrderDetails);
document.getElementById('orderDetailsDialog').addEventListener('cancel',event=>{event.preventDefault();closeOrderDetails();});
document.getElementById('cancelCustomerOrder').addEventListener('click',async()=>{
  if(!activeProfileOrder||!window.confirm(`Cancel order ${activeProfileOrder.public_id}? Any refund due will be handled separately by Wobli.`))return;
  const order=activeProfileOrder,button=document.getElementById('cancelCustomerOrder'),status=document.getElementById('cancelOrderStatus');button.disabled=true;status.textContent='Cancelling order…';
  try{await api(`/api/account/orders/${order.id}/cancel`,{method:'POST',body:'{}'});order.fulfillment_status='cancelled';order.status_read=1;displayProfileOrders(currentProfileOrders);openOrderDetails(order);}
  catch(error){status.textContent=error.message;button.disabled=false;}
});
async function loadProfile() {
  const version = ++profileLoadingVersion;
  unreadReplyIds = []; unreadInstallationReplyIds=[]; unreadCustomLabReplyIds=[]; unreadOrderUpdates=0; updateReplyBadge();
  profileSection('home'); setMessage('profileStatus', 'Loading your profile…');
  document.getElementById('profileMessages').replaceChildren();
  document.getElementById('profileOrders').replaceChildren();
  document.getElementById('profileOrdersStatus').textContent = 'Loading your orders…';
  document.getElementById('profileInstallations').replaceChildren();
  document.getElementById('profileCustomLab').replaceChildren();
  document.getElementById('profileMessagesStatus').textContent = 'Loading your messages…';
  detailsForm.reset();
  document.getElementById('profileEmailForm').reset(); document.getElementById('profilePasswordForm').reset();
  document.getElementById('profileWelcome').textContent = 'Your space.';
  document.getElementById('profileEmail').textContent = commerce.customer.username;
  ['profileDetailsStatus', 'profileEmailStatus', 'profilePasswordStatus'].forEach(id => setMessage(id, ''));
  const save = detailsForm.querySelector('[type="submit"]'); save.disabled = true;
  try {
    const data = await api('/api/account/profile');
    if (version !== profileLoadingVersion || !commerce.customer) return;
    displayProfile(data.profile); setMessage('profileStatus', ''); save.disabled = false;
  } catch(error) { if (version === profileLoadingVersion) { setMessage('profileStatus', error.message, true); document.getElementById('profileMessagesStatus').textContent = 'Could not load your messages. Please reopen your profile to try again.'; } }
}
function clearCustomerProfile() {
  customerReplyDrafts.clear();
  profileLoadingVersion++;
  unreadReplyIds = []; unreadInstallationReplyIds=[]; unreadCustomLabReplyIds=[]; unreadOrderUpdates=0; updateReplyBadge();
  document.getElementById('profileMessages').replaceChildren();
  document.getElementById('profileMessagesStatus').textContent = '';
  commerce.customer = null; adminUI();
  detailsForm.reset(); document.getElementById('profileEmailForm').reset(); document.getElementById('profilePasswordForm').reset();
  document.getElementById('profileWelcome').textContent = 'Your space.';
  document.getElementById('profileEmail').textContent = '';
  document.getElementById('profileDetailsSummary').textContent = '';
  openView('home');
}
document.getElementById('profileLogout').onclick = async () => {
  try { await api('/api/account/logout', {method:'POST',body:'{}'}); clearCustomerProfile(); }
  catch(error) { setMessage('profileStatus', error.message, true); }
};
document.getElementById('deleteAccount').onclick=async()=>{
  if(!window.confirm('Permanently delete your Wobli account and all associated profile data, requests and conversations? This cannot be undone.'))return;
  const button=document.getElementById('deleteAccount');button.disabled=true;setMessage('deleteAccountStatus','Deleting your account…');
  try{await api('/api/account',{method:'DELETE',body:'{}'});clearCustomerProfile();}
  catch(error){setMessage('deleteAccountStatus',error.message,true);button.disabled=false;}
};
detailsForm.addEventListener('submit', async event => {
  event.preventDefault(); const button = detailsForm.querySelector('[type="submit"]'); if (button.disabled) return;
  button.disabled = true; setMessage('profileDetailsStatus', 'Saving…');
  const data = Object.fromEntries(new FormData(detailsForm));
  try { const result = await api('/api/account/profile', {method:'PUT',body:JSON.stringify(data)}); displayProfile(result.profile); setMessage('profileDetailsStatus', 'Your personal details are saved.'); }
  catch(error) { setMessage('profileDetailsStatus', error.message, true); }
  finally { button.disabled = false; }
});
for (const kind of ['Email', 'Password']) {
  const form = document.getElementById(`profile${kind}Form`);
  form.addEventListener('submit', async event => {
    event.preventDefault(); const button = form.querySelector('[type="submit"]'); if (button.disabled) return;
    if (kind === 'Password' && form.elements.password.value !== form.elements.confirmation.value) { setMessage('profilePasswordStatus', 'The new passwords do not match.', true); return; }
    const data = Object.fromEntries(new FormData(form));
    button.disabled = true; setMessage(`profile${kind}Status`, 'Saving…');
    try {
      await api(`/api/account/${kind.toLowerCase()}`, {method:'POST',body:JSON.stringify(data)});
      clearCustomerProfile(); openAdminLogin();
      document.getElementById('authEmail').value = kind === 'Email' ? data.email.trim() : '';
      authStatus.textContent = `${kind} updated. Please log in again.`;
    } catch(error) { setMessage(`profile${kind}Status`, error.message, true); }
    finally { button.disabled = false; form.querySelectorAll('[type="password"]').forEach(input => { input.value = ''; }); }
  });
}
decorateButtons(document.getElementById('view-profile'));

// Refresh replies while the profile is open without touching unsaved settings.
let refreshingReplies = false;
setInterval(async () => {
  if (refreshingReplies || document.hidden || !commerce.customer || !document.getElementById('view-profile').classList.contains('active')) return;
  refreshingReplies = true;
  const version = profileLoadingVersion;
  try {
    const data = await api('/api/account/profile');
    if (version === profileLoadingVersion && commerce.customer && !sendingCustomerReply && !document.activeElement.closest('.customer-reply-form')) { displayProfileMessages(data.profile);displayProfileOrders(data.profile.orders||[]); }
  } catch { /* Keep the existing messages; retry on the next refresh. */ }
  finally { refreshingReplies = false; }
}, 30000);
