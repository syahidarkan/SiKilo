'use client';

import { useEffect, useRef } from 'react';
import * as THREE from 'three';
import { RoomEnvironment } from 'three/examples/jsm/environments/RoomEnvironment.js';
import './story.css';

/* ─────────────────────────────────────────────────────────────────────────────
   Satu hari di Laundry Barokah, dibangun sebagai ruko deret yang nyata:
   plesteran, keramik, paving, kaca, rolling door, tiang listrik dengan kabel melendut.
   Kamera orthographic isometrik. Scroll mengatur kamera, jam (langit, matahari,
   bayangan), beban tiap mesin, produksi surya, dan aliran listrik.
   Parallax: lapisan rumah belakang dan skyline mengikuti kamera dengan faktor berbeda,
   ditambah awan CSS di balik canvas dan dorongan kecil dari pointer.
   ───────────────────────────────────────────────────────────────────────────── */

const CHAPTERS = [
  { a: 0, b: 0.11, kick: 'Ilustrasi · Sukoharjo · 05.30', h: 1, title: 'Satu hari di Laundry Barokah', body: 'Satu meteran listrik, delapan mesin, dan tagihan yang baru ketahuan di akhir bulan. Gulir untuk mengikuti satu hari kerja di toko ini.', rail: 'Meteran' },
  { a: 0.14, b: 0.26, kick: '01 · Sensor', title: 'Dipasang di panel, bukan di tiap mesin', body: 'Sensor jepit melingkar di kabel masuk. Arus dan tegangan seluruh toko terbaca dari satu titik, tanpa membongkar instalasi.', rail: 'Sensor' },
  { a: 0.3, b: 0.5, kick: '02 · Pembacaan beban', title: 'Pengering dan setrika menyala bersamaan', body: 'Dari bentuk gelombang arusnya, NILM memisahkan tiap mesin. Di jam sibuk pagi, semua beban ditarik dari PLN sekaligus.', rail: 'Mesin' },
  { a: 0.54, b: 0.66, kick: '03 · Panel surya', title: 'Matahari naik, panel mulai bekerja', body: 'Panel di atap baru berguna kalau ada mesin yang menyala di jam yang sama. Sejak Permen ESDM 2/2024, kelebihan listrik tidak lagi memotong tagihan.', rail: 'Surya' },
  { a: 0.69, b: 0.86, kick: '04 · Penjadwalan', title: 'Mesin berat digeser ke jam matahari', body: 'Agen menjadwal ulang beban yang fleksibel. Mesin cuci bergantian, pengering dan setrika uap menyusul di jam produksi surya tertinggi.', rail: 'Jadwal' },
  { a: 0.9, b: 1.01, kick: '05 · Hasil', title: 'Meteran hijau di siang hari', body: 'Sebagian besar beban siang kini dilayani panel. Angka di layar ini ilustrasi. Hasil untuk usahamu dihitung di simulator.', rail: 'Hasil', cta: true },
];

const CAM_KEYS = [
  { p: 0.0, zoom: 0.86, t: [0, 3.6, 0.5], az: 30, el: 25 },
  { p: 0.11, zoom: 0.92, t: [0, 3.4, 0.5], az: 33, el: 25 },
  { p: 0.2, zoom: 2.9, t: [2.1, 1.9, 3.5], az: 24, el: 18 },
  { p: 0.3, zoom: 2.6, t: [1.8, 1.9, 3.5], az: 22, el: 18 },
  { p: 0.38, zoom: 1.85, t: [-0.5, 1.7, 0.8], az: 20, el: 21 },
  { p: 0.5, zoom: 1.7, t: [0, 5.1, 1.0], az: 22, el: 21 },
  { p: 0.6, zoom: 1.7, t: [0.2, 7.6, 0.5], az: 34, el: 33 },
  { p: 0.76, zoom: 1.15, t: [0.2, 3.9, 0.5], az: 32, el: 26 },
  { p: 0.9, zoom: 0.95, t: [0, 3.6, 0.5], az: 30, el: 25 },
  { p: 1.0, zoom: 0.88, t: [0, 3.6, 0.5], az: 28, el: 24 },
];

const HOUR_KEYS: [number, number][] = [[0, 5.3], [0.2, 6.6], [0.4, 9], [0.58, 12], [0.8, 13.6], [1, 17.2]];

const clamp01 = (x: number) => Math.max(0, Math.min(1, x));
const lerp = (a: number, b: number, t: number) => a + (b - a) * t;
const smooth = (a: number, b: number, x: number) => { const t = clamp01((x - a) / (b - a)); return t * t * (3 - 2 * t); };
const backOut = (t: number) => { const c = 1.70158, u = clamp01(t) - 1; return 1 + (c + 1) * u * u * u + c * u * u; };
const win = (p: number, a: number, b: number) => smooth(a, a + 0.02, p) * (1 - smooth(b - 0.02, b, p));
const hourAt = (p: number) => {
  for (let i = 0; i < HOUR_KEYS.length - 1; i++) {
    const [p0, h0] = HOUR_KEYS[i], [p1, h1] = HOUR_KEYS[i + 1];
    if (p <= p1) return lerp(h0, h1, clamp01((p - p0) / (p1 - p0)));
  }
  return HOUR_KEYS[HOUR_KEYS.length - 1][1];
};

type Kind = 'washer' | 'dryer' | 'ironer' | 'sewing';
interface MachineDef { kind: Kind; name: string; x: number; floor: 0 | 1; z: number; kw: number; before: [number, number]; after: [number, number] }
const FH = 3.4;                     // tinggi tiap lantai
const W = 5.4, D = 7.2;             // lebar dan kedalaman ruko
const H = FH * 2;
const Y0 = 0.14, Y1 = FH + 0.13;    // permukaan lantai 0 dan 1
const MACHINES: MachineDef[] = [
  { kind: 'washer', name: 'Mesin cuci 1', x: -1.85, floor: 0, z: 0.7, kw: 0.55, before: [0.3, 0.5], after: [0.6, 0.68] },
  { kind: 'washer', name: 'Mesin cuci 2', x: -1.0, floor: 0, z: 0.7, kw: 0.55, before: [0.31, 0.5], after: [0.66, 0.76] },
  { kind: 'washer', name: 'Mesin cuci 3', x: -0.15, floor: 0, z: 0.7, kw: 0.55, before: [0.32, 0.5], after: [0.72, 0.84] },
  { kind: 'dryer', name: 'Pengering', x: 0.95, floor: 0, z: 0.75, kw: 1.8, before: [0.34, 0.5], after: [0.62, 0.86] },
  { kind: 'ironer', name: 'Setrika uap', x: -1.0, floor: 0, z: -1.5, kw: 1.3, before: [0.36, 0.5], after: [0.64, 0.86] },
  { kind: 'sewing', name: 'Mesin jahit 1', x: -1.6, floor: 1, z: 1.0, kw: 0.4, before: [0.34, 0.53], after: [0.62, 0.9] },
  { kind: 'sewing', name: 'Mesin jahit 2', x: -0.45, floor: 1, z: 1.0, kw: 0.4, before: [0.34, 0.53], after: [0.64, 0.9] },
  { kind: 'sewing', name: 'Mesin jahit 3', x: 0.7, floor: 1, z: 1.0, kw: 0.4, before: [0.35, 0.53], after: [0.66, 0.9] },
];
const BASE_KW = 0.3;
const TAG_DY = [0, -28, -56, -22, -8, 0, -28, -56]; // geser vertikal label supaya tidak bertumpuk
const PV_KWP = 4.2;

