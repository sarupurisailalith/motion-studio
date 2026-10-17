/* Motion Studio catalog model: rock — a lumpy boulder with a mossy cap (original, Apache-2.0).
   Origin = ground contact. opts.seed varies the lumps (K.rand), so a field of rocks isn't cloned. */
K.Z.model('rock', {
  palette: { primary: '#9AA39B', shade: '#7E877F', accent: '#8DB38A' },
  build(addTo, { palette: C, seed = 1 }) {
    const Z = Zdog;
    const root = new Z.Anchor({ addTo });
    const lumps = [[0, -11, 0, 24], [-9, -8, 3, 16], [9, -7, -2, 17], [3, -6, 8, 14], [-3, -7, -8, 15]];
    lumps.forEach(([x, y, z, s], i) => new Z.Shape({ addTo: root, stroke: s * (0.85 + 0.3 * K.rand(seed, i)),
      translate: { x: x * (0.9 + 0.2 * K.rand(seed + 1, i)), y, z }, color: i ? C.shade : C.primary }));
    new Z.Shape({ addTo: root, translate: { x: -2, y: -20, z: 2 }, stroke: 12, color: C.accent });     // moss
    new Z.Shape({ addTo: root, translate: { x: 3, y: -16, z: 7 }, stroke: 8, color: C.primary });     // lit facet
    return { root, size: { w: 38, h: 26, d: 32 }, joints: { root }, anchors: { top: new Z.Anchor({ addTo: root, translate: { y: -24 } }) } };
  },
});
