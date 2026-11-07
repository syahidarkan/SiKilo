import * as THREE from 'three';

export interface EnvRefs {
  group: THREE.Group;
  truckRef: THREE.Group;
}

function mat(hex: number, rough = 0.85, metal = 0.0): THREE.MeshStandardMaterial {
  return new THREE.MeshStandardMaterial({ color: hex, roughness: rough, metalness: metal });
}

function box(
  w: number, h: number, d: number,
  material: THREE.Material,
  x = 0, y = 0, z = 0,
  rx = 0, ry = 0, rz = 0,
): THREE.Mesh {
  const m = new THREE.Mesh(new THREE.BoxGeometry(w, h, d), material);
  m.position.set(x, y, z);
  m.rotation.set(rx, ry, rz);
  m.castShadow = true;
  m.receiveShadow = true;
  return m;
}

function cyl(
  rt: number, rb: number, h: number, seg: number,
  material: THREE.Material,
  x = 0, y = 0, z = 0,
): THREE.Mesh {
  const m = new THREE.Mesh(new THREE.CylinderGeometry(rt, rb, h, seg), material);
  m.position.set(x, y, z);
  m.castShadow = true;
  return m;
}

function spanCable(
  x1: number, y1: number, z1: number,
  x2: number, y2: number, z2: number,
  sag = 0.4,
): THREE.Mesh {
  const mid = new THREE.Vector3((x1 + x2) / 2, (y1 + y2) / 2 - sag, (z1 + z2) / 2);
  const curve = new THREE.CatmullRomCurve3([
    new THREE.Vector3(x1, y1, z1),
    mid,
    new THREE.Vector3(x2, y2, z2),
  ]);
  const geo = new THREE.TubeGeometry(curve, 20, 0.035, 5, false);
  const wireMat = new THREE.MeshStandardMaterial({ color: 0x1A1A1A, roughness: 0.9 });
  const m = new THREE.Mesh(geo, wireMat);
  m.castShadow = false;
  return m;
}

function buildPole(x: number, z: number, g: THREE.Group): void {
  const poleM = mat(0x506070, 0.7, 0.3);
  const capM  = mat(0x607080, 0.6, 0.4);

  // Main shaft
  g.add(cyl(0.10, 0.14, 7.2, 8, poleM, x, 3.6, z));
  // Cap
  g.add(cyl(0.14, 0.14, 0.14, 8, capM, x, 7.27, z));
  // Cross-arm
  const arm = box(2.6, 0.09, 0.09, capM, x, 6.65, z);
  g.add(arm);
  // 3 insulator studs at arm ends and center
  for (const ix of [x - 1.2, x, x + 1.2]) {
    g.add(cyl(0.045, 0.045, 0.14, 6, mat(0xC8C8C8, 0.5, 0.0), ix, 6.75, z));
  }
}

function buildTruck(g: THREE.Group): THREE.Group {
  const truck = new THREE.Group();

  // Cabin
  const cabinM = mat(0xE63946, 0.6, 0.1);
  const cabin  = box(2.4, 1.0, 1.4, cabinM, 0, 0.9, 0);
  truck.add(cabin);
  // Windshield
  const glassM = new THREE.MeshStandardMaterial({ color: 0x90CAF9, roughness: 0.1, metalness: 0.3, transparent: true, opacity: 0.6 });
  truck.add(box(1.3, 0.5, 0.06, glassM, 0.6, 1.1, 0.68));

  // Cargo bed
  truck.add(box(3.0, 0.14, 1.4, mat(0xCC3030, 0.7), -1.0, 0.44, 0));
  truck.add(box(3.0, 0.60, 0.08, mat(0x8B2020, 0.8), -1.0, 0.76, 0.69));
  truck.add(box(3.0, 0.60, 0.08, mat(0x8B2020, 0.8), -1.0, 0.76, -0.69));
  truck.add(box(0.08, 0.60, 1.40, mat(0x8B2020, 0.8), -2.5, 0.76, 0));

  // Chassis
  truck.add(box(5.6, 0.22, 1.2, mat(0x444444, 0.9), -0.2, 0.11, 0));

  // Wheels (4)
  const wheelM = mat(0x1A1A1A, 0.95, 0.0);
  const rimM   = mat(0xBBBBBB, 0.4, 0.8);
  for (const [wx, wz] of [[-1.5, 0.76], [-1.5, -0.76], [1.0, 0.76], [1.0, -0.76]]) {
    const w = new THREE.Mesh(new THREE.CylinderGeometry(0.32, 0.32, 0.22, 12), wheelM);
    w.rotation.x = Math.PI / 2;
    w.position.set(wx, 0.32, wz as number);
    truck.add(w);
    const r = new THREE.Mesh(new THREE.CylinderGeometry(0.18, 0.18, 0.24, 8), rimM);
    r.rotation.x = Math.PI / 2;
    r.position.set(wx, 0.32, wz as number);
    truck.add(r);
  }

  // Headlights
  const lightM = new THREE.MeshStandardMaterial({ color: 0xFFFFCC, emissive: new THREE.Color(0xFFFF88), emissiveIntensity: 1.0 });
  truck.add(new THREE.Mesh(new THREE.BoxGeometry(0.08, 0.14, 0.24), lightM));
  const hl = new THREE.Mesh(new THREE.BoxGeometry(0.08, 0.14, 0.24), lightM);
  hl.position.set(0, 0, 0);
  truck.add(hl);
  const hl1 = new THREE.Mesh(new THREE.BoxGeometry(0.08, 0.14, 0.24), lightM);
  hl1.position.set(1.2, 0.72, 0.5);
  truck.add(hl1);
  const hl2 = new THREE.Mesh(new THREE.BoxGeometry(0.08, 0.14, 0.24), lightM);
  hl2.position.set(1.2, 0.72, -0.5);
  truck.add(hl2);

  // Face truck along +X (direction of travel: position.x loops -18→+18)
  truck.rotation.y = 0;
  truck.position.set(0, 0.0, 6.8);

  g.add(truck);
  return truck;
}

