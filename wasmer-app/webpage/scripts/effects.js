const observer=new IntersectionObserver(entries=>{
  entries.forEach(entry=>{
    if(entry.isIntersecting) entry.target.classList.add("visible");
  });
},{threshold:.16});
document.querySelectorAll(".fade,.slide-left,.slide-right").forEach(el=>observer.observe(el));


// One shared sequence keeps the arrow and border synchronized even on pointer exit.
const labShortcut=document.getElementById("labShortcut");
let labSignalTimer;
function signalCustomLab(){
  if(labShortcut.hidden||document.hidden||window.matchMedia("(prefers-reduced-motion: reduce)").matches||labShortcut.classList.contains("lab-signaling"))return;
  labShortcut.classList.add("lab-signaling");
  // Three flashes (2.1s), a 0.5s pause, then a 0.35s fade to steady amber.
  labSignalTimer=window.setTimeout(()=>labShortcut.classList.remove("lab-signaling"),3000);
}
labShortcut.addEventListener("pointerenter",event=>{if(event.pointerType!=="touch")signalCustomLab()});
labShortcut.addEventListener("focus",signalCustomLab);
window.addEventListener("load",()=>window.setTimeout(signalCustomLab,600),{once:true});

// Run one alternating four-row sweep, then pause before repeating under a held hover.
document.querySelectorAll('.process-panel').forEach(panel=>{
  let hovered=false,running=false,finishTimer=null,repeatTimer=null;
  const reduced=()=>window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  function run(){
    if(running||!hovered||reduced())return;
    running=true;panel.classList.remove('process-sequence');void panel.offsetWidth;panel.classList.add('process-sequence');
    finishTimer=window.setTimeout(()=>{
      panel.classList.remove('process-sequence');running=false;
      if(hovered)repeatTimer=window.setTimeout(run,2500);
    },1740);
  }
  panel.addEventListener('pointerenter',event=>{if(event.pointerType==='touch')return;hovered=true;clearTimeout(repeatTimer);run();});
  panel.addEventListener('pointerleave',()=>{hovered=false;clearTimeout(repeatTimer);});
});

const glow=document.getElementById("cursorGlow");
window.addEventListener("mousemove",e=>{
  glow.style.left=e.clientX+"px";
  glow.style.top=e.clientY+"px";
});
