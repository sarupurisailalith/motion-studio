/* Motion Studio catalog model: ground-block — a slab of terrain with a coloured top and strata
   seams on the front (original, Apache-2.0; from the 2026-10-16 forest spike). Origin = centre of
   the top face. opts: width, depth, height. Line several up (different tops) for a course. */
K.Z.model('ground-block', {
  palette: { primary: '#D9C79E', shade: '#3F5A4C', neutral: '#34493E', ink: '#36503F' },
  build(addTo, { palette: C, width = 120, depth = 60, height = 60 }) {
    const Z = Zdog;
    const root = new Z.Anchor({ addTo });
    new Z.Box({ addTo: root, width, height, depth, translate: { y: height / 2 }, stroke: 0.5,
      color: C.shade, topFace: C.primary, leftFace: C.neutral, rightFace: C.neutral, bottomFace: false });
    [Math.min(14, height * 0.3), Math.min(34, height * 0.65)].forEach((d, i) => new Z.Shape({ addTo: root, closed: false,
      path: [{ x: -width / 2 + 2, y: d }, { x: 0, y: d + (i ? 3 : -2) }, { x: width / 2 - 2, y: d }].map(q => ({ ...q, z: depth / 2 + 0.6 })),
      stroke: 2.2, color: C.ink }));
    return { root, size: { w: width, h: height, d: depth }, joints: { root }, anchors: { top: root } };
  },
});
