/* =========================================================================
   MOTION KIT · ZDOG ADD-ON (kit-zdog.js) — K.Z: helpers for Zdog scenes driven as a pure
   function of t, plus the rig + clip library (E10.3, E10.4) and the model registry (E11.1).
   Load order:  vendor/zdog.dist.min.js → kit.js → kit-zdog.js → models/*.js → scene script.
   (vendor.py P zdog downloads Zdog; it is never bundled with the plugin.)

   RULES (same contract as kit.js)
     - Never use Zdog.Illustration, Dragger or requestAnimationFrame: pose(t) sets transforms,
       then K.Z.render(scene, ctx, view) draws one frame.
     - Group sort order depends on the previous frame unless reset: K.Z.render does that
       (canonicalSort) so any seek order gives the same picture.
     - Colours come from palette slots (K.Z.make(id, addTo, { palette })), never hex in scenes.
   ========================================================================= */
(() => {
  const K = window.K;
  if (!K) throw new Error('kit-zdog.js: load kit.js first');
  if (!window.Zdog) throw new Error('kit-zdog.js: load vendor/zdog.dist.min.js first (python3 vendor.py P zdog)');
  const Z = window.Zdog, TAU = Z.TAU;

  // ---------------- drawing ----------------
  // Group.updateSort sorts a persistent array IN PLACE, so ties resolve by last frame's order
  // (history-dependent). Rebuilding each Group's flat list restores a fixed starting order.
  function canonicalSort(item) {
    if (item instanceof Z.Group) item.updateFlatGraph();
    item.children.forEach(canonicalSort);
  }
  // Draw one frame. view = { zoom, cx, cy } in CSS px (cx, cy = where the scene origin lands);
  // dpr defaults to devicePixelRatio (the canvas backing store is W*dpr). background: a colour
  // to fill first; clear: false draws over what is there (e.g. into p5's drawingContext between
  // p5 calls). The context's own state (transform, styles) is saved and restored.
  // The view is kept for K.Z.project.
  function render(scene, ctx, view = {}) {
    const dpr = view.dpr || window.devicePixelRatio || 1;
    const zoom = view.zoom ?? 1, cx = view.cx ?? 0, cy = view.cy ?? 0;
    canonicalSort(scene);
    scene.updateGraph();
    ctx.save();
    ctx.setTransform(1, 0, 0, 1, 0, 0);
    if (view.background) { ctx.fillStyle = view.background; ctx.fillRect(0, 0, ctx.canvas.width, ctx.canvas.height); }
    else if (view.clear !== false) ctx.clearRect(0, 0, ctx.canvas.width, ctx.canvas.height);
    ctx.setTransform(dpr * zoom, 0, 0, dpr * zoom, dpr * cx, dpr * cy);
    ctx.lineJoin = 'round'; ctx.lineCap = 'round';
    scene.renderGraphCanvas(ctx);
    ctx.restore();
    scene._kzView = { zoom, cx, cy };
    return scene;
  }
  // Screen position (CSS px) of an anchor after the last K.Z.render of its scene (or `view`).
  // z is Zdog's depth (bigger = nearer). Use it to pin DOM text or K.proxy boxes to the 3D scene.
  function project(anchor, view) {
    let root = anchor; while (root.addTo) root = root.addTo;
    const v = view || root._kzView;
    if (!v) throw new Error('K.Z.project: render the scene with K.Z.render first (or pass a view)');
    const o = anchor.renderOrigin;
    return { x: v.cx + v.zoom * o.x, y: v.cy + v.zoom * o.y, z: o.z };
  }
  // Canvas at W x H CSS px with a W*dpr backing store (render.py --scale 2 stays crisp).
  function canvas(W, H, parent) {
    const dpr = window.devicePixelRatio || 1, cv = document.createElement('canvas');
    cv.width = Math.round(W * dpr); cv.height = Math.round(H * dpr);
    Object.assign(cv.style, { position: 'absolute', left: 0, top: 0, width: W + 'px', height: H + 'px' });
    if (parent) parent.appendChild(cv);
    return cv;
  }

  // ---------------- depth layers ----------------
  // Zdog sorts by average z, so big ground solids trade places with a character as the camera
  // swings. layer(item, bias) adds a fixed sort bias to item and its subtree (Groups sort inside
  // themselves, so their children are left alone). Far → near: e.g. FAR -40000 … FORE +10000.
  function layer(item, bias) {
    const walk = it => {
      if (!it._kzBase) it._kzBase = it.updateSortValue;
      const base = it._kzBase;
      it.updateSortValue = function () { base.call(this); this.sortValue += bias; };
      if (!(it instanceof Z.Group)) it.children.forEach(walk);
    };
    walk(item);
    return item;
  }
  const LAYERS = { FAR: -40000, RIDGE: -30000, MID: -20000, STAGE: -10000, SHADOW: -9000, ACTOR: 0, FORE: 10000 };

  // ---------------- camera ----------------
  // Counter-roll for an orbit camera (yaw about y, then pitch about x). A ground circle stays
  // level under yaw + pitch, but a long course along the world x axis tilts on screen by
  // atan(sin yaw · sin pitch). roll.rotate.z = levelRoll(yaw, pitch) puts that axis back level
  // (side-scrolling dioramas); it leans verticals by the same angle, so keep yaw small with it.
  const levelRoll = (yaw, pitch) => -Math.atan2(Math.sin(yaw) * Math.sin(pitch), Math.cos(yaw));
  // scene → roll (screen roll) → cam (yaw, pitch) → world (translated by -target). Add the set
  // to `world`. set({ yaw, pitch, target, level }) each frame; pitch > 0 looks down from above;
  // level: true applies levelRoll (dioramas), false (default) for turntables and orbits.
  // Orthographic: there is no dolly, zoom is the view's `zoom`.
  function camera(scene) {
    const roll = new Z.Anchor({ addTo: scene });
    const cam = new Z.Anchor({ addTo: roll });
    const world = new Z.Anchor({ addTo: cam });
    function set({ yaw = 0, pitch = 0, target = {}, level = false } = {}) {
      cam.rotate.y = yaw; cam.rotate.x = -pitch;
      roll.rotate.z = level ? levelRoll(yaw, pitch) : 0;
      world.translate.set({ x: -(target.x || 0), y: -(target.y || 0), z: -(target.z || 0) });
    }
    return { roll, cam, world, set };
  }

  // ---------------- shaping ----------------
  // Volume-preserving squash: amt > 0 squashes (y shrinks, x/z grow), amt < 0 stretches.
  // pivot (anchor-local point, default the origin) stays fixed, e.g. the feet.
  function squash(anchor, amt, pivot = { x: 0, y: 0, z: 0 }) {
    if (!anchor._kzRest) anchor._kzRest = anchor.translate.copy();
    const sy = Math.max(0.05, 1 - amt), sxz = 1 / Math.sqrt(sy);
    anchor.scale.set({ x: sxz, y: sy, z: sxz });
    const r = anchor._kzRest, px = pivot.x || 0, py = pivot.y || 0, pz = pivot.z || 0;
    anchor.translate.set({ x: r.x + px * (1 - sxz), y: r.y + py * (1 - sy), z: r.z + pz * (1 - sxz) });
    return anchor;
  }
  // Contact shadow for `caster` (an anchor whose translate is its feet, in the same parent).
  // surfaceFn(x, z) -> the y of the ground below (default 0). Returns { shape, update() };
  // call update() in pose(t) after moving the caster. It shrinks with height (falloff px).
  function shadow(caster, surfaceFn = () => 0, o = {}) {
    const shape = new Z.Ellipse({ addTo: o.addTo || caster.addTo, diameter: o.diameter || 30,
      rotate: { x: TAU / 4 }, fill: true, stroke: 0, color: o.color || 'rgba(30,42,36,0.22)' });
    if (o.bias !== undefined) layer(shape, o.bias);
    const falloff = o.falloff || 110, min = o.min ?? 0.2;
    function update() {
      const { x, y, z } = caster.translate, g = surfaceFn(x, z);
      shape.translate.set({ x, y: g - 0.3, z });
      shape.scale = Math.max(min, 1 - Math.max(0, g - y) / falloff);
      return shape;
    }
    update();
    return { shape, update };
  }
  // Fake extrusion (Zdog has none): `layers` copies of a flat shape stepped back along -z by
  // `depth`, the back ones in `side` colour. shape = a Zdog item (copied with copyGraph) or a
  // factory (addTo, z, i) => item for things copyGraph can't clone (e.g. Zfont TextGroup).
  // Returns a Group (sorted inside; deterministic through K.Z.render's canonicalSort).
  function extrude(shape, depth = 6, layers = 4, o = {}) {
    const isFn = typeof shape === 'function';
    const addTo = o.addTo || (isFn ? null : shape.addTo);
    if (!addTo) throw new Error('K.Z.extrude: pass { addTo } with a factory');
    const g = new Z.Group({ addTo, updateSort: true });
    const z0 = isFn ? 0 : shape.translate.z;
    for (let i = layers; i >= 1; i--) {
      const z = z0 - depth * i / layers;
      if (isFn) shape(g, z, i);
      else shape.copyGraph({ addTo: g, translate: { x: shape.translate.x, y: shape.translate.y, z },
        color: o.side || shade(shape.color, { z: -1 }) });
    }
    if (isFn) shape(g, z0, 0);
    else { addTo.removeChild(shape); g.addChild(shape); }
    return g;
  }
  // ---- colour ----
  const hex2 = h => {
    const s = String(h).replace('#', ''), f = s.length === 3 ? s.split('').map(c => c + c).join('') : s.slice(0, 6);
    return [0, 2, 4].map(i => parseInt(f.slice(i, i + 2), 16));
  };
  const toHex = rgb => '#' + rgb.map(v => Math.round(K.clamp(v, 0, 255)).toString(16).padStart(2, '0')).join('').toUpperCase();
  const mix = (a, b, p) => { const A = hex2(a), B = hex2(b); return toHex(A.map((v, i) => K.lerp(v, B[i], p))); };
  // Flat Lambert shade of a colour for a face normal: ambient + (1 - ambient)·max(0, n·l).
  // Default light comes from upper-left-front (Zdog: -y is up, +z toward the camera).
  const LIGHT = { x: -0.45, y: -0.8, z: 0.4 };
  function shade(hexc, normal, light = LIGHT, ambient = 0.62) {
    if (typeof hexc !== 'string' || hexc[0] !== '#') return hexc;   // rgba() etc.: leave alone
    const n = norm(normal), l = norm(light);
    const k = ambient + (1 - ambient) * Math.max(0, n.x * l.x + n.y * l.y + n.z * l.z);   // 1 = facing the light
    return mix(hexc, '#000000', (1 - k) * 0.9);
  }
  const norm = v => { const x = v.x || 0, y = v.y || 0, z = v.z || 0, m = Math.hypot(x, y, z) || 1; return { x: x / m, y: y / m, z: z / m }; };
  // Box face colours from one base colour (static: Zdog has no lighting, faces don't relight).
  const boxFaces = (c, light) => ({ color: shade(c, { z: 1 }, light), topFace: shade(c, { y: -1 }, light),
    bottomFace: shade(c, { y: 1 }, light), leftFace: shade(c, { x: -1 }, light),
    rightFace: shade(c, { x: 1 }, light), rearFace: shade(c, { z: -1 }, light), frontFace: shade(c, { z: 1 }, light) });
  // Show / hide a whole subtree (Anchors have no `visible` of their own).
  function show(item, on) { if ('visible' in item) item.visible = on; item.children.forEach(c => show(c, on)); return item; }

  // ---------------- models (E11.1) ----------------
  // A model file registers itself: K.Z.model('pip', { palette: {slot: hex}, build(addTo, opts) }).
  // build returns { root, joints, size: {w, h, d}, anchors }. K.Z.make(id, addTo, { palette,
  // scale, translate, rotate }) resolves the palette (model defaults ← brand slots; a brand
  // `primary` without `shade` gets a derived shade) and wraps the model in a scaled root anchor.
  const MODELS = {};
  function model(id, def) {
    if (!def || typeof def.build !== 'function') throw new Error(`K.Z.model("${id}"): needs { palette, build }`);
    MODELS[id] = def;
    return def;
  }
  function palette(defaults, brand = {}) {
    const P = Object.assign({}, defaults);
    for (const k in brand) if (brand[k] !== undefined && brand[k] !== null) P[k] = brand[k];
    if (brand.primary && !brand.shade && 'shade' in P) P.shade = mix(brand.primary, '#000000', 0.22);
    if (brand.primary && !brand.light && 'light' in P && defaults.light === undefined) P.light = mix(brand.primary, '#FFFFFF', 0.4);
    return P;
  }
  function make(id, addTo, o = {}) {
    const def = MODELS[id];
    if (!def) throw new Error(`K.Z.make: no model "${id}" — load models/${id}.js (catalog.py use P ${id}) after kit-zdog.js`);
    const s = o.scale ?? 1;
    const root = new Z.Anchor({ addTo, translate: o.translate, rotate: o.rotate, scale: s });
    const P = palette(def.palette || {}, o.palette);
    const m = def.build(root, Object.assign({}, o, { palette: P, scale: s })) || {};
    const size = m.size || {};
    return Object.assign({ id, joints: {}, anchors: {} }, m, { root, palette: P,
      size: { w: (size.w || 0) * s, h: (size.h || 0) * s, d: (size.d || 0) * s } });
  }

  // ---------------- rig + clips (E10.4) ----------------
  // Joint names: root (feet / travel), hips (squash pivot at the feet), spine, neck, head,
  // armL, armR, forearmL, forearmR, legL, legR. A clip channel is "<joint>.<prop>.<axis>"
  // (prop: translate | rotate | scale) or "squash" (volume-preserving, on hips). Channels are
  // ADDITIVE offsets from the rest pose, so clips layer, blend (weight / fades) and time-shift.
  // A channel is a K.track key table in clip-local seconds, or a function (u, p) -> offset.
  const JOINTS = ['root', 'hips', 'spine', 'neck', 'head', 'armL', 'armR', 'forearmL', 'forearmR', 'legL', 'legR'];
  const io = K.bezier(.45, 0, .15, 1), outE = K.bezier(.16, 1, .3, 1);
  // Landing squash l·e^(−kτ)·cos(wτ), tapered to exactly 0 between τ = 4/k and 6/k (amplitude
  // < 2 % of l there), so a one-shot clip ends at rest and loop seams stay pixel-exact.
  const settle = (u, l, k = 7, w = 16) => u <= 0 ? 0 :
    l * Math.exp(-k * u) * Math.cos(w * u) * (1 - K.ease.inOutCubic(K.seg(u, 4 / k, 6 / k)));
  // Clip factories: K.Z.CLIPS.hop({ h: 30 }) -> { dur, loop, ch }. Numbers from Pip (spikes):
  // stride 0.36 s; crouch 0.15–0.25 s; squash ≤ 0.24 then l·e^(−7τ)·cos(16τ); arm overlap
  // springTrack ω 14–16, ζ 0.75–0.8. No elastic easing, no landing shake.
  const CLIPS = {
    idle: ({ period = 2.4, breathe = 0.6, sway = 0.06 } = {}) => ({ dur: period, loop: true, ch: {
      'spine.translate.y': u => breathe * Math.sin(TAU * u / period),
      'neck.rotate.z': u => sway * Math.sin(TAU * u / period) } }),
    anticipate: ({ crouch = 0.16, len = 0.2 } = {}) => ({ dur: len, ch: {
      squash: [[0, 0], [len, crouch, K.ease.outCubic]],
      'armL.rotate.z': [[0, 0], [len, -0.3]], 'armR.rotate.z': [[0, 0], [len, 0.3]] } }),
    hop: ({ h = 22, air = 0.5, crouch = 0.12, pre = 0.12, land = 0.14 } = {}) => {
      const t0 = pre, t1 = pre + air;
      return { dur: t1 + 0.9, ch: {
        'root.translate.y': u => (u > t0 && u < t1) ? -h * 4 * ((u - t0) / air) * (1 - (u - t0) / air) : 0,
        squash: u => K.track([[0, 0], [t0, crouch, K.ease.outCubic], [t0 + 0.07, -0.12, K.ease.outCubic], [t0 + 0.26, 0]], u)
          + settle(u - t1, land),
        'armL.rotate.z': u => 1.0 * K.springTrack([[0, 0], [t0 + 0.06, 1], [t1 + 0.02, 0]], u, 16, .8),
        'armR.rotate.z': u => -1.0 * K.springTrack([[0, 0], [t0 + 0.06, 1], [t1 + 0.02, 0]], u, 16, .8),
        'neck.rotate.x': u => 0.25 * K.track([[t0 - 0.02, 0], [t0 + 0.08, 1], [t1 - 0.08, 1], [t1, 0]], u) } };
    },
    leap: (p = {}) => CLIPS.hop(Object.assign({ h: 56, air: 1.1, crouch: 0.22, pre: 0.25, land: 0.24 }, p)),
    land: ({ amt = 0.2 } = {}) => ({ dur: 0.9, ch: { squash: u => settle(u, amt) } }),
    run: ({ stride = 0.36, legs = 0.9, arms = 0.85, lean = 0.2 } = {}) => {
      const st = K.len(stride);
      return { dur: st, loop: true, ch: {
        'legL.rotate.x': u => legs * Math.sin(TAU * u / st), 'legR.rotate.x': u => -legs * Math.sin(TAU * u / st),
        'armL.rotate.x': u => -arms * Math.sin(TAU * u / st), 'armR.rotate.x': u => arms * Math.sin(TAU * u / st),
        'spine.translate.y': u => 2 * Math.abs(Math.cos(TAU * u / st)) - 1.2,
        'spine.rotate.x': () => -lean } };
    },
    wave: ({ len = 1.6, hz = 2.1, amp = 0.32, raise = 2.55, side = 'R' } = {}) => {
      const sgn = side === 'R' ? -1 : 1, arm = 'arm' + side;
      return { dur: len + 0.5, ch: {
        [arm + '.rotate.z']: u => {
          const r = K.springTrack([[0, 0], [0.0001, 1], [len - 0.35, 0]], u, 13, .78);
          const w = Math.sin(TAU * hz * (u - 0.25)) * amp * K.seg(u, 0.25, 0.5) * (1 - K.seg(u, len - 0.6, len - 0.35));
          return sgn * raise * r + w * r;
        } } };
    },
    point: ({ len = 1.2, side = 'R', angle = 1.5 } = {}) => {
      const sgn = side === 'R' ? -1 : 1;
      return { dur: len + 0.5, ch: { ['arm' + side + '.rotate.z']: u =>
        sgn * angle * K.springTrack([[0, 0], [0.0001, 1], [len - 0.3, 0]], u, 15, .8) } };
    },
    // from: the root yaw to turn away from (e.g. -camYaw - current facing); ends facing the camera
    'turn-to-camera': ({ from = -TAU / 4, len = 0.45 } = {}) => ({ dur: len, ch: {
      'root.rotate.y': [[0, 0], [len, -from, io]] } }),
    // entrances hold their first value before `at` (holdIn), so the actor is off-stage / hidden
    'drop-in': ({ h = 220, len = 0.5, land = 0.22 } = {}) => ({ dur: len + 0.9, holdIn: true, ch: {
      'root.translate.y': [[0, -h], [len, 0, K.ease.inCubic]],
      squash: u => settle(u - len, land) } }),
    'spin-reveal': ({ len = 0.8, turns = 1 } = {}) => ({ dur: len, holdIn: true, ch: {
      'root.rotate.y': [[0, -TAU * turns], [len, 0, io]],
      'root.scale.x': [[0, -0.999], [len * 0.7, 0, outE]], 'root.scale.y': [[0, -0.999], [len * 0.7, 0, outE]],
      'root.scale.z': [[0, -0.999], [len * 0.7, 0, outE]] } }),
  };
  const evalCh = (ch, u, p) => typeof ch === 'function' ? ch(u, p) : K.track(ch, u, K.ease.inOutCubic);
  // rig(joints) captures the rest pose. rig.pose(t, layers) resets every joint to rest and adds
  // each layer: { clip: 'hop' | clipObject, at: seconds | '8b', speed, weight, in, until, out, ...params }.
  // A one-shot clip holds its last value after it ends; a loop clip plays from `at` to `until`.
  // Before `at` a layer adds nothing, except entrance clips (holdIn: drop-in, spin-reveal),
  // which hold their first value so the actor waits off-stage.
  // `in` / `out` are fade lengths (s) on the weight: cross-fade run → idle with two layers.
  function rig(joints) {
    const rest = {};
    for (const [name, j] of Object.entries(joints)) {
      if (!j) continue;
      rest[name] = { translate: j.translate.copy(), rotate: j.rotate.copy(), scale: j.scale.copy() };
      j._kzRest = j.translate.copy();
    }
    const cache = new Map();
    const clipOf = L => {
      if (typeof L.clip !== 'string') return L.clip;
      const key = L.clip + JSON.stringify(L);
      if (!cache.has(key)) {
        const f = CLIPS[L.clip];
        if (!f) throw new Error(`K.Z.rig: unknown clip "${L.clip}" (have ${Object.keys(CLIPS).join(', ')})`);
        cache.set(key, f(L));
      }
      return cache.get(key);
    };
    function pose(t, layers = []) {
      const acc = {};
      for (const L of layers) {
        const clip = clipOf(L), at = K.sec(L.at ?? 0), speed = L.speed ?? 1;
        if (t < at && !clip.holdIn) continue;
        const until = L.until !== undefined ? K.sec(L.until) : Infinity;
        let w = (L.weight ?? 1) * (L.in && t >= at ? K.seg(t, at, at + L.in) : 1);
        if (until < Infinity) w *= L.out ? 1 - K.seg(t, until - L.out, until) : (t < until ? 1 : 0);
        if (w <= 0) continue;
        let u = Math.max(0, t - at) * speed;
        if (clip.loop) u = K.wrap(u, clip.dur); else u = Math.min(u, clip.dur);
        for (const [ch, def] of Object.entries(clip.ch)) acc[ch] = (acc[ch] || 0) + w * evalCh(def, u, L);
      }
      for (const [name, r] of Object.entries(rest)) {
        const j = joints[name];
        j.translate.set(r.translate); j.rotate.set(r.rotate); j.scale.set(r.scale);
      }
      for (const [ch, v] of Object.entries(acc)) {
        if (ch === 'squash') { if (joints.hips) squash(joints.hips, v); continue; }
        const [name, prop, axis] = ch.split('.');
        const j = joints[name];
        if (j && j[prop]) j[prop][axis] += v;   // a clip touching a joint the model lacks is skipped
      }
      return acc;
    }
    return { joints, rest, pose };
  }
  const clip = (name, params) => {
    const f = CLIPS[name];
    if (!f) throw new Error(`K.Z.clip: unknown clip "${name}"`);
    return f(params);
  };

  K.Z = { render, project, canvas, canonicalSort, layer, LAYERS, levelRoll, camera, squash, shadow, extrude,
    shade, LIGHT, boxFaces, mix, show, model, make, palette, MODELS, rig, clip, CLIPS, JOINTS, settle, TAU };
})();
