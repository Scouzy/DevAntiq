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
  // Extrude the original alpha contour into connected side surfaces.
  let logo = null, litLogo = null, reflection = null, contours=[], sideMesh=[];
  // Trace the alpha boundary once, then join rings into real side surfaces.
  // Unlike stacked sprites, these surfaces retain their area exactly at profile.
  function traceContours(mask) {
    const step=1, w=mask.width, h=mask.height;
    const rgba=mask.getContext('2d').getImageData(0,0,mask.width,mask.height).data;
    const filled=(x,y)=>x>=0 && y>=0 && x<w && y<h &&
      rgba[(y*mask.width+x)*4+3]>127;
    const edges=new Map(),key=(x,y)=>x+','+y;
    const edge=(x,y,u,v)=>{const k=key(x,y);if(!edges.has(k)) edges.set(k,[]);edges.get(k).push([u,v])};
    for(let y=0;y<h;y++) for(let x=0;x<w;x++) if(filled(x,y)) {
      if(!filled(x,y-1)) edge(x,y,x+1,y);
      if(!filled(x+1,y)) edge(x+1,y,x+1,y+1);
      if(!filled(x,y+1)) edge(x+1,y+1,x,y+1);
      if(!filled(x-1,y)) edge(x,y+1,x,y);
    }
    function simplify(points) {
      if(points.length<=2) return points;
      const a=points[0],b=points[points.length-1],dx=b[0]-a[0],dy=b[1]-a[1],length=dx*dx+dy*dy;
      let best=1.2*1.2,index=-1;
      for(let i=1;i<points.length-1;i++) {
        const t=length?Math.max(0,Math.min(1,((points[i][0]-a[0])*dx+(points[i][1]-a[1])*dy)/length)):0;
        const d=(points[i][0]-a[0]-t*dx)**2+(points[i][1]-a[1]-t*dy)**2;
        if(d>best) {best=d;index=i}
      }
      return index<0?[a,b]:simplify(points.slice(0,index+1)).slice(0,-1).concat(simplify(points.slice(index)));
    }
    const loops=[];
    while(edges.size) {
      const start=edges.keys().next().value,points=[start.split(',').map(Number)];
      let current=start;
      do {
        const next=edges.get(current);if(!next) break;
        const point=next.pop();if(!next.length) edges.delete(current);
        points.push(point);current=key(...point);
      } while(current!==start);
      if(current===start && points.length>8) {
        const half=Math.floor(points.length/2);
        let loop=simplify(points.slice(0,half+1)).slice(0,-1).concat(simplify(points.slice(half)).slice(0,-1));
        // Round the traced pixel corners once, rather than exposing the raster
        // staircase as a gold edge. Closed-loop subdivision preserves holes.
        loop=loop.flatMap((a,i)=>{
          const b=loop[(i+1)%loop.length];
          return [[a[0]*.75+b[0]*.25,a[1]*.75+b[1]*.25],
            [a[0]*.25+b[0]*.75,a[1]*.25+b[1]*.75]];
        });
        loops.push(loop.map(([x,y])=>[(x*step-mask.width/2)/mask.width,(y*step-mask.height/2)/mask.width]));
      }
    }
    return loops;
  }
  let pointerX=0, pointerY=0, cameraX=0, cameraY=0, appPitch=0;
  let rotation=-.60, activeApp=null, hoveredApp=null;
  const universe=document.querySelector('.universe');
  const satellites=Array.from(document.querySelectorAll('.app-satellite'));
  const appColors=satellites.map((element,i)=>element.dataset.color || `hsl(${i*360/satellites.length} 70% 72%)`);
  const bodies=satellites.map((element,i)=>({element,time:i*.83,period:4.2+i*.47,w:0,h:0,impact:null,
    angle:(Number.isFinite(Number(element.dataset.angle)) ? Number(element.dataset.angle) : -90+i*360/satellites.length)*Math.PI/180}));
  const sphereRadius=()=>Math.min(width,height)*.36;
  function moveSatellites() {
    if(!width || !height) return;
    bodies.forEach((body,i)=>{
      const t=(body.time/body.period)%1;
      const angle=body.angle;
      const tilt=((Math.cos(angle)<-.1?-7:Math.cos(angle)>.1?7:0)+Math.sin(t*Math.PI*2)*4)*Math.PI/180;
      const nx=Math.cos(angle),ny=Math.sin(angle),r=sphereRadius();
      const localAngle=angle-tilt;
      // Distance from the sphere centre to a rotated rectangular card.
      let low=r,high=r+body.w+body.h;
      for(let j=0;j<18;j++) {
        const mid=(low+high)/2;
        const dx=Math.max(0,Math.abs(Math.cos(localAngle)*mid)-body.w/2);
        const dy=Math.max(0,Math.abs(Math.sin(localAngle)*mid)-body.h/2);
        if(Math.hypot(dx,dy)<r) low=mid; else high=mid;
      }
      const distance=high+Math.sin(Math.PI*t)*Math.min(30,width*.05);
      const x=width*.5+nx*distance,y=height*.46+ny*distance;
      body.element.style.transform=`translate3d(${x-body.w/2}px,${y-body.h/2}px,0) rotate(${tilt}rad)`;
      // The nearest card corner determines the actual point of contact.
      const lx=-Math.cos(localAngle)*high,ly=-Math.sin(localAngle)*high;
      const qx=Math.max(-body.w/2,Math.min(body.w/2,lx));
      const qy=Math.max(-body.h/2,Math.min(body.h/2,ly));
      body.impact={x:width*.5+nx*high+qx*Math.cos(tilt)-qy*Math.sin(tilt),y:height*.46+ny*high+qx*Math.sin(tilt)+qy*Math.cos(tilt),age:t};
    });
  }
  function drawGlass(ctx,cx,cy) {
    const r=sphereRadius();
    ctx.save();
    const glass=ctx.createRadialGradient(cx-r*.3,cy-r*.4,r*.1,cx,cy,r);
    glass.addColorStop(0,'#d3f4ff03');glass.addColorStop(.7,'#81bfff00');
    glass.addColorStop(.92,'#92bfff16');glass.addColorStop(.985,'#b9e4ff45');glass.addColorStop(1,'#e4f8ff88');
    ctx.fillStyle=glass;ctx.beginPath();ctx.arc(cx,cy,r,0,Math.PI*2);ctx.fill();
    ctx.strokeStyle='#badfff70';ctx.lineWidth=1.2;ctx.stroke();
    ctx.shadowColor='#8fcfff';ctx.shadowBlur=12;
    ctx.strokeStyle='#effbffb0';ctx.lineWidth=3;
    ctx.beginPath();ctx.arc(cx,cy,r*.965,Math.PI*1.12,Math.PI*1.57);ctx.stroke();
    ctx.strokeStyle='#a8d9ff55';ctx.lineWidth=5;
    ctx.beginPath();ctx.arc(cx,cy,r*.94,.06,.64);ctx.stroke();
    ctx.shadowBlur=0;
    const shine=ctx.createRadialGradient(cx-r*.38,cy-r*.58,0,cx-r*.38,cy-r*.58,r*.24);
    shine.addColorStop(0,'#f0fbff44');shine.addColorStop(1,'#e0f5ff00');
    ctx.fillStyle=shine;ctx.beginPath();ctx.ellipse(cx-r*.38,cy-r*.58,r*.24,r*.12,-.6,0,Math.PI*2);ctx.fill();
    bodies.forEach((body,i)=>{
      if(!body.impact || body.impact.age>.16 || paused || body.element===activeApp) return;
      const p=body.impact.age/.16;
      ctx.globalAlpha=(1-p)*.8;ctx.strokeStyle=appColors[i];ctx.lineWidth=2*(1-p)+.5;
      ctx.beginPath();ctx.arc(body.impact.x,body.impact.y,4+p*22,0,Math.PI*2);ctx.stroke();
    });
    ctx.restore();
  }
  satellites.forEach((app,i)=>app.style.setProperty('--app-color',appColors[i]));
  function updateActiveApp() {
    activeApp=hoveredApp || satellites.find(app=>app.contains(document.activeElement));
    satellites.forEach(app=>app.classList.toggle('app-active',app===activeApp));
    universe?.classList.toggle('app-engaged',Boolean(activeApp));
    draw();
  }
  satellites.forEach(app=>{
    app.addEventListener('pointerenter',event=>{
      if(event.pointerType==='mouse' && finePointer.matches) {hoveredApp=app;updateActiveApp()}
    });
    app.addEventListener('pointerleave',()=>{if(hoveredApp===app) hoveredApp=null;updateActiveApp()});
    app.addEventListener('focus',updateActiveApp);
    app.addEventListener('blur',()=>queueMicrotask(updateActiveApp));
  });
  if (context) {
    const source=new Image();
    source.onload=()=>{
      // Soften the silhouette corners once, retaining a crisp antialiased contour.
      const rounded=document.createElement('canvas');rounded.width=source.naturalWidth;rounded.height=source.naturalHeight;
      const roundContext=rounded.getContext('2d');
      if (!roundContext) return;
      roundContext.filter='blur(12px)';roundContext.drawImage(source,0,0);roundContext.filter='none';
      const pixels=roundContext.getImageData(0,0,rounded.width,rounded.height);
      for(let i=3;i<pixels.data.length;i+=4) {
        const t=Math.max(0,Math.min(1,(pixels.data[i]-108)/38));
        pixels.data[i]=Math.round(255*t*t*(3-2*t));
      }
      roundContext.putImageData(pixels,0,0);
      contours=traceContours(rounded);
      const levels=[-1,-.98,-.92,-.85,-.80,-.65,-.4,-.2,.2,.4,.65,.80,.85,.92,.98,1];
      const ring=(point,t)=>{
        const bevel=Math.max(0,(Math.abs(t)-.2)/.8);
        const size=.9+.1*Math.sqrt(Math.max(0,1-bevel*bevel));
        return [point[0]*size,point[1]*size,t*.11];
      };
      sideMesh=[];
      for(const contour of contours) for(let j=0;j<levels.length-1;j++) {
        const lo=levels[j],hi=levels[j+1];
        const gold=Math.abs((lo+hi)/2)>.80 && Math.abs((lo+hi)/2)<.85;
        for(let i=0;i<contour.length;i++) {
          const a=contour[i],b=contour[(i+1)%contour.length];
          sideMesh.push({points:[ring(a,lo),ring(b,lo),ring(b,hi),ring(a,hi)],gold});
        }
      }
      const face=document.createElement('canvas');face.width=rounded.width;face.height=rounded.height;
      const faceContext=face.getContext('2d');
      if (!faceContext) return;
      // Enhance the source itself: no opaque color layer over its internal facets.
      faceContext.filter='brightness(1.9) saturate(1.25) contrast(1.1)';
      faceContext.drawImage(source,0,0);
      faceContext.filter='none';
      faceContext.globalCompositeOperation='destination-in';faceContext.drawImage(rounded,0,0);
      logo=face;
      // Bake the face lighting once. A canvas filter on every rotated frame
      // repeatedly rasterizes the texture and can interrupt smooth motion.
      litLogo=document.createElement('canvas');litLogo.width=face.width;litLogo.height=face.height;
      const litContext=litLogo.getContext('2d');
      litContext.filter='brightness(1.1)';litContext.drawImage(face,0,0);
      reflection=document.createElement('canvas');reflection.width=face.width;reflection.height=face.height;
      document.querySelector('.universe').classList.add('brand-canvas-ready');
      draw();
    };
    source.src='./img/devantiq-logo.png';
  }
  function drawLogo(ctx,cx,cy) {
    if (!logo) return;
    const logoWidth=sphereRadius()*1.63;
    const logoHeight=logoWidth*logo.height/logo.width;
    const depth=logoWidth*.22;
    const yaw=rotation+cameraX*.22;
    const pitch=-.24+cameraY*.15+appPitch;
    const cosY=Math.cos(yaw),sinY=Math.sin(yaw),cosX=Math.cos(pitch),sinX=Math.sin(pitch);
    const front=cosY>=0;
    function plane(image,z,mirror=false,size=1) {
      ctx.save();
      ctx.translate(cx+sinY*z,cy-cosY*sinX*z);
      ctx.transform(cosY,sinY*sinX,0,cosX,0,0);
      if(mirror) ctx.scale(-1,1);
      ctx.scale(size,size);
      ctx.drawImage(image,-logoWidth/2,-logoHeight/2,logoWidth,logoHeight);
      ctx.restore();
    }
    // Connected side quads stay solid at 90 degrees. There is no slice-order
    // switch, artificial minimum width or superposition of different angles.
    const surfaces=[];
    for(const face of sideMesh) {
      const points=face.points.map(([x,y,z])=>[
        cx+logoWidth*(cosY*x+sinY*z),
        cy+logoWidth*(sinY*sinX*x+cosX*y-cosY*sinX*z),
        -sinY*cosX*x+sinX*y+cosY*cosX*z
      ]);
      const a=points[0],b=points[1],d=points[3];
      const area=(b[0]-a[0])*(d[1]-a[1])-(b[1]-a[1])*(d[0]-a[0]);
      if(area<=0) continue;
      const depth=points.reduce((sum,p)=>sum+p[2],0)/4;
      surfaces.push({points,depth,gold:face.gold});
    }
    surfaces.sort((a,b)=>a.depth-b.depth);
    ctx.save();ctx.lineWidth=.25;ctx.lineJoin='round';
    for(const surface of surfaces) {
      const points=surface.points;
      const meanY=points.reduce((sum,p)=>sum+p[1],0)/points.length;
      const light=Math.max(0,Math.min(1,.55-(meanY-cy)/logoHeight));
      ctx.fillStyle=surface.gold
        ? `rgb(${Math.round(135+95*light)},${Math.round(91+90*light)},${Math.round(24+57*light)})`
        : '#020305';
      ctx.strokeStyle=ctx.fillStyle;
      ctx.beginPath();ctx.moveTo(points[0][0],points[0][1]);
      for(let i=1;i<points.length;i++) ctx.lineTo(points[i][0],points[i][1]);
      ctx.closePath();ctx.fill();ctx.stroke();
    }
    ctx.restore();
    const faceZ=(front?1:-1)*(depth/2+.8);
    // Fade the face smoothly into the black edge before swapping front/back.
    const faceVisibility=Math.min(1,Math.abs(cosY)/.10);
    ctx.save();
    ctx.globalAlpha*=faceVisibility*faceVisibility*(3-2*faceVisibility);
    plane(litLogo,faceZ,!front,.90);
    // Moving blue specular reflection, clipped to the face rather than a rectangle.
    const shine=reflection.getContext('2d');
    if (shine) {
      shine.globalCompositeOperation='source-over';shine.clearRect(0,0,reflection.width,reflection.height);
      shine.drawImage(logo,0,0);shine.globalCompositeOperation='source-in';
      const sweep=(.5+.45*Math.sin(yaw*1.4))*reflection.width;
      const light=shine.createLinearGradient(sweep-reflection.width*.45,0,sweep+reflection.width*.45,reflection.height*.3);
      light.addColorStop(0,'#365db900');light.addColorStop(.2,'#365db900');
      light.addColorStop(.43,'#7da8ef0a');light.addColorStop(.5,'#93bdff22');
      light.addColorStop(.57,'#7da8ef0a');light.addColorStop(.8,'#365db900');light.addColorStop(1,'#365db900');
      shine.fillStyle=light;shine.fillRect(0,0,reflection.width,reflection.height);
      plane(reflection,faceZ+(front?1:-1)*.1,!front,.90);
    }
    ctx.restore();
  }
  function drawAppConnection(ctx,cx,cy) {
    if(!activeApp) return;
    const rect=activeApp.getBoundingClientRect(), bounds=canvas.getBoundingClientRect();
    const targetX=(rect.left+rect.width/2-bounds.left)*width/bounds.width;
    const targetY=(rect.top+rect.height/2-bounds.top)*height/bounds.height;
    const dx=targetX-cx,dy=targetY-cy,length=Math.hypot(dx,dy)||1;
    const distance=Math.min(width,height)*.20;
    const startX=cx+dx/length*distance,startY=cy+dy/length*distance;
    const color=appColors[satellites.indexOf(activeApp)];
    ctx.save();ctx.strokeStyle=color;ctx.shadowColor=color;ctx.shadowBlur=12;ctx.lineWidth=1.5;
    ctx.beginPath();ctx.moveTo(startX,startY);ctx.lineTo(targetX,targetY);ctx.stroke();
    const t=paused?.5:(phase*.7)%1;
    ctx.fillStyle=color;ctx.beginPath();ctx.arc(startX+(targetX-startX)*t,startY+(targetY-startY)*t,3,0,Math.PI*2);ctx.fill();
    ctx.beginPath();ctx.arc(startX,startY,5,0,Math.PI*2);ctx.stroke();ctx.restore();
  }
  function draw() {
    if (!context || !width || !height) return;
    moveSatellites();
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
    drawLogo(ctx,cx,cy);
    drawGlass(ctx,cx,cy);
    drawAppConnection(ctx,cx,cy);
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
    universe.classList.add('glass-physics');
    bodies.forEach(body=>{body.w=body.element.offsetWidth;body.h=body.element.offsetHeight});
    // Supersample thin gold edges even on standard-density desktop displays.
    const dpr = 2;
    canvas.width = Math.round(width*dpr); canvas.height = Math.round(height*dpr);
    context.setTransform(dpr,0,0,dpr,0,0); draw();
  }
  function tick(time) {
      // Draw on every display frame; skipping alternate frames made the
      // thin silhouette visibly step as it rotated. Bound long-frame jumps.
      const delta=last?Math.min(time-last,32):0;
      phase+=delta*.0003;
      bodies.forEach(body=>{if(body.element!==activeApp) body.time+=delta/1000});
      if(activeApp) {
        const target=Math.cos(bodies[satellites.indexOf(activeApp)].angle)*.75;
        const difference=Math.atan2(Math.sin(target-rotation),Math.cos(target-rotation));
        rotation+=difference*(1-Math.exp(-delta*.004));
      } else rotation=(rotation+delta*.000225)%(Math.PI*2);
      const easing=1-Math.exp(-delta*.004);
      cameraX+=(pointerX-cameraX)*easing;
      cameraY+=(pointerY-cameraY)*easing;
      const targetPitch=activeApp?(satellites.indexOf(activeApp)>1?.10:-.10):0;
      appPitch+=(targetPitch-appPitch)*easing;
      last=time;draw();
    frame=requestAnimationFrame(tick);
  }
  function sync() {
    root.classList.toggle('motion-paused',paused);
    root.classList.toggle('motion-enabled',!paused);
    if (button) {
      button.setAttribute('aria-pressed',String(paused));
      button.textContent = paused ? '▶ Reprendre les animations' : 'Ⅱ Mettre en pause';
    }
    cancelAnimationFrame(frame); last=0;
    const active = !paused && !document.hidden && visible;
    document.querySelector('.universe')?.classList.toggle('scene-idle',!active);
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
