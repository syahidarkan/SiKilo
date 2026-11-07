import * as THREE from 'three';

export interface ShopsRefs {
  group: THREE.Group;
  pvGroup1: THREE.Group;
  pvGroup2: THREE.Group;
  pvGroup3: THREE.Group;
  meterInd1: THREE.Mesh;
  meterInd2: THREE.Mesh;
  meterInd3: THREE.Mesh;
  drumGroup: THREE.Group;
  // World positions for mascot placement
  shop1CounterPos: THREE.Vector3;
  shop2TablePos: THREE.Vector3;
  shop3BasketPos: THREE.Vector3;
  meterPos1: THREE.Vector3;
  meterPos2: THREE.Vector3;
  meterPos3: THREE.Vector3;
}

function mat(hex: number, rough = 0.8, metal = 0.0): THREE.MeshStandardMaterial {
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

function makeSignTexture(line1: string, line2: string, bgColor: string, textColor: string): THREE.CanvasTexture {
  const canvas = document.createElement('canvas');
  canvas.width = 512; canvas.height = 128;
  const ctx = canvas.getContext('2d')!;
  ctx.fillStyle = bgColor;
  ctx.fillRect(0, 0, 512, 128);
  ctx.strokeStyle = textColor;
  ctx.lineWidth = 3;
  ctx.strokeRect(4, 4, 504, 120);
  ctx.fillStyle = textColor;
  ctx.textAlign = 'center';
  ctx.textBaseline = 'middle';
  if (line2) {
    ctx.font = 'bold 28px Arial, sans-serif';
    ctx.fillText(line1, 256, 44);
    ctx.font = '22px Arial, sans-serif';
    ctx.fillText(line2, 256, 84);
  } else {
    ctx.font = 'bold 32px Arial, sans-serif';
    ctx.fillText(line1, 256, 64);
  }
  return new THREE.CanvasTexture(canvas);
}

function makePVTexture(): THREE.CanvasTexture {
  const canvas = document.createElement('canvas');
  canvas.width = 320; canvas.height = 160;
  const ctx = canvas.getContext('2d')!;
  ctx.fillStyle = '#071628';
  ctx.fillRect(0, 0, 320, 160);
  ctx.strokeStyle = '#1E3A6A';
  ctx.lineWidth = 1;
  for (let y = 20; y < 160; y += 20) {
    ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(320, y); ctx.stroke();
  }
  ctx.strokeStyle = '#2563EB';
  ctx.lineWidth = 1.5;
  for (const x of [80, 160, 240]) {
    ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x, 160); ctx.stroke();
  }
  return new THREE.CanvasTexture(canvas);
}

function buildPVArray(cx: number, roofY: number, g: THREE.Group): THREE.Group {
  const pvGroup = new THREE.Group();

  const pvTex = makePVTexture();
  const pvMat = new THREE.MeshStandardMaterial({
    map: pvTex,
    roughness: 0.15,
    metalness: 0.45,
    color: 0x0B192C,
  });
  const frameMat = mat(0xAAAAAA, 0.4, 0.6);

  // 4 panels arranged 2×2
  const positions: [number, number][] = [[-1.3, -0.55], [0.1, -0.55], [-1.3, 0.55], [0.1, 0.55]];
  for (const [px, pz] of positions) {
    // Panel face
    const panel = new THREE.Mesh(new THREE.BoxGeometry(1.2, 0.07, 1.0), pvMat);
    panel.position.set(cx + px, 0, pz);
    pvGroup.add(panel);
    // Aluminium frame
    const frameTop    = box(1.2, 0.07, 0.06, frameMat, cx + px, 0, pz - 0.52);
    const frameBottom = box(1.2, 0.07, 0.06, frameMat, cx + px, 0, pz + 0.52);
    const frameLeft   = box(0.06, 0.07, 1.0, frameMat, cx + px - 0.63, 0, pz);
    const frameRight  = box(0.06, 0.07, 1.0, frameMat, cx + px + 0.63, 0, pz);
    pvGroup.add(frameTop, frameBottom, frameLeft, frameRight);
  }

  // Tilt group 15 degrees
  const tiltGroup = new THREE.Group();
  tiltGroup.add(pvGroup);
  tiltGroup.rotation.x = -0.26; // 15°

  const wrapper = new THREE.Group();
  wrapper.add(tiltGroup);
  wrapper.position.set(0, roofY + 0.12, -0.6);
  wrapper.scale.set(1, 0, 1); // starts collapsed, animated by scene

  g.add(wrapper);
  return wrapper;
}

