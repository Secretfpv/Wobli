// Category IDs stay stable when labels change; products retain their assignment.
function applyCategories(categories) {
  Object.keys(categoryNames).forEach(key => delete categoryNames[key]);
  categories.forEach(category => { categoryNames[category.id] = category.name; });
  const filters = document.getElementById('shopCategoryFilters');
  const selected = new Set([...filters.querySelectorAll(':checked')].map(input => input.value));
  if (!selected.size) selected.add('all');
  filters.replaceChildren(element('legend', '', 'Category'));
  [{id:'all', name:'All categories'}, ...categories].forEach(category => {
    const label = element('label', 'shop-filter');
    const input = document.createElement('input'); input.type = 'checkbox'; input.name = 'shopCategory'; input.value = category.id;
    input.checked = selected.has(category.id);
    bindShopFilter(input);
    label.append(input, document.createTextNode(category.name)); filters.append(label);
  });
  if (!filters.querySelector(':checked')) filters.querySelector('input').checked = true;
  const select = document.querySelector('#productForm [name="category"]');
  const previous = select.value;
  select.replaceChildren(...categories.map(category => {
    const option = document.createElement('option'); option.value = category.id; option.textContent = category.name; return option;
  }));
  if (categories.some(category => category.id === previous)) select.value = previous;
}
async function refreshCategories() {
  const data = await api('/api/categories');
  applyCategories(data.categories); renderCategoryManager(data.categories); renderShop();
}
function renderCategoryManager(categories) {
  const container = document.getElementById('adminCategories'); container.replaceChildren();
  if (!categories.length) container.append(element('p', 'commerce-help', 'No categories yet. Add one to start.'));
  categories.forEach(category => {
    const form = element('form', 'category-form');
    const label = element('label', 'commerce-field', 'Category name');
    const input = document.createElement('input'); input.value = category.name; input.required = true; input.maxLength = 80; label.append(input);
    const save = element('button', 'btn', 'Save name'); save.type = 'submit';
    const remove = actionButton('Remove', 'btn danger', async () => {
      if (!confirm(`Remove category “${category.name}”? Products must be moved to another category first.`)) return;
      await change('DELETE');
    });
    async function change(method) {
      save.disabled = remove.disabled = true;
      setMessage('categoryStatus', 'Saving…');
      try {
        await api(`/api/admin/categories/${category.id}`, {method, ...(method === 'PUT' ? {body:JSON.stringify({name:input.value})} : {})});
        await refreshCategories(); setMessage('categoryStatus', method === 'PUT' ? 'Category updated.' : 'Category removed.');
      } catch(error) { setMessage('categoryStatus', error.message, true); }
      finally { save.disabled = remove.disabled = false; }
    }
    form.addEventListener('submit', event => { event.preventDefault(); if (!save.disabled) change('PUT'); });
    form.append(label, save, remove); container.append(form);
  });
  decorateButtons(container);
}
document.getElementById('newCategoryForm').addEventListener('submit', async event => {
  event.preventDefault(); const form = event.currentTarget; const button = form.querySelector('button');
  if (button.disabled) return;
  button.disabled = true;
  try {
    await api('/api/admin/categories', {method:'POST', body:JSON.stringify({name:form.elements.name.value})});
    form.reset(); await refreshCategories(); setMessage('categoryStatus', 'Category added.');
  } catch(error) { setMessage('categoryStatus', error.message, true); }
  finally { button.disabled = false; }
});
