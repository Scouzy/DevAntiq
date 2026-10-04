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
  const points = Array.from({length: 420}, (_, i) => {
    const y = 1 - i / 419 * 2;
    const r = Math.sqrt(1 - y * y);
    const a = i * Math.PI * (3 - Math.sqrt(5));
    return {x: Math.cos(a) * r, y, z: Math.sin(a) * r};
  });
  function draw() {
    if (!context) return;
    context.clearRect(0, 0, width, height);
    const radius = Math.min(width, height) * .325;
    const projected = points.map(p => {
      const x = p.x * Math.cos(phase) + p.z * Math.sin(phase);
      const z = -p.x * Math.sin(phase) + p.z * Math.cos(phase);
      const perspective = 3 / (3 - z * .35);
      return {x: width / 2 + x * radius * perspective, y: height / 2 + p.y * radius * perspective, z};
    }).sort((a,b) => a.z - b.z);
    for (const p of projected) {
      context.beginPath();
      context.arc(p.x,p.y,.6 + (p.z+1)*.7,0,Math.PI*2);
      context.fillStyle = `rgba(195,167,255,${.12+(p.z+1)*.32})`;
      context.fill();
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
    if (last) phase += Math.min(time-last,50)*.00012;
    last=time; draw(); frame=requestAnimationFrame(tick);
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
      card.style.setProperty('--rx',`${(y-.5)*-9}deg`);
      card.style.setProperty('--ry',`${(x-.5)*12}deg`);
      card.style.setProperty('--mx',`${x*100}%`);
      card.style.setProperty('--my',`${y*100}%`);
    });
    card.addEventListener('pointerleave',()=>{
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