function buildMeterBox(cx: number, g: THREE.Group): { mesh: THREE.Mesh; indMesh: THREE.Mesh; worldPos: THREE.Vector3 } {
  const mx = cx - 2.75;
  const my = 2.5;
  const mz = 2.33;

  // Meter housing
  const housingM = mat(0xE0E4EC, 0.6);
  g.add(box(0.44, 0.68, 0.10, housingM, mx, my, mz));

  // Dial face
  const dialM = mat(0xC8CCd4, 0.5);
  g.add(box(0.32, 0.22, 0.03, dialM, mx, my + 0.05, mz + 0.05));

  // Warning band (top strip)
  const bandM = mat(0xFFD700, 0.6);
  g.add(box(0.44, 0.08, 0.08, bandM, mx, my + 0.3, mz + 0.01));

  // LED indicator (animated)
  const indMat = new THREE.MeshStandardMaterial({
    color: 0xEF4444,
    emissive: new THREE.Color(0xEF4444),
    emissiveIntensity: 2.5,
    roughness: 0.3,
  });
  const indMesh = new THREE.Mesh(new THREE.CircleGeometry(0.055, 12), indMat);
  indMesh.position.set(mx, my + 0.22, mz + 0.06);
  g.add(indMesh);

  // Wall bracket
  g.add(box(0.08, 0.80, 0.08, mat(0x888888, 0.7, 0.3), mx - 0.26, my, mz - 0.04));

  // Drop cable stub (from span area to meter) — visible segment near meter
  const stubCurve = new THREE.CatmullRomCurve3([
    new THREE.Vector3(mx, 4.80, 3.40),
    new THREE.Vector3(mx, 3.60, 3.00),
    new THREE.Vector3(mx, my + 0.5, mz + 0.05),
  ]);
  const stubGeo = new THREE.TubeGeometry(stubCurve, 12, 0.025, 5, false);
  const stubMesh = new THREE.Mesh(stubGeo, new THREE.MeshStandardMaterial({ color: 0x1A1A1A, roughness: 0.9 }));
  stubMesh.userData.isDropStub = true;
  g.add(stubMesh);

  // CT clamp ring (clamped on cable at y≈3.1)
  const clampM = new THREE.MeshStandardMaterial({ color: 0x111827, roughness: 0.3, metalness: 0.65 });
  const clampBody = new THREE.Mesh(new THREE.TorusGeometry(0.10, 0.028, 10, 20), clampM);
  clampBody.position.set(mx, 3.10, 3.18);
  clampBody.rotation.x = -0.42; // align with cable angle
  g.add(clampBody);
  // Sensor module on clamp
  g.add(box(0.14, 0.09, 0.09, new THREE.MeshStandardMaterial({ color: 0x1E3A6A, roughness: 0.5, metalness: 0.3 }), mx + 0.14, 3.10, 3.18));
  // Wire from sensor to meter
  const wireCurve = new THREE.CatmullRomCurve3([
    new THREE.Vector3(mx + 0.14, 3.10, 3.18),
    new THREE.Vector3(mx + 0.14, 2.75, 2.70),
    new THREE.Vector3(mx, my + 0.1, mz + 0.05),
  ]);
  g.add(new THREE.Mesh(new THREE.TubeGeometry(wireCurve, 10, 0.012, 4, false),
    new THREE.MeshStandardMaterial({ color: 0x2FBF71, roughness: 0.8 })));

  return {
    mesh: indMesh,
    indMesh,
    worldPos: new THREE.Vector3(mx, my, mz),
  };
}

