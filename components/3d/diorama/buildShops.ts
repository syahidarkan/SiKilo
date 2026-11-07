/**
 * buildShops — 3 colourful UMKM shops with props
 *   Shop 1 (X=-7.5): Toko Kelontong 24 Jam
 *   Shop 2 (X=  0 ): Berkah Tailor & Konveksi
 *   Shop 3 (X=+7.5): Laundry Kiloan Express
 */
import * as THREE from 'three';

// ── Helpers ───────────────────────────────────────────────────────────────────
function mat(color: number, roughness = 0.82, metalness = 0, extra?: Partial<THREE.MeshStandardMaterialParameters>): THREE.MeshStandardMaterial {
  return new THREE.MeshStandardMaterial({ color, roughness, metalness, ...extra });
}
function box(w: number, h: number, d: number, m: THREE.Material, x = 0, y = 0, z = 0, rx = 0, ry = 0, rz = 0): THREE.Mesh {
  const mesh = new THREE.Mesh(new THREE.BoxGeometry(w, h, d), m);
  mesh.position.set(x, y, z); mesh.rotation.set(rx, ry, rz);
  mesh.castShadow = true; mesh.receiveShadow = true;
  return mesh;
}
function cyl(rt: number, rb: number, h: number, seg: number, m: THREE.Material, x = 0, y = 0, z = 0): THREE.Mesh {
  const mesh = new THREE.Mesh(new THREE.CylinderGeometry(rt, rb, h, seg), m);
  mesh.position.set(x, y, z); mesh.castShadow = true; mesh.receiveShadow = true;
  return mesh;
}
function sphere(r: number, m: THREE.Material, x = 0, y = 0, z = 0): THREE.Mesh {
  const mesh = new THREE.Mesh(new THREE.SphereGeometry(r, 10, 8), m);
  mesh.position.set(x, y, z); mesh.castShadow = true;
  return mesh;
}

// PV panel array — starts invisible (scale 0), animated at Beat 3
function buildPVArray(cx: number, cy: number, cz: number): THREE.Group {
  const pvG = new THREE.Group();
  const frameMat = mat(0xB0B7C3, 0.4, 0.85);
  const pvMat    = mat(0x0F172A, 0.3, 0.45);
  const cellMat  = new THREE.MeshStandardMaterial({
    color: 0x1E3A5F, roughness: 0.5,
    emissive: new THREE.Color(0x1E3A8A), emissiveIntensity: 0.5,
  });
  const offsets: [number, number][] = [
    [-2.1, -0.4], [0, -0.4], [2.1, -0.4],
    [-2.1,  0.4], [0,  0.4], [2.1,  0.4],
  ];
  offsets.forEach(([px, pz]) => {
    const panel = box(1.85, 0.06, 0.78, pvMat, px, 0, pz);
    pvG.add(panel);
    for (let r = 0; r < 3; r++) {
      pvG.add(box(1.85, 0.065, 0.013, cellMat, px, 0.033, pz - 0.24 + r * 0.24));
    }
  });
  for (const fz of [-0.68, 0.68]) {
    pvG.add(box(6.6, 0.07, 0.07, frameMat, 0, 0, fz));
  }
  pvG.position.set(cx, cy, cz);
  pvG.rotation.x = -THREE.MathUtils.degToRad(12);
  pvG.scale.setScalar(0);
  pvG.visible = false;
  return pvG;
}

