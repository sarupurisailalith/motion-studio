/* Motion Studio catalog model: round-tree — a lollipop tree with a lit crown (original, Apache-2.0;
   from the 2026-10-16 forest spike). Origin = base of the trunk. */
K.Z.model('round-tree', {
  palette: { primary: '#6FA58C', light: '#8CBDA4', neutral: '#8A5A3C' },
  build(addTo, { palette: C }) {
    const Z = Zdog;
    const root = new Z.Anchor({ addTo });
    new Z.Shape({ addTo: root, path: [{ y: 0 }, { y: -22 }], stroke: 5, color: C.neutral });
    const crown = new Z.Shape({ addTo: root, translate: { y: -34 }, stroke: 32, color: C.primary });
    new Z.Shape({ addTo: crown, translate: { x: -5, y: -6, z: 6 }, stroke: 14, color: C.light });   // fake key light
    return { root, size: { w: 32, h: 50, d: 32 }, joints: { root }, anchors: { crown } };
  },
});
