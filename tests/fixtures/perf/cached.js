// E8.4 fixture asset (see cached.html): a box whose colour and size follow t.
window.MOTION = { width: 160, height: 160, fps: 24, duration: 1, loop: false };
window.ready = Promise.resolve();
window.seek = t => {
  const s = document.getElementById('s'), g = Math.round(40 + 180 * t);
  s.style.background = `rgb(${g},90,${255 - g})`;
  s.style.width = (60 + 100 * t) + 'px';
};
