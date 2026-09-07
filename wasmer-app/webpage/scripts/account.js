const accountModal=document.getElementById("accountModal");
const authForm=document.getElementById("authForm");
const authPassword=document.getElementById("authPassword");
const authConfirm=document.getElementById("authConfirm");
const authStatus=document.getElementById("authStatus");
const togglePassword=document.getElementById("togglePassword");
let authMode="login";
let afterAccountLogin = null;
function setAuthMode(mode){
  authMode=mode;
  const register=mode==="register", reset=mode==="reset";
  document.querySelectorAll("[data-auth]").forEach(button=>button.setAttribute("aria-pressed",String(button.dataset.auth===mode)));
  document.getElementById("authTitle").textContent=reset?"Let’s get you back in.":register?"Make it yours.":"Welcome back.";
  document.getElementById("authIntro").textContent=reset?"Enter your email to request a password reset.":register?"Create your account. Start building your own garage.":"Your next upgrade starts here. Log in to your account.";
  document.getElementById("authConfirmField").hidden=!register;
  authConfirm.disabled=!register;authConfirm.required=register;authConfirm.value="";authConfirm.setCustomValidity("");
  const identifier=document.getElementById("authEmail");
  identifier.type=mode==="login"?"text":"email";
  identifier.autocomplete=mode==="login"?"username":"email";
  identifier.placeholder=mode==="login"?"Email or username":"you@example.com";
  document.getElementById("authIdentifierLabel").textContent=mode==="login"?"Email or username":"Email address";
  document.getElementById("authPasswordField").hidden=reset;
  authPassword.disabled=reset;authPassword.required=!reset;
  authPassword.minLength=register?8:1;
  authPassword.autocomplete=register?"new-password":"current-password";
  authPassword.placeholder=register?"Create a password":"Enter your password";
  authPassword.value="";authPassword.type="password";
  hidePassword();
  document.getElementById("authPasswordHint").hidden=!register;
  document.getElementById("forgotPassword").hidden=mode!=="login";
  document.getElementById("authSubmitLabel").textContent=reset?"Send reset link":register?"Create account":"Log in";
  authStatus.textContent="";
}
document.getElementById("accountBtn").onclick=()=>openAdminLogin();
document.getElementById("closeModal").onclick=()=>accountModal.close();
accountModal.addEventListener("click",event=>{if(event.target===accountModal){const box=accountModal.getBoundingClientRect();if(event.clientX<box.left||event.clientX>box.right||event.clientY<box.top||event.clientY>box.bottom)accountModal.close()}});
accountModal.addEventListener("close",()=>{document.body.style.overflow=document.querySelector("dialog[open]")?"hidden":"";authForm.reset();afterAccountLogin=null;authStatus.textContent="";document.getElementById("accountBtn").focus()});
document.querySelectorAll("[data-auth]").forEach(button=>button.addEventListener("click",()=>setAuthMode(button.dataset.auth)));
document.getElementById("forgotPassword").onclick=()=>{setAuthMode("reset");document.getElementById("authEmail").focus()};
function hidePassword(){authPassword.type="password";togglePassword.classList.remove("revealing")}
function revealPassword(){if(!authPassword.disabled){authPassword.type="text";togglePassword.classList.add("revealing")}}
togglePassword.addEventListener("pointerdown",event=>{if(event.button!==0)return;event.preventDefault();togglePassword.setPointerCapture(event.pointerId);revealPassword()});
["pointerup","pointercancel","lostpointercapture","pointerleave","blur"].forEach(name=>togglePassword.addEventListener(name,hidePassword));
togglePassword.addEventListener("keydown",event=>{if(event.key===" "||event.key==="Enter"){event.preventDefault();revealPassword()}});
togglePassword.addEventListener("keyup",event=>{if(event.key===" "||event.key==="Enter"){event.preventDefault();hidePassword()}});
togglePassword.addEventListener("contextmenu",event=>event.preventDefault());
window.addEventListener("blur",hidePassword);
document.addEventListener("visibilitychange",()=>{if(document.hidden)hidePassword()});
accountModal.addEventListener("close",hidePassword);
function validateConfirmation() {
  authConfirm.setCustomValidity(authMode === 'register' && authConfirm.value !== authPassword.value ? 'Passwords do not match.' : '');
}
authConfirm.addEventListener('input', validateConfirmation);
authPassword.addEventListener('input', validateConfirmation);
authForm.addEventListener('submit', async event => {
  event.preventDefault();
  if (authMode === 'reset') {
    authStatus.textContent='Password recovery is not connected yet. No reset email has been sent.'; return;
  }
  validateConfirmation(); if (!authForm.reportValidity()) return;
  const submittedMode = authMode;
  const button=authForm.querySelector('[type="submit"]');
  if (button.disabled) return;
  button.disabled=true;authStatus.textContent=submittedMode === 'register' ? 'Creating your account…' : 'Signing in…';
  const identifier=document.getElementById('authEmail').value.trim();
  try {
    const isAdmin = submittedMode === 'login' && (!identifier.includes('@') || identifier === '@dmin');
    if (isAdmin) {
      const data = await api('/api/admin/login', {method:'POST',body:JSON.stringify({username:identifier==='@dmin'?'admin':identifier,password:authPassword.value})});
      commerce.admin=data.admin; commerce.customer=null;
    } else {
      const data = await api(submittedMode === 'register' ? '/api/account/register' : '/api/account/login', {method:'POST',body:JSON.stringify({email:identifier,password:authPassword.value,confirmation:authConfirm.value})});
      commerce.customer=data.account; commerce.admin=null;
    }
    adminUI();
    await refreshAccountNotifications();
    const resume = afterAccountLogin;
    accountModal.addEventListener('close', () => {
      if (resume) resume();
      else if (commerce.admin) openView('admin');
      else showCustomerAccount(submittedMode === 'register' ? 'Your account has been created and saved. You are now signed in.' : 'You are signed in.');
    }, {once:true});
    accountModal.close();
  } catch(error) {authStatus.textContent=error.message;}
  finally {button.disabled=false;authPassword.value='';hidePassword();}
});

function showCustomerAccount(message = '') {
  openView('profile');
  setMessage('profileStatus', message);
}
function loginForQuestion(resume) {
  setAuthMode('login'); afterAccountLogin = resume;
  accountModal.showModal(); document.body.style.overflow = 'hidden';
  document.getElementById('authIntro').textContent = 'Log in or create an account to ask a question. We’ll return you to this product automatically.';
  document.getElementById('authEmail').focus();
}
function loginForRequest(resume, label) {
  setAuthMode('login'); afterAccountLogin = resume;
  accountModal.showModal(); document.body.style.overflow = 'hidden';
  document.getElementById('authIntro').textContent = `Log in or create an account to send your ${label}. Your completed form will be kept.`;
  document.getElementById('authEmail').focus();
}
