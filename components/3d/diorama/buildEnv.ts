/**
 * buildEnv — Road, trotoar, utility poles, tropical trees, vehicles
 * Full-color environment for NOTA LISTRIK 3-shop diorama.
 */
import * as THREE from 'three';

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

export interface EnvRefs {
  group: THREE.Group;
  truckRef: THREE.Group; // for vibration animation
}

export function buildEnv(): EnvRefs {
  const g = new THREE.Group();

  // ── Ground shadow catcher ───────────────────────────────────────────────
  const gcatcher = new THREE.Mesh(new THREE.PlaneGeometry(80, 50), mat(0xF4EFE6, 1.0));
  gcatcher.rotation.x = -Math.PI / 2;
  gcatcher.position.set(0, -0.15, 2);
  gcatcher.receiveShadow = true;
  g.add(gcatcher);

  // ── Road ────────────────────────────────────────────────────────────────
  g.add(box(44, 0.20, 16, mat(0x2D3748, 0.95), 0, -0.10, 5.5));

  // Lane markings (dashed center line)
  const dashM = mat(0xFFFFFF, 0.95);
  for (let i = -20; i <= 20; i += 3.2) {
    g.add(box(1.8, 0.02, 0.22, dashM, i, 0.01, 5.5));
  }

  // ── Sidewalk (trotoar) ───────────────────────────────────────────────────
  g.add(box(44, 0.25, 6.5, mat(0xE5E7EB, 0.90), 0, 0.125, 0.75));
  // Kerb face
  g.add(box(44, 0.25, 0.14, mat(0xD1D5DB, 0.85), 0, 0.0, 3.57));
  // Paving seam lines
  const seamM = mat(0xCED2DA, 0.92);
  for (let i = -20; i <= 20; i += 2) {
    g.add(box(0.06, 0.26, 6.5, seamM, i, 0.125, 0.75));
  }

  // ── Utility Poles (PLN) — AT TROTOAR LEVEL ───────────────────────────────
  const poleM = mat(0xC9C5BD, 0.80, 0.05);
  const capM  = mat(0x94A3B8, 0.50, 0.3);
  const insM  = mat(0xFAFAF9, 0.50);
  const wireLineMat = new THREE.LineBasicMaterial({ color: 0x1F2937, linewidth: 2 });

  function addPole(px: number) {
    const pg = new THREE.Group();
    // Concrete shaft
    pg.add(cyl(0.10, 0.14, 7.0, 10, poleM, 0, 3.5, 0));
    // Cross arm
    pg.add(box(3.0, 0.10, 0.10, poleM, 0, 6.65, 0));
    // Ceramic insulators
    for (const ix of [-1.35, 0, 1.35]) {
      const ins = new THREE.Mesh(new THREE.SphereGeometry(0.09, 8, 6), insM);
      ins.position.set(ix, 6.52, 0); ins.castShadow = true;
      pg.add(ins);
    }
    // PLN cap
    pg.add(cyl(0.15, 0.15, 0.14, 10, capM, 0, 7.10, 0));
    pg.position.set(px, 0, 3.2);
    g.add(pg);

    // Drooping wires from each insulator to shop meter area
    const wireTargets = [-7.8, 0.0, 7.8];
    wireTargets.forEach((tx) => {
      const pts: THREE.Vector3[] = [];
      for (let t = 0; t <= 1; t += 0.08) {
        const wx = px + (tx - px) * t;
        const wy = 6.5 - Math.sin(t * Math.PI) * 0.7;
        const wz = 3.2 - t * 1.0;
        pts.push(new THREE.Vector3(wx, wy, wz));
      }
      const lineGeo = new THREE.BufferGeometry().setFromPoints(pts);
      g.add(new THREE.Line(lineGeo, wireLineMat));
    });
  }

  addPole(-11.5);
  addPole(+11.5);

  // ── Tropical Trees (trachycarpus / pohon peneduh) ─────────────────────────
  function addTree(px: number) {
    const tg = new THREE.Group();
    // Trunk
    tg.add(cyl(0.15, 0.20, 2.8, 8, mat(0x78350F, 0.85), 0, 1.4, 0));
    // Canopy layers — rich tropical green
    const leaf1M = mat(0x16A34A, 0.75);
    const leaf2M = mat(0x15803D, 0.70);
    tg.add(new THREE.Mesh(new THREE.SphereGeometry(1.3, 10, 7), leaf1M));
    const top = new THREE.Mesh(new THREE.SphereGeometry(0.85, 9, 6), leaf2M);
    top.position.y = 1.05; top.castShadow = true;
    tg.add(top);
    tg.children.forEach((c) => { (c as THREE.Mesh).castShadow = true; (c as THREE.Mesh).receiveShadow = true; });
    tg.position.set(px, 2.8, 3.6);
    g.add(tg);
  }
  addTree(-3.8);
  addTree(+3.8);

  // ── Pickup Truck — BLUE ───────────────────────────────────────────────────
  const truck = new THREE.Group();
  const cabM   = mat(0x1E40AF, 0.65);       // dark blue
  const windM  = mat(0x93C5FD, 0.10, 0.1, { transparent: true, opacity: 0.55 });
  const bedM   = mat(0x1E3A8A, 0.75);
  const tireM  = mat(0x111827, 0.95);
  const rimM   = mat(0xB0B7C3, 0.55, 0.5);
  const lampM  = mat(0xFEF08A, 0.1, 0.0, { emissive: new THREE.Color(0xFEF08A), emissiveIntensity: 0.9 });

  // Cabin
  truck.add(box(2.4, 1.1, 1.6, cabM, 0, 1.35, 0));
  // Windshield
  truck.add(box(2.41, 0.6, 0.07, windM, 0, 1.55, -0.77));
  // Headlamps
  truck.add(box(0.28, 0.18, 0.07, lampM, -0.75, 1.1, -0.80));
  truck.add(box(0.28, 0.18, 0.07, lampM,  0.75, 1.1, -0.80));
  // Truck bed
  truck.add(box(2.4, 0.65, 2.6, bedM, 0, 0.93, 1.6));
  truck.add(box(2.4, 0.38, 0.09, bedM, 0, 1.19, 2.9));  // tailgate
  truck.add(box(0.09, 0.38, 2.6, bedM, -1.2, 1.19, 1.6));
  truck.add(box(0.09, 0.38, 2.6, bedM,  1.2, 1.19, 1.6));
  // Undercarriage
  truck.add(box(2.4, 0.38, 4.5, mat(0x374151, 0.9), 0, 0.54, 0.75));
  // Wheels
  for (const [wx, wz] of [[-1.1, -0.65], [1.1, -0.65], [-1.1, 2.1], [1.1, 2.1]]) {
    const w = cyl(0.40, 0.40, 0.30, 12, tireM, wx, 0.40, wz);
    w.rotation.z = Math.PI / 2; truck.add(w);
    const r = cyl(0.20, 0.20, 0.32, 10, rimM, wx, 0.40, wz);
    r.rotation.z = Math.PI / 2; truck.add(r);
  }
  // Rice sacks (8 cylinders, goni krem)
  const sackM = mat(0xD7C4A5, 0.90);
  const sackPositions: [number, number][] = [
    [-0.6,1.1],[0.6,1.1],[-0.6,1.8],[0.6,1.8],[0,2.5],[-0.6,2.5],[0.6,2.5],[0,1.5],
  ];
  sackPositions.forEach(([sx, sz]) => {
    const sack = cyl(0.30, 0.34, 0.60, 8, sackM, sx, 1.52, sz);
    sack.rotation.x = Math.PI / 2; truck.add(sack);
  });

  truck.position.set(-4.0, 0, 6.2);
  truck.rotation.y = 0.05;
  g.add(truck);

  // ── Motorcycle — RED ──────────────────────────────────────────────────────
  const moto = new THREE.Group();
  const bodyM = mat(0xDC2626, 0.65);
  moto.add(box(0.30, 0.55, 1.3, bodyM, 0, 0.78, 0));
  moto.add(box(0.28, 0.30, 0.55, mat(0xB91C1C, 0.60), 0, 1.04, -0.28));  // tank
  moto.add(box(0.24, 0.10, 0.60, mat(0x111827, 0.80), 0, 1.03, 0.25));   // seat
  moto.add(box(0.60, 0.07, 0.07, mat(0x9CA3AF, 0.5, 0.6), 0, 1.21, -0.60)); // handlebar
  // Wheels
  for (const wz of [-0.52, 0.52]) {
    const tw = cyl(0.30, 0.30, 0.15, 12, tireM, 0, 0.30, wz);
    tw.rotation.z = Math.PI / 2; moto.add(tw);
  }
  moto.position.set(-5.8, 0, 3.6);
  moto.rotation.y = -0.25;
  g.add(moto);

  return { group: g, truckRef: truck };
}
