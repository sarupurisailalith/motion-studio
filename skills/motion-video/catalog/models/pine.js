/* Motion Studio catalog model: pine — a three-tier conifer (original, Apache-2.0; from the
   2026-10-16 forest spike). Origin = base of the trunk. Scatter with K.rand for a tree line. */
K.Z.model('pine', {
  palette: { primary: '#2F6B5B', shade: '#245548', neutral: '#8A5A3C' },
  build(addTo, { palette: C }) {
    const Z = Zdog, TAU = Z.TAU;
    const root = new Z.Anchor({ addTo });
    new Z.Shape({ addTo: root, path: [{ y: 0 }, { y: -10 }], stroke: 5, color: C.neutral });
    [[30, 22, -8], [24, 20, -20], [17, 17, -32]].forEach(([d, l, y]) =>
      new Z.Cone({ addTo: root, diameter: d, length: l, translate: { y }, rotate: { x: TAU / 4 },
        stroke: false, color: C.primary, backface: C.shade }));
    return { root, size: { w: 30, h: 49, d: 30 }, joints: { root }, anchors: { top: new Z.Anchor({ addTo: root, translate: { y: -49 } }) } };
  },
});
