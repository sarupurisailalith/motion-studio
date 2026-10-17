/* Motion Studio catalog model: house — a small gabled house (original, Apache-2.0).
   Origin = centre of the ground footprint. */
K.Z.model('house', {
  palette: { primary: '#F2E3C6', shade: '#D9C59E', accent: '#D9573B', ink: '#5B3B2E', light: '#BFE3F0' },
  build(addTo, { palette: C }) {
    const Z = Zdog, W = 50, D = 40, Hw = 30, R = 20;
    const root = new Z.Anchor({ addTo });
    new Z.Box({ addTo: root, width: W, height: Hw, depth: D, translate: { y: -Hw / 2 }, stroke: 0.5,
      color: C.primary, leftFace: C.shade, rightFace: C.shade, topFace: false, bottomFace: false });
    // gable ends (triangles) and two roof slopes
    [D / 2, -D / 2].forEach(z => new Z.Shape({ addTo: root, path: [{ x: -W / 2, y: -Hw }, { x: 0, y: -Hw - R }, { x: W / 2, y: -Hw }],
      translate: { z }, stroke: 0.5, fill: true, color: z > 0 ? C.primary : C.shade }));
    const o = 3;   // eaves overhang
    [-1, 1].forEach(s => new Z.Shape({ addTo: root, path: [
      { x: 0, y: -Hw - R - 0.5, z: -D / 2 - o }, { x: 0, y: -Hw - R - 0.5, z: D / 2 + o },
      { x: s * (W / 2 + o), y: -Hw + o * R / (W / 2), z: D / 2 + o }, { x: s * (W / 2 + o), y: -Hw + o * R / (W / 2), z: -D / 2 - o }],
      stroke: 1, fill: true, color: s < 0 ? C.accent : K.Z.shade(C.accent, { x: 1, y: -1 }) }));
    new Z.Box({ addTo: root, width: 6, height: 12, depth: 6, translate: { x: 13, y: -Hw - 14, z: -6 }, stroke: 0.5,
      ...K.Z.boxFaces(C.ink), topFace: K.Z.mix(C.ink, '#000000', 0.3) });                         // chimney
    new Z.Rect({ addTo: root, width: 10, height: 16, translate: { x: -10, y: -8, z: D / 2 + 0.3 }, stroke: 0.5, fill: true, color: C.ink });
    new Z.Rect({ addTo: root, width: 10, height: 9, translate: { x: 11, y: -16, z: D / 2 + 0.3 }, stroke: 1.5, fill: true, color: C.light });
    return { root, size: { w: W + 2 * o, h: Hw + R + 4, d: D + 2 * o }, joints: { root }, anchors: { door: root.children[root.children.length - 2] } };
  },
});
