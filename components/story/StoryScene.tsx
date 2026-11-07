'use client';

import { useEffect, useRef } from 'react';
import * as THREE from 'three';
import './story.css';

/* ─────────────────────────────────────────────────────────────────────────────
   Satu hari di Laundry Barokah.
   Scroll mengatur semuanya: kamera orthographic isometrik, jam (langit, matahari,
   bayangan), beban tiap mesin, produksi surya, dan aliran listrik. Parallax datang
   dari lapisan dunia yang mengikuti target kamera dengan faktor berbeda, ditambah
   lapisan awan CSS di balik canvas dan teks yang bergeser sendiri.
   ───────────────────────────────────────────────────────────────────────────── */

const CHAPTERS = [
  { a: 0, b: 0.11, kick: 'Sukoharjo · 05.30', h: 1, title: 'Satu hari di Laundry Barokah', body: 'Meteran sudah berputar, mesin belum menyala, tagihan sudah terasa. Scroll untuk ikut satu hari penuh bersama Bu Yanti.', rail: 'Meteran' },
  { a: 0.14, b: 0.26, kick: '01 Pasang', title: 'Satu sensor, tanpa bongkar instalasi', body: 'Cukup dijepit di kabel MCB. Arus dan tegangan seluruh toko terbaca dari satu titik ini.', rail: 'Sensor' },
  { a: 0.3, b: 0.5, kick: '02 Baca', title: 'Mesin mana yang paling boros?', body: 'NILM memisahkan sidik jari tiap mesin. Pengering dan setrika uap ternyata menyala bersamaan di pagi hari, tepat saat listrik PLN paling mahal.', rail: 'Mesin' },
  { a: 0.54, b: 0.66, kick: '03 Surya', title: 'Matahari naik, panel mulai bekerja', body: 'Panel di atap menghasilkan listrik gratis. Gunanya baru terasa kalau ada mesin yang menyala saat itu juga.', rail: 'Surya' },
  { a: 0.69, b: 0.86, kick: '04 Jadwal', title: 'Mesin bergeser ke jam terik', body: 'Agen PPO memindahkan beban yang fleksibel ke siang hari. Mesin cuci bergantian, pengering dan setrika menyusul saat produksi surya memuncak.', rail: 'Jadwal' },
  { a: 0.9, b: 1.01, kick: '05 Hasil', title: 'Meteran hijau, nota lebih ringan', body: 'Setiap angka bisa ditelusuri sampai ke satu mesin. Rapor kelayakan PLTS siap diajukan ke bank.', rail: 'Hasil', cta: true },
];