export default function StoryScene() {
  const stickyRef = useRef<HTMLDivElement>(null);
  const trackRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const sticky = stickyRef.current!;
    const track = trackRef.current!;
    const q = <T extends HTMLElement>(s: string) => sticky.querySelector(s) as T;
    const qa = (s: string) => Array.from(sticky.querySelectorAll<HTMLElement>(s));
    const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

    let renderer: THREE.WebGLRenderer;
    try {
      renderer = new THREE.WebGLRenderer({ canvas: q<HTMLCanvasElement>('canvas'), antialias: true, alpha: true });
    } catch {
      q('.st-nogl').hidden = false;
      return;
    }
    const DPR = Math.min(window.devicePixelRatio || 1, 2);
    renderer.setPixelRatio(DPR);
    renderer.shadowMap.enabled = true;
    renderer.shadowMap.type = THREE.PCFShadowMap;
    renderer.toneMapping = THREE.ACESFilmicToneMapping;
    renderer.toneMappingExposure = 1.0;

    const scene = new THREE.Scene();
    scene.fog = new THREE.Fog(0xffffff, 92, 160);
    const pmrem = new THREE.PMREMGenerator(renderer);
    scene.environment = pmrem.fromScene(new RoomEnvironment(), 0.04).texture;
    const camera = new THREE.OrthographicCamera(-10, 10, 10, -10, 0.1, 400);
    const hemi = new THREE.HemisphereLight(0xffffff, 0xb9b3a4, 0.6);
    const sun = new THREE.DirectionalLight(0xffffff, 3);
    sun.castShadow = true;
    sun.shadow.mapSize.set(2048, 2048);
    sun.shadow.bias = -0.0004;
    sun.shadow.normalBias = 0.04;
    sun.shadow.radius = 3;
    const sc = sun.shadow.camera;
    sc.left = -16; sc.right = 16; sc.top = 16; sc.bottom = -16; sc.near = 1; sc.far = 220;
    const moon = new THREE.DirectionalLight(0x8fb4ff, 0);
    moon.position.set(-10, 25, 30);
    const roomA = new THREE.PointLight(0xffc98a, 0, 9, 1.4);
    roomA.position.set(0, FH - 0.8, 1.0);
    const roomB = new THREE.PointLight(0xffe2b0, 0, 9, 1.4);
    roomB.position.set(0, H - 0.8, 1.0);
    scene.add(hemi, sun, sun.target, moon, roomA, roomB);
    sun.target.position.set(0, 2, 0);

    /* ── tekstur prosedural ── */
    const disposables: { dispose(): void }[] = [];
    let seed = 7;
    const rnd = () => { seed = (seed * 16807) % 2147483647; return seed / 2147483647; };
    function canvasTex(w: number, h: number, draw: (x: CanvasRenderingContext2D) => void, srgb = true) {
      const c = document.createElement('canvas');
      c.width = w; c.height = h;
      draw(c.getContext('2d')!);
      const t = new THREE.CanvasTexture(c);
      t.wrapS = t.wrapT = THREE.RepeatWrapping;
      t.anisotropy = 8;
      if (srgb) t.colorSpace = THREE.SRGBColorSpace;
      disposables.push(t);
      return t;
    }
    function speckle(x: CanvasRenderingContext2D, w: number, h: number, n: number, amp: number) {
      for (let i = 0; i < n; i++) {
        const v = rnd() < 0.5 ? 0 : 255;
        x.fillStyle = `rgba(${v},${v},${v},${rnd() * amp})`;
        x.fillRect(rnd() * w, rnd() * h, 1 + rnd() * 2, 1 + rnd() * 2);
      }
    }
    const texPlaster = canvasTex(256, 256, (x) => {
      x.fillStyle = '#fff'; x.fillRect(0, 0, 256, 256);
      speckle(x, 256, 256, 5000, 0.08);
      for (let i = 0; i < 14; i++) { // noda air hujan memanjang ke bawah
        const g = x.createLinearGradient(0, 0, 0, 256), px = rnd() * 256;
        g.addColorStop(0, 'rgba(60,50,30,0.0)'); g.addColorStop(0.3, `rgba(60,50,30,${0.04 + rnd() * 0.05})`); g.addColorStop(1, 'rgba(60,50,30,0)');
        x.fillStyle = g; x.fillRect(px, 0, 2 + rnd() * 6, 256);
      }
    });
    const texTile = canvasTex(256, 256, (x) => {
      x.fillStyle = '#fff'; x.fillRect(0, 0, 256, 256);
      speckle(x, 256, 256, 1500, 0.05);
      x.strokeStyle = 'rgba(90,80,60,0.55)'; x.lineWidth = 3;
      for (let i = 0; i <= 256; i += 128) { x.beginPath(); x.moveTo(i, 0); x.lineTo(i, 256); x.stroke(); x.beginPath(); x.moveTo(0, i); x.lineTo(256, i); x.stroke(); }
    });
    const texAsphalt = canvasTex(256, 256, (x) => {
      x.fillStyle = '#fff'; x.fillRect(0, 0, 256, 256);
      speckle(x, 256, 256, 9000, 0.28);
      x.strokeStyle = 'rgba(0,0,0,0.22)'; x.lineWidth = 1.2;
      for (let i = 0; i < 4; i++) { x.beginPath(); let px = rnd() * 256, py = rnd() * 256; x.moveTo(px, py); for (let k = 0; k < 6; k++) { px += (rnd() - 0.5) * 40; py += (rnd() - 0.5) * 40; x.lineTo(px, py); } x.stroke(); }
    });
    const texPaving = canvasTex(256, 256, (x) => {
      x.fillStyle = '#fff'; x.fillRect(0, 0, 256, 256);
      for (let r = 0; r < 8; r++) for (let c = 0; c < 8; c++) {
        const off = r % 2 ? 16 : 0, v = 215 + rnd() * 40;
        x.fillStyle = `rgb(${v},${v},${v})`; x.fillRect(c * 32 + off + 1, r * 32 + 1, 30, 30);
      }
      speckle(x, 256, 256, 2000, 0.12);
    });
    const texShutter = canvasTex(128, 128, (x) => {
      for (let i = 0; i < 128; i += 4) { const g = x.createLinearGradient(i, 0, i + 4, 0); g.addColorStop(0, '#d9dde0'); g.addColorStop(0.5, '#fff'); g.addColorStop(1, '#aab0b5'); x.fillStyle = g; x.fillRect(i, 0, 4, 128); }
      x.fillStyle = 'rgba(0,0,0,0.18)'; for (let y = 0; y < 128; y += 16) x.fillRect(0, y, 128, 1.5);
    });
    const texRoof = canvasTex(256, 256, (x) => {
      x.fillStyle = '#fff'; x.fillRect(0, 0, 256, 256);
      for (let r = 0; r < 16; r++) { x.fillStyle = `rgba(0,0,0,${r % 2 ? 0.1 : 0.0})`; x.fillRect(0, r * 16, 256, 16); x.fillStyle = 'rgba(0,0,0,0.35)'; x.fillRect(0, r * 16, 256, 1.5); }
      speckle(x, 256, 256, 3000, 0.16);
    });
    const texSolar = canvasTex(256, 384, (x) => {
      const g = x.createLinearGradient(0, 0, 256, 384); g.addColorStop(0, '#1f4f86'); g.addColorStop(1, '#173a68');
      x.fillStyle = g; x.fillRect(0, 0, 256, 384);
      x.strokeStyle = 'rgba(200,215,235,0.55)'; x.lineWidth = 1.4;
      for (let i = 0; i <= 6; i++) { x.beginPath(); x.moveTo(8 + i * 40, 8); x.lineTo(8 + i * 40, 376); x.stroke(); }
      for (let j = 0; j <= 10; j++) { x.beginPath(); x.moveTo(8, 8 + j * 36.8); x.lineTo(248, 8 + j * 36.8); x.stroke(); }
      x.strokeStyle = 'rgba(220,230,245,0.35)'; x.lineWidth = 0.8;
      for (let i = 0; i < 6; i++) for (const o of [14, 26]) { x.beginPath(); x.moveTo(8 + i * 40 + o, 8); x.lineTo(8 + i * 40 + o, 376); x.stroke(); }
    });
    const texWindows = canvasTex(256, 512, (x) => {
      x.fillStyle = '#9aa7b8'; x.fillRect(0, 0, 256, 512);
      speckle(x, 256, 512, 3000, 0.06);
      for (let r = 0; r < 16; r++) for (let c = 0; c < 8; c++) { x.fillStyle = rnd() < 0.5 ? '#4b5d77' : '#3c4c63'; x.fillRect(c * 32 + 8, r * 32 + 8, 16, 18); }
    });
    const texWindowsLit = canvasTex(256, 512, (x) => {
      x.fillStyle = '#000'; x.fillRect(0, 0, 256, 512);
      for (let r = 0; r < 16; r++) for (let c = 0; c < 8; c++) if (rnd() < 0.3) { x.fillStyle = rnd() < 0.5 ? '#ffd9a0' : '#fff0c8'; x.fillRect(c * 32 + 8, r * 32 + 8, 16, 18); }
    });
    const texSign = canvasTex(1024, 192, (x) => {
      x.fillStyle = '#1b6b3c'; x.fillRect(0, 0, 1024, 192);
      x.fillStyle = '#f2c230'; x.fillRect(0, 150, 1024, 42);
      x.fillStyle = '#fff'; x.font = '800 96px system-ui, sans-serif'; x.textAlign = 'center'; x.textBaseline = 'middle';
      x.fillText('LAUNDRY BAROKAH', 512, 72);
      x.fillStyle = '#10301f'; x.font = '700 30px system-ui, sans-serif';
      x.fillText('KILOAN · SATUAN · SETRIKA UAP', 512, 172);
    });
    const signTexture = (label: string, bg: string, fg: string) => canvasTex(1024, 192, (x) => {
      x.fillStyle = bg; x.fillRect(0, 0, 1024, 192);
      x.strokeStyle = fg; x.lineWidth = 8; x.strokeRect(14, 14, 996, 164);
      x.fillStyle = fg; x.font = '800 92px system-ui, sans-serif'; x.textAlign = 'center'; x.textBaseline = 'middle';
      x.fillText(label, 512, 100);
    });

    /* ── material dan helper ── */
    const matCache = new Map<string, THREE.MeshStandardMaterial>();
    function std(color: number, o: { map?: THREE.Texture; rep?: [number, number]; rough?: number; metal?: number; key?: string } = {}) {
      const k = `${color}|${o.key ?? ''}|${o.rough ?? 0.8}|${o.metal ?? 0}|${o.rep ?? ''}`;
      let m = matCache.get(k);
      if (m) return m;
      let map = o.map;
      if (map && o.rep) { map = map.clone(); map.needsUpdate = true; map.repeat.set(o.rep[0], o.rep[1]); disposables.push(map); }
      m = new THREE.MeshStandardMaterial({ color, roughness: o.rough ?? 0.8, metalness: o.metal ?? 0 });
      if (map) m.map = map;
      matCache.set(k, m);
      return m;
    }
    const plaster = (c: number, w: number, h: number) => std(c, { map: texPlaster, rep: [Math.max(0.3, w / 2.4), Math.max(0.3, h / 2.4)], key: `pl${w.toFixed(1)}${h.toFixed(1)}`, rough: 0.92 });
    const glassMat = new THREE.MeshPhysicalMaterial({ color: 0xa9c4d6, roughness: 0.04, metalness: 0, transparent: true, opacity: 0.2, envMapIntensity: 1.6, depthWrite: false, side: THREE.DoubleSide });
    const alu = std(0xaeb4ba, { rough: 0.35, metal: 0.8 });
    const geoCache = new Map<string, THREE.BufferGeometry>();
    const bx = (w: number, h: number, d: number) => {
      const k = [w, h, d].join('|');
      let g = geoCache.get(k);
      if (!g) { g = new THREE.BoxGeometry(w, h, d); geoCache.set(k, g); disposables.push(g); }
      return g as THREE.BoxGeometry;
    };
    const add = (parent: THREE.Object3D, geo: THREE.BufferGeometry, m: THREE.Material, x = 0, y = 0, z = 0, shadow = true) => {
      const o = new THREE.Mesh(geo, m);
      o.position.set(x, y, z);
      if (shadow) { o.castShadow = true; o.receiveShadow = true; }
      parent.add(o);
      return o;
    };
    const box = (parent: THREE.Object3D, w: number, h: number, d: number, m: THREE.Material, x = 0, y = 0, z = 0, shadow = true) => add(parent, bx(w, h, d), m, x, y, z, shadow);
    const cyl = (parent: THREE.Object3D, rt: number, rb: number, h: number, m: THREE.Material, x = 0, y = 0, z = 0, seg = 16) => {
      const g = new THREE.CylinderGeometry(rt, rb, h, seg); disposables.push(g);
      return add(parent, g, m, x, y, z);
    };

    /* ── lapisan dunia ── */
    const world = new THREE.Group();
    const midL = new THREE.Group();   // rumah belakang, mengikuti kamera 0.55
    const farL = new THREE.Group();   // skyline, mengikuti kamera 0.9
    scene.add(world, midL, farL);
    const layers: [THREE.Group, number][] = [[midL, 0.55], [farL, 0.9]];

    /* tanah, trotoar paving, jalan aspal */
    const groundMat = new THREE.MeshStandardMaterial({ color: 0xb9b5a8, roughness: 0.95 });
    const groundGreen = new THREE.Color(0xa9c79a), groundGrey = new THREE.Color(0xb9b5a8);
    const ground = box(world, 160, 0.6, 160, groundMat, 0, -0.3, 0, false);
    ground.receiveShadow = true;
    const pave = box(world, 160, 0.14, 2.2, std(0xd8d4cc, { map: texPaving, rep: [60, 1], key: 'pv', rough: 0.9 }), 0, 0.07, D / 2 + 1.1, false);
    pave.receiveShadow = true;
    box(world, 160, 0.2, 0.22, std(0xc5c2ba, { rough: 0.85 }), 0, 0.1, D / 2 + 2.3, false);                 // kerb
    const road = box(world, 160, 0.06, 6.6, std(0x4b4e52, { map: texAsphalt, rep: [60, 2.5], key: 'as', rough: 0.95 }), 0, 0.03, D / 2 + 5.7, false);
    road.receiveShadow = true;
    for (let x = -70; x <= 70; x += 4) box(world, 2, 0.02, 0.15, std(0xe8e6dd, { rough: 0.8 }), x, 0.07, D / 2 + 5.7, false);
    box(world, 160, 0.2, 0.22, std(0xc5c2ba, { rough: 0.85 }), 0, 0.1, D / 2 + 9.0, false);
    box(world, 160, 0.14, 2.6, std(0xd8d4cc, { map: texPaving, rep: [60, 1.2], key: 'pv2', rough: 0.9 }), 0, 0.07, D / 2 + 10.3, false);
    box(world, 160, 0.04, 0.3, std(0x6e6e6a, { rough: 0.6, metal: 0.3 }), 0, 0.15, D / 2 + 2.05, false);     // saluran air

    /* ── ruko kita, dipotong di depan (rolling door terbuka) ── */
    const ruko = new THREE.Group();
    world.add(ruko);
    const wallC = 0xf0e4cc, sideC = 0xe9dcc2;
    box(ruko, W + 0.1, Y0, D, std(0xb8b3a6, { rough: 0.9 }), 0, Y0 / 2, 0);                               // plinth
    const tileFloor0 = box(ruko, W - 0.1, 0.02, D - 0.2, std(0xdad2c0, { map: texTile, rep: [W / 0.8, D / 0.8], key: 't0', rough: 0.35 }), 0, Y0 + 0.01, 0, false);
    tileFloor0.receiveShadow = true;
    box(ruko, W, H, 0.22, plaster(0xe3ddcf, W, H), 0, H / 2, -D / 2 + 0.11);                              // dinding belakang
    box(ruko, 0.22, H + 1.0, D, plaster(sideC, D, H), -W / 2 + 0.11, (H + 1.0) / 2, 0);                  // dinding kiri
    box(ruko, 0.22, H + 1.0, D, plaster(sideC, D, H), W / 2 - 0.11, (H + 1.0) / 2, 0);                   // dinding kanan
    box(ruko, W - 0.44, 0.9, 0.04, std(0x8d9e8a, { rough: 0.7 }), 0, 0.6, -D / 2 + 0.24, false);         // cat dasar dinding
    const slabM = std(0xcfc9bb, { map: texPlaster, rep: [3, 3], key: 'sl', rough: 0.9 });
    box(ruko, W, 0.26, D, slabM, 0, FH, 0);                                                              // pelat lantai 2
    const tileFloor1 = box(ruko, W - 0.1, 0.02, D - 0.2, std(0xcfc7b6, { map: texTile, rep: [W / 0.8, D / 0.8], key: 't1', rough: 0.35 }), 0, Y1 + 0.01, 0, false);
    tileFloor1.receiveShadow = true;
    box(ruko, W + 0.3, 0.3, D + 0.3, slabM, 0, H + 0.02, 0);                                              // pelat atap
    box(ruko, W, 0.06, D - 0.2, std(0x9a9890, { rough: 0.95 }), 0, H + 0.2, 0, false);                   // finishing atap
    // fasad depan: pilaster, balok, tembok bawah jendela, jendela kaca
    const fz = D / 2 - 0.12;
    [-1, 1].forEach((s) => box(ruko, 0.5, H, 0.28, plaster(wallC, 0.5, H), s * (W / 2 - 0.25), H / 2, fz));
    box(ruko, W, 0.58, 0.28, plaster(wallC, W, 0.6), 0, FH - 0.29, fz);                                  // balok di atas rolling door
    box(ruko, W - 1.0, 0.1, 0.12, std(0x9aa0a6, { map: texShutter, rep: [8, 1], key: 'sh', rough: 0.45, metal: 0.6 }), 0, FH - 0.66, fz - 0.05, false); // gulungan rolling door
    const wallBelow = 1.0;
    box(ruko, W - 1.0, wallBelow, 0.28, plaster(wallC, W, wallBelow), 0, FH + 0.13 + wallBelow / 2, fz);  // tembok bawah jendela
    const gh = FH - 0.13 - wallBelow - 0.42;
    const gy = FH + 0.13 + wallBelow + gh / 2;
    box(ruko, W - 1.0, 0.42, 0.28, plaster(wallC, W, 0.42), 0, H - 0.21, fz);                            // balok atas jendela
    [-1, 0, 1].forEach((i) => { box(ruko, (W - 1.0) / 3 - 0.02, gh, 0.02, glassMat, i * (W - 1.0) / 3, gy, fz + 0.04, false).renderOrder = 5; });
    [-1.5, -0.5, 0.5, 1.5].forEach((i) => box(ruko, 0.05, gh, 0.07, alu, i * (W - 1.0) / 3, gy, fz + 0.05, false));
    box(ruko, W - 1.0, 0.05, 0.07, alu, 0, gy + gh / 2, fz + 0.05, false);
    box(ruko, W - 1.0, 0.05, 0.07, alu, 0, gy - gh / 2, fz + 0.05, false);
    box(ruko, W + 0.2, 0.1, 0.55, plaster(wallC, W, 0.5), 0, H - 0.05, fz + 0.28);                      // sunshade
    [-1, 1].forEach((s) => box(ruko, 0.22, 1.0, D + 0.3, plaster(sideC, D, 1.0), s * (W / 2 + 0.04), H + 0.5, 0));
    box(ruko, W + 0.3, 1.1, 0.22, plaster(wallC, W, 1.1), 0, H + 0.55, D / 2 + 0.03);                    // parapet depan
    box(ruko, W + 0.3, 1.0, 0.2, plaster(wallC, W, 1.0), 0, H + 0.5, -D / 2 - 0.02);                     // parapet belakang
    const signMesh = new THREE.Mesh(new THREE.PlaneGeometry(W - 0.5, (W - 0.5) * 0.19), new THREE.MeshStandardMaterial({ map: texSign, roughness: 0.5, emissive: 0xffffff, emissiveMap: texSign, emissiveIntensity: 0 }));
    signMesh.position.set(0, H + 0.56, D / 2 + 0.15);
    ruko.add(signMesh);
    const signMat = signMesh.material as THREE.MeshStandardMaterial;
    const tubeMat = new THREE.MeshStandardMaterial({ color: 0xf6f6ee, emissive: 0xfff2d0, emissiveIntensity: 0.25, roughness: 0.4 });
    [[0, FH - 0.2, 0.8], [0, FH - 0.2, -1.8], [0, H - 0.2, 0.8], [0, H - 0.2, -1.8]].forEach(([x, y, z]) => box(ruko, 2.6, 0.05, 0.12, tubeMat, x, y, z, false));

    /* panel listrik di pilaster kanan: kotak kWh, MCB, sensor, dan LED status */
    const panelG = new THREE.Group();
    panelG.position.set(W / 2 - 0.25, 1.55, D / 2 + 0.02);
    ruko.add(panelG);
    box(panelG, 0.38, 0.62, 0.14, std(0xcfd3d6, { rough: 0.45, metal: 0.5 }), 0, 0, 0.07);
    box(panelG, 0.28, 0.26, 0.02, std(0x20262b, { rough: 0.2 }), 0, 0.12, 0.15, false);
    const meterMat = new THREE.MeshStandardMaterial({ color: 0x222222, emissive: 0xd1453a, emissiveIntensity: 1 });
    box(panelG, 0.2, 0.1, 0.02, meterMat, 0, 0.12, 0.165, false);
    [-0.1, 0, 0.1].forEach((x) => box(panelG, 0.06, 0.1, 0.03, std(0xf2f2ee, { rough: 0.5 }), x, -0.14, 0.155, false));
    const sensor = new THREE.Group();
    sensor.position.set(0, -0.62, 0.1);
    panelG.add(sensor);
    cyl(sensor, 0.03, 0.03, 0.3, std(0x111111, { rough: 0.6 }), 0, 0.15, 0, 10);
    const clamp = add(sensor, new THREE.TorusGeometry(0.07, 0.03, 10, 20), std(0x2a2f33, { rough: 0.5 }), 0, 0.12, 0, false);
    clamp.rotation.x = Math.PI / 2;
    const esp = new THREE.Group();
    esp.position.set(0.22, 0.12, 0);
    sensor.add(esp);
    box(esp, 0.16, 0.1, 0.06, std(0xf4f4f0, { rough: 0.5 }), 0, 0, 0);
    const ledMat = new THREE.MeshStandardMaterial({ color: 0x113311, emissive: 0x2fbf71, emissiveIntensity: 1 });
    add(esp, new THREE.SphereGeometry(0.012, 8, 6), ledMat, 0.05, 0.02, 0.035, false);
    sensor.scale.setScalar(0.001);

    /* ── mesin ── */
    interface Machine { def: MachineDef; g: THREE.Group; lamp: THREE.MeshStandardMaterial; spin?: THREE.Object3D; needle?: THREE.Object3D; puffs: THREE.Mesh[]; top: THREE.Vector3; act: number }
    const white = std(0xeeeeea, { rough: 0.32, metal: 0.1 });
    const steel = std(0xb9bfc4, { rough: 0.28, metal: 0.9 });
    const darkMat = std(0x1c2024, { rough: 0.4 });
    const clothCols = [0xe05a4a, 0x4a86c8, 0xf3d36b, 0x6fbf8a];
    const machines: Machine[] = MACHINES.map((def) => {
      const g = new THREE.Group();
      const y0 = def.floor === 0 ? Y0 : Y1;
      g.position.set(def.x, y0, def.z);
      ruko.add(g);
      const lamp = new THREE.MeshStandardMaterial({ color: 0x222222, emissive: 0x2fbf71, emissiveIntensity: 0.2 });
      let spin: THREE.Object3D | undefined, needle: THREE.Object3D | undefined, topY = 1;
      const puffs: THREE.Mesh[] = [];
      if (def.kind === 'washer' || def.kind === 'dryer') {
        const dry = def.kind === 'dryer';
        const h = dry ? 1.55 : 1.05, w = dry ? 0.85 : 0.78, d = 0.78;
        topY = h;
        box(g, w, h, d, dry ? std(0xe9e4d6, { rough: 0.35, metal: 0.15 }) : white, 0, h / 2, 0);
        box(g, w + 0.02, 0.07, d + 0.02, steel, 0, h + 0.03, 0);
        box(g, w - 0.1, 0.16, 0.03, darkMat, 0, h - 0.14, d / 2 + 0.01, false);
        box(g, 0.2, 0.05, 0.01, lamp, 0.12, h - 0.14, d / 2 + 0.03, false);
        [-0.2, -0.1].forEach((x) => { cyl(g, 0.025, 0.025, 0.03, steel, x, h - 0.14, d / 2 + 0.03, 10).rotation.x = Math.PI / 2; });
        const dy = dry ? h * 0.45 : h * 0.48;
        add(g, new THREE.TorusGeometry(0.27, 0.035, 12, 28), steel, 0, dy, d / 2 + 0.01);
        const door = cyl(g, 0.265, 0.265, 0.02, glassMat, 0, dy, d / 2 + 0.015, 28); door.rotation.x = Math.PI / 2; door.castShadow = false; door.renderOrder = 4;
        const back = cyl(g, 0.255, 0.255, 0.01, darkMat, 0, dy, d / 2 - 0.02, 24); back.rotation.x = Math.PI / 2;
        spin = new THREE.Group();
        spin.position.set(0, dy, d / 2 - 0.0);
        clothCols.forEach((c, i) => { const a = (i / 4) * Math.PI * 2; box(spin!, 0.13, 0.09, 0.02, std(c, { rough: 0.95 }), Math.cos(a) * 0.15, Math.sin(a) * 0.15, 0, false).rotation.z = a; });
        g.add(spin);
        [-1, 1].forEach((s) => box(g, 0.07, 0.04, 0.07, darkMat, s * (w / 2 - 0.06), 0.02, d / 2 - 0.06, false));
        if (dry) cyl(g, 0.07, 0.07, 0.5, std(0x8e949b, { rough: 0.5, metal: 0.6 }), 0.2, h + 0.3, -0.2, 10);
      } else if (def.kind === 'ironer') {
        topY = 1.15;
        box(g, 1.7, 0.1, 0.8, steel, 0, 0.82, 0);
        box(g, 1.6, 0.06, 0.7, std(0xe8e2d2, { rough: 0.95 }), 0, 0.9, 0, false);
        [-0.75, 0.75].forEach((x) => [-0.3, 0.3].forEach((z) => box(g, 0.06, 0.8, 0.06, steel, x, 0.4, z)));
        box(g, 1.5, 0.18, 0.46, std(0xdadfe3, { rough: 0.35, metal: 0.4 }), 0, 1.12, 0);
        box(g, 0.3, 0.05, 0.01, lamp, 0.5, 1.12, 0.24, false);
        for (let i = 0; i < 3; i++) puffs.push(add(g, new THREE.SphereGeometry(0.1, 10, 8), new THREE.MeshBasicMaterial({ color: 0xffffff, transparent: true, opacity: 0, depthWrite: false }), -0.45 + i * 0.45, 1.3, 0, false));
      } else {
        topY = 1.0;
        box(g, 1.1, 0.05, 0.6, std(0xb88a56, { rough: 0.6 }), 0, 0.76, 0);
        [-0.5, 0.5].forEach((x) => box(g, 0.05, 0.74, 0.5, steel, x, 0.37, 0));
        box(g, 1.0, 0.05, 0.45, steel, 0, 0.12, 0, false);
        box(g, 0.45, 0.2, 0.2, std(0xeeeeea, { rough: 0.35 }), 0, 0.9, -0.05);
        box(g, 0.16, 0.26, 0.16, std(0xeeeeea, { rough: 0.35 }), -0.14, 0.93, -0.05);
        needle = box(g, 0.02, 0.14, 0.02, steel, 0.12, 0.84, 0.06, false);
        box(g, 0.28, 0.02, 0.18, std(0xf4a7b9, { rough: 0.95 }), 0.0, 0.8, 0.12, false);
        box(g, 0.03, 0.03, 0.03, lamp, -0.2, 1.0, -0.05, false);
        cyl(g, 0.2, 0.2, 0.04, std(0x2a2f33, { rough: 0.6 }), 0.05, 0.46, 0.75, 14);
        cyl(g, 0.025, 0.025, 0.46, steel, 0.05, 0.23, 0.75, 8);
        box(g, 0.34, 0.3, 0.04, std(0x2a2f33, { rough: 0.6 }), 0.05, 0.7, 1.0);
      }
      return { def, g, lamp, spin, needle, puffs, top: new THREE.Vector3(def.x, y0 + topY, def.z), act: 0 };
    });
    /* properti: rak, keranjang, rak gantung, meja kasir */
    const shelfM = std(0x6e7a82, { rough: 0.5, metal: 0.6 });
    [-1.6, 0.0].forEach((x) => {
      [0.3, 0.8, 1.3, 1.8].forEach((y) => box(ruko, 1.3, 0.04, 0.4, shelfM, x, Y0 + y, -D / 2 + 0.5, false));
      [-0.64, 0.64].forEach((dx) => box(ruko, 0.04, 1.9, 0.4, shelfM, x + dx, Y0 + 0.95, -D / 2 + 0.5, false));
      [0.34, 0.84, 1.34].forEach((y, i) => { for (let k = 0; k < 3; k++) box(ruko, 0.34, 0.14 + rnd() * 0.08, 0.32, std([0xf4f1e8, 0xcfe0f0, 0xf7d9c4, 0xe4eedd][(i + k) % 4], { rough: 0.95 }), x - 0.4 + k * 0.4, Y0 + y + 0.1, -D / 2 + 0.5, false); });
    });
    box(ruko, 1.4, 0.9, 0.55, std(0xb88a56, { rough: 0.55 }), 1.4, Y0 + 0.45, -2.6);
    box(ruko, 0.35, 0.22, 0.04, std(0x20262b, { rough: 0.3 }), 1.3, Y0 + 1.0, -2.6, false);
    [0x2d6fb5, 0xd2483b, 0x2d6fb5].forEach((c, i) => box(ruko, 0.55, 0.32, 0.4, std(c, { rough: 0.6 }), -2.0, Y0 + 0.16 + i * 0.32, -1.9, false));
    cyl(ruko, 0.02, 0.02, 1.9, steel, 1.9, Y0 + 0.95, -1.0, 8);
    cyl(ruko, 0.02, 0.02, 1.9, steel, 0.5, Y0 + 0.95, -1.0, 8);
    box(ruko, 1.4, 0.03, 0.03, steel, 1.2, Y0 + 1.82, -1.0, false);
    [0.4, 0.62, 0.84, 1.06, 1.28, 1.5, 1.72].forEach((x, i) => box(ruko, 0.14, 0.78, 0.04, std([0x6a9bd0, 0xe3e0d6, 0xd97b6c, 0x7fb08e, 0xf1c969, 0xdadfe6, 0x5b7fa6][i], { rough: 0.95 }), x, Y0 + 1.4, -1.0, false));
    [-0.8, 0.5, 1.8].forEach((x, i) => cyl(ruko, 0.13, 0.13, 0.9, std([0xd97b6c, 0x6a9bd0, 0xf1c969][i], { rough: 0.95 }), x, Y1 + 0.5, -D / 2 + 0.55, 12));
    box(ruko, 2.4, 0.05, 0.5, shelfM, 0.5, Y1 + 0.9, -D / 2 + 0.55, false);
    box(ruko, 1.2, 0.85, 0.5, std(0xc9c3b4, { rough: 0.8 }), -1.7, Y1 + 0.43, -D / 2 + 0.55);

    /* atap: panel surya dengan rangka, inverter, toren air, parabola */
    const roofTop = H + 0.23;
    const panels = new THREE.Group();
    ruko.add(panels);
    const panelMeshes: { g: THREE.Group; m: THREE.MeshStandardMaterial[] }[] = [];
    const cellMat = new THREE.MeshStandardMaterial({ map: texSolar, roughness: 0.18, metalness: 0.45, envMapIntensity: 1.2, transparent: true });
    const frameMat = new THREE.MeshStandardMaterial({ color: 0xc4c9ce, roughness: 0.35, metalness: 0.85, transparent: true });
    for (let r = 0; r < 2; r++) for (let c = 0; c < 4; c++) {
      const g = new THREE.Group();
      g.position.set(-1.9 + c * 1.27, roofTop + 0.32, 1.9 - r * 2.2);
      g.rotation.x = -0.2;
      const pm = cellMat.clone();
      const fm = frameMat.clone();
      box(g, 1.2, 0.04, 1.7, fm, 0, 0, 0);
      add(g, bx(1.12, 0.012, 1.62), pm, 0, 0.026, 0, false);
      [-0.5, 0.5].forEach((z) => box(g, 0.04, 0.34, 0.04, std(0x7a8086, { rough: 0.5, metal: 0.7 }), 0.0, -0.17, z * 0.9, false));
      g.visible = false;
      panels.add(g);
      panelMeshes.push({ g, m: [pm, fm] });
    }
    const inverter = new THREE.Group();
    inverter.position.set(2.0, roofTop + 0.5, 3.0);
    ruko.add(inverter);
    box(inverter, 0.5, 0.42, 0.18, std(0xf0f0ec, { rough: 0.4 }), 0, 0, 0);
    box(inverter, 0.06, 0.06, 0.01, new THREE.MeshStandardMaterial({ color: 0x222222, emissive: 0x2fbf71, emissiveIntensity: 1 }), 0.12, 0.1, 0.1, false);
    box(inverter, 0.1, 0.9, 0.1, std(0x7a8086, { rough: 0.6 }), -0.25, -0.2, 0, false);
    const toren = new THREE.Group();
    toren.position.set(-1.9, roofTop, -2.8);
    ruko.add(toren);
    box(toren, 1.0, 0.7, 1.0, std(0x9aa0a6, { rough: 0.5, metal: 0.6 }), 0, 0.35, 0);
    cyl(toren, 0.45, 0.45, 1.1, std(0x2f6fb0, { rough: 0.45 }), 0, 1.25, 0, 24);
    add(toren, new THREE.SphereGeometry(0.45, 24, 10, 0, Math.PI * 2, 0, Math.PI / 2), std(0x2f6fb0, { rough: 0.45 }), 0, 1.8, 0);
    const dish = add(ruko, new THREE.SphereGeometry(0.3, 18, 8, 0, Math.PI * 2, 0, Math.PI / 2.2), std(0xe6e8ea, { rough: 0.4, metal: 0.4 }), 2.0, roofTop + 1.0, -2.4);
    dish.rotation.x = -1.0; dish.rotation.z = 0.2; (dish.material as THREE.MeshStandardMaterial).side = THREE.DoubleSide;
    cyl(ruko, 0.02, 0.02, 0.8, steel, 2.0, roofTop + 0.5, -2.4, 6);

    /* ── ruko tetangga: tertutup, dengan gaya masing-masing ── */
    function neighbour(cx: number, o: { c: number; sign: string; bg: string; fg: string; extra?: number; ac?: boolean; tank?: number }) {
      const g = new THREE.Group();
      g.position.set(cx, 0, 0);
      world.add(g);
      const ex = o.extra ?? 0, h2 = H + ex;
      box(g, W, h2, D, plaster(o.c, W, h2), 0, h2 / 2, 0);
      box(g, W + 0.3, 0.3, D + 0.3, slabM, 0, h2 + 0.02, 0);
      [-1, 1].forEach((s) => box(g, 0.2, 0.95, D + 0.3, plaster(o.c, D, 1), s * (W / 2 + 0.02), h2 + 0.5, 0));
      box(g, W + 0.3, 1.0, 0.2, plaster(o.c, W, 1), 0, h2 + 0.5, D / 2 + 0.03);
      box(g, W - 1.0, FH - 0.7, 0.1, std(0xb8bec3, { map: texShutter, rep: [10, 3], key: 'shd', rough: 0.45, metal: 0.6 }), 0, (FH - 0.7) / 2 + 0.1, D / 2 - 0.02);
      [-1, 1].forEach((s) => box(g, 0.5, FH, 0.28, plaster(o.c, 0.5, FH), s * (W / 2 - 0.25), FH / 2, D / 2 - 0.12));
      box(g, W, 0.58, 0.28, plaster(o.c, W, 0.6), 0, FH - 0.29, D / 2 - 0.12);
      box(g, W, FH + ex, 0.28, plaster(o.c, W, FH), 0, FH + (FH + ex) / 2, D / 2 - 0.12);
      const ww = (W - 1.6) / 2;
      [-1, 1].forEach((s) => {
        const wx = s * (ww / 2 + 0.2);
        box(g, ww, 1.7, 0.04, std(0x2b3440, { rough: 0.5 }), wx, FH + 1.9, D / 2 + 0.03, false);
        box(g, ww - 0.1, 1.6, 0.02, glassMat, wx, FH + 1.9, D / 2 + 0.06, false).renderOrder = 5;
        box(g, ww + 0.14, 0.06, 0.1, alu, wx, FH + 2.78, D / 2 + 0.06, false);
        box(g, ww + 0.14, 0.06, 0.1, alu, wx, FH + 1.05, D / 2 + 0.06, false);
        box(g, ww + 0.14, 0.14, 0.2, plaster(o.c, 1, 0.2), wx, FH + 2.9, D / 2 + 0.1, false);
        box(g, 0.04, 1.7, 0.1, alu, wx, FH + 1.9, D / 2 + 0.07, false);
      });
      const sg = new THREE.Mesh(new THREE.PlaneGeometry(W - 0.6, (W - 0.6) * 0.19), new THREE.MeshStandardMaterial({ map: signTexture(o.sign, o.bg, o.fg), roughness: 0.55 }));
      sg.position.set(0, h2 + 0.56, D / 2 + 0.15);
      g.add(sg);
      if (o.ac) { box(g, 0.8, 0.55, 0.3, std(0xe3e5e6, { rough: 0.5 }), W / 2 - 1.0, FH + 0.55, D / 2 + 0.3); const f = cyl(g, 0.2, 0.2, 0.02, std(0x333b41, { rough: 0.5 }), W / 2 - 1.0, FH + 0.55, D / 2 + 0.46, 16); f.rotation.x = Math.PI / 2; }
      if (o.tank) { cyl(g, 0.45, 0.45, 1.1, std(o.tank, { rough: 0.45 }), 1.2, h2 + 1.3, -1.8, 24); box(g, 1, 0.7, 1, std(0x9aa0a6, { rough: 0.5, metal: 0.6 }), 1.2, h2 + 0.45, -1.8); }
    }
    neighbour(-W, { c: 0xdfe6d2, sign: 'TOKO KELONTONG', bg: '#c23b2e', fg: '#ffffff', ac: true, tank: 0xd96a1f });
    neighbour(W, { c: 0xe8d4c0, sign: 'KONVEKSI JAYA', bg: '#233a66', fg: '#f4e7c0', tank: 0x2f6fb0 });
    neighbour(-2 * W, { c: 0xd8dde6, sign: 'APOTEK SEHAT', bg: '#2e7d52', fg: '#ffffff', extra: 0.6 });
    neighbour(2 * W, { c: 0xe6e0cf, sign: 'BENGKEL MOTOR', bg: '#e0a21a', fg: '#222222', ac: true });

    /* tiang listrik beton dengan trafo, kabel melendut dan sambungan ke meteran */
    function pole(x: number, z: number, withTransformer = false) {
      const g = new THREE.Group();
      g.position.set(x, 0, z);
      world.add(g);
      cyl(g, 0.1, 0.16, 8.2, std(0xaeaaa0, { rough: 0.9 }), 0, 4.1, 0, 12);
      box(g, 2.2, 0.1, 0.12, std(0x5a5a58, { rough: 0.7, metal: 0.4 }), 0, 7.7, 0);
      box(g, 1.6, 0.1, 0.12, std(0x5a5a58, { rough: 0.7, metal: 0.4 }), 0, 7.2, 0);
      [-0.9, -0.3, 0.3, 0.9].forEach((dx) => cyl(g, 0.04, 0.04, 0.14, std(0xe9e4d6, { rough: 0.4 }), dx, 7.82, 0, 8));
      if (withTransformer) cyl(g, 0.3, 0.3, 0.85, std(0x8a9094, { rough: 0.5, metal: 0.6 }), 0.55, 6.3, 0.18, 18);
    }
    pole(4.2, D / 2 + 1.5, true); pole(-14, D / 2 + 1.5); pole(22, D / 2 + 1.5);
    const wireMat = new THREE.MeshStandardMaterial({ color: 0x1b1d20, roughness: 0.6 });
    function wire(a: THREE.Vector3, b: THREE.Vector3, sag: number, r = 0.014) {
      const mid = a.clone().lerp(b, 0.5); mid.y -= sag;
      const c = new THREE.QuadraticBezierCurve3(a, mid, b);
      const t = new THREE.Mesh(new THREE.TubeGeometry(c, 24, r, 5, false), wireMat);
      disposables.push(t.geometry);
      world.add(t);
    }
    [-0.9, -0.3, 0.3, 0.9].forEach((dx) => {
      wire(new THREE.Vector3(4.2 + dx, 7.85, D / 2 + 1.5), new THREE.Vector3(-14 + dx, 7.85, D / 2 + 1.5), 0.7);
      wire(new THREE.Vector3(4.2 + dx, 7.85, D / 2 + 1.5), new THREE.Vector3(22 + dx, 7.85, D / 2 + 1.5), 0.9);
    });
    const meterPos = new THREE.Vector3(W / 2 - 0.25, 2.0, D / 2 + 0.14);
    const gridCurve = new THREE.CatmullRomCurve3([new THREE.Vector3(4.2, 7.3, D / 2 + 1.5), new THREE.Vector3(3.6, 4.9, D / 2 + 1.2), new THREE.Vector3(3.0, 3.1, D / 2 + 0.6), meterPos]);
    const solarCurve = new THREE.CatmullRomCurve3([new THREE.Vector3(2.0, roofTop + 0.45, 3.0), new THREE.Vector3(W / 2 - 0.25, H + 0.1, D / 2 + 0.5), new THREE.Vector3(W / 2 - 0.2, H - 1.2, D / 2 + 0.2), new THREE.Vector3(W / 2 - 0.25, 3.0, D / 2 + 0.17), meterPos]);
    const condMat = std(0xe4e4de, { rough: 0.5 });
    const tubeOf = (c: THREE.Curve<THREE.Vector3>, r: number, m: THREE.Material) => { const t = new THREE.Mesh(new THREE.TubeGeometry(c, 40, r, 6, false), m); t.castShadow = true; disposables.push(t.geometry); world.add(t); };
    tubeOf(gridCurve, 0.022, wireMat);
    tubeOf(solarCurve, 0.03, condMat);

    interface Flow { curve: THREE.Curve<THREE.Vector3>; n: number; speed: number; kind: 'grid' | 'solar' }
    const flows: Flow[] = [{ curve: gridCurve, n: 22, speed: 0.3, kind: 'grid' }, { curve: solarCurve, n: 22, speed: 0.3, kind: 'solar' }];
    const TOTAL = flows.reduce((s, f) => s + f.n, 0);
    const fPos = new Float32Array(TOTAL * 3), fCol = new Float32Array(TOTAL * 3);
    const fGeo = new THREE.BufferGeometry();
    fGeo.setAttribute('position', new THREE.BufferAttribute(fPos, 3));
    fGeo.setAttribute('color', new THREE.BufferAttribute(fCol, 3));
    const dotTex = canvasTex(32, 32, (x) => {
      const g = x.createRadialGradient(16, 16, 0, 16, 16, 16);
      g.addColorStop(0, 'rgba(255,255,255,1)'); g.addColorStop(0.45, 'rgba(255,255,255,.85)'); g.addColorStop(1, 'rgba(255,255,255,0)');
      x.fillStyle = g; x.fillRect(0, 0, 32, 32);
    }, false);
    const fMat = new THREE.PointsMaterial({ size: 7 * DPR, map: dotTex, vertexColors: true, transparent: true, depthWrite: false, sizeAttenuation: false, fog: false });
    const flowPts = new THREE.Points(fGeo, fMat);
    flowPts.frustumCulled = false;
    flowPts.renderOrder = 10;
    scene.add(flowPts);
    const AMBER = new THREE.Color(0xffa23a), GREEN = new THREE.Color(0x45f09a);
    const tmpV = new THREE.Vector3();

    /* ── lapisan tengah: rumah dengan atap genteng di belakang deretan ruko ── */
    function house(x: number, z: number, w: number, d: number, h: number, c: number) {
      const g = new THREE.Group();
      g.position.set(x, 0, z);
      midL.add(g);
      box(g, w, h + 10, d, plaster(c, w, h), 0, h / 2 - 5, 0);
      const rh = 1.5 + w * 0.12;
      const shape = new THREE.Shape(); shape.moveTo(-w / 2 - 0.4, 0); shape.lineTo(w / 2 + 0.4, 0); shape.lineTo(0, rh); shape.closePath();
      const geo = new THREE.ExtrudeGeometry(shape, { depth: d + 0.8, bevelEnabled: false }); geo.translate(0, 0, -(d + 0.8) / 2); disposables.push(geo);
      add(g, geo, std(0xc2643a, { map: texRoof, rep: [3, 2], key: 'rf', rough: 0.85 }), 0, h, 0);
      box(g, 1.0, 1.3, 0.05, std(0x39485a, { rough: 0.3 }), -w * 0.18, h * 0.45, d / 2 + 0.03, false);
      box(g, 1.0, 1.3, 0.05, std(0x39485a, { rough: 0.3 }), w * 0.18, h * 0.45, d / 2 + 0.03, false);
    }
    const hc = [0xe9dfc9, 0xdcd6c6, 0xe5d2bd, 0xd9e0d0];
    for (let i = -6; i <= 6; i++) house(i * 8.2 + (rnd() - 0.5) * 2, -16 - rnd() * 3, 5 + rnd() * 2.5, 6, 3.2 + rnd() * 1.6, hc[(i + 6) % 4]);
    for (let i = 0; i < 14; i++) {
      const g = new THREE.Group(); g.position.set(-52 + i * 8 + rnd() * 3, 0, -11 - rnd() * 2); midL.add(g);
      cyl(g, 0.18, 0.26, 2.4, std(0x6d5538, { rough: 0.95 }), 0, 1.2, 0, 8);
      const fm = std([0x4f8a47, 0x3f7a3f, 0x5a9650][i % 3], { rough: 0.9 });
      [[0, 3.6, 0, 1.7], [0.9, 3.0, 0.3, 1.2], [-0.9, 3.1, -0.2, 1.3]].forEach(([px, py, pz, r]) => { const b = add(g, new THREE.IcosahedronGeometry(r, 1), fm, px, py, pz); disposables.push(b.geometry); });
    }

    /* ── skyline jauh: gedung bertingkat dengan tekstur jendela, hanya siluet berkabut ── */
    const farMats: THREE.MeshStandardMaterial[] = [];
    for (let i = -12; i <= 12; i++) {
      const w = 5 + rnd() * 4, h = 14 + rnd() * 22, d = 5;
      const mp = texWindows.clone(); mp.needsUpdate = true; mp.repeat.set(w / 8, h / 16);
      const me = texWindowsLit.clone(); me.needsUpdate = true; me.repeat.copy(mp.repeat);
      disposables.push(mp, me);
      const m = new THREE.MeshStandardMaterial({ color: 0xb4bcc8, map: mp, emissive: 0xffd9a0, emissiveMap: me, emissiveIntensity: 0, roughness: 0.9 });
      const b = new THREE.Mesh(bx(w, h + 20, d), m);
      b.position.set(i * 9 + rnd() * 3, h / 2 - 10, -52 - rnd() * 10);
      farL.add(b);
      farMats.push(m);
    }

    /* pohon pinggir jalan di seberang, muncul di akhir */
    const trees: { g: THREE.Group; d: number }[] = [];
    [-9, -3, 5, 11].forEach((x, i) => {
      const g = new THREE.Group();
      g.position.set(x, 0, D / 2 + 10.2);
      cyl(g, 0.12, 0.2, 2.2, std(0x6d5538, { rough: 0.95 }), 0, 1.1, 0, 8);
      const fm = std([0x4f8a47, 0x5a9650, 0x3f7a3f][i % 3], { rough: 0.9 });
      [[0, 2.9, 0, 1.1], [0.6, 2.4, 0.2, 0.8], [-0.6, 2.5, -0.2, 0.85]].forEach(([px, py, pz, r]) => { const b = add(g, new THREE.IcosahedronGeometry(r, 1), fm, px, py, pz); disposables.push(b.geometry); });
      g.scale.setScalar(0.001);
      world.add(g);
      trees.push({ g, d: i * 0.012 });
    });
    const bulbMats: THREE.MeshStandardMaterial[] = [];
    [-9, 9.5, 22].forEach((x) => {
      const g = new THREE.Group(); g.position.set(x, 0, D / 2 + 2.45); world.add(g);
      cyl(g, 0.05, 0.07, 4.4, std(0x2a2d30, { rough: 0.5, metal: 0.5 }), 0, 2.2, 0, 8);
      box(g, 0.9, 0.05, 0.05, std(0x2a2d30, { rough: 0.5, metal: 0.5 }), 0.35, 4.35, 0, false);
      const bm = new THREE.MeshStandardMaterial({ color: 0xfff1cf, emissive: 0xffc46b, emissiveIntensity: 0 });
      box(g, 0.3, 0.08, 0.14, bm, 0.7, 4.3, 0, false);
      bulbMats.push(bm);
    });

    /* ── kamera dan resize ── */
    const cam = { zoom: 1, tx: 0, ty: 3.6, tz: 0.5, az: 30, el: 25 };
    function sampleKeys(p: number) {
      let i = 0;
      while (i < CAM_KEYS.length - 2 && p > CAM_KEYS[i + 1].p) i++;
      const a = CAM_KEYS[i], b = CAM_KEYS[i + 1];
      const u = smooth(0, 1, clamp01((p - a.p) / (b.p - a.p)));
      cam.zoom = lerp(a.zoom, b.zoom, u);
      cam.az = lerp(a.az, b.az, u);
      cam.el = lerp(a.el, b.el, u);
      cam.tx = lerp(a.t[0], b.t[0], u); cam.ty = lerp(a.t[1], b.t[1], u); cam.tz = lerp(a.t[2], b.t[2], u);
    }
    let viewW = 25, viewH = 14, aspect = 1.78, cw = 1000, chh = 600;
    function resize() {
      cw = sticky.clientWidth; chh = sticky.clientHeight;
      if (!cw || !chh) return;
      renderer.setSize(cw, chh, false);
      aspect = cw / chh;
      viewW = aspect >= 1 ? 14 * aspect : 13;
      viewH = viewW / aspect;
    }
    const ro = new ResizeObserver(resize);
    ro.observe(sticky);
    resize();

    const ptr = { x: 0, y: 0, sx: 0, sy: 0 };
    const onPtr = (e: PointerEvent) => {
      if (e.pointerType === 'touch') return;
      ptr.x = (e.clientX / window.innerWidth) * 2 - 1;
      ptr.y = (e.clientY / window.innerHeight) * 2 - 1;
    };
    window.addEventListener('pointermove', onPtr, { passive: true });

    let target = 0, pSm = 0;
    const readScroll = () => {
      const r = track.getBoundingClientRect();
      const total = r.height - window.innerHeight;
      target = total <= 0 ? 0 : clamp01(-r.top / total);
    };
    window.addEventListener('scroll', readScroll, { passive: true });
    window.addEventListener('resize', readScroll);
    readScroll();
    pSm = target;

    /* ── referensi DOM ── */
    const copies = qa('.st-copy');
    const railEls = qa('.st-rail li');
    const clouds = qa('.st-cloud');
    const tags = qa('.st-tag');
    const skyEl = q('.st-sky'), starsEl = q('.st-stars'), sunOrb = q('.st-sun'), moonOrb = q('.st-moon'), hint = q('.st-hint'), scrim = q('.st-scrim');
    const rHour = q('[data-r=hour]'), rLoad = q('[data-r=load]'), rPv = q('[data-r=pv]'), rGrid = q('[data-r=grid]'), rBar = q('[data-r=bar]'), rSelf = q('[data-r=self]');
    const cA = new THREE.Color(), cB = new THREE.Color(), cT = new THREE.Color(), cI = new THREE.Color();
    const inkDark = new THREE.Color(0x14281a), inkLight = new THREE.Color(0xf1f7f2), mutDark = new THREE.Color(0x3f5a46), mutLight = new THREE.Color(0xc4d4ca);
    let lastRail = -1;
    const fmt = (n: number, d = 1) => n.toFixed(d).replace('.', ',');
    const projV = new THREE.Vector3();

    let raf = 0, last = performance.now(), time = 0, visible = true;
    const io = new IntersectionObserver((e) => { visible = e[0].isIntersecting; }, { threshold: 0 });
    io.observe(track);

    function frame(now: number) {
      raf = requestAnimationFrame(frame);
      const dt = Math.min(0.05, Math.max(0.001, (now - last) / 1000));
      last = now;
      if (!visible || document.hidden) return;
      time += dt;
      pSm = reduced ? target : pSm + (target - pSm) * (1 - Math.exp(-dt * 5.5));
      if (Math.abs(target - pSm) < 0.00015) pSm = target;
      const p = pSm;
      ptr.sx += (ptr.x - ptr.sx) * Math.min(1, dt * 3);
      ptr.sy += (ptr.y - ptr.sy) * Math.min(1, dt * 3);

      /* kamera */
      sampleKeys(p);
      const az = ((cam.az + (reduced ? 0 : ptr.sx * 3)) * Math.PI) / 180;
      const el = ((cam.el - (reduced ? 0 : ptr.sy * 1.2)) * Math.PI) / 180;
      const d = 90;
      camera.position.set(cam.tx + Math.sin(az) * Math.cos(el) * d, cam.ty + Math.sin(el) * d, cam.tz + Math.cos(az) * Math.cos(el) * d);
      const hw = viewW / 2, hh = viewH / 2;
      const sx = aspect > 1.15 ? viewW * 0.14 : 0, sy = aspect <= 1.15 ? viewH * 0.17 : 0;
      camera.left = -hw - sx; camera.right = hw - sx; camera.top = hh - sy; camera.bottom = -hh - sy;
      camera.zoom = cam.zoom * lerp(0.5, 1, smooth(0.5, 1.2, aspect));
      camera.updateProjectionMatrix();
      camera.lookAt(cam.tx, cam.ty, cam.tz);
      camera.updateMatrixWorld();

      /* parallax: lapisan bergeser mengikuti target kamera dengan faktor berbeda, plus dorongan pointer */
      layers.forEach(([g, f]) => g.position.set(cam.tx * f + ptr.sx * -f * 0.6, cam.ty * f * 0.7, cam.tz * f));

      /* jam, langit, cahaya */
      const hr = hourAt(p);
      const e = Math.sin((Math.PI * (hr - 6)) / 12);
      const dayAmt = smooth(-0.25, 0.2, e), night = 1 - smooth(-0.25, 0.12, e);
      const t01 = clamp01((hr - 6) / 12);
      const th = ((45 + (t01 - 0.5) * 170) * Math.PI) / 180, sel = (Math.max(e, 0.06) * 62 * Math.PI) / 180;
      sun.position.set(Math.sin(th) * Math.cos(sel) * 60, 2 + Math.sin(sel) * 60, Math.cos(th) * Math.cos(sel) * 60);
      sun.intensity = 3.4 * dayAmt + 0.05;
      sun.color.set(0xff9d5c).lerp(cT.set(0xfff1dc), smooth(0.05, 0.5, e));
      moon.intensity = 0.55 * night;
      hemi.intensity = 0.35 + 0.5 * dayAmt;
      hemi.color.set(0x6a82c0).lerp(cT.set(0xffffff), dayAmt);
      hemi.groundColor.set(0x1c2540).lerp(cT.set(0xc9c3b4), dayAmt);
      scene.environmentIntensity = 0.08 + 0.42 * dayAmt;
      renderer.toneMappingExposure = 0.9 + 0.2 * dayAmt;
      roomA.intensity = 5 * night + 0.9; roomB.intensity = roomA.intensity;
      tubeMat.emissiveIntensity = 0.3 + 1.2 * night;
      signMat.emissiveIntensity = 0.55 * night;
      farMats.forEach((m) => { m.emissiveIntensity = 1.1 * night; });
      bulbMats.forEach((m) => { m.emissiveIntensity = 2 * night; });
      const warm = (1 - smooth(0.08, 0.55, e)) * (1 - night);
      cA.set(0x8ecaf1).lerp(cT.set(0xf2b9a1), warm).lerp(cT.set(0x0b1630), night);
      cB.set(0xdcf0fb).lerp(cT.set(0xffe6c8), warm).lerp(cT.set(0x233559), night);
      skyEl.style.background = `linear-gradient(180deg, #${cA.getHexString()}, #${cB.getHexString()})`;
      (scene.fog as THREE.Fog).color.copy(cB);
      starsEl.style.opacity = (night * night * 0.9).toFixed(3);
      const arc = (t: number) => clamp01((t + 0.08) / 0.1) * (1 - clamp01((t - 0.92) / 0.1));
      const tm = ((((hr - 18) % 24) + 24) % 24) / 12;
      sunOrb.style.left = lerp(8, 92, t01) + '%'; sunOrb.style.top = 76 - Math.sin(Math.PI * t01) * 52 + '%'; sunOrb.style.opacity = (arc(t01) * (1 - 0.3 * warm)).toFixed(3);
      moonOrb.style.left = lerp(10, 90, clamp01(tm)) + '%'; moonOrb.style.top = 70 - Math.sin(Math.PI * clamp01(tm)) * 46 + '%'; moonOrb.style.opacity = (arc(clamp01(tm)) * 0.95).toFixed(3);

      /* warna teks mengikuti langit */
      const lum = 0.5 * (0.299 * cA.r + 0.587 * cA.g + 0.114 * cA.b + 0.299 * cB.r + 0.587 * cB.g + 0.114 * cB.b);
      const kd = smooth(0.42, 0.55, lum);
      sticky.style.setProperty('--ink', '#' + cI.copy(inkLight).lerp(inkDark, kd).getHexString());
      sticky.style.setProperty('--ink-muted', '#' + cI.copy(mutLight).lerp(mutDark, kd).getHexString());
      sticky.style.setProperty('--btn-ink', kd > 0.5 ? '#f1f7f2' : '#14281a');
      sticky.style.setProperty('--accent', kd > 0.5 ? '#1e8e4f' : '#6fe39a');
      cI.copy(cB).lerp(cT.set(kd > 0.5 ? 0xffffff : 0x0a1426), 0.3);
      sticky.style.setProperty('--scrim', `${Math.round(cI.r * 255)}, ${Math.round(cI.g * 255)}, ${Math.round(cI.b * 255)}`);

      clouds.forEach((c, i) => {
        const f = [0.25, 0.5, 0.8, 0.35][i % 4];
        c.style.transform = `translate3d(${(-p * 520 * f + ptr.sx * -18 * f + ((time * (6 + i * 3)) % 1400)).toFixed(1)}px,${(-p * 70 * f).toFixed(1)}px,0)`;
      });

      /* mesin dan angka listrik */
      let load = BASE_KW;
      machines.forEach((m) => {
        m.act = Math.max(win(p, m.def.before[0], m.def.before[1]), win(p, m.def.after[0], m.def.after[1]));
        load += m.def.kw * m.act;
      });
      const panelOn = smooth(0.55, 0.72, p);
      const pv = PV_KWP * Math.max(0, e) * 0.92 * panelOn;
      const grid = Math.max(0, load - pv);
      const selfShare = load > 0 ? Math.min(pv, load) / load : 0;
      const nilm = smooth(0.27, 0.34, p) * (1 - smooth(0.93, 0.98, p));

      machines.forEach((m, i) => {
        if (m.spin) m.spin.rotation.z -= dt * 6 * m.act * (reduced ? 0 : 1);
        if (m.needle) m.needle.position.y = 0.84 + (reduced ? 0 : Math.abs(Math.sin(time * 26)) * 0.06 * m.act);
        m.puffs.forEach((pf, k) => {
          const ph = (time * 0.6 + k / 3) % 1;
          pf.position.y = 1.3 + ph * 0.8;
          pf.scale.setScalar(0.6 + ph * 1.3);
          (pf.material as THREE.MeshBasicMaterial).opacity = m.act * (1 - ph) * 0.4;
        });
        const kw = m.def.kw * m.act;
        m.lamp.emissiveIntensity = 0.2 + m.act * 1.5;
        m.lamp.emissive.set(kw > 1 && pv < load ? 0xef4444 : 0x2fbf71);
        /* label HTML yang menempel pada mesin */
        const tag = tags[i];
        projV.copy(m.top); projV.y += 0.12;
        projV.project(camera);
        const px = (projV.x * 0.5 + 0.5) * cw, py = (-projV.y * 0.5 + 0.5) * chh;
        const onScreen = projV.z < 1 && px > 0 && px < cw && py > 0 && py < chh;
        tag.style.opacity = onScreen ? nilm.toFixed(2) : '0';
        tag.style.transform = `translate3d(${px.toFixed(1)}px,${(py + TAG_DY[i]).toFixed(1)}px,0) translate(-50%,-100%)`;
        (tag.querySelector('b') as HTMLElement).textContent = fmt(kw, 2) + ' kW';
        (tag.querySelector('i') as HTMLElement).style.background = kw > 1 && pv < load ? '#ef4444' : kw > 0.05 ? '#2fbf71' : '#9ca3af';
      });

      /* aliran listrik di kabel */
      let idx = 0;
      flows.forEach((f) => {
        const I = f.kind === 'grid' ? clamp01(grid / 5) : clamp01(pv / 3.5);
        const count = Math.ceil(f.n * I - 1e-4);
        const col = f.kind === 'grid' ? AMBER : GREEN;
        for (let k = 0; k < f.n; k++) {
          const i3 = (idx + k) * 3;
          if (k < count) {
            const t = (time * f.speed + k / f.n) % 1;
            f.curve.getPointAt(t, tmpV);
            fPos[i3] = tmpV.x; fPos[i3 + 1] = tmpV.y; fPos[i3 + 2] = tmpV.z;
            fCol[i3] = col.r; fCol[i3 + 1] = col.g; fCol[i3 + 2] = col.b;
          } else fPos[i3 + 1] = -999;
        }
        idx += f.n;
      });
      fGeo.attributes.position.needsUpdate = true;
      fGeo.attributes.color.needsUpdate = true;

      /* meteran: merah saat PLN yang menanggung, hijau saat surya */
      const ms = smooth(0.2, 0.8, 1 - (load > 0 ? grid / load : 1)) * smooth(0.5, 0.62, p);
      meterMat.emissive.set(0xd1453a).lerp(cT.set(0x2fbf71), ms);
      meterMat.emissiveIntensity = 0.9 + Math.sin(time * 3) * 0.1;
      sensor.scale.setScalar(Math.max(0.001, backOut(smooth(0.14, 0.2, p))));
      ledMat.emissiveIntensity = 0.4 + (Math.sin(time * 8) > 0.6 ? 1.4 : 0.3);

      /* panel surya dipasang satu per satu, lalu pepohonan */
      const inst = smooth(0.54, 0.68, p);
      panelMeshes.forEach(({ g, m }, i) => {
        const u = clamp01(inst * 1.7 - i * 0.1);
        g.visible = u > 0.001;
        g.position.y = roofTop + 0.32 + (1 - u) * 0.9;
        m.forEach((mm) => { mm.opacity = u; });
      });
      trees.forEach((t) => t.g.scale.setScalar(Math.max(0.001, backOut((smooth(0.88, 0.97, p) - t.d * 5) / 0.8))));
      groundMat.color.copy(groundGrey).lerp(groundGreen, smooth(0.9, 1, p) * 0.5);

      /* blok teks: muncul per band scroll */
      let maxO = 0;
      copies.forEach((el2, i) => {
        const c = CHAPTERS[i], fade = 0.025;
        let o = 0;
        if (p >= c.a - fade && p <= c.b + fade) o = p < c.a ? (p - (c.a - fade)) / fade : p > c.b ? 1 - (p - c.b) / fade : 1;
        o = clamp01(o) < 0.01 ? 0 : clamp01(o);
        const mid = (c.a + c.b) / 2;
        el2.style.opacity = String(o);
        el2.style.visibility = o === 0 ? 'hidden' : 'visible';
        el2.style.pointerEvents = o > 0.5 ? 'auto' : 'none';
        el2.style.transform = `translate3d(0,${((1 - o) * 22 + (p - mid) * -90).toFixed(1)}px,0)`;
        if (o > maxO) maxO = o;
      });
      scrim.style.opacity = maxO.toFixed(2);
      hint.style.opacity = p > 0.02 ? '0' : '1';

      let cur = 0;
      CHAPTERS.forEach((c, i) => { if (p >= c.a - 0.02) cur = i; });
      if (cur !== lastRail) {
        lastRail = cur;
        railEls.forEach((el2, i) => { el2.className = (i < cur ? 'seen ' : '') + (i === cur ? 'now' : ''); });
      }

      const hh2 = Math.floor(hr), mm = Math.floor((hr - hh2) * 60);
      rHour.textContent = String(hh2).padStart(2, '0') + '.' + String(mm).padStart(2, '0');
      rLoad.textContent = fmt(load) + ' kW';
      rPv.textContent = fmt(pv) + ' kW';
      rGrid.textContent = fmt(grid) + ' kW';
      rSelf.textContent = Math.round(selfShare * 100) + '%';
      rBar.style.width = Math.round(selfShare * 100) + '%';

      renderer.render(scene, camera);
    }
    raf = requestAnimationFrame(frame);

    return () => {
      cancelAnimationFrame(raf);
      ro.disconnect();
      io.disconnect();
      window.removeEventListener('pointermove', onPtr);
      window.removeEventListener('scroll', readScroll);
      window.removeEventListener('resize', readScroll);
      scene.traverse((o) => { const m = o as THREE.Mesh; if (m.geometry) m.geometry.dispose(); });
      matCache.forEach((m) => m.dispose());
      disposables.forEach((x) => x.dispose());
      pmrem.dispose();
      renderer.dispose();
    };
  }, []);

  return (
    <div ref={trackRef} className="st-track">
      <div ref={stickyRef} className="st-sticky">
        <div className="st-sky">
          <div className="st-stars" />
          <div className="st-orb st-sun" />
          <div className="st-orb st-moon" />
          <div className="st-cloud" style={{ top: '12%', left: '-8%', width: 220 }} />
          <div className="st-cloud" style={{ top: '26%', left: '30%', width: 300, opacity: 0.8 }} />
          <div className="st-cloud" style={{ top: '8%', left: '58%', width: 180 }} />
          <div className="st-cloud" style={{ top: '34%', left: '78%', width: 260, opacity: 0.7 }} />
        </div>
        <canvas className="st-canvas" />
        <div className="st-scrim" />
        <div className="st-labels" aria-hidden="true">
          {MACHINES.map((m) => (
            <div className="st-tag" key={m.name}><i />{m.name}<b>0,00 kW</b></div>
          ))}
        </div>
        <div className="st-nogl" hidden>Browser kamu belum mendukung WebGL, jadi demo 3D tidak bisa tampil.</div>

        {CHAPTERS.map((c, i) => (
          <div className="st-copy" key={i}>
            <div className="st-kick">{c.kick}</div>
            {c.h ? <h1>{c.title}</h1> : <h2>{c.title}</h2>}
            <p>{c.body}</p>
            {c.cta && <a className="st-btn" href="#simulator-section">Hitung untuk usahamu</a>}
          </div>
        ))}

        <ol className="st-rail" aria-hidden="true">
          {CHAPTERS.map((c, i) => (
            <li key={i} className={i === 0 ? 'now' : ''}><span>{c.rail}</span><i /></li>
          ))}
        </ol>

        <dl className="st-readout" aria-label="Contoh pembacaan listrik, ilustrasi">
          <small><span>Contoh pembacaan</span><span data-r="hour">05.18</span></small>
          <dt>Beban toko</dt><dd data-r="load">0,3 kW</dd>
          <dt>Produksi surya</dt><dd data-r="pv">0,0 kW</dd>
          <dt>Dari PLN</dt><dd data-r="grid">0,3 kW</dd>
          <dt>Pakai surya</dt><dd data-r="self">0%</dd>
          <div className="st-bar"><i data-r="bar" /></div>
        </dl>
        <div className="st-hint">Gulir ↓</div>
      </div>
    </div>
  );
}
