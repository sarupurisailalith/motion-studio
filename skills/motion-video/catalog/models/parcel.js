/* Motion Studio catalog model: parcel — a taped cardboard box (original, Apache-2.0).
   Origin = centre of the bottom face. joints.hips squashes it on landing (K.Z.squash). */
K.Z.model('parcel', {
  palette: { primary: '#E8C58A', shade: '#C9A26A', light: '#F3DCAE', accent: '#B8844A' },
  build(addTo, { palette: C }) {
    const Z = Zdog;
    const root = new Z.Anchor({ addTo });
    const hips = new Z.Anchor({ addTo: root });
    const box = new Z.Box({ addTo: hips, width: 40, height: 32, depth: 34, translate: { y: -16 }, stroke: 1,
      color: C.primary, leftFace: C.shade, rightFace: C.shade, topFace: C.light, bottomFace: C.shade });
    new Z.Shape({ addTo: box, path: [{ x: 0, y: -16.6, z: -17.6 }, { x: 0, y: -16.6, z: 17.6 }, { x: 0, y: 16, z: 17.6 }],
      closed: false, stroke: 4, color: C.accent });                                               // tape
    return { root, size: { w: 40, h: 32, d: 34 }, joints: { root, hips }, anchors: { top: new Z.Anchor({ addTo: hips, translate: { y: -32 } }) } };
  },
});
