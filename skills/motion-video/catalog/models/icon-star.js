/* Motion Studio catalog model: icon-star — a chunky extruded five-point star (original, Apache-2.0).
   Origin = centre; faces +z. Generic icon (ratings, favourites): no brand meaning. */
K.Z.model('icon-star', {
  palette: { primary: '#FFC53D', shade: '#D9961A' },
  build(addTo, { palette: C }) {
    const Z = Zdog, TAU = Z.TAU, pts = [];
    for (let i = 0; i < 10; i++) { const a = -TAU / 4 + i * TAU / 10, r = i % 2 ? 11 : 24; pts.push({ x: Math.cos(a) * r, y: Math.sin(a) * r }); }
    const root = new Z.Anchor({ addTo });
    const face = new Z.Shape({ addTo: root, path: pts, stroke: 4, fill: true, color: C.primary });
    K.Z.extrude(face, 8, 4, { side: C.shade });
    return { root, size: { w: 52, h: 50, d: 12 }, joints: { root }, anchors: {} };
  },
});