const CAM_KEYS = [
  { p: 0.0, zoom: 1.0, t: [0, 2.6, 0], az: 34, el: 27 },
  { p: 0.11, zoom: 1.05, t: [0, 2.6, 0], az: 36, el: 27 },
  { p: 0.2, zoom: 2.5, t: [3.6, 1.7, 0.5], az: 42, el: 25 },
  { p: 0.3, zoom: 2.2, t: [3.2, 1.7, 0.5], az: 40, el: 26 },
  { p: 0.38, zoom: 1.7, t: [-0.2, 1.0, -0.4], az: 30, el: 28 },
  { p: 0.5, zoom: 1.6, t: [0, 3.9, 0], az: 30, el: 28 },
  { p: 0.6, zoom: 1.85, t: [0.8, 5.9, -0.4], az: 38, el: 30 },
  { p: 0.76, zoom: 1.25, t: [0.5, 3.0, 0], az: 34, el: 28 },
  { p: 0.9, zoom: 1.0, t: [0, 2.6, 0], az: 30, el: 26 },
  { p: 1.0, zoom: 0.92, t: [0, 2.6, 0], az: 28, el: 25 },
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
const FH = 2.7;
const MACHINES: MachineDef[] = [
  { kind: 'washer', name: 'Mesin cuci 1', x: -2.6, floor: 0, z: -1.2, kw: 0.55, before: [0.3, 0.5], after: [0.6, 0.68] },
  { kind: 'washer', name: 'Mesin cuci 2', x: -1.4, floor: 0, z: -1.2, kw: 0.55, before: [0.31, 0.5], after: [0.66, 0.76] },
  { kind: 'washer', name: 'Mesin cuci 3', x: -0.2, floor: 0, z: -1.2, kw: 0.55, before: [0.32, 0.5], after: [0.72, 0.84] },
  { kind: 'dryer', name: 'Pengering', x: 1.1, floor: 0, z: -1.2, kw: 1.8, before: [0.34, 0.5], after: [0.62, 0.86] },
  { kind: 'ironer', name: 'Setrika uap', x: 2.5, floor: 0, z: -0.9, kw: 1.3, before: [0.36, 0.5], after: [0.64, 0.86] },
  { kind: 'sewing', name: 'Jahit 1', x: -2.4, floor: 1, z: -0.8, kw: 0.4, before: [0.34, 0.53], after: [0.62, 0.9] },
  { kind: 'sewing', name: 'Jahit 2', x: -0.5, floor: 1, z: -0.8, kw: 0.4, before: [0.34, 0.53], after: [0.64, 0.9] },
  { kind: 'sewing', name: 'Jahit 3', x: 1.4, floor: 1, z: -0.8, kw: 0.4, before: [0.35, 0.53], after: [0.66, 0.9] },
];
const BASE_KW = 0.3;
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
    renderer.shadowMap.type = THREE.PCFSoftShadowMap;

    const scene = new THREE.Scene();
    scene.fog = new THREE.Fog(0xffffff, 88, 150);
    const camera = new THREE.OrthographicCamera(-10, 10, 10, -10, 0.1, 400);
    const hemi = new THREE.HemisphereLight(0xffffff, 0xcfd6dc, 0.6);
    const sun = new THREE.DirectionalLight(0xffffff, 0.8);
    sun.castShadow = true;
    sun.shadow.mapSize.set(2048, 2048);
    sun.shadow.bias = -0.0006;
    sun.shadow.normalBias = 0.03;
    const sc = sun.shadow.camera;
    sc.left = -18; sc.right = 18; sc.top = 18; sc.bottom = -18; sc.near = 1; sc.far = 200;
    const moon = new THREE.DirectionalLight(0x8fb4ff, 0);
    moon.position.set(-10, 25, 30);
    const roomA = new THREE.PointLight(0xffc27a, 0, 12, 1.6);
    roomA.position.set(0, 2.2, 1.2);
    const roomB = new THREE.PointLight(0xffc27a, 0, 12, 1.6);
    roomB.position.set(0, FH + 2.2, 1.2);
    scene.add(hemi, sun, sun.target, moon, roomA, roomB);
    sun.target.position.set(0, 2, 0);

    /* ── helpers ── */
    const stdCache = new Map<string, THREE.MeshStandardMaterial>();
    const mat = (c: number, rough = 0.7) => {
      const k = c + '/' + rough;
      let m = stdCache.get(k);
      if (!m) { m = new THREE.MeshStandardMaterial({ color: c, roughness: rough }); stdCache.set(k, m); }
      return m;
    };
    const boxGeo = new Map<string, THREE.BoxGeometry>();
    const bx = (w: number, h: number, d: number) => {
      const k = [w, h, d].join('|');
      let g = boxGeo.get(k);
      if (!g) { g = new THREE.BoxGeometry(w, h, d); boxGeo.set(k, g); }
      return g;
    };
    const add = (parent: THREE.Object3D, geo: THREE.BufferGeometry, m: THREE.Material, x = 0, y = 0, z = 0, shadow = true) => {
      const o = new THREE.Mesh(geo, m);
      o.position.set(x, y, z);
      if (shadow) { o.castShadow = true; o.receiveShadow = true; }
      parent.add(o);
      return o;
    };
    const box = (parent: THREE.Object3D, w: number, h: number, d: number, m: THREE.Material, x = 0, y = 0, z = 0, shadow = true) => add(parent, bx(w, h, d), m, x, y, z, shadow);
    let seed = 7;
    const rnd = () => { seed = (seed * 16807) % 2147483647; return seed / 2147483647; };

    function label(text: string, w = 1.5) {
      const c = document.createElement('canvas');
      c.width = 256; c.height = 64;
      const x = c.getContext('2d')!;
      x.fillStyle = 'rgba(255,255,255,0.94)';
      x.beginPath(); x.roundRect(2, 8, 252, 48, 24); x.fill();
      x.fillStyle = '#1f2937'; x.font = '700 26px system-ui, sans-serif'; x.textAlign = 'center'; x.textBaseline = 'middle';
      x.fillText(text, 128, 33);
      const s = new THREE.Sprite(new THREE.SpriteMaterial({ map: new THREE.CanvasTexture(c), transparent: true, depthTest: false }));
      s.scale.set(w, w / 4, 1);
      s.renderOrder = 30;
      return s;
    }

    /* ── world layers: each follows the camera target by its own factor, which is the parallax ── */
    const world = new THREE.Group();            // factor 0: fixed in the world
    const midL = new THREE.Group();             // follows 0.5
    const farL = new THREE.Group();             // follows 0.88
    const frontL = new THREE.Group();           // follows -0.3 (moves faster than the stage)
    scene.add(world, midL, farL, frontL);
    const layers: [THREE.Group, number][] = [[midL, 0.5], [farL, 0.88], [frontL, -0.3]];

    /* ground, sidewalk, road */
    const groundMat = new THREE.MeshStandardMaterial({ color: 0xb4bab6, roughness: 0.95 });
    const groundGreen = new THREE.Color(0x8fcf9c), groundGrey = new THREE.Color(0xb4bab6);
    const ground = add(world, bx(150, 0.6, 150), groundMat, 0, -0.3, 0);
    ground.castShadow = false;
    box(world, 150, 0.1, 2.4, mat(0xd2d0c8, 0.9), 0, 0.03, 3.6, false);
    box(world, 150, 0.06, 5, mat(0x4a5058, 0.9), 0, 0.02, 7.8, false);
    for (let x = -60; x <= 60; x += 3.6) box(world, 1.6, 0.02, 0.16, mat(0xf2f2ee, 0.9), x, 0.06, 7.8, false);

    /* the ruko, cut away at the front */
    const W = 7.4, D = 4.6, H = FH * 2;
    const shell = mat(0xf1e6cf, 0.85), inner = mat(0xdff1e5, 0.9), slab = mat(0xc9bfa8, 0.85);
    const ruko = new THREE.Group();
    world.add(ruko);
    const upper = new THREE.Group();   // lifts away so the ground floor can be seen
    ruko.add(upper);
    box(ruko, W + 0.4, 0.22, D + 0.4, slab, 0, 0.0, 0);                      // ground slab
    box(ruko, W, H, 0.2, inner, 0, H / 2, -D / 2 + 0.1);                     // back wall
    box(ruko, 0.2, H, D, shell, -W / 2 + 0.1, H / 2, 0);                     // left wall
    box(ruko, 0.2, H, D, shell, W / 2 - 0.1, H / 2, 0);                      // right wall
    box(upper, W, 0.22, D, slab, 0, FH, 0);                                    // middle floor
    box(upper, W + 0.3, 0.26, D + 0.3, mat(0xb8ad96, 0.8), 0, H, 0);           // roof slab
    [-W / 2 + 0.1, W / 2 - 0.1].forEach((x) => box(ruko, 0.22, H, 0.22, shell, x, H / 2, D / 2 - 0.1));
    box(upper, W, 0.5, 0.22, shell, 0, FH - 0.25, D / 2 - 0.1);                // header floor 0
    box(upper, W, 0.5, 0.22, shell, 0, H - 0.25, D / 2 - 0.1);                 // header floor 1
    box(upper, W + 0.3, 0.12, 1.2, mat(0xff9e2c, 0.55), 0, FH - 0.55, D / 2 + 0.4); // awning
    // sign
    {
      const c = document.createElement('canvas'); c.width = 512; c.height = 96;
      const x = c.getContext('2d')!;
      x.fillStyle = '#1e8e4f'; x.fillRect(0, 0, 512, 96);
      x.fillStyle = '#fff'; x.font = '800 54px system-ui, sans-serif'; x.textAlign = 'center'; x.textBaseline = 'middle';
      x.fillText('LAUNDRY BAROKAH', 256, 52);
      const t = new THREE.CanvasTexture(c); t.anisotropy = 4;
      const s = new THREE.Mesh(new THREE.PlaneGeometry(3.4, 0.64), new THREE.MeshBasicMaterial({ map: t }));
      s.position.set(0, FH + 0.35, D / 2 + 0.03);
      upper.add(s);
    }
    // windows on the right wall + ceiling strip lights
    const fixtureMat = new THREE.MeshStandardMaterial({ color: 0xfff4d6, emissive: 0xffe3a0, emissiveIntensity: 0.2 });
    [0, 1].forEach((f) => box(upper, 3.2, 0.06, 0.3, fixtureMat, 0, FH * (f + 1) - 0.2, 0.2, false));
    const winMats: THREE.MeshStandardMaterial[] = [];
    const winFrame = mat(0xf6f1e6, 0.6);
    function addWindows(parent: THREE.Object3D, w: number, h: number, ox: number, oy: number, z: number, cols: number, rows: number, sx = 1.6, sy = 2.2, nightOnly = false) {
      for (let r = 0; r < rows; r++) for (let c = 0; c < cols; c++) {
        const m = new THREE.MeshStandardMaterial({ color: 0x8fb3cc, roughness: 0.2, emissive: 0xffbf70, emissiveIntensity: 0 });
        (m as THREE.MeshStandardMaterial & { th: number }).th = rnd();
        winMats.push(m);
        const g = new THREE.Group();
        g.position.set(ox + c * sx, oy + r * sy, z);
        g.add(new THREE.Mesh(bx(w + 0.14, h + 0.14, 0.05), winFrame));
        const gl = new THREE.Mesh(bx(w, h, 0.06), m); gl.position.z = 0.012;
        g.add(gl);
        parent.add(g);
        void nightOnly;
      }
    }

    /* MCB panel with meter light, mounted on the outside of the right wall */
    const panelG = new THREE.Group();
    panelG.position.set(W / 2 + 0.05, 1.5, 0.5);
    ruko.add(panelG);
    box(panelG, 0.22, 0.95, 0.7, mat(0x9aa3ad, 0.5), 0.11, 0, 0);
    box(panelG, 0.05, 0.62, 0.5, mat(0x1f2937, 0.4), 0.245, 0.05, 0, false);
    const meterMat = new THREE.MeshStandardMaterial({ color: 0x222222, emissive: 0xd1453a, emissiveIntensity: 1 });
    box(panelG, 0.06, 0.2, 0.34, meterMat, 0.28, 0.2, 0, false);
    [-0.15, 0, 0.15].forEach((z) => box(panelG, 0.05, 0.1, 0.07, mat(0xf2f2ee, 0.4), 0.28, -0.12, z, false));
    // sensor clip around the incoming wire
    const sensor = new THREE.Group();
    sensor.position.set(0.3, -0.55, 0);
    panelG.add(sensor);
    const clip = add(sensor, new THREE.TorusGeometry(0.17, 0.05, 10, 20), mat(0x2fbf71, 0.4), 0, 0, 0, false);
    clip.rotation.x = Math.PI / 2;
    box(sensor, 0.2, 0.16, 0.14, mat(0xfdfdfb, 0.4), 0.18, 0, 0, false);
    const ping = add(sensor, new THREE.TorusGeometry(0.2, 0.012, 6, 28), new THREE.MeshBasicMaterial({ color: 0x2fbf71, transparent: true, opacity: 0 }), 0, 0, 0, false);
    ping.rotation.x = Math.PI / 2;

    /* machines */
    interface Machine { def: MachineDef; g: THREE.Group; bar: THREE.Mesh; barG: THREE.Group; tag: THREE.Sprite; lamp: THREE.MeshStandardMaterial; spin?: THREE.Object3D; needle?: THREE.Object3D; puffs: THREE.Mesh[]; top: THREE.Vector3; act: number }
    const machines: Machine[] = MACHINES.map((def) => {
      const g = new THREE.Group();
      const y0 = def.floor === 0 ? 0.11 : FH + 0.11;
      g.position.set(def.x, y0, def.z);
      (def.floor === 1 ? upper : ruko).add(g);
      const lamp = new THREE.MeshStandardMaterial({ color: 0x333333, emissive: 0x2fbf71, emissiveIntensity: 0.15 });
      let spin: THREE.Object3D | undefined, needle: THREE.Object3D | undefined, topY = 1;
      const puffs: THREE.Mesh[] = [];
      if (def.kind === 'washer' || def.kind === 'dryer') {
        const dry = def.kind === 'dryer';
        const h = dry ? 1.5 : 1.05;
        topY = h;
        box(g, 0.95, h, 0.85, mat(dry ? 0xf6efe0 : 0xf3f5f6, 0.5), 0, h / 2, 0);
        const ring = add(g, new THREE.CylinderGeometry(0.34, 0.34, 0.08, 24), mat(0x9aa3ad, 0.4), 0, h * (dry ? 0.5 : 0.52), 0.43);
        ring.rotation.x = Math.PI / 2;
        const glass = add(g, new THREE.CylinderGeometry(0.27, 0.27, 0.06, 24), new THREE.MeshStandardMaterial({ color: dry ? 0xffb35c : 0x6cb4e4, roughness: 0.2, transparent: true, opacity: 0.85 }), 0, h * (dry ? 0.5 : 0.52), 0.47, false);
        glass.rotation.x = Math.PI / 2;
        spin = new THREE.Group();
        spin.position.set(0, h * (dry ? 0.5 : 0.52), 0.5);
        [0, 1, 2].forEach((i) => { const s = box(spin!, 0.34, 0.07, 0.02, mat(0xffffff, 0.5), 0, 0, 0, false); s.rotation.z = (i * Math.PI) / 3; });
        g.add(spin);
        add(g, new THREE.SphereGeometry(0.06, 10, 8), lamp, 0.34, h - 0.12, 0.43, false);
      } else if (def.kind === 'ironer') {
        topY = 1.05;
        box(g, 1.5, 0.12, 0.8, mat(0xdcd3c0, 0.6), 0, 0.82, 0);
        [-0.65, 0.65].forEach((x) => box(g, 0.08, 0.8, 0.08, mat(0x6b7280, 0.5), x, 0.4, 0));
        const arm = box(g, 1.3, 0.16, 0.34, mat(0xffffff, 0.5), 0, 1.0, -0.1);
        arm.rotation.z = 0.02;
        add(g, new THREE.SphereGeometry(0.06, 10, 8), lamp, 0.62, 1.0, 0.1, false);
        for (let i = 0; i < 3; i++) {
          const p = add(g, new THREE.SphereGeometry(0.1, 10, 8), new THREE.MeshBasicMaterial({ color: 0xffffff, transparent: true, opacity: 0 }), -0.3 + i * 0.3, 1.1, 0.1, false);
          puffs.push(p);
        }
      } else {
        topY = 0.95;
        box(g, 1.15, 0.08, 0.6, mat(0xc98a4b, 0.8), 0, 0.68, 0);
        [-0.5, 0.5].forEach((x) => box(g, 0.07, 0.64, 0.5, mat(0x6b7280, 0.5), x, 0.32, 0));
        box(g, 0.42, 0.28, 0.26, mat(0xf3f5f6, 0.5), 0, 0.86, -0.08);
        needle = box(g, 0.025, 0.2, 0.025, mat(0x6b7280, 0.3), 0.1, 0.78, 0.1, false);
        add(g, new THREE.SphereGeometry(0.05, 10, 8), lamp, -0.15, 1.02, -0.08, false);
        box(g, 0.34, 0.1, 0.3, mat(0xf4a7b9, 0.9), -0.38, 0.77, 0.08);
      }
      // floating load bar (the NILM readout) + name tag
      const barG = new THREE.Group();
      barG.position.set(0, topY + 0.35, 0.1);
      box(barG, 0.16, 0.9, 0.16, new THREE.MeshBasicMaterial({ color: 0xffffff, transparent: true, opacity: 0.35 }), 0, 0.45, 0, false);
      const barGeo = new THREE.BoxGeometry(0.16, 1, 0.16); barGeo.translate(0, 0.5, 0);
      const bar = add(barG, barGeo, new THREE.MeshBasicMaterial({ color: 0x2fbf71 }), 0, 0, 0, false);
      bar.scale.y = 0.001;
      const tag = label(def.name, 1.45);
      tag.position.set(0, 1.2, 0);
      barG.add(tag);
      barG.scale.setScalar(0.001);
      g.add(barG);
      return { def, g, bar, barG, tag, lamp, spin, needle, puffs, top: new THREE.Vector3(def.x, y0 + topY, def.z), act: 0 };
    });
    // shelf + folded laundry upstairs, and a few baskets
    box(upper, 1.0, 1.5, 0.4, mat(0xc98a4b, 0.8), 3.0, FH + 0.86, -1.8);
    [0.5, 0.95, 1.4].forEach((y, i) => box(upper, 0.9, 0.14, 0.34, mat([0xf4a7b9, 0x8fd0f2, 0xffe0a8][i], 0.9), 3.0, FH + 0.15 + y, -1.8));
    [-3.0, -2.2].forEach((x) => { const b = add(ruko, new THREE.CylinderGeometry(0.34, 0.26, 0.4, 14), mat(0xd9a15f, 0.8), x, 0.33, 1.3); void b; });

    /* rooftop: inverter, battery, panels (they pop in on cue) */
    const roofY = H + 0.13;
    const inverter = new THREE.Group();
    inverter.position.set(2.7, roofY, -1.5);
    upper.add(inverter);
    box(inverter, 0.7, 0.9, 0.3, mat(0xf3f5f6, 0.5), 0, 0.45, 0);
    box(inverter, 0.12, 0.12, 0.04, new THREE.MeshStandardMaterial({ color: 0x222, emissive: 0x2fbf71, emissiveIntensity: 1 }), 0.15, 0.7, 0.17, false);
    box(upper, 0.9, 0.7, 0.6, mat(0x35d28a, 0.5), 1.5, roofY + 0.35, -1.6);
    const panels = new THREE.Group();
    upper.add(panels);
    const panelMeshes: THREE.Group[] = [];
    const cellMat = new THREE.MeshStandardMaterial({ color: 0x2a5d8f, roughness: 0.25, metalness: 0.5, emissive: 0x153a5a, emissiveIntensity: 0.3 });
    for (let r = 0; r < 2; r++) for (let c = 0; c < 4; c++) {
      const g = new THREE.Group();
      g.position.set(-2.55 + c * 1.18, roofY + 0.32, 0.55 - r * 1.35);
      g.rotation.x = -0.34;
      box(g, 1.08, 0.06, 1.2, mat(0xe5e7eb, 0.4), 0, 0, 0);
      box(g, 0.98, 0.03, 1.1, cellMat, 0, 0.04, 0, false);
      [-0.33, 0, 0.33].forEach((x) => box(g, 0.012, 0.035, 1.1, mat(0xb7c4d6, 0.4), x, 0.058, 0, false));
      [-0.55, 0.55].forEach((z) => box(g, 0.05, 0.3, 0.05, mat(0x6b7280, 0.5), 0.3 * (z > 0 ? -1 : 1), -0.18, z * 0.4, false));
      g.scale.setScalar(0.001);
      panels.add(g);
      panelMeshes.push(g);
    }
    // street pole carrying the PLN line
    const pole = new THREE.Group();
    pole.position.set(W / 2 + 3.6, 0, 2.2);
    world.add(pole);
    add(pole, new THREE.CylinderGeometry(0.1, 0.14, 4.8, 8), mat(0x6b5a40, 0.9), 0, 2.4, 0);
    box(pole, 1.2, 0.1, 0.1, mat(0x6b5a40, 0.9), 0, 4.5, 0);
    box(pole, 0.5, 0.6, 0.4, mat(0x8a9099, 0.5), 0.5, 3.7, 0);

    /* cables + the electrons that run through them */
    const V = (x: number, y: number, z: number) => new THREE.Vector3(x, y, z);
    const panelIn = V(W / 2 + 0.3, 1.95, 0.5);
    const gridCurve = new THREE.CatmullRomCurve3([V(W / 2 + 3.6, 4.5, 2.2), V(W / 2 + 2.2, 3.55, 1.5), V(W / 2 + 0.9, 2.5, 0.9), panelIn]);
    const solarCurve = new THREE.CatmullRomCurve3([V(2.7, roofY + 0.9, -1.5), V(W / 2 + 0.2, roofY + 0.6, -0.6), V(W / 2 + 0.55, H - 1.2, 0.0), V(W / 2 + 0.45, 2.7, 0.35), panelIn]);
    const cableMat = new THREE.MeshStandardMaterial({ color: 0x1f2937, roughness: 0.6 });
    const tube = (c: THREE.Curve<THREE.Vector3>, r = 0.03, m: THREE.Material = cableMat) => { const t = new THREE.Mesh(new THREE.TubeGeometry(c, 40, r, 6, false), m); world.add(t); return t; };
    tube(gridCurve); tube(solarCurve);
    const thin = new THREE.MeshStandardMaterial({ color: 0x4b5563, roughness: 0.6, transparent: true, opacity: 0.55 });
    interface Flow { curve: THREE.Curve<THREE.Vector3>; n: number; speed: number; kind: 'grid' | 'solar' | 'inner'; m?: Machine }
    const flows: Flow[] = [
      { curve: gridCurve, n: 20, speed: 0.34, kind: 'grid' },
      { curve: solarCurve, n: 20, speed: 0.34, kind: 'solar' },
    ];
    machines.forEach((m) => {
      const p0 = V(W / 2 - 0.15, 1.5, 0.5);
      const c = new THREE.CatmullRomCurve3([p0, V(W / 2 - 0.7, (p0.y + m.top.y) / 2 + 0.5, 0.45), V(lerp(p0.x, m.top.x, 0.5), m.top.y + 0.9, lerp(0.45, m.top.z, 0.6)), V(m.top.x, m.top.y + 0.32, m.top.z + 0.1)]);
      const t = new THREE.Mesh(new THREE.TubeGeometry(c, 30, 0.014, 5, false), thin);
      ruko.add(t);
      t.position.set(0, 0, 0);
      flows.push({ curve: c, n: 8, speed: 0.45, kind: 'inner', m });
    });
    // wires were authored in ruko-local space for the machine feeds, world space for the rest (ruko sits at the origin), so they match

    const TOTAL = flows.reduce((s, f) => s + f.n, 0);
    const fPos = new Float32Array(TOTAL * 3), fCol = new Float32Array(TOTAL * 3);
    const fGeo = new THREE.BufferGeometry();
    fGeo.setAttribute('position', new THREE.BufferAttribute(fPos, 3));
    fGeo.setAttribute('color', new THREE.BufferAttribute(fCol, 3));
    const dotTex = (() => {
      const c = document.createElement('canvas'); c.width = c.height = 32;
      const x = c.getContext('2d')!;
      const g = x.createRadialGradient(16, 16, 0, 16, 16, 16);
      g.addColorStop(0, 'rgba(255,255,255,1)'); g.addColorStop(0.4, 'rgba(255,255,255,.9)'); g.addColorStop(1, 'rgba(255,255,255,0)');
      x.fillStyle = g; x.fillRect(0, 0, 32, 32);
      return new THREE.CanvasTexture(c);
    })();
    const fMat = new THREE.PointsMaterial({ size: 11 * DPR, map: dotTex, vertexColors: true, transparent: true, depthWrite: false, sizeAttenuation: false });
    const flowPts = new THREE.Points(fGeo, fMat);
    flowPts.frustumCulled = false;
    flowPts.renderOrder = 10;
    scene.add(flowPts);
    const AMBER = new THREE.Color(0xff9e2c), GREEN = new THREE.Color(0x2fe08a);
    const tmpV = new THREE.Vector3(), tmpC = new THREE.Color();

    /* ── mid layer: neighbours ── */
    function neighbour(x: number, z: number, w: number, h: number, d: number, col: number) {
      const g = new THREE.Group();
      g.position.set(x, 0, z);
      box(g, w, h + 14, d, mat(col, 0.85), 0, h / 2 - 7, 0);
      box(g, w + 0.3, 0.3, d + 0.3, mat(0xb8ad96, 0.8), 0, h, 0);
      addWindows(g, 0.9, 1.1, -w / 2 + 0.9, 1.3, d / 2 + 0.03, Math.max(1, Math.floor((w - 0.8) / 1.6)), Math.max(1, Math.floor((h - 1) / 2.3)), 1.6, 2.2);
      midL.add(g);
      return g;
    }
    neighbour(-8.6, -3.5, 4.6, 8.5, 4.4, 0xe3d7bd);
    neighbour(9.4, -4.5, 4.4, 6, 4.4, 0xdbe4d6);
    neighbour(-14, -9, 5, 11, 4.5, 0xd6dbe3);
    neighbour(15.5, -9, 5, 9, 4.5, 0xe8d9c6);

    /* ── far layer: skyline silhouette ── */
    const skyMat = mat(0xcfd6e0, 0.95);
    for (let i = -14; i <= 14; i++) {
      const w = 2 + rnd() * 3, h = 6 + rnd() * 14;
      const b = new THREE.Mesh(bx(w, h + 20, 3), skyMat);
      b.position.set(i * 4.2 + rnd() * 2, h / 2 - 10, -34 - rnd() * 8);
      farL.add(b);
    }

    /* ── front layer: low bushes and a lamp, moving faster than the stage ── */
    const bushMats = [0x2fbf5c, 0x259a4a, 0x45cf72].map((c) => mat(c, 0.7));
    const bushes: THREE.Mesh[] = [];
    for (let i = 0; i < 14; i++) {
      const r = 0.5 + rnd() * 0.5;
      const b = add(frontL, new THREE.SphereGeometry(r, 12, 8), bushMats[i % 3], -22 + i * 3.4 + rnd() * 1.4, r * 0.7 - 0.1, 11.5 + rnd() * 1.4);
      b.scale.y = 0.8;
      bushes.push(b);
    }
    for (let i = 0; i < 5; i++) {
      const g = new THREE.Group();
      g.position.set(-18 + i * 9, 0, 10.2);
      add(g, new THREE.CylinderGeometry(0.05, 0.07, 3.2, 8), mat(0x2a2a2e, 0.6), 0, 1.6, 0);
      const bulb = add(g, new THREE.SphereGeometry(0.17, 12, 10), new THREE.MeshStandardMaterial({ color: 0xffefc0, emissive: 0xffc46b, emissiveIntensity: 0 }), 0, 3.3, 0, false);
      (bulb as THREE.Mesh & { isBulb: boolean }).isBulb = true;
      frontL.add(g);
    }
    const bulbs: THREE.MeshStandardMaterial[] = [];
    frontL.traverse((o) => { if ((o as THREE.Mesh & { isBulb?: boolean }).isBulb) bulbs.push((o as THREE.Mesh).material as THREE.MeshStandardMaterial); });
    // trees that arrive at the end
    const trees: { g: THREE.Group; d: number }[] = [];
    [[-5.6, 3.4], [6.4, 4], [-7.6, 5], [9.6, 3]].forEach(([x, z], i) => {
      const g = new THREE.Group();
      g.position.set(x, 0, z);
      add(g, new THREE.CylinderGeometry(0.15, 0.2, 1.4, 8), mat(0x8b5a2b, 0.8), 0, 0.7, 0);
      add(g, new THREE.SphereGeometry(0.95, 14, 10), mat(0x2fbf5c, 0.6), 0, 2.0, 0);
      add(g, new THREE.SphereGeometry(0.7, 14, 10), mat(0x45cf72, 0.6), 0.45, 2.7, 0.15);
      g.scale.setScalar(0.001);
      world.add(g);
      trees.push({ g, d: i * 0.012 });
    });
    // a few windows on the ruko's neighbours were registered above; give each its own on/off threshold
    const thresholds = winMats.map((m) => (m as THREE.MeshStandardMaterial & { th: number }).th);

    /* ── camera + resize ── */
    const ct = { zoom: 1, tx: 0, ty: 2.6, tz: 0, az: 34, el: 27 };
    function sampleKeys(p: number) {
      let i = 0;
      while (i < CAM_KEYS.length - 2 && p > CAM_KEYS[i + 1].p) i++;
      const a = CAM_KEYS[i], b = CAM_KEYS[i + 1];
      const u = smooth(0, 1, clamp01((p - a.p) / (b.p - a.p)));
      ct.zoom = lerp(a.zoom, b.zoom, u);
      ct.az = lerp(a.az, b.az, u);
      ct.el = lerp(a.el, b.el, u);
      ct.tx = lerp(a.t[0], b.t[0], u); ct.ty = lerp(a.t[1], b.t[1], u); ct.tz = lerp(a.t[2], b.t[2], u);
    }
    let viewW = 25, viewH = 14, aspect = 1.78;
    function resize() {
      const w = sticky.clientWidth, h = sticky.clientHeight;
      if (!w || !h) return;
      renderer.setSize(w, h, false);
      aspect = w / h;
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

    /* ── scroll ── */
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

    /* ── DOM refs for the per-frame updates ── */
    const copies = qa('.st-copy');
    const railEls = qa('.st-rail li');
    const clouds = qa('.st-cloud');
    const skyEl = q('.st-sky'), starsEl = q('.st-stars'), sunOrb = q('.st-sun'), moonOrb = q('.st-moon'), hint = q('.st-hint');
    const rHour = q('[data-r=hour]'), rLoad = q('[data-r=load]'), rPv = q('[data-r=pv]'), rGrid = q('[data-r=grid]'), rBar = q('[data-r=bar]'), rSelf = q('[data-r=self]');
    const cA = new THREE.Color(), cB = new THREE.Color(), cT = new THREE.Color(), cI = new THREE.Color();
    const inkDark = new THREE.Color(0x14281a), inkLight = new THREE.Color(0xf1f7f2), mutDark = new THREE.Color(0x3f5a46), mutLight = new THREE.Color(0xc4d4ca);
    let lastRail = -1;

    const fmt = (n: number, d = 1) => n.toFixed(d).replace('.', ',');

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

      /* camera */
      sampleKeys(p);
      if (aspect <= 1.15) ct.ty += 1.6 * smooth(0.3, 0.36, p) * (1 - smooth(0.46, 0.5, p));
      const az = ((ct.az + (reduced ? 0 : ptr.sx * 3)) * Math.PI) / 180;
      const el = ((ct.el - (reduced ? 0 : ptr.sy * 1.2)) * Math.PI) / 180;
      const d = 90;
      camera.position.set(ct.tx + Math.sin(az) * Math.cos(el) * d, ct.ty + Math.sin(el) * d, ct.tz + Math.cos(az) * Math.cos(el) * d);
      const hw = viewW / 2, hh = viewH / 2;
      const sx = aspect > 1.15 ? viewW * 0.14 : 0, sy = aspect <= 1.15 ? viewH * 0.17 : 0;
      camera.left = -hw - sx; camera.right = hw - sx; camera.top = hh - sy; camera.bottom = -hh - sy;
      camera.zoom = ct.zoom * lerp(0.5, 1, smooth(0.5, 1.2, aspect));
      camera.updateProjectionMatrix();
      camera.lookAt(ct.tx, ct.ty, ct.tz);

      /* parallax: layers drift with the camera target at different rates, plus a little pointer push */
      layers.forEach(([g, f]) => {
        g.position.set(ct.tx * f + ptr.sx * -f * 0.6, ct.ty * f, ct.tz * f);
      });

      /* time of day */
      const hr = hourAt(p);
      const e = Math.sin((Math.PI * (hr - 6)) / 12);
      const dayAmt = smooth(-0.25, 0.2, e), night = 1 - smooth(-0.25, 0.12, e);
      const t01 = clamp01((hr - 6) / 12);
      const th = ((45 + (t01 - 0.5) * 170) * Math.PI) / 180, sel = (Math.max(e, 0.06) * 62 * Math.PI) / 180;
      sun.position.set(Math.sin(th) * Math.cos(sel) * 60, 2 + Math.sin(sel) * 60, Math.cos(th) * Math.cos(sel) * 60);
      sun.intensity = 0.95 * dayAmt + 0.04;
      sun.color.set(0xffb26b).lerp(cT.set(0xfff4e0), smooth(0.05, 0.5, e));
      moon.intensity = 0.9 * night;
      hemi.intensity = 0.45 + 0.2 * dayAmt;
      hemi.color.set(0x7088c8).lerp(cT.set(0xffffff), dayAmt);
      hemi.groundColor.set(0x1c2540).lerp(cT.set(0xcfd6dc), dayAmt);
      roomA.intensity = (6 * night + 1.2) * 0.9; roomB.intensity = roomA.intensity;
      fixtureMat.emissiveIntensity = 0.2 + 0.9 * night;
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
      winMats.forEach((m, i) => { const lit = smooth(thresholds[i], thresholds[i] + 0.3, night); m.emissiveIntensity = 0.9 * lit; m.color.set(0x8fb3cc).lerp(cT.set(0x1f2c4a), night * 0.8); });
      bulbs.forEach((b) => { b.emissiveIntensity = 1.4 * night; });

      /* ink colour follows the sky so the copy always reads */
      const lum = 0.5 * (0.299 * cA.r + 0.587 * cA.g + 0.114 * cA.b + 0.299 * cB.r + 0.587 * cB.g + 0.114 * cB.b);
      const kd = smooth(0.42, 0.55, lum);
      sticky.style.setProperty('--ink', '#' + cI.copy(inkLight).lerp(inkDark, kd).getHexString());
      sticky.style.setProperty('--ink-muted', '#' + cI.copy(mutLight).lerp(mutDark, kd).getHexString());
      sticky.style.setProperty('--btn-ink', kd > 0.5 ? '#f1f7f2' : '#14281a');
      sticky.style.setProperty('--accent', kd > 0.5 ? '#1e8e4f' : '#6fe39a');
      cI.copy(cB).lerp(cT.set(kd > 0.5 ? 0xffffff : 0x0a1426), 0.3);
      sticky.style.setProperty('--scrim', `${Math.round(cI.r * 255)}, ${Math.round(cI.g * 255)}, ${Math.round(cI.b * 255)}`);

      /* CSS cloud parallax (behind the canvas) */
      clouds.forEach((c, i) => {
        const f = [0.25, 0.5, 0.8, 0.35][i % 4];
        c.style.transform = `translate3d(${(-p * 520 * f + ptr.sx * -18 * f + ((time * (6 + i * 3)) % 1400)).toFixed(1)}px,${(-p * 70 * f).toFixed(1)}px,0)`;
      });

      const lift = smooth(0.285, 0.325, p) * (1 - smooth(0.455, 0.495, p));
      upper.position.y = lift * 8;
      /* machines + power numbers */
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
      machines.forEach((m) => {
        const on = m.act > 0.05;
        if (m.spin) m.spin.rotation.z += dt * 7 * m.act * (reduced ? 0 : 1);
        if (m.needle) m.needle.position.y = 0.78 + (reduced ? 0 : Math.abs(Math.sin(time * 26)) * 0.07 * m.act);
        m.puffs.forEach((pf, i) => {
          const ph = (time * 0.7 + i / 3) % 1;
          pf.position.y = 1.1 + ph * 0.9;
          pf.scale.setScalar(0.5 + ph * 1.2);
          (pf.material as THREE.MeshBasicMaterial).opacity = m.act * (1 - ph) * 0.55;
        });
        m.lamp.emissiveIntensity = 0.15 + m.act * 1.4;
        m.lamp.emissive.set(on ? (m.def.kw * m.act > 1 && pv < load ? 0xef4444 : 0x2fbf71) : 0x2fbf71);
        const bs = Math.max(0.001, backOut(nilm));
        m.barG.scale.setScalar(nilm > 0.01 ? bs : 0.001);
        const h = Math.max(0.001, (m.def.kw * m.act) / 1.8) * 0.9 + 0.001;
        m.bar.scale.y += (h - m.bar.scale.y) * Math.min(1, dt * 10);
        const k = clamp01(m.def.kw * m.act / 1.8);
        (m.bar.material as THREE.MeshBasicMaterial).color.setHSL(lerp(0.38, 0.0, k), 0.8, 0.5);
        m.tag.material.opacity = nilm;
      });

      /* flows */
      let idx = 0;
      const solarShare = load > 0 ? Math.min(1, pv / load) : 0;
      flows.forEach((f) => {
        let I = 0;
        if (f.kind === 'grid') I = clamp01(grid / 5);
        else if (f.kind === 'solar') I = clamp01(pv / 3.5);
        else I = f.m!.act * (f.m!.def.floor === 1 ? 1 - lift : 1);
        const count = Math.ceil(f.n * I - 1e-4);
        for (let k = 0; k < f.n; k++) {
          const i3 = (idx + k) * 3;
          if (k < count) {
            const t = (time * f.speed + k / f.n) % 1;
            f.curve.getPointAt(t, tmpV);
            fPos[i3] = tmpV.x; fPos[i3 + 1] = tmpV.y; fPos[i3 + 2] = tmpV.z;
            if (f.kind === 'grid') tmpC.copy(AMBER);
            else if (f.kind === 'solar') tmpC.copy(GREEN);
            else tmpC.copy(AMBER).lerp(GREEN, solarShare);
            fCol[i3] = tmpC.r; fCol[i3 + 1] = tmpC.g; fCol[i3 + 2] = tmpC.b;
          } else { fPos[i3 + 1] = -999; }
        }
        idx += f.n;
      });
      fGeo.attributes.position.needsUpdate = true;
      fGeo.attributes.color.needsUpdate = true;

      /* meter: red while the grid carries the load, green when the sun does */
      const ms = smooth(0.2, 0.8, 1 - (load > 0 ? grid / load : 1)) * smooth(0.5, 0.62, p);
      meterMat.emissive.set(0xd1453a).lerp(cT.set(0x2fbf71), ms);
      meterMat.emissiveIntensity = 0.9 + Math.sin(time * 3) * 0.12;
      const sp = smooth(0.14, 0.2, p) * (1 - 0 * p);
      sensor.scale.setScalar(Math.max(0.001, backOut(sp)));
      const pg = (time * 0.8) % 1;
      ping.scale.setScalar(1 + pg * 1.6);
      (ping.material as THREE.MeshBasicMaterial).opacity = sp > 0.5 ? (1 - pg) * 0.7 : 0;

      /* panels pop in one by one, then the greenery arrives */
      panelMeshes.forEach((g, i) => {
        const u = backOut((smooth(0.54, 0.66, p) * 1.6 - i * 0.09) / 0.6);
        g.scale.setScalar(Math.max(0.001, clamp01(smooth(0.54, 0.66, p) * 1.6 - i * 0.09) > 0.001 ? u : 0.001));
      });
      trees.forEach((t) => t.g.scale.setScalar(Math.max(0.001, backOut((smooth(0.88, 0.97, p) - t.d * 5) / 0.8))));
      groundMat.color.copy(groundGrey).lerp(groundGreen, smooth(0.9, 1, p));

      /* copy blocks: fade in bands tied to scroll */
      let maxO = 0;
      copies.forEach((el, i) => {
        const c = CHAPTERS[i], fade = 0.025;
        let o = 0;
        if (p >= c.a - fade && p <= c.b + fade) o = p < c.a ? (p - (c.a - fade)) / fade : p > c.b ? 1 - (p - c.b) / fade : 1;
        o = clamp01(o) < 0.01 ? 0 : clamp01(o);
        const mid = (c.a + c.b) / 2;
        el.style.opacity = String(o);
        el.style.visibility = o === 0 ? 'hidden' : 'visible';
        el.style.pointerEvents = o > 0.5 ? 'auto' : 'none';
        el.style.transform = `translate3d(0,${((1 - o) * 22 + (p - mid) * -90).toFixed(1)}px,0)`;
        if (o > maxO) maxO = o;
      });
      sticky.style.setProperty('--scrim-o', maxO.toFixed(2));
      (q('.st-scrim')).style.opacity = maxO.toFixed(2);
      hint.style.opacity = p > 0.02 ? '0' : '1';

      let cur = 0;
      CHAPTERS.forEach((c, i) => { if (p >= c.a - 0.02) cur = i; });
      if (cur !== lastRail) {
        lastRail = cur;
        railEls.forEach((el, i) => { el.className = (i < cur ? 'seen ' : '') + (i === cur ? 'now' : ''); });
      }

      /* readout */
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
      scene.traverse((o) => {
        const m = o as THREE.Mesh;
        if (m.geometry) m.geometry.dispose();
      });
      stdCache.forEach((m) => m.dispose());
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
        <div className="st-nogl" hidden>Browser kamu belum mendukung WebGL, jadi demo 3D tidak bisa tampil.</div>


        {CHAPTERS.map((c, i) => (
          <div className="st-copy" key={i}>
            <div className="st-kick">{c.kick}</div>
            {c.h ? <h1>{c.title}</h1> : <h2>{c.title}</h2>}
            <p>{c.body}</p>
            {c.cta && <a className="st-btn" href="#simulator-section">Coba simulator</a>}
          </div>
        ))}

        <ol className="st-rail" aria-hidden="true">
          {CHAPTERS.map((c, i) => (
            <li key={i} className={i === 0 ? 'now' : ''}><span>{c.rail}</span><i /></li>
          ))}
        </ol>

        <dl className="st-readout" aria-label="Pembacaan listrik langsung">
          <small><span>Pembacaan langsung</span><span data-r="hour">05.18</span></small>
          <dt>Beban toko</dt><dd data-r="load">0,3 kW</dd>
          <dt>Produksi surya</dt><dd data-r="pv">0,0 kW</dd>
          <dt>Dari PLN</dt><dd data-r="grid">0,3 kW</dd>
          <dt>Pakai surya</dt><dd data-r="self">0%</dd>
          <div className="st-bar"><i data-r="bar" /></div>
        </dl>
        <div className="st-hint">Scroll ↓</div>
      </div>
    </div>
  );
}
