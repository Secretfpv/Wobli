// Installation requests are stored by the server; Custom Lab remains a preview.
const installVehicleForm = document.getElementById('installVehicleForm');
const installationForm = document.getElementById('installationRequestForm');
const installStepOne = document.getElementById('installStepOne');
const installStepTwo = document.getElementById('installStepTwo');
const installationThanks = document.getElementById('installationThanks');
const requestSuccessDialog=document.getElementById('requestSuccessDialog');
let requestSuccessTimer;
function closeRequestSuccess(){if(requestSuccessDialog.open)requestSuccessDialog.close();}
function flashRequestSuccess(){if(!requestSuccessDialog.open||requestSuccessDialog.classList.contains('question-lock'))return;clearTimeout(requestSuccessTimer);requestSuccessDialog.classList.add('question-lock');requestSuccessTimer=setTimeout(closeRequestSuccess,1500);}
function showRequestSuccess(message){
  clearTimeout(requestSuccessTimer);
  requestSuccessDialog.classList.remove('question-success','question-lock');
  document.getElementById('requestSuccessMessage').textContent=message;
  if(!requestSuccessDialog.open)requestSuccessDialog.showModal();
  document.body.style.overflow='hidden';
  // Start only after the dialog has painted, so the red sweep cannot run while hidden.
  requestAnimationFrame(()=>requestAnimationFrame(()=>{
    if(!requestSuccessDialog.open)return;
    requestSuccessDialog.classList.add('question-success');
    document.getElementById('requestSuccessTitle').focus();
    requestSuccessTimer=setTimeout(flashRequestSuccess,2100);
  }));
}
requestSuccessDialog.addEventListener('animationend',event=>{if(event.target!==requestSuccessDialog||event.pseudoElement!=='::before')return;if(event.animationName==='sectionLedSweep')flashRequestSuccess();if(event.animationName==='questionLockFlash')closeRequestSuccess();});
requestSuccessDialog.addEventListener('close',()=>{clearTimeout(requestSuccessTimer);requestSuccessDialog.classList.remove('question-success','question-lock');document.body.style.overflow=document.querySelector('dialog[open]')?'hidden':'';});
async function showInstallationStepTwo() {
  const select = document.getElementById('installationProduct');
  const previous = select.value;
  try {
    const products = (await api('/api/products')).products;
    select.replaceChildren(new Option('Choose a product', ''), ...products.map(product => new Option(product.name, product.id)));
    if (products.some(product => product.id === previous)) select.value = previous;
    installStepOne.hidden = true; installStepTwo.hidden = false; select.focus();
  } catch(error) { setMessage('installationStatus', error.message, true); }
}
installVehicleForm.addEventListener('submit', event => { event.preventDefault(); if (installVehicleForm.reportValidity()) showInstallationStepTwo(); });
document.getElementById('installationBack').onclick = () => { installStepTwo.hidden = true; installStepOne.hidden = false; installVehicleForm.elements.vehicle_type.focus(); };
async function sendInstallationRequest() {
  const button = installationForm.querySelector('[type="submit"]'); button.disabled = true; setMessage('installationStatus', 'Sending your request…');
  const vehicle = Object.fromEntries(new FormData(installVehicleForm));
  const request = Object.fromEntries(new FormData(installationForm));
  try {
    await api('/api/installations', {method:'POST', body:JSON.stringify({...vehicle,...request})});
    installStepTwo.hidden = true; installStepOne.hidden = false; installVehicleForm.reset();
    showRequestSuccess('Thank you for your installation request. Wobli will contact you as soon as possible to find a suitable date.');
    installationForm.reset();
    if (commerce.customer && document.getElementById('view-profile').classList.contains('active')) loadProfile();
  } catch(error) { setMessage('installationStatus', error.message, true); }
  finally { button.disabled = false; }
}
installationForm.addEventListener('submit', event => {
  event.preventDefault(); if (!installationForm.reportValidity()) return;
  if (!commerce.customer) {
    setMessage('installationStatus', 'Log in or create an account to send this request.');
    loginForRequest(sendInstallationRequest, 'installation request'); return;
  }
  sendInstallationRequest();
});
document.getElementById('installationAgain').onclick = () => { installationThanks.hidden = true; installStepOne.hidden = false; installVehicleForm.reset(); setMessage('installationStatus', ''); };
const customLabForm=document.getElementById('customLabForm');
const customLabType=document.getElementById('customLabType');
function syncCustomLabForm(){
  const suggestion=customLabType.value==='new_product';
  document.getElementById('newProductFields').hidden=!suggestion;
  document.getElementById('customProductFields').hidden=suggestion;
  customLabForm.elements.product_name.required=suggestion;
  for(const name of ['vehicle_type','vehicle_model','vehicle_year','budget']) customLabForm.elements[name].required=!suggestion;
}
customLabType.onchange=syncCustomLabForm;
async function sendCustomLabRequest(){
  const button=customLabForm.querySelector('[type="submit"]');button.disabled=true;setMessage('customLabStatus','Sending your request…');
  const data=Object.fromEntries(new FormData(customLabForm));
  try{await api('/api/custom-lab',{method:'POST',body:JSON.stringify(data)});customLabForm.reset();syncCustomLabForm();showRequestSuccess('Thank you for your Custom Lab request. Wobli will review your idea and contact you as soon as possible.');}
  catch(error){setMessage('customLabStatus',error.message,true);}
  finally{button.disabled=false;}
}
customLabForm.addEventListener('submit',event=>{
  event.preventDefault();syncCustomLabForm();if(!customLabForm.reportValidity())return;
  if(!commerce.customer){setMessage('customLabStatus','Log in or create an account to send this request.');loginForRequest(sendCustomLabRequest,'Custom Lab request');return;}
  sendCustomLabRequest();
});
document.getElementById('customLabAgain').onclick=()=>{document.getElementById('customLabThanks').hidden=true;customLabForm.hidden=false;customLabForm.reset();syncCustomLabForm();setMessage('customLabStatus','');};
syncCustomLabForm();