// ─── Shop 1: Toko Kelontong ──────────────────────────────────────────────────
function buildKelontong(cx: number, g: THREE.Group): {
  pvGroup: THREE.Group;
  meterInd: THREE.Mesh;
  meterPos: THREE.Vector3;
  counterPos: THREE.Vector3;
} {
  // Shell
  buildShell(cx, g, 0xFFF8F0, 0x2D5A27, 'TOKO KELONTONG', '24 JAM', '#FFF3E0', '#1A3B0D');

  // Freezer / display shelves
  const freezerM = mat(0xCCE5FF, 0.4, 0.2);
  g.add(box(1.8, 1.0, 0.72, freezerM, cx - 0.5, 0.5, -1.0));
  g.add(box(1.8, 0.05, 0.72, mat(0x90CAF9, 0.3, 0.3), cx - 0.5, 1.02, -1.0));
  // Shelving unit
  g.add(box(2.2, 1.6, 0.4, mat(0xD4A574, 0.8), cx + 2.0, 0.8, -1.6));
  for (const sy of [0.4, 0.8, 1.2]) {
    g.add(box(2.2, 0.04, 0.4, mat(0xC4956A, 0.7), cx + 2.0, sy, -1.6));
  }
  // Counter / kasir
  g.add(box(1.6, 0.80, 0.70, mat(0xC4A882, 0.7), cx - 2.0, 0.40, 0.8));
  g.add(box(1.6, 0.06, 0.70, mat(0xDEB887, 0.5), cx - 2.0, 0.83, 0.8));
  // Cash register on counter
  g.add(box(0.3, 0.3, 0.2, mat(0x222222, 0.5), cx - 2.3, 1.0, 0.75));

  // Fuel pump (highlight piece)
  const pumpM = mat(0xE63946, 0.5, 0.1);
  g.add(box(0.3, 0.9, 0.3, pumpM, cx - 2.6, 0.45, 0.4));
  g.add(box(0.14, 0.14, 0.14, mat(0x444444, 0.4), cx - 2.6, 0.95, 0.4));

  const pvGroup = buildPVArray(cx, 4.60, g);
  const { indMesh, worldPos } = buildMeterBox(cx, g);

  return {
    pvGroup,
    meterInd: indMesh,
    meterPos: worldPos,
    counterPos: new THREE.Vector3(cx - 2.0, 1.0, 0.8),
  };
}

// ─── Shop 2: Konveksi ────────────────────────────────────────────────────────
function buildKonveksi(cx: number, g: THREE.Group): {
  pvGroup: THREE.Group;
  meterInd: THREE.Mesh;
  meterPos: THREE.Vector3;
  tablePos: THREE.Vector3;
} {
  buildShell(cx, g, 0xFFF0F5, 0x5A2D82, 'BERKAH TAILOR', '& SABLON', '#F3E8FF', '#3D1A5A');

  // Sewing tables
  for (const tx of [-1.4, 0.2]) {
    g.add(box(1.3, 0.72, 0.6, mat(0xBE8A60, 0.7), cx + tx, 0.36, 0.6));
    g.add(box(1.3, 0.04, 0.6, mat(0xD4A878, 0.5), cx + tx, 0.74, 0.6));
    // Sewing machine on table
    g.add(box(0.4, 0.25, 0.28, mat(0x111111, 0.3), cx + tx - 0.2, 0.86, 0.5));
    g.add(box(0.08, 0.5, 0.08, mat(0x888888, 0.5), cx + tx, 0.74, 0.3));
  }

  // Fabric roll rack
  g.add(box(0.3, 1.5, 2.2, mat(0x8B6914, 0.8), cx + 2.5, 0.75, -0.5));
  for (const fz of [-1.0, -0.4, 0.2, 0.8]) {
    const col = [0xFFCDD2, 0xC8E6C9, 0xBBDEFB, 0xFFF9C4][Math.floor((fz + 1.0) / 0.6)];
    g.add(box(0.3, 0.14, 0.26, mat(col ?? 0xFFFFFF, 0.7), cx + 2.5, 0.8 + fz * 0.3 + 0.4, fz));
  }

  // Boiler / steam iron unit
  const boilerM = mat(0xCFCFCF, 0.4, 0.5);
  g.add(box(0.5, 0.5, 0.4, boilerM, cx - 2.4, 0.25, -0.8));

  // Mannequin
  g.add(cyl2(0.14, 0.18, 0.7, 8, mat(0xDDDDDD, 0.5), cx + 1.6, 0.75, 1.3));
  g.add(cyl2(0.03, 0.03, 0.8, 6, mat(0x888888, 0.6), cx + 1.6, 0.4, 1.3));

  const pvGroup = buildPVArray(cx, 4.60, g);
  const { indMesh, worldPos } = buildMeterBox(cx, g);

  return {
    pvGroup,
    meterInd: indMesh,
    meterPos: worldPos,
    tablePos: new THREE.Vector3(cx + 0.2, 0.92, 0.6),
  };
}

