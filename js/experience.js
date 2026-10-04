(() => {
  'use strict';
  const root = document.documentElement;
  const reduced = matchMedia('(prefers-reduced-motion: reduce)');
  const finePointer = matchMedia('(hover: hover) and (pointer: fine)');
  const button = document.querySelector('.motion-toggle');
  const video = document.querySelector('.hero-film');
  let savedPause = false;
  try { savedPause = sessionStorage.getItem('devantiq-motion-paused') === 'true'; } catch { /* Storage may be disabled. */ }
  let paused = reduced.matches || Boolean(navigator.connection?.saveData) || savedPause;
  let visible = true;
  let frame = 0;
  let phase = 0;
  let last = 0;
  const canvas = document.getElementById('universe-canvas');
  const context = canvas?.getContext('2d');
  let width = 0, height = 0;
  // Closed trefoil tube: actual 3D geometry, perspective projection and lighting.
  const segments = 144, sides = 32;
  const normalize = v => {const n=Math.hypot(...v);return v.map(x=>x/n)};
  const cross = (a,b) => [a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0]];
  const center = t => [(1+.32*Math.cos(3*t))*Math.cos(2*t),(1+.32*Math.cos(3*t))*Math.sin(2*t),.52*Math.sin(3*t)];
  const mesh = [];
  for (let i=0;i<segments;i++) {
    const t=i/segments*Math.PI*2, c=center(t), next=center(t+.001);
    const tangent=normalize(next.map((v,j)=>v-c[j]));
    const normal=normalize(cross(tangent,[0,0,1]));
    const binormal=cross(tangent,normal);
    for (let j=0;j<sides;j++) {
      const a=j/sides*Math.PI*2;
      const n=normal.map((v,k)=>v*Math.cos(a)+binormal[k]*Math.sin(a));
      mesh.push({p:c.map((v,k)=>v+n[k]*.235),n});
    }
  }
  let pointerX=0, pointerY=0, cameraX=0, cameraY=0;
  function rotate(v) {
    const ay=phase*.6+cameraX*.35, ax=.45+Math.sin(phase*.4)*.22+cameraY*.3;
    const x=v[0]*Math.cos(ay)+v[2]*Math.sin(ay), z=-v[0]*Math.sin(ay)+v[2]*Math.cos(ay);
    const y=v[1]*Math.cos(ax)-z*Math.sin(ax), zz=v[1]*Math.sin(ax)+z*Math.cos(ax);
    const az=-.3+Math.sin(phase*.25)*.18;
    return [x*Math.cos(az)-y*Math.sin(az),x*Math.sin(az)+y*Math.cos(az),zz];
  }
  function draw() {
    if (!context || !width || !height) return;
    const ctx=context, cx=width*.5, cy=height*.46;
    ctx.clearRect(0,0,width,height);
    const radius=Math.min(width,height)*.265;
    const halo=ctx.createRadialGradient(cx,cy,20,cx,cy,radius*1.95);
    halo.addColorStop(0,'#a340ff42');halo.addColorStop(.55,'#6124c522');halo.addColorStop(1,'#6124c500');
    ctx.fillStyle=halo;ctx.fillRect(0,0,width,height);
    // Ground plane anchors the floating sculpture in space.
    ctx.save();ctx.translate(cx,height*.84);ctx.scale(1,.22);
    const shadow=ctx.createRadialGradient(0,0,0,0,0,radius*1.4);
    shadow.addColorStop(0,'#b259ff66');shadow.addColorStop(.5,'#6926bf30');shadow.addColorStop(1,'#09091100');
    ctx.fillStyle=shadow;ctx.beginPath();ctx.arc(0,0,radius*1.4,0,Math.PI*2);ctx.fill();
    for(let i=0;i<3;i++){ctx.beginPath();ctx.ellipse(0,0,radius*(1.1+i*.28),radius*(1.1+i*.28),0,0,Math.PI*2);ctx.strokeStyle=i===0?'#ae7fff66':'#ae7fff22';ctx.lineWidth=1;ctx.stroke()}
    ctx.restore();
    const vertices=mesh.map(v=>{
      const p=rotate(v.p),n=rotate(v.n),scale=4.8/(4.8-p[2]);
      return {x:cx+p[0]*radius*scale,y:cy+p[1]*radius*scale,z:p[2],n};
    });
    const faces=[];
    for(let i=0;i<segments;i++) for(let j=0;j<sides;j++) {
      const ids=[i*sides+j,((i+1)%segments)*sides+j,((i+1)%segments)*sides+(j+1)%sides,i*sides+(j+1)%sides];
      const vs=ids.map(id=>vertices[id]);
      faces.push({vs,z:vs.reduce((sum,v)=>sum+v.z,0)/4});
    }
    faces.sort((a,b)=>a.z-b.z);
    for(const face of faces) {
      const vs=face.vs,n=normalize([0,1,2].map(k=>vs.reduce((sum,v)=>sum+v.n[k],0)));
      const diffuse=Math.max(0,n[0]*-.4+n[1]*-.6+n[2]*.69);
      const spec=Math.pow(Math.max(0,n[0]*-.25+n[1]*-.38+n[2]*.89),24);
      const rim=Math.pow(1-Math.abs(n[2]),3);
      const cyan=Math.max(0,n[0]*.8+n[1]*.2+n[2]*.35);
      const r=Math.min(255,35+100*diffuse+185*spec+60*rim);
      const g=Math.min(255,16+48*diffuse+200*spec+100*cyan+35*rim);
      const b=Math.min(255,85+130*diffuse+140*spec+65*cyan+65*rim);
      ctx.fillStyle=`rgb(${r|0},${g|0},${b|0})`;ctx.strokeStyle=ctx.fillStyle;ctx.lineWidth=.65;
      ctx.beginPath();vs.forEach((v,i)=>i?ctx.lineTo(v.x,v.y):ctx.moveTo(v.x,v.y));ctx.closePath();ctx.fill();ctx.stroke();
    }
    // Sparse foreground glints, at different depths.
    for(let i=0;i<25;i++) {
      const a=i*2.399+phase*.08, r=radius*(1.65+(i%4)*.12);
      const x=cx+Math.cos(a)*r,y=cy+Math.sin(a)*r*.85;
      ctx.fillStyle=i%5===0?'#c8f9ffbb':'#d0bbff55';ctx.beginPath();ctx.arc(x,y,i%5===0?1.7:.7,0,Math.PI*2);ctx.fill();
    }
  }
  function resize() {
    if (!context) return;
    const rect = canvas.getBoundingClientRect();
    width = rect.width; height = rect.height;
    const dpr = Math.min(devicePixelRatio || 1, 2);
    canvas.width = Math.round(width*dpr); canvas.height = Math.round(height*dpr);
    context.setTransform(dpr,0,0,dpr,0,0); draw();
  }
  function tick(time) {
    if (!last || time-last>=32) {
      if(last) phase+=Math.min(time-last,64)*.0003;
      last=time;cameraX+=(pointerX-cameraX)*.08;cameraY+=(pointerY-cameraY)*.08;draw();
    }
    frame=requestAnimationFrame(tick);
  }
  function sync() {
    root.classList.toggle('motion-paused',paused);
    if (button) {
      button.setAttribute('aria-pressed',String(paused));
      button.textContent = paused ? '▶ Reprendre les animations' : 'Ⅱ Mettre en pause';
    }
    cancelAnimationFrame(frame); last=0;
    const active = !paused && !document.hidden && visible;
    if (active && context) frame=requestAnimationFrame(tick);
    if (video) {
      if (active) {
        if (!video.src) video.src=video.dataset.src;
        video.play().catch(() => { /* Poster remains visible if autoplay is unavailable. */ });
      } else video.pause();
    }
    window.dispatchEvent(new CustomEvent('motionchange',{detail:{paused:paused || document.hidden}}));
  }
  button?.addEventListener('click',()=>{
    paused=!paused;
    try { sessionStorage.setItem('devantiq-motion-paused',String(paused)); } catch { /* Optional preference. */ }
    sync();
  });
  reduced.addEventListener('change',()=>{paused=reduced.matches;sync()});
  document.addEventListener('visibilitychange',sync);
  document.querySelectorAll('.project-card, #services .card-hover, .universe').forEach(card=>{
    card.addEventListener('pointermove',event=>{
      if (paused || !finePointer.matches) return;
      const rect=card.getBoundingClientRect();
      const x=(event.clientX-rect.left)/rect.width;
      const y=(event.clientY-rect.top)/rect.height;
      if(card.classList.contains('universe')) {pointerX=(x-.5)*2;pointerY=(y-.5)*2}
      card.style.setProperty('--rx',`${(y-.5)*-16}deg`);
      card.style.setProperty('--ry',`${(x-.5)*20}deg`);
      card.style.setProperty('--mx',`${x*100}%`);
      card.style.setProperty('--my',`${y*100}%`);
    });
    card.addEventListener('pointerleave',()=>{
      if(card.classList.contains('universe')) {pointerX=0;pointerY=0}
      card.style.setProperty('--rx','0deg');card.style.setProperty('--ry','0deg');
    });
  });
  if ('IntersectionObserver' in window) {
    root.classList.add('js-motion');
    const reveal=new IntersectionObserver(entries=>entries.forEach(entry=>{
      if (entry.isIntersecting) {entry.target.classList.add('visible');reveal.unobserve(entry.target)}
    }),{threshold:.08});
    document.querySelectorAll('.reveal').forEach(el=>reveal.observe(el));
    if (canvas) new IntersectionObserver(entries=>{visible=entries[0].isIntersecting;sync()},{rootMargin:'100px'}).observe(canvas);
  }
  if (canvas) {new ResizeObserver(resize).observe(canvas);resize()}
  sync();
})();
