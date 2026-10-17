/* Motion Studio catalog model: icon-heart — an extruded heart (original, Apache-2.0).
   Origin = centre; faces +z. Generic icon (likes, care). */
K.Z.model('icon-heart', {
  palette: { primary: '#FF4D6A', shade: '#C9304A' },
  build(addTo, { palette: C }) {
    const Z = Zdog;
    const root = new Z.Anchor({ addTo });
    const face = new Z.Shape({ addTo: root, stroke: 4, fill: true, color: C.primary, translate: { y: -2 }, path: [
      { x: 0, y: -9 },
      { bezier: [{ x: 4, y: -20 }, { x: 22, y: -18 }, { x: 20, y: -4 }] },
      { bezier: [{ x: 18, y: 8 }, { x: 4, y: 14 }, { x: 0, y: 22 }] },
      { bezier: [{ x: -4, y: 14 }, { x: -18, y: 8 }, { x: -20, y: -4 }] },
      { bezier: [{ x: -22, y: -18 }, { x: -4, y: -20 }, { x: 0, y: -9 }] },
    ] });
    K.Z.extrude(face, 8, 4, { side: C.shade });
    return { root, size: { w: 46, h: 46, d: 12 }, joints: { root }, anchors: {} };
  },
});
