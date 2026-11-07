/**
 * buildStreet - Road, sidewalk, utility pole, vehicles, trees
 * for the WASKITA 3-shop street diorama.
 */
import * as THREE from 'three';

function clay(
  color: number,
  roughness = 0.80,
  metalness = 0,
  extra?: Partial<THREE.MeshStandardMaterialParameters>,
): THREE.MeshStandardMaterial {
  return new THREE.MeshStandardMaterial({ color, roughness, metalness, ...extra });
}

function box(
  w: number, h: number, d: number,
  mat: THREE.Material,
  x = 0, y = 0, z = 0,
  rx = 0, ry = 0, rz = 0,
): THREE.Mesh {
  const m = new THREE.Mesh(new THREE.BoxGeometry(w, h, d), mat);
  m.position.set(x, y, z);
  m.rotation.set(rx, ry, rz);
  m.castShadow = true; m.receiveShadow = true;
  return m;
}

function cyl(
  rt: number, rb: number, h: number, seg: number,
  mat: THREE.Material,
  x = 0, y = 0, z = 0,
): THREE.Mesh {
  const m = new THREE.Mesh(new THREE.CylinderGeometry(rt, rb, h, seg), mat);
  m.position.set(x, y, z);
  m.castShadow = true; m.receiveShadow = true;
  return m;
}

export interface StreetRefs {
  group: THREE.Group;
  pvGroupConveksi: THREE.Group;  // scale.y starts 0
  pvGroupLaundry: THREE.Group;   // scale.y starts 0
}