export function buildEnv(scene: THREE.Scene): EnvRefs {
  const g = new THREE.Group();

  // ── Ground plane ──────────────────────────────────────────────
  const groundM = mat(0xC8C4B0, 0.95);
  g.add(box(50, 0.14, 24, groundM, 0, -0.07, 5.0));

  // ── Trotoar (sidewalk) Z 2.2→5.0, centre 3.6 ────────────────
  const trotoarM = new THREE.MeshStandardMaterial({ color: 0xD0CCBC, roughness: 0.9 });
  g.add(box(50, 0.24, 2.8, trotoarM, 0, 0.12, 3.6));

  // Paving pattern — thin lines
  const lineM = new THREE.MeshStandardMaterial({ color: 0xB8B4A4, roughness: 1.0 });
  for (let xi = -24; xi <= 24; xi += 2) {
    g.add(box(0.04, 0.26, 2.8, lineM, xi, 0.13, 3.6));
  }
  for (const zi of [2.5, 3.0, 3.5, 4.0, 4.5]) {
    g.add(box(50, 0.26, 0.04, lineM, 0, 0.13, zi));
  }

  // ── Road Z 5.0→14.0, centre 9.5 ──────────────────────────────
  const roadM = new THREE.MeshStandardMaterial({ color: 0x2B2F38, roughness: 0.95, polygonOffset: true, polygonOffsetFactor: -1 });
  g.add(box(50, 0.18, 9.0, roadM, 0, -0.06, 9.5));

  // Kerb strip
  const kerbM = mat(0x888880, 0.8);
  g.add(box(50, 0.28, 0.18, kerbM, 0, 0.14, 5.0));

  // Lane markings (dashed centre line)
  const dashM = new THREE.MeshStandardMaterial({ color: 0xF5F0DC, roughness: 0.9 });
  for (let xi = -23; xi <= 23; xi += 3.0) {
    g.add(box(1.6, 0.21, 0.12, dashM, xi, -0.095, 9.5));
  }

  // ── PLN Poles at X=±14, Z=4.0 ────────────────────────────────
  buildPole(-14, 3.8, g);
  buildPole(+14, 3.8, g);

  // ── 3 Horizontal span cables between poles ───────────────────
  g.add(spanCable(-13.7, 6.60, 3.78,  13.7, 6.60, 3.78, 0.35));
  g.add(spanCable(-13.7, 6.68, 3.80,  13.7, 6.68, 3.80, 0.32));
  g.add(spanCable(-13.7, 6.76, 3.82,  13.7, 6.76, 3.82, 0.30));

  // ── Parked motorcycle (stationary decoration) ─────────────────
  const motoGroup = new THREE.Group();
  const motoBodyM = mat(0x4A4A8A, 0.6, 0.2);
  motoGroup.add(box(1.3, 0.38, 0.38, motoBodyM, 0, 0.4, 0));
  for (const wx of [-0.5, 0.5]) {
    const wh = new THREE.Mesh(new THREE.CylinderGeometry(0.22, 0.22, 0.14, 10), mat(0x111111, 0.9));
    wh.rotation.x = Math.PI / 2;
    wh.position.set(wx, 0.22, 0);
    motoGroup.add(wh);
  }
  motoGroup.rotation.y = -Math.PI / 2;
  motoGroup.position.set(-16.5, 0.0, 4.5);
  g.add(motoGroup);

  // ── Moving pickup truck ───────────────────────────────────────
  const truckRef = buildTruck(g);

  scene.add(g);
  return { group: g, truckRef };
}
