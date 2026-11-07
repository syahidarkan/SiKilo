/**
 * buildRuko — Procedural diorama geometry for the NOTA LISTRIK hero scene.
 * Ruko (shophouse) cutaway: open on +X and +Z faces so the camera at
 * (18,16,18) can see into both floors and the rooftop.
 * No external model files — pure Three.js primitives.
 */

import * as THREE from 'three';

// ─── Material helpers ─────────────────────────────────────────────────────────

function clay(
  color: number,
  roughness = 0.78,
  metalness = 0,
  extra?: Partial<THREE.MeshStandardMaterialParameters>,
): THREE.MeshStandardMaterial {
  return new THREE.MeshStandardMaterial({ color, roughness, metalness, ...extra });
}

function mesh(
  geo: THREE.BufferGeometry,
  mat: THREE.Material,
  x = 0, y = 0, z = 0,
  rx = 0, ry = 0, rz = 0,
  shadow = true,
): THREE.Mesh {
  const m = new THREE.Mesh(geo, mat);
  m.position.set(x, y, z);
  m.rotation.set(rx, ry, rz);
  m.castShadow = shadow;
  m.receiveShadow = shadow;
  return m;
}

// ─── Main builder ─────────────────────────────────────────────────────────────

export interface DioramaRefs {
  buildingGroup: THREE.Group;
  pvGroup: THREE.Group;
  meterWorldPos: THREE.Vector3;
}