export function buildStreet(): StreetRefs {
  const g = new THREE.Group();

  // ── Road ─────────────────────────────────────────────────────────────────
  const roadMat = clay(0x374151, 0.95);
  g.add(box(36, 0.12, 14, roadMat, 0, -0.06, 5.5));

  // Dashed white lane markings
  const dashMat = clay(0xFFFFFF, 0.95);
  for (let i = -16; i <= 16; i += 3) {
    g.add(box(1.6, 0.02, 0.18, dashMat, i, 0.0, 5.5));
  }

  // ── Sidewalk (trotoar) ────────────────────────────────────────────────────
  const paveTop  = clay(0xD1D5DB, 0.90);
  const paveSide = clay(0xB0B7C3, 0.90);
  // Main slab
  g.add(box(36, 0.20, 5, paveTop, 0, 0.10, -1.0));
  // Kerb face
  g.add(box(36, 0.20, 0.10, paveSide, 0, 0.0, 1.5));
  // Paving block lines (longitudinal)
  const lineM = clay(0xC0C8D0, 0.95);
  for (let i = -16; i <= 16; i += 2) {
    g.add(box(0.05, 0.22, 5, lineM, i, 0.10, -1.0));
  }

  // Ground shadow catcher
  const catcherM = new THREE.MeshStandardMaterial({ color: 0xF4EFE6, roughness: 1.0 });
  const catcher = new THREE.Mesh(new THREE.PlaneGeometry(60, 40), catcherM);
  catcher.rotation.x = -Math.PI / 2;
  catcher.position.set(0, -0.14, 2);
  catcher.receiveShadow = true;
  g.add(catcher);

  // ── Utility Pole (tiang listrik PLN) ─────────────────────────────────────
  const poleMat = clay(0xC9C5BD, 0.80, 0.05);
  const wireMat = clay(0x1F2937, 0.60);

  function addPole(px: number) {
    const poleG = new THREE.Group();
    // Shaft
    poleG.add(cyl(0.09, 0.12, 8.5, 8, poleMat, 0, 4.25, 0));
    // Cross-arm
    poleG.add(box(2.8, 0.09, 0.09, poleMat, 0, 7.8, 0));
    // Insulators (white ceramic spheres)
    for (const ix of [-1.3, 0, 1.3]) {
      const ins = new THREE.Mesh(new THREE.SphereGeometry(0.08, 8, 6), clay(0xFAFAF9, 0.50));
      ins.position.set(ix, 7.65, 0);
      ins.castShadow = true;
      poleG.add(ins);
    }
    // PLN cap
    poleG.add(cyl(0.14, 0.14, 0.12, 8, clay(0x94A3B8, 0.5), 0, 8.60, 0));
    poleG.position.set(px, 0, -3.2);
    g.add(poleG);

    // Wires from pole to shops (3 drooping curves)
    const wireTargetXs = [-8, 0, 8];
    wireTargetXs.forEach((tx) => {
      const pts = [];
      for (let t = 0; t <= 1; t += 0.1) {
        const wx = px + (tx - px) * t;
        const wy = 7.6 - Math.sin(t * Math.PI) * 0.5;
        pts.push(new THREE.Vector3(wx, wy, -1.8 + t * 1.5));
      }
      const wireGeo = new THREE.BufferGeometry().setFromPoints(pts);
      const wire = new THREE.Line(wireGeo, new THREE.LineBasicMaterial({ color: 0x1F2937 }));
      g.add(wire);
    });
  }

  addPole(-14);
  addPole(14);

  // ── Trees (2 pohon peneduh) ───────────────────────────────────────────────
  function addTree(px: number) {
    const treeG = new THREE.Group();
    // Trunk
    treeG.add(cyl(0.14, 0.18, 2.4, 7, clay(0x92400E, 0.85), 0, 1.2, 0));
    // Canopy layers
    const leafMat = clay(0x4ADE80, 0.80);
    treeG.add(new THREE.Mesh(new THREE.SphereGeometry(1.1, 9, 7), leafMat));
    const top = new THREE.Mesh(new THREE.SphereGeometry(0.75, 9, 6), clay(0x22C55E, 0.75));
    top.position.y = 0.9;
    treeG.add(top);
    treeG.children.slice(1).forEach((c) => { (c as THREE.Mesh).castShadow = true; });
    treeG.position.set(px, 2.4, -2.8);
    g.add(treeG);
  }

  addTree(-5);
  addTree(5);

  // ── Pickup Truck (mobil pikap) ────────────────────────────────────────────
  const truckG = new THREE.Group();
  const cabMat  = clay(0xF5EBE1, 0.75);
  const bedMat  = clay(0xE5E0D8, 0.80);
  const tireMat = clay(0x1F2937, 0.95);
  const rimMat  = clay(0xC0C8D0, 0.60, 0.5);

  // Cabin
  truckG.add(box(2.2, 1.0, 1.5, cabMat, 0, 1.3, 0));
  // Windshield (blue glass)
  truckG.add(box(2.21, 0.55, 0.06, clay(0xBFDBFE, 0.1, 0, { transparent: true, opacity: 0.55 }),
    0, 1.5, -0.72));
  // Truck bed
  truckG.add(box(2.2, 0.60, 2.4, bedMat, 0, 0.9, 1.5));
  // Bed walls
  truckG.add(box(2.2, 0.35, 0.09, bedMat, 0, 1.12, 2.7));
  truckG.add(box(0.09, 0.35, 2.4, bedMat, -1.1, 1.12, 1.5));
  truckG.add(box(0.09, 0.35, 2.4, bedMat,  1.1, 1.12, 1.5));
  // Undercarriage
  truckG.add(box(2.2, 0.35, 4.2, clay(0x374151, 0.9), 0, 0.52, 0.65));
  // Wheels
  for (const [wx, wz] of [[-0.95, -0.55], [0.95, -0.55], [-0.95, 1.9], [0.95, 1.9]]) {
    const wheel = cyl(0.38, 0.38, 0.28, 10, tireMat, wx, 0.38, wz);
    wheel.rotation.z = Math.PI / 2;
    truckG.add(wheel);
    const rim = cyl(0.19, 0.19, 0.30, 8, rimMat, wx, 0.38, wz);
    rim.rotation.z = Math.PI / 2;
    truckG.add(rim);
  }
  // Cargo: rice sack cylinders in bed
  const sackMat = clay(0xFEF3C7, 0.90);
  for (const [sx, sz] of [[-0.5, 1.2], [0.5, 1.2], [0, 1.9], [-0.5, 2.5], [0.5, 2.5]]) {
    const sack = cyl(0.28, 0.32, 0.55, 8, sackMat, sx, 1.5, sz);
    sack.rotation.x = Math.PI / 2;
    truckG.add(sack);
  }
  // Truck position: parked on road left
  truckG.position.set(-10, 0, 7.5);
  truckG.rotation.y = Math.PI * 0.08;
  g.add(truckG);

  // ── Motorcycle (motor bebek) ──────────────────────────────────────────────
  const motoG = new THREE.Group();
  const motoBodyMat = clay(0x1D4ED8, 0.70);
  // Body
  motoG.add(box(0.28, 0.5, 1.2, motoBodyMat, 0, 0.72, 0));
  // Fuel tank
  motoG.add(box(0.26, 0.28, 0.5, clay(0x2563EB, 0.65), 0, 0.98, -0.25));
  // Seat
  motoG.add(box(0.22, 0.09, 0.55, clay(0x1F2937, 0.80), 0, 0.97, 0.22));
  // Handlebars
  motoG.add(box(0.55, 0.06, 0.06, clay(0x9CA3AF, 0.5, 0.6), 0, 1.14, -0.56));
  // Wheels
  for (const wz of [-0.5, 0.5]) {
    const tw = cyl(0.28, 0.28, 0.14, 10, tireMat, 0, 0.28, wz);
    tw.rotation.z = Math.PI / 2;
    motoG.add(tw);
  }
  motoG.position.set(-6.2, 0, 1.8);
  motoG.rotation.y = -0.2;
  g.add(motoG);

  // ── PV groups (empty containers, filled by buildShops) ──────────────────
  const pvGroupConveksi = new THREE.Group();
  const pvGroupLaundry  = new THREE.Group();
  g.add(pvGroupConveksi);
  g.add(pvGroupLaundry);

  return { group: g, pvGroupConveksi, pvGroupLaundry };
}
