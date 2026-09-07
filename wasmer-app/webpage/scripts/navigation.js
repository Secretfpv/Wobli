const navTabs=document.querySelectorAll(".navtab");
const views=document.querySelectorAll(".view");

function openView(name){
  if(name === "admin" && !commerce.admin){openAdminLogin();return;}
  if(name === "profile" && !commerce.customer){
    setAuthMode('login'); afterAccountLogin = () => { if (commerce.customer) openView('profile'); };
    accountModal.showModal(); return;
  }
  if(!document.getElementById("view-"+name))return;
  views.forEach(v=>v.classList.remove("active"));
  navTabs.forEach(t=>t.classList.remove("active"));
  document.getElementById("view-"+name).classList.add("active");
  const tab=document.querySelector(`.navtab[data-view="${name}"]`);
  if(tab)tab.classList.add("active");
  const accountButton = document.getElementById('accountBtn');
  accountButton.classList.toggle('active', name === 'profile' || name === 'admin');
  if (name === 'profile' || name === 'admin') accountButton.setAttribute('aria-current', 'page');
  else accountButton.removeAttribute('aria-current');
  window.scrollTo({top:0,behavior:"instant"});
  document.getElementById("labShortcut").hidden=["custom","admin","cart"].includes(name);
  if(name==="shop"){maybeShowPreorder();loadShop();}
  if(name==="cart")renderCart();
  if(name==="admin")loadAdminProducts();
  if(name==="profile")loadProfile();
  if(name==="custom" && typeof syncCustomLabForm === 'function')syncCustomLabForm();
}
navTabs.forEach(t=>t.addEventListener("click",()=>openView(t.dataset.view)));
document.querySelectorAll("[data-open]").forEach(b=>b.addEventListener("click",()=>openView(b.dataset.open)));
