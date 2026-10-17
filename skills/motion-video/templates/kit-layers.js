/* =========================================================================
   MOTION KIT · LAYERS ADD-ON (kit-layers.js) — several engines on one timeline (E10.12) and
   gate-visible boxes for text drawn on a canvas (E10.13). Load after kit.js (and after any
   engine add-on: kit-p5.js, kit-zdog.js).

   K.layers([{ name, el, ready, seek, blend }], { stage }) stacks the layers in order (first =
   back), builds window.ready / window.seek, and seeks every layer for the same t.
   Rule of thumb: one engine per depth plane (p5 atmosphere → Zdog characters → Three hero →
   DOM type), no shared depth between layers, at most one WebGL layer (render with --gl).
   ========================================================================= */
(() => {
  const K = window.K;
  if (!K) throw new Error('kit-layers.js: load kit.js first');

  // layer: { name, el (element, or () => element once ready), ready (promise or fn), seek(t),
  //          blend ('multiply' | 'screen' | …: CSS mix-blend-mode), opacity }
  function layers(list, o = {}) {
    if (!K.FORMAT) throw new Error('K.layers: call K.init(window.MOTION) first');
    const stage = o.stage || document.getElementById('stage');
    if (!stage) throw new Error('K.layers: no #stage element (pass { stage })');
    const names = new Set();
    list.forEach(L => {
      if (!L.name || names.has(L.name)) throw new Error(`K.layers: every layer needs a unique name (got "${L.name}")`);
      if (typeof L.seek !== 'function') throw new Error(`K.layers: layer "${L.name}" has no seek(t)`);
      names.add(L.name);
    });
    const { W, H } = K.FORMAT;
    const place = (L, i) => {
      const el = typeof L.el === 'function' ? L.el() : L.el;
      if (!el) return;
      if (el.parentElement !== stage) stage.appendChild(el);
      // canvases keep their W*dpr backing store; only the CSS box is set here
      Object.assign(el.style, { position: 'absolute', left: '0px', top: '0px', width: W + 'px', height: H + 'px',
        zIndex: String(i + 1), mixBlendMode: L.blend || '', opacity: L.opacity ?? '' });
      el.dataset.layer = L.name;
    };
    const ready = Promise.all(list.map(L => typeof L.ready === 'function' ? L.ready() : L.ready))
      .then(() => { list.forEach(place); });
    // layers draw back to front for the same t; each seek may be async (p5 redraw, image decode)
    const seek = async t => { await ready; for (const L of list) await L.seek(t); };
    if (o.install !== false) { window.ready = ready; window.seek = seek; }
    return { ready, seek, layers: list };
  }

  // ---- gate proxies (E10.13) ----
  // Canvas-drawn text is invisible to the safe_area / text_duration gates (they read the DOM).
  // K.proxy(name, box, { safe, text }) adds an empty, transparent DOM box with data-safe /
  // data-text; keep it on the drawn text every frame with p.set(box, alpha). box = { x, y, w, h }
  // in stage px (from K.Z.project, K.textBox, or the engine's own projection); alpha = the drawn
  // text's opacity (0 hides it from the gates, ≥ 0.9 counts as readable).
  function proxy(name, box, o = {}) {
    const parent = o.parent || document.getElementById('stage');
    if (!parent) throw new Error('K.proxy: no #stage element (pass { parent })');
    const el = document.createElement('div');
    el.id = name;
    el.className = 'k-proxy';
    if (o.safe !== false) el.setAttribute('data-safe', '');
    if (o.text !== false) el.setAttribute('data-text', '');
    Object.assign(el.style, { position: 'absolute', left: '0px', top: '0px', pointerEvents: 'none',
      background: 'transparent', zIndex: '99' });
    parent.appendChild(el);
    const p = {
      el,
      set(b, alpha = 1) {
        if (!b) return p.hide();
        Object.assign(el.style, { left: b.x + 'px', top: b.y + 'px', width: Math.max(0, b.w) + 'px',
          height: Math.max(0, b.h) + 'px', opacity: String(K.clamp(alpha)) });
        return p;
      },
      hide() { el.style.opacity = '0'; return p; },
    };
    p.set(box, box ? 1 : 0);
    return p;
  }

  // Ink box of text drawn on a 2D context at (x, y) with the context's current font, textAlign
  // and textBaseline -> { x, y, w, h } in the context's user units (CSS px for p5 and K.Z canvases
  // drawn without a scale transform). For p5: K.textBox(p.drawingContext, str, x, y).
  function textBox(ctx, str, x, y) {
    const m = ctx.measureText(str);
    const left = m.actualBoundingBoxLeft, right = m.actualBoundingBoxRight;
    const up = m.actualBoundingBoxAscent, down = m.actualBoundingBoxDescent;
    return { x: x - left, y: y - up, w: left + right, h: up + down };
  }

  Object.assign(K, { layers, proxy, textBox });
})();
