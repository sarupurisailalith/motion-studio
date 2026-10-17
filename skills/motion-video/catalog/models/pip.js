/* Motion Studio catalog model: pip — the Motion Studio mascot (original, Apache-2.0).
   A round character rigged with the standard joints (K.Z.JOINTS), from the 2026-10-16 spikes.
   Origin = between the feet; +y is down, so the head is at about y = -78. */
K.Z.model('pip', {
  palette: { primary: '#FF4D1F', shade: '#C93A12', neutral: '#2B2B2B', ink: '#111111', light: '#FFFFFF' },
  build(addTo, { palette: C }) {
    const Z = Zdog, TAU = Z.TAU;
    const root = new Z.Anchor({ addTo });                                  // feet; travel + facing
    const hips = new Z.Anchor({ addTo: root });                            // squash pivot (origin = feet)
    const spine = new Z.Anchor({ addTo: hips, translate: { y: -38 } });
    new Z.Shape({ addTo: spine, stroke: 40, color: C.primary });                                     // torso
    new Z.Shape({ addTo: spine, path: [{ x: -7 }, { x: 7 }], translate: { y: 10, z: 12 }, stroke: 14, color: C.shade });
    const neck = new Z.Anchor({ addTo: spine, translate: { y: -24 } });
    const head = new Z.Shape({ addTo: neck, stroke: 30, color: C.primary });
    // the face is a Group so the pupils always draw over the eye whites
    const face = new Z.Group({ addTo: head, translate: { z: 13 }, updateSort: true });
    const eyeL = new Z.Anchor({ addTo: face, translate: { x: -5, y: -2 } });
    new Z.Ellipse({ addTo: eyeL, diameter: 6, stroke: 1, fill: true, color: C.light, backface: false });
    new Z.Ellipse({ addTo: eyeL, diameter: 2.6, stroke: 1, fill: true, color: C.ink, translate: { z: 0.6 }, backface: false });
    const eyeR = eyeL.copyGraph({ translate: { x: 5, y: -2 } });
    new Z.Ellipse({ addTo: face, diameter: 6, quarters: 2, translate: { y: 5 }, rotate: { z: TAU / 4 },
      closed: false, stroke: 1.6, color: C.ink, backface: false });                                  // smile
    const armL = new Z.Shape({ addTo: spine, path: [{ y: 0 }, { y: 18 }], translate: { x: -18, y: -6 }, stroke: 7, color: C.neutral });
    const handL = new Z.Shape({ addTo: armL, translate: { y: 20 }, stroke: 10, color: C.primary });
    const armR = armL.copyGraph({ translate: { x: 18, y: -6 } });
    const legL = new Z.Shape({ addTo: hips, path: [{ y: 0 }, { y: 12 }], translate: { x: -9, y: -15 }, stroke: 8, color: C.neutral });
    new Z.RoundedRect({ addTo: legL, width: 6, height: 10, cornerRadius: 3, translate: { y: 13, z: 3 },
      rotate: { x: TAU / 4 }, stroke: 6, fill: true, color: C.neutral });                           // foot
    const legR = legL.copyGraph({ translate: { x: 9, y: -15 } });
    return {
      root, size: { w: 50, h: 80, d: 40 },
      joints: { root, hips, spine, neck, head, armL, armR, legL, legR, eyeL, eyeR },
      anchors: { head, face, handL, handR: armR.children[0], top: neck },
      // blink at the given times (eyes squash for 0.14 s)
      blink(t, times) {
        const d = times.reduce((m, b) => Math.min(m, Math.abs(t - b)), 9);
        eyeL.scale.y = eyeR.scale.y = d < 0.07 ? 0.15 : 1;
      },
    };
  },
});
