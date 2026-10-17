/* Motion Studio catalog model: stepping-stone — a flat round stone with moss (original, Apache-2.0).
   Origin = centre of the top face (a character's feet go here). */
K.Z.model('stepping-stone', {
  palette: { primary: '#9AA39B', shade: '#7E877F', accent: '#8DB38A' },
  build(addTo, { palette: C, diameter = 30, height = 8 }) {
    const Z = Zdog, TAU = Z.TAU;
    const root = new Z.Anchor({ addTo });
    new Z.Cylinder({ addTo: root, diameter, length: height, translate: { y: height / 2 }, rotate: { x: TAU / 4 },
      stroke: 2, color: C.shade, frontFace: C.primary, backface: C.shade });
    new Z.Ellipse({ addTo: root, width: diameter * 0.45, height: diameter * 0.3, translate: { x: -diameter * 0.15, y: -0.6 },
      rotate: { x: TAU / 4 }, stroke: 2, fill: true, color: C.accent });
    return { root, size: { w: diameter, h: height, d: diameter }, joints: { root }, anchors: { top: root } };
  },
});