// ─── Shop 3: Laundry ─────────────────────────────────────────────────────────
function buildLaundry(cx: number, g: THREE.Group, drumGroup: THREE.Group): {
  pvGroup: THREE.Group;
  meterInd: THREE.Mesh;
  meterPos: THREE.Vector3;
  basketPos: THREE.Vector3;
} {
  buildShell(cx, g, 0xF0F8FF, 0x1565C0, 'LAUNDRY KILOAN', 'EXPRESS', '#E3F2FD', '#0D3B6E');

  // Washing machines
  const wmM  = mat(0xEEEEEE, 0.4, 0.2);
  const wmDM = mat(0x90CAF9, 0.3, 0.3);
  for (const wx of [cx - 2.5, cx - 1.3]) {
    g.add(box(0.9, 0.9, 0.7, wmM, wx, 0.45, -0.9));
    g.add(cyl2(0.26, 0.26, 0.05, 12, wmDM, wx, 0.74, -0.56));
  }

  // Dryer (larger)
  g.add(box(1.0, 1.1, 0.8, mat(0xF5F5F5, 0.4, 0.2), cx + 1.4, 0.55, -0.9));
  g.add(cyl2(0.30, 0.30, 0.06, 12, mat(0xFFCC80, 0.3, 0.2), cx + 1.4, 0.80, -0.54));

  // Folding table
  g.add(box(2.0, 0.76, 0.65, mat(0xC0A060, 0.7), cx, 0.38, 0.8));
  g.add(box(2.0, 0.04, 0.65, mat(0xD4B478, 0.5), cx, 0.78, 0.8));

  // Laundry baskets with clothes
  const basketColors = [0xF48FB1, 0x81C784, 0xFFD54F];
  for (let i = 0; i < 3; i++) {
    const bx = cx + (i - 1) * 1.0;
    g.add(box(0.52, 0.42, 0.42, mat(0xA0A0A0, 0.9), bx, 0.21, 1.6));
    g.add(box(0.42, 0.14, 0.32, mat(basketColors[i], 0.8), bx, 0.49, 1.6));
  }

  // Rotating drum items (clothes)
  for (let ci = 0; ci < 4; ci++) {
    const wx = cx - 2.5 + (ci % 2 === 0 ? 0 : 1.2);
    const wz = -0.9;
    const cloth = box(0.14, 0.12, 0.05, mat([0xEF9A9A, 0x90CAF9, 0xA5D6A7, 0xFFE082][ci], 0.8),
      wx + Math.cos(ci * Math.PI / 2) * 0.12,
      0.74 + Math.sin(ci * Math.PI / 2) * 0.12,
      wz,
    );
    cloth.userData.drumCenter = new THREE.Vector3(wx, 0.74, wz);
    cloth.userData.drumAngle  = ci * Math.PI / 2;
    drumGroup.add(cloth);
  }
  g.add(drumGroup);

  const pvGroup = buildPVArray(cx, 4.60, g);
  const { indMesh, worldPos } = buildMeterBox(cx, g);

  return {
    pvGroup,
    meterInd: indMesh,
    meterPos: worldPos,
    basketPos: new THREE.Vector3(cx, 0.6, 1.6),
  };
}

