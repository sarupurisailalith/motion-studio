/* Motion Studio catalog model: stream — a water channel with drifting ripples (original, Apache-2.0;
   from the 2026-10-16 forest spike). Origin = centre of the water surface. animate(t, D) moves the
   ripples; with D (the loop length) the drift is periodic, so the loop seam holds. */
K.Z.model('stream', {
  palette: { primary: '#7CC3D6', light: '#A5D8E4', accent: '#D6EEF3' },
  build(addTo, { palette: C, width = 90, depth = 60, height = 30 }) {
    const Z = Zdog;
    const root = new Z.Anchor({ addTo });
    new Z.Box({ addTo: root, width, height, depth, translate: { y: height / 2 }, stroke: 0.5,
      color: C.primary, topFace: C.light, leftFace: C.primary, rightFace: C.primary, bottomFace: false });
    const ripples = [0, 1, 2].map(i => new Z.Shape({ addTo: root, path: [{ x: -6 }, { x: 6 }],
      translate: { y: -0.5, z: -depth / 3 + depth / 3 * i }, stroke: 2, color: C.accent }));
    const span = width - 14;
    return {
      root, size: { w: width, h: height, d: depth }, joints: { root }, anchors: { ripples },
      animate(t, D) {
        const speed = D ? Math.max(1, Math.round(18 * D / span)) * span / D : 18;   // whole laps per loop
        ripples.forEach((r, i) => { r.translate.x = -span / 2 + K.wrap(speed * t + span * i / 3, span); });
      },
    };
  },
});
