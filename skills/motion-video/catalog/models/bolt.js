/* Motion Studio catalog model: bolt — a small boxy robot (original, Apache-2.0).
   Same joint names as pip (K.Z.JOINTS), so every rig clip works on it unchanged.
   Origin = between the feet; the antenna tip is at about y = -92. */
K.Z.model('bolt', {
  palette: { primary: '#3F7CFF', shade: '#2A55B8', neutral: '#2B2F3A', accent: '#FFC53D', ink: '#0E1220', light: '#E8F0FF' },
  build(addTo, { palette: C }) {
    const Z = Zdog, TAU = Z.TAU;
    const root = new Z.Anchor({ addTo });
    const hips = new Z.Anchor({ addTo: root });
    const legL = new Z.Shape({ addTo: hips, path: [{ y: 0 }, { y: 14 }], translate: { x: -8, y: -16 }, stroke: 7, color: C.neutral });
    new Z.Box({ addTo: legL, width: 9, height: 4, depth: 12, translate: { y: 15, z: 2 }, stroke: 1.5,
      color: C.neutral, topFace: C.neutral, leftFace: C.ink, rightFace: C.ink, frontFace: C.neutral });
    const legR = legL.copyGraph({ translate: { x: 8, y: -16 } });
    const spine = new Z.Anchor({ addTo: hips, translate: { y: -34 } });
    new Z.Box({ addTo: spine, width: 34, height: 30, depth: 24, stroke: 3, color: C.primary,
      ...K.Z.boxFaces(C.primary) });
    new Z.RoundedRect({ addTo: spine, width: 18, height: 10, cornerRadius: 3, translate: { y: 2, z: 13.5 },
      stroke: 1.5, fill: true, color: C.light });                                                     // chest panel
    new Z.Shape({ addTo: spine, translate: { x: -4, y: 2, z: 14.6 }, stroke: 3.4, color: C.accent });  // status light
    const armL = new Z.Shape({ addTo: spine, path: [{ y: 0 }, { y: 16 }], translate: { x: -21, y: -8 }, stroke: 6, color: C.neutral });
    new Z.Shape({ addTo: armL, translate: { y: 18 }, stroke: 9, color: C.shade });                   // hand
    const armR = armL.copyGraph({ translate: { x: 21, y: -8 } });
    const neck = new Z.Anchor({ addTo: spine, translate: { y: -15 } });
    new Z.Shape({ addTo: neck, path: [{ y: 0 }, { y: -6 }], stroke: 6, color: C.neutral });
    const head = new Z.Anchor({ addTo: neck, translate: { y: -18 } });
    new Z.Box({ addTo: head, width: 30, height: 22, depth: 22, stroke: 3, ...K.Z.boxFaces(C.primary) });
    const face = new Z.Group({ addTo: head, translate: { z: 12.6 }, updateSort: true });
    new Z.RoundedRect({ addTo: face, width: 24, height: 12, cornerRadius: 4, stroke: 1, fill: true, color: C.ink, backface: false });
    const eyeL = new Z.Anchor({ addTo: face, translate: { x: -5, z: 0.6 } });
    new Z.Ellipse({ addTo: eyeL, width: 4.4, height: 5, stroke: 1, fill: true, color: C.accent, backface: false });
    const eyeR = eyeL.copyGraph({ translate: { x: 5, z: 0.6 } });
    new Z.Shape({ addTo: head, path: [{ y: -11 }, { y: -20 }], stroke: 2, color: C.neutral });       // antenna
    new Z.Shape({ addTo: head, translate: { y: -22 }, stroke: 6, color: C.accent });
    return {
      root, size: { w: 52, h: 94, d: 26 },
      joints: { root, hips, spine, neck, head, armL, armR, legL, legR, eyeL, eyeR },
      anchors: { head, face, handL: armL.children[0], handR: armR.children[0], top: head },
      blink(t, times) {
        const d = times.reduce((m, b) => Math.min(m, Math.abs(t - b)), 9);
        eyeL.scale.y = eyeR.scale.y = d < 0.07 ? 0.15 : 1;
      },
    };
  },
});