// Shop shell (open facade)
function buildShell(g: THREE.Group, cx: number, wallColor: number, roofColor: number, accentColor: number, label: string) {
  void label;
  const wallM   = mat(wallColor, 0.85);
  const floorM  = mat(0xD1D5DB, 0.90);
  const roofM   = mat(roofColor, 0.68, 0.30);
  const accentM = mat(accentColor, 0.70);

  // Walls
  g.add(box(6.5, 4.0, 0.22, wallM, cx, 2.0, -2.11));      // back
  g.add(box(0.22, 4.0, 4.5, wallM, cx - 3.25, 2.0, 0.14)); // left
  g.add(box(0.22, 4.0, 4.5, wallM, cx + 3.25, 2.0, 0.14)); // right
  g.add(box(6.5, 0.14, 4.5, floorM, cx, 0.07, 0.14));      // floor
  g.add(box(6.5, 0.18, 4.5, mat(0xE0DBCF, 0.85), cx, 4.0, 0.14)); // ceiling
  // Front columns
  g.add(box(0.26, 4.0, 0.26, wallM, cx - 3.0, 2.0, 2.37));
  g.add(box(0.26, 4.0, 0.26, wallM, cx + 3.0, 2.0, 2.37));
  // Plinth
  g.add(box(6.5, 0.28, 0.14, accentM, cx, 0.14, 2.37));

  // Corrugated roof (tilted canopy)
  g.add(box(6.5, 0.12, 4.2, roofM, cx, 4.3, 0.14, -0.13));
  // Ridge cap
  g.add(box(6.5, 0.14, 0.14, mat(0xC0C8D0, 0.6, 0.4), cx, 4.68, -1.95));
  // Roof ridges
  const ridgeM = mat(roofColor - 0x111111, 0.72, 0.28);
  for (let i = -2.0; i <= 2.0; i += 0.52) {
    g.add(box(6.5, 0.07, 0.10, ridgeM, cx, 4.32, 0.14 + i * 0.42, -0.13));
  }

  // Signboard
  g.add(box(5.0, 0.60, 0.16, mat(accentColor, 0.60), cx, 3.70, 2.38));
  g.add(box(4.7, 0.34, 0.17, mat(0xFFFFF5, 0.60), cx, 3.70, 2.39));

  // Meter box (PLN)
  const mb = box(0.44, 0.68, 0.10, mat(0xE9EBF0, 0.70), cx - 2.75, 2.5, 2.33);
  g.add(mb);
  g.add(box(0.065, 0.11, 0.08, mat(0x374151, 0.60, 0.4), cx - 2.75, 2.14, 2.37));
  const dial = new THREE.Mesh(new THREE.CylinderGeometry(0.09, 0.09, 0.03, 10), mat(0x1F2937, 0.4));
  dial.rotation.x = Math.PI / 2; dial.position.set(cx - 2.75, 2.52, 2.37); g.add(dial);
  // CT-clamp (orange sensor ring)
  const ct = new THREE.Mesh(new THREE.TorusGeometry(0.065, 0.025, 6, 10), mat(0xFF9E2C, 0.5, 0.1));
  ct.rotation.y = Math.PI / 2; ct.position.set(cx - 2.5, 2.5, 2.35); g.add(ct);
}