// ─── Shared shell builder ────────────────────────────────────────────────────
function buildShell(
  cx: number,
  g: THREE.Group,
  wallColor: number,
  roofColor: number,
  signLine1: string,
  signLine2: string,
  signBg: string,
  signText: string,
): void {
  const wallM  = mat(wallColor, 0.9);
  const roofM  = mat(roofColor, 0.8, 0.0);
  const tileM  = mat(0xDDD8D0, 0.95);
  const colM   = mat(0xBBB8B2, 0.7);

  // Floor
  g.add(box(6.5, 0.14, 4.5, tileM, cx, 0.07, 0.14));

  // Back wall
  g.add(box(6.5, 4.4, 0.20, wallM, cx, 2.2, -2.11));

  // Side walls
  g.add(box(0.20, 4.4, 4.3, wallM, cx - 3.15, 2.2, 0.0));
  g.add(box(0.20, 4.4, 4.3, wallM, cx + 3.15, 2.2, 0.0));

  // Front columns
  g.add(box(0.20, 4.4, 0.20, colM, cx - 3.0, 2.2, 2.37));
  g.add(box(0.20, 4.4, 0.20, colM, cx + 3.0, 2.2, 2.37));

  // Front beam — ghost-transparent so camera can see shop interior
  const frontBeamM = new THREE.MeshStandardMaterial({ color: 0xBBB8B2, roughness: 0.7, transparent: true, opacity: 0.28, depthWrite: false });
  g.add(box(6.5, 0.22, 0.22, frontBeamM, cx, 4.31, 2.37));

  // Ceiling — ghost-transparent so isometric camera sees inside
  const ceilM = new THREE.MeshStandardMaterial({ color: 0xEEEAE0, roughness: 0.9, transparent: true, opacity: 0.12, depthWrite: false });
  g.add(box(6.5, 0.14, 4.5, ceilM, cx, 4.37, 0.14));

  // Roof overhang — ghost
  const ovhM = new THREE.MeshStandardMaterial({ color: roofColor, roughness: 0.8, transparent: true, opacity: 0.20, depthWrite: false });
  g.add(box(7.0, 0.20, 1.6, ovhM, cx, 4.47, 2.6));
  g.add(box(7.0, 0.20, 0.5, ovhM, cx, 4.75, 1.8));

  // Roof top flat — ghost
  const rfTopM = new THREE.MeshStandardMaterial({ color: 0xCCC8C0, roughness: 0.9, transparent: true, opacity: 0.18, depthWrite: false });
  g.add(box(6.8, 0.22, 4.9, rfTopM, cx, 4.59, -0.1));
  g.add(box(6.8, 0.22, 0.4, new THREE.MeshStandardMaterial({ color: roofColor, roughness: 0.7, transparent: true, opacity: 0.18, depthWrite: false }), cx, 4.70, 2.4));

  // Porch floor
  g.add(box(6.5, 0.14, 1.0, tileM, cx, 0.07, 2.9));

  // Shop signboard with CanvasTexture
  try {
    const signTex = makeSignTexture(signLine1, signLine2, signBg, signText);
    const signMesh = new THREE.Mesh(
      new THREE.PlaneGeometry(4.6, 0.55),
      new THREE.MeshBasicMaterial({ map: signTex }),
    );
    signMesh.position.set(cx, 3.72, 2.42);
    g.add(signMesh);
  } catch {
    // fallback: plain colored plank
    g.add(box(4.6, 0.55, 0.06, mat(0xFFF8E1, 0.6), cx, 3.72, 2.42));
  }

  // Tile floor lines
  const tLineM = mat(0xBBB8B0, 0.9);
  for (let tx = cx - 3.0; tx <= cx + 3.0; tx += 0.9) {
    g.add(box(0.03, 0.15, 4.5, tLineM, tx, 0.07, 0.14));
  }
}

function cyl2(
  rt: number, rb: number, h: number, seg: number,
  material: THREE.Material,
  x = 0, y = 0, z = 0,
): THREE.Mesh {
  const m = new THREE.Mesh(new THREE.CylinderGeometry(rt, rb, h, seg), material);
  m.position.set(x, y, z);
  m.castShadow = true;
  return m;
}

export function buildShops(scene: THREE.Scene): ShopsRefs {
  const g = new THREE.Group();
  const drumGroup = new THREE.Group();

  const CX = [-9, 0, 9] as const;

  const shop1 = buildKelontong(CX[0], g);
  const shop2 = buildKonveksi(CX[1], g);
  const shop3 = buildLaundry(CX[2], g, drumGroup);

  scene.add(g);

  return {
    group: g,
    pvGroup1: shop1.pvGroup,
    pvGroup2: shop2.pvGroup,
    pvGroup3: shop3.pvGroup,
    meterInd1: shop1.meterInd,
    meterInd2: shop2.meterInd,
    meterInd3: shop3.meterInd,
    drumGroup,
    shop1CounterPos: shop1.counterPos,
    shop2TablePos: shop2.tablePos,
    shop3BasketPos: shop3.basketPos,
    meterPos1: shop1.meterPos,
    meterPos2: shop2.meterPos,
    meterPos3: shop3.meterPos,
  };
}
