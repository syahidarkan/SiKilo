import * as THREE from 'three';

export interface CableParticles {
  pts: Float32Array;
  mat: THREE.PointsMaterial;
  curves: THREE.CatmullRomCurve3[];
  ts: Float32Array;
  speeds: Float32Array;
  curveIdx: Uint8Array;
  TOTAL: number;
}

export interface CableRefs {
  group: THREE.Group;
  particles: CableParticles;
}

function dropCable(
  ax: number, ay: number, az: number,
  bx: number, by: number, bz: number,
): THREE.Mesh {
  const mid = new THREE.Vector3(
    (ax + bx) / 2,
    (ay + by) / 2 + 0.3,
    (az + bz) / 2,
  );
  const curve = new THREE.CatmullRomCurve3([
    new THREE.Vector3(ax, ay, az),
    mid,
    new THREE.Vector3(bx, by, bz),
  ]);
  const geo = new THREE.TubeGeometry(curve, 16, 0.030, 5, false);
  const wireMat = new THREE.MeshStandardMaterial({ color: 0x1A1A1A, roughness: 0.9 });
  return new THREE.Mesh(geo, wireMat);
}

export function buildCables(scene: THREE.Scene, shopMeterPositions: THREE.Vector3[]): CableRefs {
  const g = new THREE.Group();

  // Span cable height and Z
  const spanY = 6.68;
  const spanZ = 3.80;

  // ── 3 Drop cables: from span above each meter down to meter ──
  for (const mp of shopMeterPositions) {
    const cable = dropCable(mp.x, spanY, spanZ, mp.x, mp.y + 0.1, mp.z);
    g.add(cable);
  }

  // ── Particle flow ─────────────────────────────────────────────
  const TOTAL = 300;
  const pts    = new Float32Array(TOTAL * 3);
  const ts     = new Float32Array(TOTAL);
  const speeds = new Float32Array(TOTAL);
  const curveIdx = new Uint8Array(TOTAL);

  // Build curves: 3 drop routes + a horizontal pan route
  const curves: THREE.CatmullRomCurve3[] = [];

  // Drop curve per shop
  for (const mp of shopMeterPositions) {
    const mid = new THREE.Vector3(mp.x, (spanY + mp.y) / 2 + 0.3, (spanZ + mp.z) / 2);
    curves.push(new THREE.CatmullRomCurve3([
      new THREE.Vector3(mp.x, spanY, spanZ),
      mid,
      new THREE.Vector3(mp.x, mp.y + 0.1, mp.z),
    ]));
  }

  // Horizontal pan route (left pole → right pole along span)
  curves.push(new THREE.CatmullRomCurve3([
    new THREE.Vector3(-13.7, spanY, spanZ),
    new THREE.Vector3(0,  spanY - 0.3, spanZ),
    new THREE.Vector3(13.7, spanY, spanZ),
  ]));

  for (let i = 0; i < TOTAL; i++) {
    ts[i]       = Math.random();
    speeds[i]   = 0.08 + Math.random() * 0.14;
    curveIdx[i] = Math.floor(Math.random() * curves.length);
  }

  const geo = new THREE.BufferGeometry();
  geo.setAttribute('position', new THREE.BufferAttribute(pts, 3));

  const pMat = new THREE.PointsMaterial({
    size: 0.08,
    color: 0x2FBF71,
    transparent: true,
    opacity: 0.85,
    blending: THREE.AdditiveBlending,
    depthWrite: false,
  });

  const particles = new THREE.Points(geo, pMat);
  g.add(particles);

  scene.add(g);

  return {
    group: g,
    particles: { pts, mat: pMat, curves, ts, speeds, curveIdx, TOTAL },
  };
}

export function tickParticles(
  p: CableParticles,
  delta: number,
  sp: number,
): void {
  const { pts, curves, ts, speeds, curveIdx, TOTAL } = p;

  // Color: red when sp<0.28, green when sp>0.76, mix in between
  if (sp < 0.28) {
    p.mat.color.setHex(0xEF4444);
  } else if (sp < 0.52) {
    p.mat.color.setHex(0xF97316);
  } else if (sp < 0.76) {
    p.mat.color.setHex(0xFBBF24);
  } else {
    p.mat.color.setHex(0x2FBF71);
  }

  for (let i = 0; i < TOTAL; i++) {
    ts[i] += speeds[i] * delta;
    if (ts[i] > 1) {
      ts[i] = 0;
      curveIdx[i] = Math.floor(Math.random() * curves.length);
    }
    const ci = Math.min(curveIdx[i], curves.length - 1);
    const pt = curves[ci].getPoint(ts[i]);
    pts[i * 3]     = pt.x;
    pts[i * 3 + 1] = pt.y;
    pts[i * 3 + 2] = pt.z;
  }

  const geo = (p as unknown as { _mesh?: THREE.Points })['_mesh'];
  if (geo) return; // handled outside

  // Attribute needs manual update - the scene loop accesses the attribute directly
}
