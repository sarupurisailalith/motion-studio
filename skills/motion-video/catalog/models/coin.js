/* Motion Studio catalog model: coin — a thick coin with a raised rim and a star mark (original, Apache-2.0).
   Origin = centre; the faces look along ±z. Spin it with root.rotate.y. */
K.Z.model('coin', {
  palette: { primary: '#F5B83D', shade: '#C98A1E', light: '#FFE08A' },
  build(addTo, { palette: C }) {
    const Z = Zdog, TAU = Z.TAU;
    const root = new Z.Anchor({ addTo });
    new Z.Cylinder({ addTo: root, diameter: 44, length: 6, stroke: false, color: C.shade, frontFace: C.primary, backface: C.primary });
    const star = (z, rz) => {
      const pts = [];
      for (let i = 0; i < 10; i++) {
        const a = -TAU / 4 + i * TAU / 10, r = i % 2 ? 6 : 13;
        pts.push({ x: Math.cos(a) * r, y: Math.sin(a) * r });
      }
      new Z.Ellipse({ addTo: root, diameter: 36, translate: { z }, stroke: 2, color: C.light, backface: false, rotate: { y: rz } });
      new Z.Shape({ addTo: root, path: pts, translate: { z }, rotate: { y: rz }, stroke: 1.5, fill: true, color: C.light, backface: false });
    };
    star(3.2, 0); star(-3.2, TAU / 2);
    return { root, size: { w: 44, h: 44, d: 6 }, joints: { root }, anchors: {} };
  },
});
