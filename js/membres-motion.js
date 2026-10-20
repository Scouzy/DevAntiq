(() => {
  'use strict';
  const root = document.body;
  const button = document.getElementById('member-motion');
  const grid = document.getElementById('applications');
  if (!button || !grid) return;
  const reduced = matchMedia('(prefers-reduced-motion: reduce)');
  const fine = matchMedia('(hover: hover) and (pointer: fine)');
  let paused = reduced.matches;
  let active = null;
  let frame = 0;
  function reset() {
    cancelAnimationFrame(frame);
    if (active) {
      active.style.removeProperty('--tilt-x');
      active.style.removeProperty('--tilt-y');
    }
    active = null;
  }
  function sync() {
    root.classList.toggle('motion-paused', paused || document.hidden);
    root.classList.toggle('motion-enabled', !paused);
    button.setAttribute('aria-pressed', String(paused));
    button.textContent = paused ? 'Activer les animations' : 'Mettre en pause';
    reset();
  }
  button.hidden = false;
  button.addEventListener('click', () => { paused = !paused; sync(); });
  reduced.addEventListener('change', () => { paused = reduced.matches; sync(); });
  document.addEventListener('visibilitychange', sync);
  grid.addEventListener('pointermove', event => {
    if (paused || !fine.matches || event.pointerType !== 'mouse') return;
    const card = event.target.closest('.app-card');
    if (!card) { reset(); return; }
    if (active !== card) { reset(); active = card; }
    cancelAnimationFrame(frame);
    frame = requestAnimationFrame(() => {
      const rect = card.getBoundingClientRect();
      const x = Math.max(-.5, Math.min(.5, (event.clientX - rect.left) / rect.width - .5));
      const y = Math.max(-.5, Math.min(.5, (event.clientY - rect.top) / rect.height - .5));
      card.style.setProperty('--tilt-x', `${-y * 7}deg`);
      card.style.setProperty('--tilt-y', `${x * 9}deg`);
    });
  });
  grid.addEventListener('pointerleave', reset);
  grid.addEventListener('focusin', reset);
  sync();
})();
