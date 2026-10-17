/* =========================================================================
   MOTION KIT · P5 ADD-ON (kit-p5.js) — helpers for p5.js 2.x sketches under the composition
   contract (E10.7). Load order: vendor/p5.min.js → kit.js → kit-p5.js → scene script.
   (vendor.py P p5 downloads p5.js, LGPL-2.1, as an unmodified separate file; never inline it.)

   RULES (references/gotchas.md, "p5.js")
     - Instance mode + noLoop(): seek(t) sets the time and calls redraw(); draw() reads only t.
     - Never frameCount / millis() / deltaTime; randomSeed() at the top of every draw
       (K.sketch does it); noiseSeed() once in setup.
     - Accumulating sketches (trails, particles with state) recompute from a fixed warm-up or
       pre-simulate with K.presim, then index by frame.
   ========================================================================= */
(() => {
  const K = window.K;
  if (!K) throw new Error('kit-p5.js: load kit.js first');
  const TAU = Math.PI * 2;

  // A point on a circle in noise space: walking it over [0, D) returns to the start, so
  // p.noise(x + n.x, y + n.y) loops seamlessly. r = how far the walk travels (bigger = livelier).
  // cycles > 1 runs the circle several times per loop (faster change, same seam).
  function loopNoise(t, D, r = 1, cycles = 1) {
    const a = TAU * cycles * t / D;
    return { x: r * Math.cos(a), y: r * Math.sin(a), a };
  }

  // Fixed-dt pre-simulation for anything that integrates (particles, trails, physics).
  // step(state, i, dt) -> next state (return a NEW object; the previous one is kept).
  // Simulates `warmup` seconds before t = 0 (to skip the start transient), then D seconds.
  // Returns { at(t) -> state at frame floor(t / dt), states, dt }. Do it once in setup.
  function presim(step, dt, D, init, { warmup = 0 } = {}) {
    let s = init;
    const nw = Math.round(warmup / dt);
    for (let i = 0; i < nw; i++) s = step(s, i - nw, dt);
    const n = Math.round(D / dt), states = [s];
    for (let i = 1; i <= n; i++) states.push(s = step(s, i, dt));
    const at = t => states[K.clamp(Math.floor(t / dt + 1e-6), 0, n)];
    return { at, states, dt };
  }

  // Mount a p5 instance under the contract. o = { parent, width, height, seed, setup, draw }.
  //   setup: async (p) => { … }  load fonts / images here (p5 2.x: promises, no preload)
  //   draw:  (p, t) => { … }     the frame for time t; random() is re-seeded before each call
  // Returns { p, ready, seek(t) }. width/height default to K.FORMAT; pixelDensity = dpr, so
  // render.py --scale 2 stays crisp. renderer: p.WEBGL for 3D (render with --gl).
  function sketch(o) {
    if (!window.p5) throw new Error('K.sketch: load vendor/p5.min.js first (python3 vendor.py P p5)');
    const W = o.width ?? K.FORMAT.W, H = o.height ?? K.FORMAT.H, seed = o.seed ?? 1;
    let T = 0, resolve, reject;
    const ready = new Promise((a, b) => { resolve = a; reject = b; });
    const inst = new window.p5(p => {
      p.setup = async () => {
        try {
          p.pixelDensity(window.devicePixelRatio || 1);
          const c = p.createCanvas(W, H, o.renderer);
          if (o.parent) c.parent(o.parent);
          p.noLoop();
          p.noiseSeed(seed);
          if (o.setup) await o.setup(p);
          resolve(p);
        } catch (e) { reject(e); }
      };
      p.draw = () => { p.randomSeed(seed); o.draw(p, T); };
    }, o.parent || undefined);
    const seek = async t => { await ready; T = t; await inst.redraw(); };   // 2.x: redraw is async
    return { p: inst, ready, seek, get canvas() { return inst.canvas; } };
  }

  Object.assign(K, { loopNoise, presim, sketch });
})();
