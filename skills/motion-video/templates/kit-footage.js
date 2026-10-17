/* =========================================================================
   FOOTAGE KIT (kit-footage.js) — speech-timed helpers for footage-led pieces (E12).
   A classic script. Load it AFTER kit.js (it extends window.K) and after the data files:
     <script src="assets/assets.js"></script>   window.ASSETS      (ingest.py)
     <script src="transcript.js"></script>      window.TRANSCRIPT  (transcribe.py)
     <script src="edl.js"></script>             window.EDL         (cut.py)       optional
     <script src="story.js"></script>           window.STORY       (story.py)     optional
     <script src="kit.js"></script> <script src="kit-footage.js"></script>

   Same rules as kit.js: every value is a pure function of t, no timers, no network. All data
   is loaded before window.ready; windowed clips are awaited inside seek via K.edlSeek(t).

   TIME
     K.footage({transcript, edl, assets})  register the data (defaults: the window.* above)
     K.edl(t)        -> {ev, i, clip, clipT, local, jump} for timeline time t, or null in a gap
     K.edlSeek(t)    -> Promise: decode the frame K.edl(t) needs (windowed clips) + prefetch
                        the next event's in-point. `await` it first thing in seek(t).
     K.punch(t, k)   -> scale (1 or k, eased) that covers jump cuts with a punch-in
     K.wordT(id)     -> timeline seconds of word id (through the EDL); throws if it was cut
     K.cue(when)     -> seconds: a number, 'w12', 'w12+0.25', or a beat string '16b'
   GRAPHICS (each returns {el, update(t)}; K.footageUpdate(t) updates every one made)
     K.captions(parent, opts)       ≤ 7 words per group, current word highlighted
     K.lowerThird(parent, {name, role, at, until})
     K.keywordPop(parent, {text, at, until, claim})
     K.statCard(parent, {value, label, at, until, claim})
     K.featureList(parent, {title, items:[{text, at, claim}], at, until})
     K.pullQuote(parent, {from, to, at, until})
     K.ctaCard(parent, {line, url, at, claim})
     K.deviceShot(parent, {src, w, h, at, until, device})   minimal frame; E3.4 has the real one
   SPEAKER
     K.speakerRect(layout)   'full' | 'corner' | 'split' | 'shape' | 'pig' -> {x, y, w, h, r}
     K.graphicsArea(rect)    the free part of K.safe.ui next to the speaker (pass as {area})
     K.mixRect(a, b, p)      in-between rect (layout changes)
     K.drawSpeaker(ctx, asset, clipT, rect, {focus:[fx, fy], zoom})   cover-fit, masked
   GATES (render.py --check-only reads these attributes)
     data-cue="w12"   the element must first show within ±2 frames of word w12 (cue_timing)
     data-claim       "w3-w9" (a quote), "source:N" (line N of docs/source.md) or "label"
                      (no numbers): every [data-text] in a footage piece needs one (claim_trace)
   ========================================================================= */