// ── Shop 1: Kelontong ──────────────────────────────────────────────────────────
function buildKelontong(g: THREE.Group, pvGroup: THREE.Group) {
  const CX = -7.5;
  buildShell(g, CX, 0xFEF9EF, 0xB45309, 0x16A34A, 'TOKO KELONTONG 24 JAM');

  // Pertamini dispenser kiosk (blue-white, red stripe)
  const pumpG = new THREE.Group();
  pumpG.add(box(0.55, 1.6, 0.42, mat(0xF8FAFC, 0.70), 0, 0.8, 0));
  pumpG.add(box(0.56, 0.12, 0.43, mat(0xEF4444, 0.60), 0, 1.52, 0)); // red stripe
  pumpG.add(box(0.56, 0.12, 0.43, mat(0xEF4444, 0.60), 0, 0.28, 0));
  // Hose (CatmullRomCurve3 → TubeGeometry)
  const hosePts = [
    new THREE.Vector3(0.27, 0.80, 0),
    new THREE.Vector3(0.55, 0.60, 0.3),
    new THREE.Vector3(0.42, 0.20, 0.5),
  ];
  const hoseCurve = new THREE.CatmullRomCurve3(hosePts);
  const hoseTube = new THREE.TubeGeometry(hoseCurve, 10, 0.03, 6, false);
  const hose = new THREE.Mesh(hoseTube, mat(0x111827, 0.8));
  hose.castShadow = true;
  pumpG.add(hose);
  // Nozzle
  pumpG.add(box(0.08, 0.14, 0.08, mat(0x16A34A, 0.60, 0.3), 0.42, 0.20, 0.55));
  pumpG.position.set(CX - 2.6, 0, 2.3);
  g.add(pumpG);

  // Freezer (white box, blue lis, transparent glass lid)
  g.add(box(1.3, 0.90, 0.80, mat(0xF8FAFC, 0.70), CX + 0.4, 0.45, 2.1));
  g.add(box(1.32, 0.09, 0.82, mat(0x1D4ED8, 0.60), CX + 0.4, 0.90, 2.1)); // blue lis top
  const glassLid = box(1.28, 0.06, 0.78, mat(0xBAE6FD, 0.1, 0, { transparent: true, opacity: 0.55 }), CX + 0.4, 0.86, 2.1, -0.25);
  g.add(glassLid);
  // Ice cream sticker (yellow/red squares on front)
  g.add(box(0.25, 0.25, 0.02, mat(0xFBBF24, 0.5), CX + 0.15, 0.55, 2.52));
  g.add(box(0.25, 0.25, 0.02, mat(0xEF4444, 0.5), CX + 0.60, 0.55, 2.52));

  // LPG 3kg cylinders (bright green, stacked 2×2)
  const lpgM = mat(0x22C55E, 0.65, 0.1);
  const handleM = mat(0x374151, 0.60, 0.4);
  for (const [lx, lz] of [[CX - 0.9, 1.6], [CX - 0.3, 1.6], [CX - 0.9, 1.0], [CX - 0.3, 1.0]]) {
    const tank = cyl(0.18, 0.20, 0.52, 10, lpgM, lx, 0.26, lz);
    g.add(tank);
    const handle = new THREE.Mesh(new THREE.TorusGeometry(0.10, 0.025, 6, 10), handleM);
    handle.position.set(lx, 0.56, lz); handle.rotation.x = Math.PI / 2; g.add(handle);
  }

  // Water gallon rack (iron + 4 blue gallon cylinders)
  const rackM = mat(0x6B7280, 0.65, 0.5);
  g.add(box(1.1, 0.06, 0.55, rackM, CX + 1.9, 0.90, 1.5));
  g.add(box(1.1, 0.06, 0.55, rackM, CX + 1.9, 0.44, 1.5));
  g.add(box(0.06, 0.95, 0.55, rackM, CX + 1.4, 0.68, 1.5));
  g.add(box(0.06, 0.95, 0.55, rackM, CX + 2.4, 0.68, 1.5));
  const galonM = mat(0x38BDF8, 0.30, 0.1, { transparent: true, opacity: 0.75 });
  const capGM  = mat(0xE2E8F0, 0.60);
  for (const gx of [CX + 1.55, CX + 2.25]) {
    g.add(cyl(0.17, 0.17, 0.46, 12, galonM, gx, 0.70, 1.5));
    g.add(cyl(0.09, 0.09, 0.09, 8, capGM, gx, 0.96, 1.5));
  }

  // Snack shelf (2-tier wooden rack)
  const shelfWoodM = mat(0x92400E, 0.80);
  const shelf1 = new THREE.Group();
  shelf1.add(box(2.0, 0.07, 0.50, shelfWoodM, 0, 0.90, 0));
  shelf1.add(box(2.0, 0.07, 0.50, shelfWoodM, 0, 0.44, 0));
  shelf1.add(box(0.07, 0.95, 0.50, shelfWoodM, -0.97, 0.47, 0));
  shelf1.add(box(0.07, 0.95, 0.50, shelfWoodM,  0.97, 0.47, 0));
  const snackColors = [0xEF4444, 0xFBBF24, 0x16A34A, 0xF97316, 0x8B5CF6, 0x0EA5E9];
  snackColors.forEach((c, i) => {
    shelf1.add(box(0.28, 0.32, 0.26, mat(c, 0.65), -0.65 + i * 0.26, 0.60, -0.1));
    shelf1.add(box(0.28, 0.28, 0.26, mat(c, 0.65), -0.65 + i * 0.26, 0.17, -0.1));
  });
  shelf1.position.set(CX + 2.5, 0, 0.5);
  g.add(shelf1);

  // PV on kelontong roof (we don't add PV here per spec — only Konveksi + Laundry have PV)
  void pvGroup;
}

