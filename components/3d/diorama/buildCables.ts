/**
 * buildCables — Physical TubeGeometry cables + Points particle system
 * for NOTA LISTRIK energy-flow visualisation.
 */
import * as THREE from 'three';

export interface CableRefs {
  group: THREE.Group;
  particles: {
    pts:      THREE.Points;
    mat:      THREE.PointsMaterial;
    curves:   THREE.CatmullRomCurve3[];
    ts:       Float32Array;
    speeds:   Float32Array;
    curveIdx: Uint8Array;
    TOTAL:    number;
  };
}

function tubeCurve(pts: THREE.Vector3[], r = 0.055): THREE.Mesh {
  const curve = new THREE.CatmullRomCurve3(pts);
  const geo = new THREE.TubeGeometry(curve, 20, r, 7, false);
  const mesh = new THREE.Mesh(geo, new THREE.MeshStandardMaterial({ color: 0x1F2937, roughness: 0.70 }));
  mesh.castShadow = true;
  return mesh;
}

export function buildCables(): CableRefs {
  const g = new THREE.Group();

  // ── Cable 1: PLN Pole → Kelontong Meter ───────────────────────────────────
  const c1pts = [
    new THREE.Vector3(-11.5, 6.5, 3.2),
    new THREE.Vector3(-10.5, 5.8, 2.8),
    new THREE.Vector3(-9.0,  4.2, 2.6),
    new THREE.Vector3(-7.8,  2.2, 2.33),
  ];
  g.add(tubeCurve(c1pts, 0.055));

  // ── Cable 2: Kelontong Meter → Freezer ────────────────────────────────────
  const c2pts = [
    new THREE.Vector3(-10.3, 2.5, 2.33),
    new THREE.Vector3(-9.0,  1.8, 2.5),
    new THREE.Vector3(-7.8,  0.5, 2.3),
    new THREE.Vector3(-7.1,  0.5, 2.3),
  ];
  g.add(tubeCurve(c2pts, 0.045));

  // ── Cable 3: Laundry PV Roof → Washing machine ────────────────────────────
  const c3pts = [
    new THREE.Vector3(7.5, 4.6, -0.9),
    new THREE.Vector3(7.5, 3.5,  0.5),
    new THREE.Vector3(7.5, 2.5,  1.5),
    new THREE.Vector3(7.2, 1.2,  2.0),
  ];
  g.add(tubeCurve(c3pts, 0.045));

  // ── Particle flow ──────────────────────────────────────────────────────────
  const curves = [
    new THREE.CatmullRomCurve3(c1pts),
    new THREE.CatmullRomCurve3(c2pts),
    new THREE.CatmullRomCurve3(c3pts),
    // extra curve: pole to laundry side
    new THREE.CatmullRomCurve3([
      new THREE.Vector3(11.5, 6.5, 3.2),
      new THREE.Vector3(9.5, 4.0, 2.8),
      new THREE.Vector3(7.8, 2.4, 2.4),
    ]),
    // extra curve: Konveksi meter area
    new THREE.CatmullRomCurve3([
      new THREE.Vector3(-2.75, 2.5, 2.33),
      new THREE.Vector3(0, 2.0, 2.0),
      new THREE.Vector3(2.65, 1.1, 1.8),
    ]),
  ];

  const TOTAL = 60;
  const positions = new Float32Array(TOTAL * 3);
  const ts     = new Float32Array(TOTAL).map(() => Math.random());
  const speeds = new Float32Array(TOTAL).map(() => 0.12 + Math.random() * 0.14);
  const curveIdx = new Uint8Array(TOTAL).map((_, i) => i % curves.length);

  const geo = new THREE.BufferGeometry();
  geo.setAttribute('position', new THREE.BufferAttribute(positions, 3));

  const pMat = new THREE.PointsMaterial({
    color: 0xEF4444,
    size:  0.22,
    transparent: true,
    opacity: 0.95,
    blending: THREE.AdditiveBlending,
    depthWrite: false,
    sizeAttenuation: false,
  });

  const pts = new THREE.Points(geo, pMat);
  g.add(pts);

  return { group: g, particles: { pts, mat: pMat, curves, ts, speeds, curveIdx, TOTAL } };
}