(() => {
  const K = window.K;
  if (!K) throw new Error('kit-footage.js: load kit.js first');
  const F = { tr: null, edl: null, words: new Map(), order: [], assets: new Map(), parts: [] };

  function footage(o = {}) {
    F.tr = o.transcript || window.TRANSCRIPT || null;
    const e = o.edl !== undefined ? o.edl : window.EDL || null;
    F.edl = e ? (Array.isArray(e) ? { edl: e } : e) : null;
    const inv = o.assets || window.ASSETS;
    F.assets = new Map(((inv && inv.assets) || []).map(a => [a.id, a]));
    F.words = new Map(((F.tr && F.tr.words) || []).map((w, i) => [w.id, Object.assign({ i }, w)]));
    F.order = (F.tr && F.tr.words) || [];
    return { duration: F.edl ? edlDuration() : (F.tr ? F.tr.duration : 0) };
  }
  const asset = id => { const a = F.assets.get(id); if (!a) throw new Error(`K: asset "${id}" not in assets.js`); return a; };
  const events = () => (F.edl && F.edl.edl) || [];
  const evDur = e => (e.out - e.in) / (e.speed || 1);
  const edlDuration = () => events().reduce((m, e) => Math.max(m, e.at + evDur(e)), 0);

  // ---- EDL (E12.5) ----
  function edl(t) {
    const evs = events();
    for (let i = 0; i < evs.length; i++) {
      const e = evs[i], d = evDur(e);
      if (t >= e.at - 1e-9 && (t < e.at + d - 1e-9 || (i === evs.length - 1 && t <= e.at + d + 1e-9))) {
        const local = Math.max(0, t - e.at);
        return { ev: e, i, clip: e.clip, clipT: e.in + local * (e.speed || 1), local, jump: !!e.jump };
      }
    }
    if (!evs.length && F.tr && F.tr.clip) return { ev: null, i: -1, clip: F.tr.clip, clipT: t, local: t, jump: false };
    return null;
  }
  async function edlSeek(t) {
    const s = edl(t);
    if (!s) return null;
    await K.clipSeek(asset(s.clip), s.clipT);
    const next = events()[s.i + 1];
    if (next && next.at - t < 1.0) K.clipSeek(asset(next.clip), next.in).catch(() => {});   // prefetch, not awaited
    return s;
  }
  // Punch-in over jump cuts: alternate events after a jump sit at scale k. The scale switches
  // exactly on the cut, so the cut stays the only discontinuity.
  function punch(t, k = 1.12) {
    const s = edl(t);
    if (!s || !s.ev) return 1;
    let n = 0;
    for (let i = s.i; i > 0 && events()[i].jump; i--) n++;
    return n % 2 ? k : 1;
  }

  // ---- words -> timeline ----
  function srcToTimeline(clip, ts) {
    const evs = events();
    if (!evs.length) return ts;
    for (const e of evs)
      if (e.clip === clip && ts >= e.in - 1e-6 && ts < e.out - 1e-6) return e.at + (ts - e.in) / (e.speed || 1);
    return null;
  }
  const word = id => { const w = F.words.get(id); if (!w) throw new Error(`K: no word "${id}" in transcript.js`); return w; };
  function wordT(id, edge = 't0') {
    const w = word(id), clip = F.tr.clip || (F.edl && F.edl.clip);
    const t = srcToTimeline(clip, w[edge]);
    if (t === null) throw new Error(`K.wordT: word ${id} ("${w.w}") was cut by the EDL — cue it on a kept word`);
    return t;
  }
  const isWordRef = v => typeof v === 'string' && /^[a-z]+\d+([+-]\d+(\.\d+)?)?$/i.test(v.trim()) && !/b$/.test(v.trim());
  function cue(when) {
    if (typeof when === 'number') return when;
    if (isWordRef(when)) {
      const m = when.trim().match(/^([a-z]+\d+)([+-]\d+(?:\.\d+)?)?$/i);
      return wordT(m[1]) + (m[2] ? parseFloat(m[2]) : 0);
    }
    return K.sec(when);
  }
  const cueId = when => isWordRef(when) ? when.trim().match(/^[a-z]+\d+/i)[0] : null;
  // kept words on the timeline: [{id, w, t0, t1, i}] (cut words dropped)
  function timelineWords() {
    const clip = F.tr && (F.tr.clip || (F.edl && F.edl.clip));
    return F.order.map((w, i) => {
      const t0 = srcToTimeline(clip, w.t0);
      if (t0 === null) return null;
      const t1 = srcToTimeline(clip, Math.max(w.t0, w.t1 - 1e-4));
      return { id: w.id, w: w.w, t0, t1: t1 === null ? t0 + 0.1 : t1, i, phrase: w.phrase };
    }).filter(Boolean);
  }

  // ---- DOM helpers ----
  const css = (el, o) => { Object.assign(el.style, o); return el; };
  const mk = (parent, tag, cls, text) => {
    const el = document.createElement(tag);
    if (cls) el.className = cls;
    if (text !== undefined) el.textContent = text;
    parent.appendChild(el);
    return el;
  };
  const px = v => Math.round(v) + 'px';
  const unit = () => Math.min(K.FORMAT.W, K.FORMAT.H) / 1080;   // 1 at 1080 short side
  const font = 'var(--font-display, system-ui, sans-serif)';
  // in/out envelope: rises over `inD` from t0, falls over `outD` ending at t1. 0..1
  // The rise starts one frame early so the cue's own frame already shows it (cue_timing: 0 frames).
  function env(t, t0, t1, inD = 0.18, outD = 0.2) {
    const f = 1 / ((window.MOTION && window.MOTION.fps) || 30);
    if (t <= t0 - f || t >= t1) return 0;
    const up = K.ease.outCubic(K.seg(t, t0 - f, t0 + inD));
    return t1 === Infinity ? up : Math.min(up, 1 - K.ease.inCubic(K.seg(t, t1 - outD, t1)));
  }
  const springIn = (t, t0) => K.spring(t - t0, 22, 0.86);
  function register(part) { F.parts.push(part); return part; }
  function footageUpdate(t) { F.parts.forEach(p => p.update(t)); }
  function setVis(el, o) { el.style.opacity = o > 0.001 ? Math.min(1, o).toFixed(4) : '0'; el.style.visibility = o > 0.001 ? 'visible' : 'hidden'; }
  function markCue(el, at) { const id = cueId(at); if (id) el.dataset.cue = id; el.dataset.cueT = cue(at).toFixed(4); }
  // a claim's provenance: explicit, else the words under `at` when the text quotes them
  function quoteClaim(text, at) {
    const id = cueId(at);
    if (!id) return null;
    const norm = s => s.toLowerCase().replace(/[^\p{L}\p{N}%]+/gu, ' ').trim().split(/\s+/).filter(Boolean);
    const want = norm(text), w0 = word(id).i;
    const got = F.order.slice(w0, w0 + want.length).map(w => norm(w.w).join(' ')).join(' ');
    return got === want.join(' ') ? (want.length > 1 ? `${id}-${F.order[w0 + want.length - 1].id}` : id) : null;
  }
  function claimOf(text, at, claim) {
    const c = claim || quoteClaim(text, at);
    if (!c) throw new Error(`K: "${text}" needs a claim: a quote of the words at its cue, or { claim: 'source:N' } (a docs/source.md line)`);
    return c;
  }

  // ---- captions (E6.2 / E12.7) ----
  function captionGroups(words, max = 7, gap = 0.35, minDur = 0.6) {
    const groups = [];
    let g = null;
    words.forEach((w, k) => {
      const prev = words[k - 1];
      const brk = !g || g.words.length >= max || w.phrase !== prev.phrase || w.t0 - prev.t1 > gap ||
                  /[.?!;:]$/.test(prev.w) || (/,$/.test(prev.w) && g.words.length >= 3);
      if (brk) { g = { words: [] }; groups.push(g); }
      g.words.push(w);
    });
    groups.forEach((g, i) => {
      g.t0 = g.words[0].t0;
      const nxt = groups[i + 1] ? groups[i + 1].words[0].t0 : Infinity;
      let t1 = Math.max(g.words[g.words.length - 1].t1 + 0.15, g.t0 + minDur);
      if (nxt - t1 < 0.3) t1 = nxt;   // no flicker between close groups
      g.t1 = Math.min(t1, nxt);
    });
    return groups;
  }
  function captions(parent, o = {}) {
    const S = K.safe.ui, u = unit();
    const size = o.size || Math.round(K.pick({ '9x16': 58, default: 50 }) * u);
    const groups = captionGroups(timelineWords(), o.maxWords || 7, o.gap, o.minDur);
    const els = groups.map(g => {
      const box = mk(parent, 'div', 'k-caption');
      box.dataset.text = ''; box.dataset.safe = '';
      box.dataset.claim = g.words.length > 1 ? `${g.words[0].id}-${g.words[g.words.length - 1].id}` : g.words[0].id;
      css(box, { position: 'absolute', left: px(S.x + S.w / 2), top: px(S.y + S.h - (o.bottom ?? 24 * u)),
                 transform: 'translate(-50%,-100%)', maxWidth: px(S.w * 0.92), width: 'max-content',
                 padding: `${px(10 * u)} ${px(22 * u)}`, borderRadius: px(14 * u), textAlign: 'center',
                 background: o.plate ?? 'rgba(10,10,12,.78)', color: o.color || '#fff',
                 font: `700 ${size}px/1.18 ${font}`, letterSpacing: '-0.01em' });
      const spans = g.words.map((w, i) => { const s = mk(box, 'span', null, (i ? ' ' : '') + w.w); return s; });
      return { box, spans, g };
    });
    return register({ el: parent, groups, update(t) {
      els.forEach(({ box, spans, g }) => {
        setVis(box, env(t, g.t0, g.t1, 0.08, 0.08));
        spans.forEach((s, i) => { s.style.color = t >= g.words[i].t0 ? (o.highlight || 'var(--accent, #ffd23f)') : ''; });
      });
    } });
  }

  // ---- graphics (E12.7): every one keyed to a cue (word id), built from kit calls ----
  function window_(at, until, dflt = 2.5) {
    const t0 = cue(at);
    const t1 = until !== undefined ? cue(until) : t0 + dflt;
    return [t0, Math.max(t1, t0 + 1.0)];
  }
  function lowerThird(parent, o) {
    const S = o.area || K.safe.ui, u = unit(), [t0, t1] = window_(o.at, o.until, 3.5);
    const card = mk(parent, 'div', 'k-lower-third');
    card.dataset.safe = '';
    markCue(card, o.at);
    css(card, { position: 'absolute', left: px(S.x), top: px(S.y + S.h * K.pick({ '9x16': 0.58, default: 0.66 })),
                padding: `${px(14 * u)} ${px(26 * u)}`, background: 'var(--bg, #fff)', color: 'var(--ink, #111)',
                borderLeft: `${px(10 * u)} solid var(--accent, #ff4d1f)`, maxWidth: px(S.w * 0.8) });
    const n = mk(card, 'div', null, o.name), r = mk(card, 'div', null, o.role || '');
    [n, r].forEach(el => { el.dataset.text = ''; el.dataset.claim = o.claim || 'label'; });
    css(n, { font: `800 ${px(56 * u)}/1.1 ${font}` });
    css(r, { font: `500 ${px(36 * u)}/1.25 ${font}`, opacity: 0.75 });
    return register({ el: card, t0, t1, update(t) {
      const e = env(t, t0, t1);
      setVis(card, e);
      card.style.transform = `translateX(${((1 - K.springCrit(t - t0, 18)) * 40 * u).toFixed(2)}px)`;   // slides in from the right: never left of the safe edge
    } });
  }
  function popBox(parent, cls, o, t0, t1) {
    const el = mk(parent, 'div', cls);
    el.dataset.safe = '';
    markCue(el, o.at);
    return { el, update(t, k = 1) {
      setVis(el, env(t, t0, t1, 0.12, 0.18));
      const s = 0.82 + 0.18 * springIn(t, t0);
      el.style.transform = `translate(-50%,-50%) scale(${(s * k).toFixed(4)})`;
    } };
  }
  function keywordPop(parent, o) {
    const S = o.area || K.safe.ui, u = unit(), [t0, t1] = window_(o.at, o.until, 1.6);
    const b = popBox(parent, 'k-keyword', o, t0, t1);
    b.el.textContent = o.text;
    b.el.dataset.text = '';
    b.el.dataset.claim = claimOf(o.text, o.at, o.claim);
    css(b.el, { position: 'absolute', left: px(o.x ?? S.x + S.w / 2), top: px(o.y ?? S.y + S.h * 0.3),
                font: `900 ${px((o.size || 110) * u)}/1 ${font}`, color: o.color || 'var(--accent, #ff4d1f)',
                letterSpacing: '-0.04em', whiteSpace: 'nowrap', maxWidth: px(S.w) });
    return register({ el: b.el, t0, t1, update: t => b.update(t) });
  }
  function statCard(parent, o) {
    const S = o.area || K.safe.ui, u = unit(), [t0, t1] = window_(o.at, o.until, 2.4);
    const b = popBox(parent, 'k-stat', o, t0, t1);
    css(b.el, { position: 'absolute', left: px(o.x ?? S.x + S.w / 2), top: px(o.y ?? S.y + S.h * 0.36),
                padding: `${px(26 * u)} ${px(40 * u)}`, background: 'var(--bg, #fff)', color: 'var(--ink, #111)',
                borderRadius: px(24 * u), textAlign: 'center', maxWidth: px(S.w * 0.9) });
    const v = mk(b.el, 'div', null, String(o.value)), l = mk(b.el, 'div', null, o.label || '');
    const claim = claimOf(`${o.value} ${o.label || ''}`.trim(), o.at, o.claim);
    [v, l].forEach(el => { el.dataset.text = ''; el.dataset.claim = claim; });
    css(v, { font: `900 ${px(150 * u)}/1 ${font}`, color: 'var(--accent, #ff4d1f)', letterSpacing: '-0.05em' });
    css(l, { font: `600 ${px(36 * u)}/1.2 ${font}`, marginTop: px(8 * u) });
    return register({ el: b.el, t0, t1, update: t => b.update(t) });
  }
  function featureList(parent, o) {
    const S = o.area || K.safe.ui, u = unit(), [t0, t1] = window_(o.at, o.until, 4);
    const box = mk(parent, 'div', 'k-features');
    box.dataset.safe = '';
    css(box, { position: 'absolute', left: px(o.x ?? S.x + S.w * 0.06), top: px(o.y ?? S.y + S.h * 0.12),
               maxWidth: px(S.w * 0.88),
               color: 'var(--ink, #111)', font: `700 ${px(52 * u)}/1.25 ${font}` });
    const head = o.title ? mk(box, 'div', null, o.title) : null;
    if (head) { head.dataset.text = ''; head.dataset.claim = o.titleClaim || 'label'; css(head, { opacity: 0.6, fontSize: px(36 * u), marginBottom: px(10 * u) }); }
    const rows = o.items.map(it => {
      const r = mk(box, 'div', 'k-feature', '— ' + it.text);
      r.dataset.text = '';
      r.dataset.claim = claimOf(it.text, it.at, it.claim);
      markCue(r, it.at);
      css(r, { padding: `${px(8 * u)} 0` });
      return { r, ti: Math.max(cue(it.at), t0) };
    });
    markCue(box, o.at);
    return register({ el: box, t0, t1, update(t) {
      setVis(box, env(t, t0, t1));
      if (head) setVis(head, env(t, t0, t1));
      rows.forEach(({ r, ti }) => {
        setVis(r, env(t, ti, t1, 0.14, 0.2));
        r.style.transform = `translateY(${((1 - springIn(t, ti)) * 24 * u).toFixed(2)}px)`;
      });
    } });
  }
  function pullQuote(parent, o) {
    const S = o.area || K.safe.ui, u = unit();
    const a = word(o.from).i, b = word(o.to).i;
    const text = F.order.slice(a, b + 1).map(w => w.w).join(' ');
    const [t0, t1] = window_(o.at || o.from, o.until ?? (o.to + '+1.2'), 3);
    const el = mk(parent, 'div', 'k-quote', `“${text.replace(/^["“]|["”]$/g, '')}”`);
    el.dataset.text = ''; el.dataset.safe = '';
    el.dataset.claim = a === b ? o.from : `${o.from}-${o.to}`;
    markCue(el, o.at || o.from);
    css(el, { position: 'absolute', left: px(S.x + S.w * 0.06), top: px(S.y + S.h * 0.2), width: px(S.w * 0.88),
              font: `800 ${px((o.size || 72) * u)}/1.12 ${font}`, color: 'var(--ink, #111)', letterSpacing: '-0.02em' });
    return register({ el, t0, t1, update(t) {
      setVis(el, env(t, t0, t1, 0.2, 0.25));
      el.style.transform = `translateY(${((1 - springIn(t, t0)) * 30 * u).toFixed(2)}px)`;
    } });
  }
  function ctaCard(parent, o) {
    const S = o.area || K.safe.ui, u = unit(), t0 = cue(o.at), t1 = o.until !== undefined ? cue(o.until) : Infinity;
    const card = mk(parent, 'div', 'k-cta');
    card.dataset.safe = '';
    markCue(card, o.at);
    css(card, { position: 'absolute', left: px(S.x + S.w / 2), top: px(S.y + S.h / 2), textAlign: 'center',
                color: 'var(--ink, #111)', width: px(S.w * 0.9) });
    const line = o.line ? mk(card, 'div', null, o.line) : null;
    const url = mk(card, 'div', null, o.url);
    if (line) { line.dataset.text = ''; line.dataset.claim = o.lineClaim || claimOf(o.line, o.at, o.claim); css(line, { font: `800 ${px(72 * u)}/1.1 ${font}` }); }
    url.dataset.text = ''; url.dataset.claim = o.claim || 'label';
    css(url, { font: `700 ${px(46 * u)}/1.2 ${font}`, color: 'var(--accent, #ff4d1f)', marginTop: px(18 * u) });
    return register({ el: card, t0, t1, update(t) {
      setVis(card, env(t, t0, t1, 0.25));
      card.style.transform = `translate(-50%,-50%) scale(${(0.9 + 0.1 * springIn(t, t0)).toFixed(4)})`;
    } });
  }
  // Minimal device frame: a rounded bezel around a supplied screenshot (never a drawn UI).
  // E3.4 brings the real device frames to kit.js; prefer those when present.
  function deviceShot(parent, o) {
    const S = o.area || K.safe.ui, u = unit(), [t0, t1] = window_(o.at, o.until, 3);
    const phone = (o.device || 'phone') === 'phone';
    const h = Math.min(S.h * (phone ? 0.78 : 0.6), phone ? S.w * 1.9 : S.w * 0.55);
    const w = phone ? h * (o.w && o.h ? o.w / o.h : 9 / 19.5) : h * (o.w && o.h ? o.w / o.h : 16 / 10);
    const frame = mk(parent, 'div', 'k-device');
    markCue(frame, o.at);
    css(frame, { position: 'absolute', left: px(o.x ?? S.x + S.w / 2), top: px(o.y ?? S.y + S.h / 2), width: px(w), height: px(h),
                 padding: px((phone ? 14 : 18) * u), borderRadius: px((phone ? 56 : 22) * u), background: '#0b0b0d',
                 boxShadow: `0 ${px(30 * u)} ${px(80 * u)} rgba(0,0,0,.35)` });
    const img = mk(frame, 'img');
    img.src = o.src;
    css(img, { width: '100%', height: '100%', objectFit: 'cover', borderRadius: px((phone ? 42 : 8) * u), display: 'block' });
    return register({ el: frame, img, t0, t1, update(t) {
      setVis(frame, env(t, t0, t1, 0.2, 0.25));
      frame.style.transform = `translate(-50%,-50%) translateY(${((1 - springIn(t, t0)) * 60 * u).toFixed(2)}px)`;
    } });
  }

  // ---- speaker layouts (E12.7) ----
  function speakerRect(name) {
    const { W, H } = K.FORMAT, S = K.safe.ui, u = unit(), port = K.FORMAT.isPortrait;
    switch (name) {
      case 'full': return { x: 0, y: 0, w: W, h: H, r: 0, shape: 'rect' };
      case 'corner': {
        const w = Math.round((port ? 0.42 : 0.26) * W), h = Math.round(w * (port ? 1.25 : 0.75));
        const band = Math.round(150 * u);   // landscape: sit above the caption band
        return { x: S.x + S.w - w, y: port ? S.y : S.y + S.h - band - h, w, h, r: Math.round(28 * u), shape: 'rect' };
      }
      case 'split': return port ? { x: 0, y: 0, w: W, h: Math.round(H * 0.44), r: 0, shape: 'rect' }
                                : { x: 0, y: 0, w: Math.round(W * 0.5), h: H, r: 0, shape: 'rect' };
      case 'shape': {
        const d = Math.round(port ? W * 0.62 : H * 0.7);
        return { x: port ? Math.round((W - d) / 2) : Math.round(W * 0.08), y: port ? S.y + Math.round(S.h * 0.08) : Math.round((H - d) / 2),
                 w: d, h: d, r: d / 2, shape: 'circle' };
      }
      case 'pig': {
        const w = Math.round((port ? 0.8 : 0.42) * W), h = Math.round(w * (port ? 1.0 : 0.62));
        return { x: port ? Math.round((W - w) / 2) : Math.round(W * 0.06), y: port ? S.y + Math.round(S.h * 0.06) : Math.round((H - h) / 2),
                 w, h, r: Math.round(36 * u), shape: 'rect' };
      }
      default: throw new Error(`K.speakerRect: unknown layout "${name}" (full, corner, split, shape, pig)`);
    }
  }
  // Where graphics go: the larger free span of K.safe.ui beside (landscape) or under (portrait)
  // the speaker rect, minus a caption band at the bottom when captions are on.
  function graphicsArea(R, o = {}) {
    const S = K.safe.ui, u = unit(), gap = Math.round(36 * u);
    const band = o.captions === false ? 0 : Math.round((o.band ?? K.pick({ '9x16': 190, default: 150 })) * u);
    let A = { x: S.x, y: S.y, w: S.w, h: S.h - band };
    const covers = R.w >= K.FORMAT.W * 0.9 && R.h >= K.FORMAT.H * 0.9;
    if (!covers) {
      if (K.FORMAT.isPortrait) {
        const top = R.y - gap - S.y, bot = S.y + S.h - band - (R.y + R.h + gap);
        A = bot >= top ? { x: S.x, y: R.y + R.h + gap, w: S.w, h: bot } : { x: S.x, y: S.y, w: S.w, h: top };
      } else {
        const left = R.x - gap - S.x, right = S.x + S.w - (R.x + R.w + gap);
        A = right >= left ? { x: R.x + R.w + gap, y: S.y, w: right, h: S.h - band } : { x: S.x, y: S.y, w: left, h: S.h - band };
      }
    }
    return { x: Math.round(A.x), y: Math.round(A.y), w: Math.round(Math.max(0, A.w)), h: Math.round(Math.max(0, A.h)) };
  }
  const mixRect = (a, b, p) => ({ x: K.lerp(a.x, b.x, p), y: K.lerp(a.y, b.y, p), w: K.lerp(a.w, b.w, p), h: K.lerp(a.h, b.h, p),
                                  r: K.lerp(a.r, b.r, p), shape: p < 0.5 ? a.shape : b.shape });
  function roundRect(ctx, x, y, w, h, r) {
    r = Math.max(0, Math.min(r, w / 2, h / 2));
    ctx.beginPath();
    ctx.moveTo(x + r, y); ctx.arcTo(x + w, y, x + w, y + h, r); ctx.arcTo(x + w, y + h, x, y + h, r);
    ctx.arcTo(x, y + h, x, y, r); ctx.arcTo(x, y, x + w, y, r); ctx.closePath();
  }
  // Cover-fit the clip frame into rect around a focus point (fractions of the frame), masked to its shape.
  function drawSpeaker(ctx, a, clipT, R, o = {}) {
    const img = K.clipFrame(a, clipT), iw = img.naturalWidth, ih = img.naturalHeight;
    const zoom = o.zoom || 1, [fx, fy] = o.focus || [0.5, 0.4];
    const s = Math.max(R.w / iw, R.h / ih) * zoom, sw = R.w / s, sh = R.h / s;
    const sx = K.clamp(fx * iw - sw / 2, 0, iw - sw), sy = K.clamp(fy * ih - sh / 2, 0, ih - sh);
    ctx.save();
    if (R.shape === 'circle') { ctx.beginPath(); ctx.ellipse(R.x + R.w / 2, R.y + R.h / 2, R.w / 2, R.h / 2, 0, 0, Math.PI * 2); ctx.clip(); }
    else if (R.r > 0) { roundRect(ctx, R.x, R.y, R.w, R.h, R.r); ctx.clip(); }
    ctx.drawImage(img, sx, sy, sw, sh, R.x, R.y, R.w, R.h);
    ctx.restore();
  }

  Object.assign(K, { footage, edl, edlSeek, punch, word, wordT, cue, timelineWords, captionGroups, captions,
                     lowerThird, keywordPop, statCard, featureList, pullQuote, ctaCard, deviceShot,
                     speakerRect, graphicsArea, mixRect, drawSpeaker, footageUpdate, footageAsset: asset });
})();