// ── Shop 2: Konveksi ───────────────────────────────────────────────────────────
function buildKonveksi(g: THREE.Group, pvGroup: THREE.Group) {
  const CX = 0;
  buildShell(g, CX, 0xFEFCF0, 0x78350F, 0xB45309, 'BERKAH TAILOR & SABLON');

  // 2 Sewing machine tables
  for (const mx of [CX - 2.0, CX + 0.5]) {
    // Table
    g.add(box(1.2, 0.07, 0.65, mat(0x92400E, 0.80), mx, 0.80, 0.8));
    g.add(box(0.07, 0.80, 0.07, mat(0x78350F, 0.80), mx - 0.55, 0.40, 0.55));
    g.add(box(0.07, 0.80, 0.07, mat(0x78350F, 0.80), mx + 0.55, 0.40, 0.55));
    g.add(box(0.07, 0.80, 0.07, mat(0x78350F, 0.80), mx - 0.55, 0.40, 1.05));
    g.add(box(0.07, 0.80, 0.07, mat(0x78350F, 0.80), mx + 0.55, 0.40, 1.05));
    // Sewing machine body (black metal)
    g.add(box(0.80, 0.26, 0.42, mat(0x1F2937, 0.55, 0.3), mx - 0.1, 0.96, 0.75));
    // Spool cylinder
    g.add(cyl(0.055, 0.055, 0.22, 7, mat(0xFBBF24, 0.60), mx - 0.1, 1.09, 0.70));
    // Flywheel
    const fw = new THREE.Mesh(new THREE.TorusGeometry(0.14, 0.04, 8, 14), mat(0x374151, 0.5, 0.4));
    fw.position.set(mx + 0.38, 0.95, 0.75); fw.rotation.y = Math.PI / 2; g.add(fw);
    // Presser arm
    g.add(box(0.06, 0.18, 0.06, mat(0x9CA3AF, 0.5, 0.5), mx + 0.08, 0.86, 0.60));
    // Pedal
    g.add(box(0.55, 0.06, 0.28, mat(0x374151, 0.80), mx, 0.10, 1.00));
  }

  // Fabric roll rack
  const rackM = mat(0x6B7280, 0.65, 0.5);
  g.add(box(0.07, 2.2, 0.07, rackM, CX - 3.0, 1.1, 1.0));
  g.add(box(0.07, 2.2, 0.07, rackM, CX - 3.0, 1.1, 2.0));
  g.add(box(2.5, 0.06, 0.06, rackM, CX - 1.75, 1.90, 1.0));
  g.add(box(2.5, 0.06, 0.06, rackM, CX - 1.75, 1.90, 2.0));
  g.add(box(2.5, 0.06, 0.06, rackM, CX - 1.75, 1.00, 1.5));
  const fabricColors = [0xDC2626, 0x1E3A8A, 0xFBBF24, 0x7C3AED, 0x065F46, 0xC2410C];
  for (let r = 0; r < 3; r++) {
    const railZ = r === 0 ? 1.0 : r === 1 ? 2.0 : 1.5;
    const railY = r === 2 ? 1.00 : 1.90;
    for (let fi = 0; fi < (r === 2 ? 4 : 5); fi++) {
      const roll = cyl(0.14, 0.14, 0.38, 10, mat(fabricColors[fi % fabricColors.length], 0.70), CX - 2.95 + fi * 0.5, railY, railZ);
      roll.rotation.z = Math.PI / 2; g.add(roll);
    }
  }

  // Mannequin torso
  g.add(cyl(0.09, 0.09, 0.95, 7, mat(0x374151, 0.60, 0.4), CX + 2.8, 0.47, 0.8));  // stand
  g.add(box(0.42, 0.65, 0.28, mat(0xF3E8FF, 0.70), CX + 2.8, 1.25, 0.8));           // torso
  g.add(cyl(0.17, 0.17, 0.08, 10, mat(0x1F2937, 0.60, 0.3), CX + 2.8, 0.97, 0.8)); // base

  // Ironing table + steam boiler
  g.add(box(1.5, 0.08, 0.50, mat(0xFEFCE8, 0.75), CX + 2.5, 0.84, 2.0));  // table
  g.add(box(0.07, 0.84, 0.07, mat(0x6B7280, 0.65, 0.5), CX + 1.78, 0.42, 1.78)); // leg
  g.add(box(0.07, 0.84, 0.07, mat(0x6B7280, 0.65, 0.5), CX + 3.22, 0.42, 1.78));
  // Steam boiler (stainless cylinder)
  g.add(cyl(0.22, 0.22, 0.65, 12, mat(0xC0C8D0, 0.3, 0.8), CX + 2.5, 1.19, 2.0));
  // Steam hose
  const steamPts = [
    new THREE.Vector3(CX + 2.5, 1.52, 2.0),
    new THREE.Vector3(CX + 2.8, 1.65, 2.2),
    new THREE.Vector3(CX + 2.8, 0.90, 2.4),
  ];
  const steamCurve = new THREE.CatmullRomCurve3(steamPts);
  const steamTube = new THREE.TubeGeometry(steamCurve, 12, 0.025, 6, false);
  g.add(new THREE.Mesh(steamTube, mat(0x9CA3AF, 0.5, 0.5)));

  // PV on roof
  const pv = buildPVArray(CX, 4.55, -0.9);
  pvGroup.add(pv);
}

