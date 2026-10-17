/* Motion Studio catalog model: plant — a potted plant with five leaves (original, Apache-2.0).
   Origin = bottom of the pot. anchors.leaves: sway them with rotate.z for a breeze. */
K.Z.model('plant', {
  palette: { primary: '#4FA36B', shade: '#2F7A4D', accent: '#D9734E', light: '#F2E3C6' },
  build(addTo, { palette: C }) {
    const Z = Zdog, TAU = Z.TAU;
    const root = new Z.Anchor({ addTo });
    new Z.Cylinder({ addTo: root, diameter: 26, length: 22, translate: { y: -11 }, rotate: { x: TAU / 4 }, stroke: false,
      color: C.accent, frontFace: K.Z.shade(C.accent, { y: 1 }), backface: K.Z.mix(C.accent, '#000000', 0.45) });
    new Z.Ellipse({ addTo: root, diameter: 28, translate: { y: -22 }, rotate: { x: TAU / 4 }, stroke: 3, color: K.Z.mix(C.accent, '#FFFFFF', 0.2) });
    const stem = new Z.Anchor({ addTo: root, translate: { y: -22 } });
    const leaves = [[0, -34, 0], [-0.7, -26, 0.6], [0.7, -26, -0.6], [-1.15, -16, -1.2], [1.15, -16, 1.4]].map(([rz, len, ry], i) => {
      const a = new Z.Anchor({ addTo: stem, rotate: { z: rz, y: ry } });
      new Z.Shape({ addTo: a, path: [{ y: 0 }, { y: len * 0.55 }], stroke: 2, color: C.shade });
      new Z.Ellipse({ addTo: a, width: 12, height: -len * 0.8, translate: { y: len * 0.62 }, stroke: 2, fill: true,
        color: i % 2 ? C.shade : C.primary });
      return a;
    });
    return { root, size: { w: 46, h: 62, d: 30 }, joints: { root }, anchors: { leaves } };
  },
});
