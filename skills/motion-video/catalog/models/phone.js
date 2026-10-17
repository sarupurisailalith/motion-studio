/* Motion Studio catalog model: phone — a generic smartphone (original, Apache-2.0). No brand marks.
   Origin = centre; the screen faces +z. anchors.screen is the screen centre (pin a screenshot there
   with K.Z.project, or draw UI as Zdog shapes on it). */
K.Z.model('phone', {
  palette: { primary: '#1E2230', shade: '#11141C', light: '#DCE6FF', accent: '#3F7CFF' },
  build(addTo, { palette: C }) {
    const Z = Zdog;
    const root = new Z.Anchor({ addTo });
    const body = new Z.RoundedRect({ addTo: root, width: 40, height: 80, cornerRadius: 8, stroke: 2, fill: true, color: C.primary });
    K.Z.extrude(body, 7, 4, { side: C.shade });
    const screen = new Z.RoundedRect({ addTo: root, width: 34, height: 72, cornerRadius: 5, translate: { z: 1.2 },
      stroke: 0.5, fill: true, color: C.light, backface: false });
    new Z.RoundedRect({ addTo: root, width: 10, height: 2.4, cornerRadius: 1.2, translate: { y: -32, z: 1.6 },
      stroke: 0.5, fill: true, color: C.primary, backface: false });                              // speaker slot
    return { root, size: { w: 40, h: 80, d: 8 }, joints: { root }, anchors: { screen } };
  },
});
