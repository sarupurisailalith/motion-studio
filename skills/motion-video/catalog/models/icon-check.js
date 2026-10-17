/* Motion Studio catalog model: icon-check — a check mark on a round badge (original, Apache-2.0).
   Origin = centre; faces +z. anchors.mark: draw it on with a path reveal or scale it in. */
K.Z.model('icon-check', {
  palette: { primary: '#2DBE7E', shade: '#1E8A5A', light: '#FFFFFF' },
  build(addTo, { palette: C }) {
    const Z = Zdog;
    const root = new Z.Anchor({ addTo });
    const disc = new Z.Ellipse({ addTo: root, diameter: 46, stroke: 2, fill: true, color: C.primary });
    K.Z.extrude(disc, 7, 4, { side: C.shade });
    const mark = new Z.Shape({ addTo: root, path: [{ x: -10, y: 1 }, { x: -3, y: 9 }, { x: 11, y: -8 }], translate: { z: 1.5 },
      closed: false, stroke: 6, color: C.light, backface: false });
    return { root, size: { w: 48, h: 48, d: 10 }, joints: { root }, anchors: { mark } };
  },
});