// ── Shop 3: Laundry ────────────────────────────────────────────────────────────
export interface LaundryRefs {
  drumGroup: THREE.Group; // for drum rotation animation
}

function buildLaundry(g: THREE.Group, pvGroup: THREE.Group): LaundryRefs {
  const CX = 7.5;
  buildShell(g, CX, 0xF0FAFB, 0x0D9488, 0x0D9488, 'LAUNDRY KILOAN EXPRESS');

  const drumGroup = new THREE.Group();

  // 2 Front-load washing machines (white, stacked in pairs)
  const wmPositions: [number, number][] = [[CX - 2.5, 1.5], [CX - 1.3, 1.5]];
  wmPositions.forEach(([wx, wz]) => {
    // Machine body
    g.add(box(0.90, 0.95, 0.80, mat(0xF8FAFC, 0.70), wx, 0.47, wz));
    // Door rim (torus)
    const rim = new THREE.Mesh(new THREE.TorusGeometry(0.26, 0.055, 10, 24), mat(0xC0C8D0, 0.5, 0.5));
    rim.position.set(wx, 0.52, wz + 0.41); g.add(rim);
    // Glass door
    const glassDoor = new THREE.Mesh(new THREE.CircleGeometry(0.22, 24), mat(0x93C5FD, 0.1, 0, { transparent: true, opacity: 0.55 }));
    glassDoor.position.set(wx, 0.52, wz + 0.42); g.add(glassDoor);
    // Clothing inside drum (rotating)
    const clothColors = [0xEF4444, 0x1D4ED8, 0xFBBF24, 0x16A34A];
    clothColors.forEach((c, ci) => {
      const cloth = box(0.08, 0.14, 0.03, mat(c, 0.75), wx + Math.cos(ci * Math.PI / 2) * 0.12, 0.52 + Math.sin(ci * Math.PI / 2) * 0.12, wz + 0.42);
      cloth.userData.drumCenter = new THREE.Vector3(wx, 0.52, wz + 0.42);
      cloth.userData.drumAngle = ci * Math.PI / 2;
      drumGroup.add(cloth);
    });
    // Control panel
    g.add(box(0.90, 0.14, 0.78, mat(0xE2E8F0, 0.60), wx, 0.95, wz));
  });
  g.add(drumGroup);

  // Dryer drum (large grey box + ventilation grill)
  const dryX = CX + 1.0;
  g.add(box(1.1, 1.0, 0.95, mat(0x374151, 0.68, 0.2), dryX, 0.50, 1.5));
  g.add(box(1.12, 0.14, 0.97, mat(0x1F2937, 0.60, 0.3), dryX, 1.0, 1.5)); // top panel
  // Ventilation grill lines
  for (let vi = -0.3; vi <= 0.3; vi += 0.15) {
    g.add(box(0.07, 0.65, 0.09, mat(0x1F2937, 0.60, 0.4), dryX + 0.56, 0.52, 1.5 + vi));
  }
  // Exhaust duct
  g.add(cyl(0.09, 0.09, 0.80, 7, mat(0x9CA3AF, 0.5, 0.5), dryX + 0.65, 0.84, 1.5));

  // Laundry baskets (3 colourful rectangular baskets)
  for (const [bx, bc] of [[CX + 2.3, 0xFB923C], [CX + 2.9, 0x2DD4BF], [CX + 2.3, 0xFCA5A5]] as [number,number][]) {
    const bz = bc === 0xFCA5A5 ? 2.2 : 1.6;
    g.add(box(0.52, 0.42, 0.42, mat(bc, 0.70), bx, 0.21, bz));
    // Basket ventilation holes (simulated with darker boxes)
    for (let bhi = 0; bhi < 3; bhi++) {
      g.add(box(0.08, 0.10, 0.03, mat(bc - 0x222222, 0.80), bx - 0.14 + bhi * 0.14, 0.22, bz + 0.22));
    }
  }

  // Clothes rail with 6 coloured garments
  g.add(box(2.5, 0.06, 0.06, mat(0x9CA3AF, 0.5, 0.5), CX + 1.5, 2.6, 0.7));  // rail rod
  g.add(cyl(0.04, 0.04, 2.6, 6, mat(0x6B7280, 0.6, 0.4), CX + 0.25, 1.3, 0.7)); // left support
  g.add(cyl(0.04, 0.04, 2.6, 6, mat(0x6B7280, 0.6, 0.4), CX + 2.75, 1.3, 0.7));
  const garmentColors = [0xEF4444, 0x1D4ED8, 0xFBBF24, 0x16A34A, 0x7C3AED, 0xF97316];
  garmentColors.forEach((c, i) => {
    const hang = box(0.30, 0.55, 0.04, mat(c, 0.72), CX + 0.4 + i * 0.42, 2.26, 0.70);
    g.add(hang);
    // Hanger wire
    g.add(box(0.04, 0.14, 0.04, mat(0x9CA3AF, 0.5, 0.5), CX + 0.4 + i * 0.42, 2.57, 0.70));
  });

  // PV on roof
  const pv = buildPVArray(CX, 4.55, -0.9);
  pvGroup.add(pv);

  return { drumGroup };
}

// ── Public API ─────────────────────────────────────────────────────────────────
export interface ShopsRefs {
  group: THREE.Group;
  pvGroupConveksi: THREE.Group;
  pvGroupLaundry: THREE.Group;
  drumGroup: THREE.Group;
  meterWorldPos: THREE.Vector3;
  freezerWorldPos: THREE.Vector3;
  laundryRoofPos: THREE.Vector3;
}

export function buildShops(): ShopsRefs {
  const g = new THREE.Group();
  const pvGroupConveksi = new THREE.Group();
  const pvGroupLaundry  = new THREE.Group();

  buildKelontong(g, new THREE.Group());
  buildKonveksi(g, pvGroupConveksi);
  const { drumGroup } = buildLaundry(g, pvGroupLaundry);

  g.add(pvGroupConveksi);
  g.add(pvGroupLaundry);

  return {
    group:          g,
    pvGroupConveksi,
    pvGroupLaundry,
    drumGroup,
    meterWorldPos:  new THREE.Vector3(-10.3, 2.5, 2.33),
    freezerWorldPos: new THREE.Vector3(-7.1, 0.86, 2.52),
    laundryRoofPos: new THREE.Vector3(7.5, 4.55, -0.9),
  };
}
