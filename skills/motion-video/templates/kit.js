/* =========================================================================
   MOTION KIT (kit.js) — small, dependency-free helpers shared by both templates.
   A classic script (not a module): load it with <script src="kit.js"></script>
   before the scene script. It defines window.K.

   RULES (the composition contract depends on them)
     - Everything is a pure function of t: same t -> same value, in any order.
     - No timers, no rAF-driven state, no Date.now()/performance.now(), no network.
     - Randomness only via K.rand(seed, i) (hash-based, seeded).
     - Copy this file next to your composition HTML (projects copy the template AND kit.js).
   ========================================================================= */
window.K = (() => {
  const clamp = (x, a = 0, b = 1) => Math.min(b, Math.max(a, x));
  const lerp = (a, b, p) => a + (b - a) * p;
  // progress of t through [a,b] -> 0..1
  const seg = (t, a, b) => clamp((t - a) / (b - a));
  const map = (t, a, b, c, d) => lerp(c, d, seg(t, a, b));

  // ---- easings (p in 0..1) ----
  const ease = {
    linear: p => p,
    inCubic: p => p * p * p,
    outCubic: p => 1 - Math.pow(1 - p, 3),
    inOutCubic: p => p < .5 ? 4 * p * p * p : 1 - Math.pow(-2 * p + 2, 3) / 2,
    outExpo: p => p >= 1 ? 1 : 1 - Math.pow(2, -10 * p),
    inExpo: p => p <= 0 ? 0 : Math.pow(2, 10 * p - 10),
    inOutExpo: p => p <= 0 ? 0 : p >= 1 ? 1 : p < .5 ? Math.pow(2, 20 * p - 10) / 2 : (2 - Math.pow(2, -20 * p + 10)) / 2,
    outQuint: p => 1 - Math.pow(1 - p, 5),
  };
  // CSS-style cubic-bezier(x1,y1,x2,y2) -> easing fn. Favourites:
  //   editorial entrance  bezier(.16,1,.3,1)      0.6-0.8s
  //   morph / camera      bezier(.45,0,.15,1)     ~0.8s (camera rides the same curve)
  function bezier(x1, y1, x2, y2) {
    const cx = 3 * x1, bx = 3 * (x2 - x1) - cx, ax = 1 - cx - bx;
    const cy = 3 * y1, by = 3 * (y2 - y1) - cy, ay = 1 - cy - by;
    const sx = s => ((ax * s + bx) * s + cx) * s, sy = s => ((ay * s + by) * s + cy) * s;
    const dx = s => (3 * ax * s + 2 * bx) * s + cx;
    return p => {
      if (p <= 0) return 0; if (p >= 1) return 1;
      let s = p;
      for (let i = 0; i < 8; i++) { const e = sx(s) - p, d = dx(s); if (Math.abs(e) < 1e-6 || !d) break; s -= e / d; }
      return sy(clamp(s));
    };
  }

  // ---- springs, closed form (never integrate!) ----
  // Critically damped step response 0->1, no overshoot. w ~ 12 (soft) .. 40 (snappy).
  const springCrit = (dt, w = 18) => dt <= 0 ? 0 : 1 - (1 + w * dt) * Math.exp(-w * dt);
  // Under-damped step response with damping ratio z (z<1 -> small overshoot). Keep z >= .7 for UI.
  function spring(dt, w = 18, z = .8) {
    if (dt <= 0) return 0;
    if (z >= 1) return springCrit(dt, w);
    const wd = w * Math.sqrt(1 - z * z);
    return 1 - Math.exp(-z * w * dt) * (Math.cos(wd * dt) + (z * w / wd) * Math.sin(wd * dt));
  }
  // A value that retargets many times stays a pure function of t:
  // sum one spring step per target change. keys = [[time, value], ...] sorted by time.
  // Key times may be seconds or beat strings like '4b' (see K.T).
  function springTrack(keys, t, w = 18, z = 1) {
    let v = keys[0][1];
    for (let i = 1; i < keys.length; i++) {
      const kt = sec(keys[i][0]), kv = keys[i][1];
      if (t < kt) break;
      v += (kv - keys[i - 1][1]) * spring(t - kt, w, z);
    }
    return v;
  }
  // Eased keyframe track: keys = [[time, value, easeFn?], ...]; time in seconds or '4b' beats.
  function track(keys, t, defEase = ease.inOutCubic) {
    if (t <= sec(keys[0][0])) return keys[0][1];
    for (let i = 1; i < keys.length; i++) {
      const t1 = sec(keys[i][0]), v1 = keys[i][1], e = keys[i][2];
      if (t <= t1) { const t0 = sec(keys[i - 1][0]), v0 = keys[i - 1][1]; return lerp(v0, v1, (e || defEase)(seg(t, t0, t1))); }
    }
    return keys[keys.length - 1][1];
  }

  // ---- seeded randomness ----
  function rand(seed, i = 0) { // -> [0,1)
    let h = (Math.imul(seed | 0, 0x9E3779B1) ^ Math.imul(i | 0, 0x85EBCA77)) >>> 0;
    h = Math.imul(h ^ (h >>> 16), 0x7FEB352D); h = Math.imul(h ^ (h >>> 15), 0x846CA68B);
    return ((h ^ (h >>> 16)) >>> 0) / 4294967296;
  }
  // smooth value noise in 1D (for gentle drift), deterministic
  function noise(seed, x) {
    const i = Math.floor(x), f = x - i, u = f * f * (3 - 2 * f);
    return lerp(rand(seed, i), rand(seed, i + 1), u) * 2 - 1;
  }

  // ---- timing helpers ----
  const beats = bpm => ({ beat: 60 / bpm, bar: 240 / bpm, at: (n) => n * 60 / bpm });
  // local time of item i; start may be '8b' (a beat time), gap may be '0.5b' (a length in beats)
  const stagger = (t, start, i, gap) => t - (sec(start) + i * len(gap));
  // loop-safe time: wrap into [0, D)
  const wrap = (t, D) => t - D * Math.floor(t / D);

  // ---- beat time (E7.1) ----
  // window.BEATS comes from beats.js (written by beats.py); include it BEFORE kit.js.
  const BEATS_ERR = 'K.T/K.U need beats.js — run beats.py and add <script src="beats.js"> before the kit';
  const needBeats = () => { const B = window.BEATS; if (!B) throw new Error(BEATS_ERR); return B; };
  const T = u => { const B = needBeats(); return B.offset + u * B.period; };   // beats -> seconds
  const U = t => { const B = needBeats(); return (t - B.offset) / B.period; }; // seconds -> beats
  // A time: a number (seconds) or a string ending in 'b' (beat index, e.g. '16b', '16.5b').
  function sec(when) {
    if (typeof when === 'number') return when;
    if (typeof when === 'string' && /^-?\d+(\.\d+)?b$/.test(when.trim())) return T(parseFloat(when));
    throw new Error(`K: bad time ${JSON.stringify(when)} (use seconds, or a beat string like '16b')`);
  }
  // A length: seconds, or '2b' = two beat periods (no offset).
  const len = d => typeof d === 'string' && /b$/.test(d.trim()) ? parseFloat(d) * needBeats().period : sec(d);

  const K = { clamp, lerp, seg, map, ease, bezier, springCrit, spring, springTrack, track, rand, noise, beats, stagger, wrap };

  // ---- formats (E2.2) ----
  // One timeline, several aspect ratios. render.py --format X loads the page with
  // ?format=X&w=..&h=..; K.init(MOTION) applies it before the scene reads W/H.
  const FORMATS = {
    '16x9': { W: 1920, H: 1080 },
    '9x16': { W: 1080, H: 1920 },
    '1x1':  { W: 1080, H: 1080 },
    '4x5':  { W: 1080, H: 1350 },
  };
  // Safe rects as fractions [x, y, w, h] of W/H. title: 5 % inset everywhere.
  // ui: where text must stay so platform chrome (captions, buttons) doesn't cover it.
  const SAFE_TITLE = [.05, .05, .90, .90];
  const SAFE_UI = { '9x16': [.06, .12, .80, .66], '4x5': [.05, .08, .90, .80] };
  const rect = (f, W, H) => ({ x: Math.round(f[0] * W), y: Math.round(f[1] * H),
                               w: Math.round(f[2] * W), h: Math.round(f[3] * H) });

  // Call right after window.MOTION is defined, before any scene code reads W/H.
  function init(M) {
    const q = new URLSearchParams(location.search);
    let name = q.get('format') || 'native';
    if (name !== 'native' && !FORMATS[name])
      throw new Error(`K.init: unknown format "${name}" (use ${Object.keys(FORMATS).join(', ')})`);
    if (name !== 'native') { M.width = FORMATS[name].W; M.height = FORMATS[name].H; }
    if (q.has('w')) M.width = +q.get('w');
    if (q.has('h')) M.height = +q.get('h');
    const W = M.width, H = M.height;
    K.FORMAT = { name, W, H, isPortrait: H > W, aspect: W / H };
    K.safe = { title: rect(SAFE_TITLE, W, H), ui: rect(SAFE_UI[name] || SAFE_TITLE, W, H) };
    return M;
  }
  // K.pick({ '9x16': a, '1x1': b, default: c }) -> the value for the current format
  function pick(map) {
    if (!K.FORMAT) throw new Error('K.pick: call K.init(window.MOTION) first');
    const v = map[K.FORMAT.name] ?? map.default;
    if (v === undefined) throw new Error(`K.pick: no value for format "${K.FORMAT.name}" and no default`);
    return v;
  }
  // Preview helpers: the format cycle (native -> 16x9 -> 9x16 -> 1x1 -> 4x5 -> native) and the
  // query string that loads a format the same way render.py --format does.
  const CYCLE = ['native', ...Object.keys(FORMATS)];
  const nextFormat = () => CYCLE[(CYCLE.indexOf(K.FORMAT ? K.FORMAT.name : 'native') + 1) % CYCLE.length];
  function formatSearch(name) {
    const q = new URLSearchParams(location.search);
    ['format', 'w', 'h'].forEach(k => q.delete(k));
    if (name !== 'native') { q.set('format', name); q.set('w', FORMATS[name].W); q.set('h', FORMATS[name].H); }
    const s = q.toString();
    return s ? '?' + s : '';
  }
  Object.defineProperty(K, 'BEATS', { get: () => window.BEATS || null, enumerable: true });
  Object.assign(K, { T, U, at: T, sec, len });

  // ---- hits (E1.3): picture <-> sound sync points ----
  // MOTION.hits = [[when, label, sfx, opts?], ...]; when = seconds or '16b'; sfx = palette name or null.
  // render.py --hits writes them to hits.json for sfx.py. Returns [{t, label, sfx, opts}] sorted by t.
  function resolveHits() {
    const list = (window.MOTION && window.MOTION.hits) || [];
    return list.map(([when, label, sfx, opts], i) => ({
      t: sec(when), label, sfx: sfx === undefined ? null : sfx, opts: Object.assign({}, opts || {}), i,
    })).sort((a, b) => a.t - b.t || a.i - b.i).map(({ i, ...h }) => h);
  }
  K.resolveHits = resolveHits;

  // ---- video clips (E3.7): frame sequences from ingest.py, never <video>.currentTime ----
  // asset = an assets.json entry of kind 'video' (fps, frame_count, pattern like 'assets/video/x/%05d.jpg').
  const CLIPS = new Map();
  const clipKey = a => a.pattern || a.path;
  const framePath = (a, i) => {
    const p = a.pattern || (a.path.replace(/\/?$/, '/') + '%05d.jpg');
    return p.replace(/%0?(\d*)d/, (_, n) => String(i).padStart(+n || 0, '0'));
  };
  // Preload and decode every frame. Call inside window.ready: window.ready = K.loadClip(asset)
  // Long clips (E12.6): K.loadClip(asset, { window: 2 }) keeps only frames near the current seek
  // decoded (LRU, ~window s each side) instead of all of them (a 2 min 1080p clip is ~25 GB of
  // bitmaps). A windowed clip must be awaited per seek: `await K.clipSeek(asset, t)` in seek(t)
  // before drawing; it decodes that frame (and prefetches the next `ahead` s, default 0.5).
  async function loadClip(a, opts = {}) {
    if (CLIPS.has(clipKey(a))) return CLIPS.get(clipKey(a)).ready;
    const win = opts.window === true ? 2 : +opts.window || 0;
    if (win > 0) {
      const c = { win, ahead: opts.ahead ?? 0.5, map: new Map(), cur: -1, decoded: 0,
                  cap: Math.ceil((2 * win + (opts.ahead ?? 0.5)) * a.fps) + 2 };
      c.ready = decodeFrame(a, c, 0).then(() => c);
      CLIPS.set(clipKey(a), c);
      return c.ready;
    }
    const frames = [];
    for (let i = 0; i < a.frame_count; i++) { const img = new Image(); img.src = framePath(a, i); frames.push(img); }
    const ready = Promise.all(frames.map(img => img.decode().catch(() => {
      throw new Error(`K.loadClip: could not decode ${img.src} (asset "${a.id}")`);
    }))).then(() => frames);
    CLIPS.set(clipKey(a), { frames, ready });
    if (a.frame_count * (a.w || 0) * (a.h || 0) * 4 > 1.5e9)
      console.warn(`K.loadClip: "${a.id}" decodes to ~${(a.frame_count * a.w * a.h * 4 / 1e9).toFixed(1)} GB; use K.loadClip(asset, { window: 2 })`);
    return ready;
  }
  const frameIndex = (a, t) => clamp(Math.floor(t * a.fps + 1e-6), 0, a.frame_count - 1);
  // windowed clips: decode frame i once, keep it until the LRU (Map insertion order) drops it
  function decodeFrame(a, c, i) {
    let e = c.map.get(i);
    if (e) { c.map.delete(i); c.map.set(i, e); return e.p; }
    const img = new Image();
    img.src = framePath(a, i);
    e = { img, ok: false, p: null };
    e.p = img.decode().then(() => { e.ok = true; c.decoded++; return img; }, () => {
      c.map.delete(i);
      throw new Error(`K.loadClip: could not decode ${img.src} (asset "${a.id}")`);
    });
    c.map.set(i, e);
    for (const k of c.map.keys()) {           // oldest first; never the frame being drawn
      if (c.map.size <= c.cap) break;
      if (k !== c.cur && k !== i) c.map.delete(k);
    }
    return e.p;
  }
  // Make the frame for clip time t drawable (windowed clips; a no-op for preloaded ones).
  async function clipSeek(a, t) {
    const c = CLIPS.get(clipKey(a));
    if (!c) throw new Error(`K.clipSeek: clip "${a.id}" not loaded — await K.loadClip(asset, { window }) inside window.ready`);
    if (!c.map) return;
    const i = frameIndex(a, t);
    c.cur = i;
    await decodeFrame(a, c, i);
    c.cur = i;
    const n = Math.ceil(c.ahead * a.fps);
    for (let k = 1; k <= n && i + k < a.frame_count; k++) decodeFrame(a, c, i + k).catch(() => {});
  }
  const clipStats = a => { const c = CLIPS.get(clipKey(a)); return c && c.map ? { windowed: true, resident: c.map.size, cap: c.cap, decoded: c.decoded } : c ? { windowed: false, resident: c.frames.length } : null; };
  // Frame for clip time t: clamp(floor(t * fps), 0, frame_count - 1). The tiny epsilon keeps
  // t = k / fps on frame k despite float error (e.g. 0.3 * 10 = 2.9999...).
  function clipFrame(a, t) {
    const c = CLIPS.get(clipKey(a));
    if (!c) throw new Error(`K.clipFrame: clip "${a.id}" not loaded — await K.loadClip(asset) inside window.ready`);
    if (c.map) {
      const e = c.map.get(frameIndex(a, t));
      if (!e || !e.ok) throw new Error(`K.clipFrame: frame ${frameIndex(a, t)} of windowed clip "${a.id}" isn't decoded — await K.clipSeek(clip, t) in seek(t) first`);
      return e.img;
    }
    return c.frames[clamp(Math.floor(t * a.fps + 1e-6), 0, c.frames.length - 1)];
  }
  function drawClip(ctx, a, t, x = 0, y = 0, w, h) {
    const img = clipFrame(a, t);
    ctx.drawImage(img, x, y, w ?? img.naturalWidth, h ?? img.naturalHeight);
  }
  Object.assign(K, { loadClip, clipSeek, clipStats, clipFrame, drawClip });
  Object.assign(K, { FORMATS, init, pick, nextFormat, formatSearch, FORMAT: null, safe: null });

  // =======================================================================
  // ---- spring presets (E7.2): numbers from references/craft.md ----
  // Each preset is callable, K.SPRING.ui(dt) -> 0..1, and carries {w, z, settle, overshoot}.
  // settle = seconds until the step response stays within 2 % of the target.
  //   snappy  w 38.8 z 1     settle 0.15 s  no overshoot     presses, toggles, small UI
  //   ui      w 16.9 z 0.72  settle 0.35 s  3.8 % overshoot  shapes, cards ("shape" in craft.md)
  //   soft    w 11.7 z 1     settle 0.50 s  no overshoot     big panels, gentle arrivals
  //   camera  w 9.7  z 1     settle 0.60 s  no overshoot     camera; settles slower than the shape
  // K.spring(dt, K.SPRING.ui) and K.springTrack(keys, t, K.SPRING.camera) take a preset in place of (w, z).
  // =======================================================================
  const preset = (w, z, settle, overshoot) =>
    Object.freeze(Object.assign(dt => spring(dt, w, z), { w, z, settle, overshoot }));
  const SPRING = Object.freeze({
    snappy: preset(38.8, 1, 0.15, 0),
    ui: preset(16.9, 0.72, 0.35, 0.038),
    soft: preset(11.7, 1, 0.5, 0),
    camera: preset(9.7, 1, 0.6, 0),
  });
  const isPreset = p => typeof p === 'function' && typeof p.w === 'number';
  K.spring = (dt, w, z) => isPreset(w) ? spring(dt, w.w, w.z) : spring(dt, w, z);
  K.springTrack = (keys, t, w, z) => isPreset(w) ? springTrack(keys, t, w.w, w.z) : springTrack(keys, t, w, z);
  // Impacts, used sparingly (one element, one moment; bouncy easing is on the default banned list).
  // wobble: a decaying sine around 0 (add it to a rotation or offset); amp in your units.
  function wobble(dt, { amp = 1, freq = 5, decay = 9 } = {}) {
    return dt <= 0 ? 0 : amp * Math.exp(-decay * dt) * Math.sin(2 * Math.PI * freq * dt);
  }
  // squash: volume-preserving scale pair for a landing at dt = 0 -> {sx, sy}, sx * sy = 1.
  // amount 0.12 = 12 % wider at the peak; it settles like an under-damped spring (w, z).
  function squash(dt, { amount = 0.12, w = 30, z = 0.45 } = {}) {
    if (dt <= 0) return { sx: 1, sy: 1 };
    const wd = w * Math.sqrt(1 - z * z);
    const k = 1 + amount * Math.exp(-z * w * dt) * Math.cos(wd * dt);
    return { sx: k, sy: 1 / k };
  }
  Object.assign(K, { SPRING, wobble, squash });

  // =======================================================================
  // ---- image helpers (E3.4): K.cover / K.crop, CSS-built device frames ----
  // Supplied assets are used as-is: these only scale, crop, mask and move, never recolour.
  // target = a CanvasRenderingContext2D (box in canvas px) or a DOM element (the viewport: the
  // <img> goes inside it; box in the element's own px, default its full size).
  // opts: fx, fy = focal point 0..1 kept in view (default .5), zoom >= 1, radius (px or
  // [tl, tr, br, bl]), fit 'cover' (default) or 'contain' (letterbox, never crops: logos).
  // =======================================================================
  const natW = img => img.naturalWidth || img.videoWidth || img.width;
  const natH = img => img.naturalHeight || img.videoHeight || img.height;
  // Pure geometry for a source region crop {x,y,w,h} (image px) in a box -> {s, dest, view, src}:
  // dest = where the scaled crop lands, view = dest ∩ box (what shows), src = image px shown in view.
  function fitRect(crop, box, o = {}) {
    const zoom = Math.max(1, o.zoom ?? 1), fx = clamp(o.fx ?? .5), fy = clamp(o.fy ?? .5);
    const s = (o.fit === 'contain' ? Math.min(box.w / crop.w, box.h / crop.h)
                                   : Math.max(box.w / crop.w, box.h / crop.h)) * zoom;
    const dw = crop.w * s, dh = crop.h * s;
    // keep the focal point centred, but never expose an edge (cover) or crop (contain)
    const ox = dw >= box.w ? clamp(box.w / 2 - fx * dw, box.w - dw, 0) : (box.w - dw) * fx;
    const oy = dh >= box.h ? clamp(box.h / 2 - fy * dh, box.h - dh, 0) : (box.h - dh) * fy;
    const dest = { x: box.x + ox, y: box.y + oy, w: dw, h: dh };
    const x0 = Math.max(box.x, dest.x), y0 = Math.max(box.y, dest.y);
    const x1 = Math.min(box.x + box.w, dest.x + dw), y1 = Math.min(box.y + box.h, dest.y + dh);
    const view = { x: x0, y: y0, w: Math.max(0, x1 - x0), h: Math.max(0, y1 - y0) };
    const src = { x: crop.x + (x0 - dest.x) / s, y: crop.y + (y0 - dest.y) / s, w: view.w / s, h: view.h / s };
    return { s, dest, view, src };
  }
  const isCtx = t => !!t && typeof t.drawImage === 'function';
  function placeImage(target, img, c0, box, o = {}) {
    const iw = natW(img), ih = natH(img);
    if (!iw || !ih) throw new Error('K.cover/K.crop: image not loaded — await img.decode() inside window.ready');
    const c = c0 || { x: 0, y: 0, w: iw, h: ih };
    if (isCtx(target)) {
      if (!box) throw new Error('K.cover(ctx, img, box): a canvas needs a box {x, y, w, h}');
      const g = fitRect(c, box, o);
      if (g.view.w <= 0 || g.view.h <= 0) return g;
      target.save();
      if (o.radius) { target.beginPath(); target.roundRect(g.view.x, g.view.y, g.view.w, g.view.h, o.radius); target.clip(); }
      target.drawImage(img, g.src.x, g.src.y, g.src.w, g.src.h, g.view.x, g.view.y, g.view.w, g.view.h);
      target.restore();
      return g;
    }
    const el = target, b = box || { x: 0, y: 0, w: el.clientWidth, h: el.clientHeight };
    const g = fitRect(c, b, o);
    el.style.overflow = 'hidden';
    if (getComputedStyle(el).position === 'static') el.style.position = 'relative';
    if (o.radius != null) el.style.borderRadius = [].concat(o.radius).map(r => r + 'px').join(' ');
    if (img.parentNode !== el) el.appendChild(img);
    // the whole image, sized with width/height (not transform: scale), offset so the crop lands on dest
    Object.assign(img.style, { position: 'absolute', maxWidth: 'none', display: 'block',
      left: (g.dest.x - c.x * g.s) + 'px', top: (g.dest.y - c.y * g.s) + 'px',
      width: iw * g.s + 'px', height: ih * g.s + 'px' });
    return g;
  }
  // K.cover(target, img, box?, opts?)   K.crop(target, img, crop {x,y,w,h} in image px, box?, opts?)
  const cover = (target, img, box, o) => placeImage(target, img, null, box, o);
  const crop = (target, img, c, box, o) => placeImage(target, img, c, box, o);

  // Device frames from geometry, no images. box = the outer frame {x, y, w, h}.
  // -> {kind, frame, screen {x,y,w,h,r}, bar/dots/pill (browser) | island (phone)}; DOM and Canvas share it.
  function deviceGeom(kind, box) {
    const { x, y, w, h } = box;
    if (kind === 'browser') {
      const bar = Math.round(clamp(w * 0.04, 22, 64)), r = Math.round(bar * 0.4), dr = bar * 0.15;
      const dots = [0, 1, 2].map(i => ({ x: x + bar * 0.6 + i * bar * 0.5, y: y + bar / 2, r: dr }));
      const pw = w * 0.42, ph = bar * 0.56;
      return { kind, frame: { x, y, w, h, r }, bar: { x, y, w, h: bar }, dots,
               pill: { x: x + (w - pw) / 2, y: y + (bar - ph) / 2, w: pw, h: ph, r: ph / 2 },
               screen: { x, y: y + bar, w, h: h - bar, r: [0, 0, r, r] } };
    }
    if (kind === 'phone') {
      const bz = Math.round(w * 0.035), r = Math.round(w * 0.15), iw = w * 0.28, ih = w * 0.075;
      return { kind, frame: { x, y, w, h, r },
               screen: { x: x + bz, y: y + bz, w: w - 2 * bz, h: h - 2 * bz, r: r - bz },
               island: { x: x + (w - iw) / 2, y: y + bz + w * 0.03, w: iw, h: ih, r: ih / 2 } };
    }
    throw new Error(`K.device: unknown kind "${kind}" (use browser or phone)`);
  }
  // Neutral chrome on purpose (no platform branding); override with opts.colors / opts.dots.
  const DEVICE_THEME = {
    light: { body: '#e8e6e1', edge: '#d2cfc8', pill: '#f7f6f3', text: '#77736b', dots: ['#c9c5bd', '#c9c5bd', '#c9c5bd'], phone: '#16161a', island: '#000' },
    dark:  { body: '#1e1e22', edge: '#2e2e34', pill: '#2b2b30', text: '#9a9aa3', dots: ['#45454c', '#45454c', '#45454c'], phone: '#0b0b0d', island: '#000' },
  };
  const devTheme = o => Object.assign({}, DEVICE_THEME[o.theme || 'light'], o.colors || {}, o.dots ? { dots: o.dots } : {});
  const radii = r => [].concat(r).map(v => v + 'px').join(' ');
  // DOM: K.device('browser'|'phone', {w, h, theme, url, dots, colors, shadow, screenBg}) -> {el, screen, geom}.
  // Build once (in layout()), move dev.el with transforms, fill it with K.cover(dev.screen, img, null, opts).
  function device(kind, o = {}) {
    const w = o.w ?? (kind === 'phone' ? 390 : 1280), h = o.h ?? (kind === 'phone' ? 844 : 800);
    const g = deviceGeom(kind, { x: 0, y: 0, w, h }), c = devTheme(o);
    const div = (r, css = {}) => {
      const d = document.createElement('div');
      Object.assign(d.style, { position: 'absolute', left: r.x + 'px', top: r.y + 'px', width: r.w + 'px',
        height: r.h + 'px', borderRadius: r.r != null ? radii(r.r) : '' }, css);
      return d;
    };
    const ring = kind === 'phone' ? Math.max(1, Math.round(w * 0.006)) : 1;
    const el = div(g.frame, { background: kind === 'phone' ? c.phone : c.body,
      boxShadow: [`inset 0 0 0 ${ring}px ${c.edge}`, o.shadow ? '0 30px 80px rgba(0,0,0,.28)' : ''].filter(Boolean).join(',') });
    el.className = `k-device k-device-${kind}`;
    const screen = div(g.screen, { overflow: 'hidden', background: o.screenBg || '#fff' });
    screen.className = 'k-device-screen';
    if (kind === 'browser') {
      g.dots.forEach((d, i) => el.appendChild(div({ x: d.x - d.r, y: d.y - d.r, w: 2 * d.r, h: 2 * d.r, r: d.r }, { background: c.dots[i] })));
      const pill = div(g.pill, { background: c.pill, color: c.text, textAlign: 'center', whiteSpace: 'nowrap', overflow: 'hidden',
        font: `500 ${Math.round(g.pill.h * 0.5)}px/${g.pill.h}px system-ui,sans-serif` });
      pill.textContent = o.url || '';
      el.appendChild(pill);
    }
    el.appendChild(screen);
    if (kind === 'phone') el.appendChild(div(g.island, { background: c.island }));
    return { el, screen, geom: g };
  }
  // Canvas: K.drawDevice(ctx, kind, box, opts, drawScreen) draws the frame, calls drawScreen(screenRect)
  // clipped to the screen (e.g. s => K.cover(ctx, img, s)), then the island on top. -> geometry.
  function drawDevice(ctx, kind, box, o = {}, drawScreen) {
    const g = deviceGeom(kind, box), c = devTheme(o);
    const rr = (r, fill) => { ctx.beginPath(); ctx.roundRect(r.x, r.y, r.w, r.h, r.r ?? 0); if (fill) { ctx.fillStyle = fill; ctx.fill(); } };
    ctx.save();
    if (o.shadow) { ctx.shadowColor = 'rgba(0,0,0,.28)'; ctx.shadowBlur = 80; ctx.shadowOffsetY = 30; }
    rr(g.frame, kind === 'phone' ? c.phone : c.body);
    ctx.restore();
    ctx.save();   // inner edge ring, like the DOM inset shadow: stroke 2x wide, clipped to the frame
    ctx.strokeStyle = c.edge; ctx.lineWidth = 2 * (kind === 'phone' ? Math.max(1, Math.round(box.w * 0.006)) : 1);
    rr(g.frame); ctx.clip(); ctx.stroke();
    ctx.restore();
    if (kind === 'browser') {
      g.dots.forEach((d, i) => { ctx.beginPath(); ctx.arc(d.x, d.y, d.r, 0, Math.PI * 2); ctx.fillStyle = c.dots[i]; ctx.fill(); });
      rr(g.pill, c.pill);
      if (o.url) {
        ctx.save(); ctx.fillStyle = c.text; ctx.font = `500 ${Math.round(g.pill.h * 0.5)}px system-ui,sans-serif`;
        ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
        ctx.fillText(o.url, g.pill.x + g.pill.w / 2, g.pill.y + g.pill.h / 2, g.pill.w * 0.9); ctx.restore();
      }
    }
    ctx.save(); rr(g.screen, o.screenBg || '#fff'); ctx.clip();
    if (drawScreen) drawScreen(g.screen);
    ctx.restore();
    if (kind === 'phone') rr(g.island, c.island);
    return g;
  }
  Object.assign(K, { fitRect, cover, crop, deviceGeom, device, drawDevice });

  // =======================================================================
  // ---- typography (E7.3): glyph layout, fitText, mask reveals, typing, scramble ----
  // Tracking is in 1/1000 em (display -40..-80, mono +20; craft.md). DOM and Canvas variants.
  // Measure only after fonts load (in window.ready / layout()); animate from t in seek().
  // =======================================================================
  const SEG = typeof Intl !== 'undefined' && Intl.Segmenter ? new Intl.Segmenter(undefined, { granularity: 'grapheme' }) : null;
  const graphemes = s => SEG ? [...SEG.segment(String(s))].map(x => x.segment) : [...String(s)];
  // DOM: fill el with one inline-block span per glyph -> [span]. Spaces keep their width.
  function glyphs(el, text, { tracking = 0, className = 'k-glyph' } = {}) {
    el.textContent = '';
    el.style.letterSpacing = tracking / 1000 + 'em';
    el.style.whiteSpace = 'pre';
    return graphemes(text).map(ch => {
      const s = document.createElement('span');
      s.className = className; s.textContent = ch; s.style.display = 'inline-block';
      el.appendChild(s);
      return s;
    });
  }
  const pxOf = font => { const m = /(\d+(?:\.\d+)?)px/.exec(font); return m ? parseFloat(m[1]) : 10; };
  // Canvas: lay out text in ctx's current font -> {glyphs:[{ch, x, w}], width, ascent, descent, offset}.
  // x keeps kerning (prefix widths) plus tracking; align left | center | right shifts every x.
  function layoutText(ctx, text, { tracking = 0, align = 'left' } = {}) {
    const chars = graphemes(text), tr = tracking / 1000 * pxOf(ctx.font), m = ctx.measureText(text);
    const width = m.width + tr * Math.max(0, chars.length - 1);
    const offset = align === 'center' ? -width / 2 : align === 'right' ? -width : 0;
    let prefix = '';
    const gl = chars.map((ch, i) => {
      const x = ctx.measureText(prefix).width + i * tr + offset;
      prefix += ch;
      return { ch, x, w: ctx.measureText(ch).width };
    });
    return { glyphs: gl, width, offset, ascent: m.fontBoundingBoxAscent ?? pxOf(ctx.font) * .8,
             descent: m.fontBoundingBoxDescent ?? pxOf(ctx.font) * .2 };
  }
  // Canvas: draw a layout at baseline (x, y). fn(g, i) -> {dx, dy, alpha, ch} or null (skip the glyph).
  // mask: true clips to the line box, for rises through a mask line.
  function drawGlyphs(ctx, lay, x, y, fn, { mask = false } = {}) {
    ctx.save();
    ctx.textAlign = 'left'; ctx.textBaseline = 'alphabetic';
    if (mask) { ctx.beginPath(); ctx.rect(x + lay.offset - 4, y - lay.ascent, lay.width + 8, lay.ascent + lay.descent); ctx.clip(); }
    const a0 = ctx.globalAlpha;
    lay.glyphs.forEach((g, i) => {
      const f = fn ? fn(g, i) : {};
      if (!f) return;
      ctx.globalAlpha = a0 * (f.alpha ?? 1);
      if (ctx.globalAlpha > 0) ctx.fillText(f.ch ?? g.ch, x + g.x + (f.dx || 0), y + (f.dy || 0));
    });
    ctx.restore();   // restores globalAlpha too
  }
  // Largest font size (0.5 px steps) whose text fits maxWidth, clamped to [min, max]. -> px
  //   DOM:    K.fitText(el, maxWidth, {min, max})                   sets el.style.fontSize
  //   Canvas: K.fitText(ctx, maxWidth, {text, tracking, min, max})  sets the px size in ctx.font
  function fitText(target, maxW, { text, tracking = 0, min = 8, max = 1000 } = {}) {
    let widthAt, done = () => {};
    if (isCtx(target)) {
      if (text == null) throw new Error('K.fitText(ctx, maxWidth, {text}): a canvas needs the text');
      const ctx = target, setPx = px => { ctx.font = ctx.font.replace(/(\d+(?:\.\d+)?)px/, px + 'px'); };
      widthAt = px => { setPx(px); return layoutText(ctx, text, { tracking }).width; };
    } else {
      const el = target, w0 = el.style.width;
      el.style.width = 'max-content';
      widthAt = px => { el.style.fontSize = px + 'px'; return el.scrollWidth; };
      done = () => { el.style.width = w0; };
    }
    let px = clamp(Math.floor(200 * maxW / widthAt(100)) / 2, min, max);
    while (px > min && widthAt(px) > maxW) px -= 0.5;
    widthAt(px); done();
    return px;
  }
  // Mask-line rise for glyph / word / line i -> {y, p, shown}, a pure function of t.
  // o: at (s or '8b'), gap (stagger, .06), dur (.7), travel (px below the line, e.g. 1.3 x font size),
  // ease (editorial bezier(.16,1,.3,1)); optional exit: out (time), outGap (.04), outDur (.45; leaves
  // upward, faster than it came). shown = part of it is inside the mask (mask px, default travel / 1.3).
  const RISE_EASE = bezier(.16, 1, .3, 1);
  function rise(t, i, o = {}) {
    const travel = o.travel ?? 100, mask = o.mask ?? travel / 1.3;
    const p = (o.ease || RISE_EASE)(seg(stagger(t, o.at ?? 0, i, o.gap ?? 0.06), 0, o.dur ?? 0.7));
    const q = o.out == null ? 0 : ease.inCubic(seg(stagger(t, o.out, i, o.outGap ?? 0.04), 0, o.outDur ?? 0.45));
    const y = (1 - p) * travel - q * travel;
    return { y, p: p * (1 - q), shown: Math.abs(y) < mask };
  }
  // DOM: rise() applied to spans (inside an overflow:hidden line) -> true if any glyph shows.
  // Set the row's opacity from it (0 when fully masked) so the gates measure the real reading time.
  function maskRise(spans, t, o) {
    let shown = false;
    spans.forEach((s, i) => { const r = rise(t, i, o); s.style.transform = `translateY(${r.y}px)`; if (r.shown) shown = true; });
    return shown;
  }
  // Typing derived from t: keystrokes at a seeded, natural rhythm (cps chars/s; longer after spaces
  // and punctuation) -> {text, n, done, caret, end}. Caret solid while typing, blinks (0.53 s) when idle.
  const TYPE_CACHE = new Map();
  function keyTimes(chars, cps, seed) {
    const key = chars.join('') + '|' + cps + '|' + seed;
    if (!TYPE_CACHE.has(key)) {
      let acc = 0;
      TYPE_CACHE.set(key, chars.map((ch, i) => {
        const prev = chars[i - 1] || '';
        acc += (0.55 + 0.9 * rand(seed, i)) * (/[.,!?;:]/.test(prev) ? 2.6 : prev === ' ' ? 1.5 : 1) / cps;
        return acc;
      }));
    }
    return TYPE_CACHE.get(key);
  }
  function typed(text, t, { at = 0, cps = 16, seed = 1 } = {}) {
    const chars = graphemes(text), times = keyTimes(chars, cps, seed), a = sec(at), lt = t - a;
    let n = 0;
    while (n < times.length && times[n] <= lt + 1e-9) n++;
    const idle = lt - (n > 0 ? times[n - 1] : 0);
    const caret = (n > 0 && n < chars.length) || (n > 0 && idle < 0.5) || Math.floor(Math.abs(idle) / 0.53) % 2 === 0;
    return { text: chars.slice(0, n).join(''), n, done: n === chars.length, caret, end: a + (times[times.length - 1] || 0) };
  }
  // Seeded scramble -> the string to show at t. Glyphs settle in a seeded Fisher-Yates order across
  // [at, at + dur] (or all at once at `snap`, e.g. a beat '16b'); unsettled glyphs cycle through
  // `chars` `rate` times per second. Spaces never scramble.
  const SCRAMBLE = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789#%&*+=?';
  function scramble(text, t, { at = 0, dur = 0.6, seed = 1, rate = 20, chars = SCRAMBLE, snap } = {}) {
    const g = graphemes(text), idx = g.map((c, i) => i).filter(i => g[i].trim());
    for (let i = idx.length - 1; i > 0; i--) { const j = Math.floor(rand(seed, i) * (i + 1)); [idx[i], idx[j]] = [idx[j], idx[i]]; }
    const settle = new Array(g.length).fill(-Infinity), a = sec(at), m = idx.length || 1;
    idx.forEach((gi, rank) => { settle[gi] = snap != null ? sec(snap) : a + dur * (rank + 1) / m; });
    const tick = Math.floor(t * rate + 1e-6), pool = graphemes(chars);
    return g.map((c, i) => t >= settle[i] ? c : pool[Math.floor(rand(seed + 7, i * 7919 + tick) * pool.length)]).join('');
  }
  Object.assign(K, { graphemes, glyphs, layoutText, drawGlyphs, fitText, rise, maskRise, typed, scramble });

  return K;
})();
