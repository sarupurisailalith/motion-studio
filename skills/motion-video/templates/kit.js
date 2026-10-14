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
  async function loadClip(a) {
    if (CLIPS.has(clipKey(a))) return CLIPS.get(clipKey(a)).ready;
    const frames = [];
    for (let i = 0; i < a.frame_count; i++) { const img = new Image(); img.src = framePath(a, i); frames.push(img); }
    const ready = Promise.all(frames.map(img => img.decode().catch(() => {
      throw new Error(`K.loadClip: could not decode ${img.src} (asset "${a.id}")`);
    }))).then(() => frames);
    CLIPS.set(clipKey(a), { frames, ready });
    return ready;
  }
  // Frame for clip time t: clamp(floor(t * fps), 0, frame_count - 1). The tiny epsilon keeps
  // t = k / fps on frame k despite float error (e.g. 0.3 * 10 = 2.9999...).
  function clipFrame(a, t) {
    const c = CLIPS.get(clipKey(a));
    if (!c) throw new Error(`K.clipFrame: clip "${a.id}" not loaded — await K.loadClip(asset) inside window.ready`);
    return c.frames[clamp(Math.floor(t * a.fps + 1e-6), 0, c.frames.length - 1)];
  }
  function drawClip(ctx, a, t, x = 0, y = 0, w, h) {
    const img = clipFrame(a, t);
    ctx.drawImage(img, x, y, w ?? img.naturalWidth, h ?? img.naturalHeight);
  }
  Object.assign(K, { loadClip, clipFrame, drawClip });
  Object.assign(K, { FORMATS, init, pick, nextFormat, formatSearch, FORMAT: null, safe: null });

  return K;
})();
