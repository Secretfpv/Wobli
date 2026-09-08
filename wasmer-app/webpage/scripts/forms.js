// Custom Lab request form.
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
