/* Motion Studio catalog model: chart-bars — 3D bar chart on a base plate (original, Apache-2.0).
   build option values: [0..1, …] (default 4 bars). Grow a bar with anchors.bars[i].scale.y = v
   (its origin is at the base, so it grows upward). Data must be real: never invent numbers. */
K.Z.model('chart-bars', {
  palette: { primary: '#3F7CFF', accent: '#FF4D1F', neutral: '#D8D2C4', shade: '#B9B2A2' },
  build(addTo, { palette: C, values = [0.45, 0.7, 0.55, 1], highlight = -1 }) {
    const Z = Zdog, n = values.length, gap = 14, bw = 10, H = 60;
    const root = new Z.Anchor({ addTo });
    const w = n * gap + 8;
    new Z.Box({ addTo: root, width: w, height: 4, depth: 22, translate: { y: -2 }, stroke: 0.5, ...K.Z.boxFaces(C.neutral) });
    const bars = values.map((v, i) => {
      const a = new Z.Anchor({ addTo: root, translate: { x: -w / 2 + 4 + gap * (i + 0.5), y: -4 }, scale: { y: v } });
      const col = i === highlight || (highlight < 0 && i === n - 1) ? C.accent : C.primary;
      new Z.Box({ addTo: a, width: bw, height: H, depth: bw, translate: { y: -H / 2 }, stroke: 0.5, ...K.Z.boxFaces(col) });
      return a;
    });
    return { root, size: { w, h: H + 4, d: 22 }, joints: { root }, anchors: { bars } };
  },
});