export function buildRuko(): DioramaRefs {
  const g = new THREE.Group();

  // ── Shared materials ───────────────────────────────────────────────────────
  const wallMat      = clay(0xE5E0D8, 0.85);
  const floorGray    = clay(0xD1D5DB, 0.90);
  const floorWood    = clay(0xEFE8DD, 0.85);
  const woodMat      = clay(0xA0845C, 0.80);
  const machineMat   = clay(0x6B7280, 0.60, 0.30);
  const metalMat     = clay(0x9CA3AF, 0.45, 0.75);
  const compMat      = clay(0xFF9E2C, 0.50, 0.10);
  const darkMat      = clay(0x374151, 0.60, 0.40);
  const boilerMat    = clay(0x9CA3AF, 0.40, 0.75);
  const towerBlueMat = clay(0x3B82F6, 0.60);

  // ── Outer shell ────────────────────────────────────────────────────────────
  // Back wall  (z = −4)
  g.add(mesh(new THREE.BoxGeometry(8.3, 6.5, 0.25), wallMat, 0, 3.25, -4));
  // Left wall  (x = −4) — visible from camera
  g.add(mesh(new THREE.BoxGeometry(0.25, 6.5, 8.3), wallMat, -4, 3.25, 0));
  // Right partial low wall (x = +4) — only bottom trim visible at beat 1
  g.add(mesh(new THREE.BoxGeometry(0.15, 1.0, 8.3), wallMat, 4, 0.5, 0));

  // ── Windows on back wall ───────────────────────────────────────────────────
  const winFrameMat = clay(0xFFF8F0, 0.6);
  const winGlassMat = clay(0xBFDBFE, 0.1, 0.0, { transparent: true, opacity: 0.55 });
  const winPositions = [
    [-2.4, 2.0], [1.0, 2.0],   // Floor 1
    [-2.4, 5.0], [1.0, 5.0],   // Floor 2
  ];
  winPositions.forEach(([wx, wy]) => {
    g.add(mesh(new THREE.BoxGeometry(1.1, 0.95, 0.15), winFrameMat, wx, wy, -4));
    g.add(mesh(new THREE.BoxGeometry(0.88, 0.75, 0.05), winGlassMat, wx, wy, -3.95));
  });

  // ── Floor slabs ────────────────────────────────────────────────────────────
  g.add(mesh(new THREE.BoxGeometry(8, 0.20, 8), floorGray,  0, 0.00,  0));  // ground
  g.add(mesh(new THREE.BoxGeometry(8, 0.20, 8), floorGray,  0, 3.25,  0));  // F1→F2 slab
  g.add(mesh(new THREE.BoxGeometry(8, 0.20, 8), wallMat,    0, 6.50,  0));  // roof deck
  // Warm wood surface on floor 2
  g.add(mesh(new THREE.BoxGeometry(7.9, 0.06, 7.9), floorWood, 0, 3.37, 0));

  // ── Floor divider beam (visible side) ─────────────────────────────────────
  g.add(mesh(new THREE.BoxGeometry(0.25, 0.25, 8), darkMat, 4.1, 3.15, 0));
  g.add(mesh(new THREE.BoxGeometry(8.3, 0.25, 0.25), darkMat, 0, 3.15, 4.1));

  // ── kWh Meter (left wall interior, floor 1) ────────────────────────────────
  // Mounted on x=−3.85 face, facing interior (+x direction)
  const meterWorldPos = new THREE.Vector3(-3.80, 2.10, -1.0);

  const meterBody = mesh(new THREE.BoxGeometry(0.60, 0.88, 0.14), clay(0xE9EBF0, 0.70), -3.85, 2.10, -1.0);
  meterBody.rotation.y = Math.PI / 2;
  g.add(meterBody);

  // Meter dial
  const dialGeo = new THREE.CylinderGeometry(0.17, 0.17, 0.025, 14);
  const dialMesh = mesh(dialGeo, clay(0x1F2937, 0.4), -3.72, 2.18, -1.0);
  dialMesh.rotation.z = Math.PI / 2;
  g.add(dialMesh);

  // MCB row
  for (let i = 0; i < 3; i++) {
    const mcb = mesh(new THREE.BoxGeometry(0.07, 0.15, 0.05), darkMat.clone(),
      -3.72, 1.76, -1.14 + i * 0.14);
    mcb.rotation.y = Math.PI / 2;
    g.add(mcb);
  }

  // ── Floor 1: Sewing machines (3 tables) ────────────────────────────────────
  ([
    [-1.5, 0.0, -0.8],
    [-1.5, 0.0,  0.9],
    [-1.5, 0.0,  2.6],
  ] as [number, number, number][]).forEach(([tx, ty, tz]) => {
    // Table body
    g.add(mesh(new THREE.BoxGeometry(0.72, 0.65, 0.52), woodMat.clone(), tx, ty + 0.33, tz));
    // Machine top (rounded cylinder + arm)
    g.add(mesh(new THREE.CylinderGeometry(0.09, 0.09, 0.28, 10), machineMat.clone(), tx, ty + 0.73, tz));
    g.add(mesh(new THREE.BoxGeometry(0.42, 0.07, 0.07), machineMat.clone(), tx + 0.08, ty + 0.88, tz));
    // Thread spool (tiny torus)
    g.add(mesh(
      new THREE.TorusGeometry(0.04, 0.02, 6, 10),
      clay(0xFCA5A5, 0.7),
      tx + 0.1, ty + 0.90, tz + 0.05,
      Math.PI / 2,
    ));
  });

  // ── Floor 1: Compressor ────────────────────────────────────────────────────
  g.add(mesh(new THREE.CylinderGeometry(0.44, 0.44, 1.18, 14), compMat, 1.9, 0.72, -0.9));

  // Compressor legs
  for (const [lx, lz] of [[-0.28, -0.28], [0.28, -0.28], [-0.28, 0.28], [0.28, 0.28]]) {
    g.add(mesh(new THREE.CylinderGeometry(0.038, 0.038, 0.28, 6), darkMat.clone(), 1.9 + lx, 0.06, -0.9 + lz));
  }

  // Pressure gauge
  g.add(mesh(new THREE.SphereGeometry(0.08, 8, 8), clay(0xF9FAFB, 0.5), 1.9 + 0.44, 1.05, -0.9));

  // Exhaust pipe from compressor to ceiling (a subtle detail)
  const pipeMat = clay(0x4B5563, 0.6, 0.5);
  g.add(mesh(new THREE.CylinderGeometry(0.025, 0.025, 1.6, 7), pipeMat, 2.2, 1.6, -1.2));

  // ── Floor 2: Ironing table ────────────────────────────────────────────────
  g.add(mesh(new THREE.BoxGeometry(2.9, 0.09, 0.68), woodMat.clone(), -0.3, 3.75, -1.4));
  // Legs
  for (const [lx, lz] of [[-1.3, -0.28], [1.0, -0.28], [-1.3, 0.28], [1.0, 0.28]]) {
    g.add(mesh(new THREE.BoxGeometry(0.07, 0.42, 0.07), clay(0x92400E, 0.7), -0.3 + lx, 3.52, -1.4 + lz));
  }

  // Iron (small metallic wedge shape)
  const ironGeo = new THREE.BoxGeometry(0.4, 0.09, 0.22);
  const ironMesh = mesh(ironGeo, metalMat.clone(), -0.3, 3.80, -1.4);
  g.add(ironMesh);

  // ── Floor 2: Steam boiler ─────────────────────────────────────────────────
  g.add(mesh(new THREE.CylinderGeometry(0.29, 0.33, 1.65, 12), boilerMat, 1.9, 4.30, -1.9));
  // Boiler top pipe
  g.add(mesh(new THREE.CylinderGeometry(0.07, 0.07, 0.42, 8), boilerMat.clone(), 1.9, 5.21, -1.9));
  // Steam output elbow (torus quarter)
  g.add(mesh(
    new THREE.TorusGeometry(0.09, 0.03, 8, 8, Math.PI / 2),
    metalMat.clone(), 1.9, 5.44, -1.75, 0, 0, 0,
  ));
  // Gauge
  g.add(mesh(new THREE.SphereGeometry(0.07, 8, 8), clay(0xFEF9C3, 0.4), 1.9 + 0.30, 4.6, -1.9));

  // ── Floor 2: Clothes rail ─────────────────────────────────────────────────
  const rodMesh = mesh(new THREE.CylinderGeometry(0.025, 0.025, 2.9, 8), metalMat.clone(), -0.2, 5.90, 2.6);
  rodMesh.rotation.z = Math.PI / 2;
  g.add(rodMesh);

  // Hangers + garments
  const garmentColors = [0x93C5FD, 0xFCA5A5, 0xBBF7D0, 0xFDE68A, 0xC4B5FD];
  for (let i = 0; i < 5; i++) {
    const hx = -1.1 + i * 0.55;
    // Hanger hook (small cylinder)
    g.add(mesh(new THREE.CylinderGeometry(0.012, 0.012, 0.18, 6), darkMat.clone(), hx, 5.80, 2.6));
    // Garment body
    g.add(mesh(new THREE.BoxGeometry(0.06, 0.38, 0.28), clay(garmentColors[i], 0.9), hx, 5.60, 2.6));
  }

  // ── Rooftop parapet (4 sides) ─────────────────────────────────────────────
  g.add(mesh(new THREE.BoxGeometry(8.5, 0.42, 0.22), wallMat.clone(), 0,  6.91, -4.0));  // back
  g.add(mesh(new THREE.BoxGeometry(0.22, 0.42, 8.5), wallMat.clone(), -4, 6.91,  0.0));  // left
  g.add(mesh(new THREE.BoxGeometry(8.5, 0.42, 0.22), wallMat.clone(), 0,  6.91,  4.0));  // front
  g.add(mesh(new THREE.BoxGeometry(0.22, 0.42, 8.5), wallMat.clone(), 4,  6.91,  0.0));  // right

  // ── Water tower ───────────────────────────────────────────────────────────
  g.add(mesh(new THREE.CylinderGeometry(0.09, 0.09, 0.78, 8), metalMat.clone(), -2.6, 7.20, -2.6));  // support
  g.add(mesh(new THREE.CylinderGeometry(0.55, 0.55, 1.12, 14), towerBlueMat, -2.6, 7.95, -2.6));     // tank
  g.add(mesh(new THREE.CylinderGeometry(0.57, 0.3, 0.32, 14), clay(0x1D4ED8, 0.6), -2.6, 8.65, -2.6)); // cap

  // ── PLTS: tilted PV array (starts Y-scale = 0, pops at beat 3) ───────────
  const pvGroup = new THREE.Group();

  const pvFrame = new THREE.Group();
  pvFrame.position.set(1.0, 6.75, 0.0);
  pvFrame.rotation.x = -THREE.MathUtils.degToRad(15);

  const frameMat = new THREE.MeshStandardMaterial({ color: 0xB0B7C3, roughness: 0.4, metalness: 0.85 });

  // 2 horizontal rails
  for (const rz of [-0.56, 0.56]) {
    pvFrame.add(mesh(new THREE.BoxGeometry(3.5, 0.07, 0.07), frameMat.clone(), 0, 0, rz));
  }
  // 3 vertical rails
  for (const rx of [-1.68, 0, 1.68]) {
    pvFrame.add(mesh(new THREE.BoxGeometry(0.07, 0.07, 1.22), frameMat.clone(), rx, 0, 0));
  }

  // 4 panels (2 × 2 grid)
  const pvMat = new THREE.MeshStandardMaterial({ color: 0x0F172A, roughness: 0.3, metalness: 0.45 });
  const cellMat = new THREE.MeshStandardMaterial({
    color: 0x1E3A5F,
    roughness: 0.5,
    emissive: new THREE.Color(0x1E3A8A),
    emissiveIntensity: 0.35,
  });

  const panelOffsets: [number, number][] = [[-0.84, -0.30], [0.84, -0.30], [-0.84, 0.30], [0.84, 0.30]];
  panelOffsets.forEach(([px, pz]) => {
    // Panel body
    pvFrame.add(mesh(new THREE.BoxGeometry(1.58, 0.05, 0.56), pvMat.clone(), px, 0, pz));
    // Horizontal cell lines (3)
    for (let r = 0; r < 3; r++) {
      pvFrame.add(mesh(new THREE.BoxGeometry(1.58, 0.055, 0.012), cellMat.clone(), px, 0.03, pz - 0.185 + r * 0.185));
    }
    // Vertical cell lines (5)
    for (let c = 0; c < 5; c++) {
      pvFrame.add(mesh(new THREE.BoxGeometry(0.012, 0.055, 0.56), cellMat.clone(), px - 0.63 + c * 0.315, 0.03, pz));
    }
  });

  pvGroup.add(pvFrame);
  pvGroup.scale.set(1, 0, 1);  // invisible on Y until beat 3
  g.add(pvGroup);

  // ── Ground shadow catcher ─────────────────────────────────────────────────
  const catcherMat = new THREE.MeshStandardMaterial({ color: 0xF4EFE6, roughness: 1.0 });
  const catcher = new THREE.Mesh(new THREE.CircleGeometry(14, 36), catcherMat);
  catcher.rotation.x = -Math.PI / 2;
  catcher.position.y = -0.11;
  catcher.receiveShadow = true;
  g.add(catcher);

  return { buildingGroup: g, pvGroup, meterWorldPos };
}
