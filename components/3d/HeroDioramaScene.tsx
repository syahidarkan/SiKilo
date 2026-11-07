'use client';

import { useEffect, useRef } from 'react';
import * as THREE from 'three';
import { buildEnv }    from '@/components/3d/diorama/buildEnv';
import { buildShops }  from '@/components/3d/diorama/buildShops';
import { buildCables } from '@/components/3d/diorama/buildCables';
import { createMascotKilo, type MascotKilo } from '@/components/3d/MascotKilo';

// ─── Story beats ──────────────────────────────────────────────────────────────
const STORY_BEATS = [
  {
    kicker: '01 POTRET NYATA UMKM',
    kickerColor: 'var(--grid-alert)',
    heading: 'Tiga usaha berdampingan,\ntiga cara listrik terbuang',
    subtitle: 'Dari freezer yang menyala nonstop hingga mesin pemanas berdaya tinggi, pemilik usaha membayar tagihan membengkak tanpa tahu alat mana yang bocor daya.',
  },
  {
    kicker: '02 DETEKSI NILM',
    kickerColor: 'var(--eco-primary)',
    heading: 'Deteksi kebocoran daya\ntanpa bongkar alat',
    subtitle: 'Algoritma NILM membaca sidik jari arus listrik secara non-invasif dari meteran induk, langsung membedakan tarikan kompresor freezer dari peralatan lainnya.',
  },
  {
    kicker: '03 PENJADWALAN PREDIKTIF',
    kickerColor: 'var(--eco-primary)',
    heading: 'Nyalakan mesin berat\nsaat surya melimpah',
    subtitle: 'Sesuai regulasi Permen ESDM 2/2024, AI menjadwalkan mesin pengering dan setrika uap bekerja saat produksi PLTS atap mencapai titik tertinggi.',
  },
  {
    kicker: '04 HASIL TERUKUR',
    kickerColor: 'var(--solar-primary)',
    heading: 'PLTS tepat ukuran,\ninvestasi aman',
    subtitle: 'Data operasional riil dikonversi menjadi rapor kelayakan bank untuk pembiayaan panel surya tanpa tebak-tebakan kapasitas.',
  },
];

// ─── Camera keyframes (lookAt targets) ───────────────────────────────────────
// Camera position is ALWAYS lookAt + (14, 12, 14) — true isometric 45°.
const CAM_TARGETS = [
  { lx:  0.0, ly: 2.0, lz: 3.0, zoom: 0.95 },
  { lx: -7.5, ly: 1.6, lz: 2.5, zoom: 2.10 },
  { lx:  5.5, ly: 2.2, lz: 2.0, zoom: 1.85 },
  { lx:  6.5, ly: 1.3, lz: 2.6, zoom: 3.80 },
];

const BEAT_RANGES: [number, number][] = [
  [0.00, 0.25], [0.25, 0.50], [0.50, 0.75], [0.75, 1.00],
];

function smoothstep(x: number, lo: number, hi: number): number {
  const t = Math.max(0, Math.min(1, (x - lo) / (hi - lo)));
  return t * t * (3 - 2 * t);
}

function beatOpacity(sp: number, s: number, e: number, fade = 0.04): number {
  if (sp <= s || sp >= e) return 0;
  if (sp < s + fade) return (sp - s) / fade;
  if (sp > e - fade) return (e - sp) / fade;
  return 1;
}

export default function HeroDioramaScene() {
  const mountRef   = useRef<HTMLDivElement>(null);
  const overlayRefs = useRef<(HTMLDivElement | null)[]>([null, null, null, null]);
  const ctaRef     = useRef<HTMLButtonElement>(null);
  const blendRef   = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!mountRef.current) return;
    const canvas = mountRef.current;

    // ── Renderer ────────────────────────────────────────────────────────────
    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: false });
    renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
    renderer.setSize(canvas.clientWidth, canvas.clientHeight);
    renderer.shadowMap.enabled = true;
    renderer.shadowMap.type = THREE.PCFSoftShadowMap;
    renderer.toneMapping = THREE.ACESFilmicToneMapping;
    renderer.toneMappingExposure = 1.15;
    renderer.outputColorSpace = THREE.SRGBColorSpace;
    canvas.appendChild(renderer.domElement);

    // ── Scene ────────────────────────────────────────────────────────────────
    const scene = new THREE.Scene();
    scene.background = new THREE.Color(0xFBF9F4);
    scene.fog = new THREE.Fog(0xFBF9F4, 26, 60);

    // ── Camera (Orthographic, true isometric) ─────────────────────────────
    const isMobile = canvas.clientWidth < 640;
    const D_BASE   = isMobile ? 7.5 : 11;
    let d = D_BASE;
    let aspect = canvas.clientWidth / canvas.clientHeight;
    const camera = new THREE.OrthographicCamera(-d * aspect, d * aspect, d, -d, 0.1, 500);
    camera.zoom = 0.95;
    camera.updateProjectionMatrix();

    // Current LERP state
    const camLook = new THREE.Vector3(0, 2.0, 3.0);
    let camZoom   = 0.95;

    // ── Lighting ─────────────────────────────────────────────────────────────
    const hemi = new THREE.HemisphereLight(0xFFF8E7, 0xE8E2D5, 0.65);
    scene.add(hemi);

    const sun = new THREE.DirectionalLight(0xFFE4C4, 1.4);
    sun.position.set(15, 20, 15);
    sun.castShadow = true;
    sun.shadow.mapSize.set(2048, 2048);
    sun.shadow.camera.near = 0.5;
    sun.shadow.camera.far  = 80;
    const sc = sun.shadow.camera as THREE.OrthographicCamera;
    sc.left = -28; sc.right = 28; sc.top = 28; sc.bottom = -28;
    scene.add(sun);

    const intLight = new THREE.PointLight(0xFFF176, 0, 8);
    intLight.position.set(6.5, 1.8, 2.0);
    scene.add(intLight);

    const signLight = new THREE.PointLight(0xFFA726, 0, 6);
    signLight.position.set(6.5, 3.5, 2.5);
    scene.add(signLight);

    // ── Build scene objects ───────────────────────────────────────────────────
    const env    = buildEnv();
    scene.add(env.group);

    const shops  = buildShops();
    scene.add(shops.group);

    const cables = buildCables();
    scene.add(cables.group);

    // ── Mascot ────────────────────────────────────────────────────────────────
    type TrackedMascot = MascotKilo & { _mood?: string };
    const mascot: TrackedMascot = createMascotKilo() as TrackedMascot;
    mascot.refs.root.scale.setScalar(0.44);
    mascot.refs.root.position.set(-6.0, 0.35, 3.2);
    mascot.setMood('shocked'); mascot._mood = 'shocked';
    scene.add(mascot.refs.root);

    const beat1Pos  = new THREE.Vector3(-6.0,  0.35, 3.2);
    const beat2Pos  = new THREE.Vector3(-6.8,  1.35, 2.4);
    const beat3Pos  = new THREE.Vector3( 6.5,  1.1,  2.4);
    const beat4Pos  = new THREE.Vector3( 6.5,  1.3,  2.6);

    // ── Scroll tracking ───────────────────────────────────────────────────────
    let rawProgress = 0, smoothProgress = 0;
    function updateRaw() {
      const track = document.getElementById('scroll-track');
      if (!track) return;
      const max = track.offsetHeight - window.innerHeight;
      rawProgress = max > 0 ? Math.min(Math.max(window.scrollY / max, 0), 1) : 0;
    }
    window.addEventListener('scroll', updateRaw, { passive: true });
    updateRaw();

    // ── Mouse for eye tracking ────────────────────────────────────────────────
    const mouse = new THREE.Vector2();
    function onMouse(e: MouseEvent) {
      mouse.x = (e.clientX / window.innerWidth) * 2 - 1;
      mouse.y = -(e.clientY / window.innerHeight) * 2 + 1;
    }
    canvas.addEventListener('mousemove', onMouse);

    // ── Animate ───────────────────────────────────────────────────────────────
    const clock = new THREE.Clock();
    let animId = 0;

    function animate() {
      animId = requestAnimationFrame(animate);
      const delta = clock.getDelta();
      const time  = clock.getElapsedTime();

      smoothProgress += (rawProgress - smoothProgress) * 0.072;
      const sp = smoothProgress;

      // ── Camera (TRUE ISOMETRIC — never flat) ────────────────────────────
      const beatIdx = BEAT_RANGES.findIndex(([s, e]) => sp >= s && sp < e);
      const bi      = beatIdx < 0 ? 3 : beatIdx;
      const bNext   = Math.min(bi + 1, 3);
      const [bs, be] = BEAT_RANGES[bi];
      const bt = bi === 3 ? 1.0 : smoothstep(sp, bs, be);
      const ca = CAM_TARGETS[bi], cb = CAM_TARGETS[bNext];
      const tLx = ca.lx + (cb.lx - ca.lx) * bt;
      const tLy = ca.ly + (cb.ly - ca.ly) * bt;
      const tLz = ca.lz + (cb.lz - ca.lz) * bt;
      const tZ  = ca.zoom + (cb.zoom - ca.zoom) * bt;

      camLook.lerp(new THREE.Vector3(tLx, tLy, tLz), 0.08);
      camZoom += (tZ - camZoom) * 0.08;

      // Isometric offset: always (+14, +12, +14) → maintains 45° angle
      camera.position.set(camLook.x + 14, camLook.y + 12, camLook.z + 14);
      camera.lookAt(camLook);
      camera.zoom = camZoom;
      camera.updateProjectionMatrix();

      // ── Lighting by beat ────────────────────────────────────────────────
      if (sp < 0.25) {
        sun.position.set(15, 20, 15); sun.color.setHex(0xFFE4C4);
        sun.intensity = 1.4; hemi.intensity = 0.60;
        intLight.intensity = 0; signLight.intensity = 0;
      } else if (sp < 0.50) {
        sun.position.set(10, 22, 12); sun.color.setHex(0xFFFBEB);
        sun.intensity = 1.7; hemi.intensity = 0.65;
        intLight.intensity = 0; signLight.intensity = 0;
      } else if (sp < 0.75) {
        const t3 = (sp - 0.50) / 0.25;
        sun.position.set(0, 28, 0); sun.color.setHex(0xFFFFFF);
        sun.intensity = THREE.MathUtils.lerp(1.7, 2.2, t3); hemi.intensity = 0.70;
        intLight.intensity = 0; signLight.intensity = 0;
      } else {
        const t4 = (sp - 0.75) / 0.25;
        sun.position.set(-10, 10, 8); sun.color.setHex(0xF97316);
        sun.intensity = THREE.MathUtils.lerp(1.3, 0.5, t4); hemi.intensity = 0.45;
        intLight.intensity  = THREE.MathUtils.lerp(0, 2.2, t4);
        signLight.intensity = THREE.MathUtils.lerp(0, 1.4, t4);
      }

      // ── PV panel scale (Beat 3: 0.52→0.68) ─────────────────────────────
      const pvScale = THREE.MathUtils.clamp(smoothstep(sp, 0.52, 0.68), 0, 1);
      [shops.pvGroupConveksi, shops.pvGroupLaundry].forEach((pvG) => {
        pvG.children.forEach((c) => {
          if (c instanceof THREE.Group) {
            c.visible = pvScale > 0.01;
            c.scale.setScalar(pvScale);
          }
        });
      });

      // ── Drum rotation (Beat 3+) ──────────────────────────────────────────
      if (sp > 0.5) {
        shops.drumGroup.children.forEach((c) => {
          const data = c.userData as { drumCenter?: THREE.Vector3; drumAngle?: number };
          if (data.drumCenter && data.drumAngle !== undefined) {
            data.drumAngle += delta * 1.2;
            (c as THREE.Object3D).position.set(
              data.drumCenter.x + Math.cos(data.drumAngle) * 0.12,
              data.drumCenter.y + Math.sin(data.drumAngle) * 0.12,
              data.drumCenter.z,
            );
          }
        });
      }

      // ── Truck vibration ─────────────────────────────────────────────────
      env.truckRef.position.y = Math.sin(time * 12) * 0.015;

      // ── Mascot ──────────────────────────────────────────────────────────
      let newMood: 'idle' | 'shocked' | 'scanning' | 'happy';
      let targetPos: THREE.Vector3;
      if      (sp < 0.25) { newMood = 'shocked';  targetPos = beat1Pos; }
      else if (sp < 0.50) { newMood = 'scanning'; targetPos = beat2Pos; }
      else if (sp < 0.75) { newMood = 'happy';    targetPos = beat3Pos; }
      else                { newMood = 'idle';     targetPos = beat4Pos; }

      if (mascot._mood !== newMood) { mascot.setMood(newMood); mascot._mood = newMood; }
      mascot.refs.root.position.lerp(targetPos, 0.035);
      if (sp > 0.75) mascot.setPointer(mouse.x, mouse.y);
      mascot.update(delta, time);

      // ── Particles ───────────────────────────────────────────────────────
      const { mat: pMat, curves, ts, speeds, curveIdx, TOTAL, pts } = cables.particles;
      const pAttr = pts.geometry.getAttribute('position') as THREE.BufferAttribute;

      if (sp < 0.25) {
        pMat.color.setHex(0xEF4444);
        pMat.opacity = 0.7 + Math.abs(Math.sin(time * 14)) * 0.25;
        pMat.size = 0.22;
      } else if (sp < 0.50) {
        pMat.color.setHex(0x00F0FF); pMat.opacity = 0.95; pMat.size = 0.22;
      } else if (sp < 0.75) {
        pMat.color.setHex(sp < 0.625 ? 0xF59E0B : 0x22C55E); pMat.opacity = 0.95; pMat.size = 0.24;
      } else {
        pMat.color.setHex(0x34D399); pMat.opacity = 0.75; pMat.size = 0.20;
      }

      for (let i = 0; i < TOTAL; i++) {
        ts[i] += speeds[i] * delta;
        if (ts[i] > 1.0) ts[i] -= 1.0;
        const ci = curveIdx[i];
        const pt = curves[ci].getPoint(ts[i]);
        pAttr.setXYZ(i, pt.x, pt.y, pt.z);
      }
      pAttr.needsUpdate = true;

      // ── Overlays ─────────────────────────────────────────────────────────
      BEAT_RANGES.forEach(([s, e], obi) => {
        const op  = beatOpacity(sp, s, e);
        const el  = overlayRefs.current[obi];
        if (el) { el.style.opacity = String(op); el.style.pointerEvents = op > 0.3 ? 'auto' : 'none'; }
      });
      if (ctaRef.current)   ctaRef.current.style.opacity   = String(beatOpacity(sp, 0.75, 1.00));
      if (blendRef.current) blendRef.current.style.opacity = String(THREE.MathUtils.clamp((sp - 0.92) / 0.08, 0, 1));

      renderer.render(scene, camera);
    }
    animate();

    // ── Resize ───────────────────────────────────────────────────────────────
    function onResize() {
      if (!canvas) return;
      const w = canvas.clientWidth, h = canvas.clientHeight;
      aspect = w / h;
      d = w < 640 ? 7.5 : D_BASE;
      renderer.setSize(w, h, false);
      camera.left = -d * aspect; camera.right = d * aspect;
      camera.top = d; camera.bottom = -d;
      camera.updateProjectionMatrix();
    }
    const ro = new ResizeObserver(onResize);
    ro.observe(canvas);

    return () => {
      cancelAnimationFrame(animId);
      window.removeEventListener('scroll', updateRaw);
      canvas.removeEventListener('mousemove', onMouse);
      ro.disconnect();
      renderer.dispose();
      canvas.innerHTML = '';
    };
  }, []);

  return (
    <div ref={mountRef} className="relative w-full h-screen">
      {/* Story beat overlays */}
      {STORY_BEATS.map((beat, i) => (
        <div
          key={i}
          ref={(el) => { overlayRefs.current[i] = el; }}
          className="absolute left-6 md:left-10 bottom-28 md:bottom-20 max-w-xs md:max-w-sm pointer-events-none"
          style={{ opacity: i === 0 ? 1 : 0, transition: 'opacity 0.1s' }}
        >
          <div
            className="rounded-2xl p-5 md:p-6"
            style={{
              background: 'rgba(251,249,244,0.88)',
              backdropFilter: 'blur(14px)',
              WebkitBackdropFilter: 'blur(14px)',
              border: '1.5px solid rgba(232,226,213,0.6)',
              boxShadow: '0 8px 32px -8px rgba(31,41,55,0.14)',
            }}
          >
            <span
              className="kicker block mb-2 text-xs font-bold tracking-widest uppercase"
              style={{ color: beat.kickerColor }}
            >
              {beat.kicker}
            </span>
            <h2
              className="text-xl md:text-2xl font-bold leading-snug mb-2 whitespace-pre-line"
              style={{ color: 'var(--metal-dark)', fontFamily: 'var(--font-display)' }}
            >
              {beat.heading}
            </h2>
            <p
              className="text-sm leading-relaxed"
              style={{ color: 'var(--metal-mid)' }}
            >
              {beat.subtitle}
            </p>
          </div>
        </div>
      ))}

      {/* CTA button (Beat 4) */}
      <button
        ref={ctaRef}
        onClick={() => {
          document.getElementById('simulator-section')?.scrollIntoView({ behavior: 'smooth' });
        }}
        className="absolute right-6 md:right-10 bottom-20 md:bottom-14 px-6 py-3 rounded-full font-semibold text-white text-sm transition-all duration-200 hover:scale-105 active:scale-95"
        style={{
          opacity: 0,
          background: 'var(--solar-primary)',
          boxShadow: '0 8px 24px -4px rgba(255,158,44,0.45)',
          fontFamily: 'var(--font-display)',
        }}
      >
        Coba Simulasi Tokomu ↓
      </button>

      {/* Dot navigation */}
      <div className="absolute right-4 top-1/2 -translate-y-1/2 flex flex-col gap-2.5">
        {STORY_BEATS.map((_, i) => (
          <button
            key={i}
            onClick={() => {
              const track = document.getElementById('scroll-track');
              if (!track) return;
              const max = track.offsetHeight - window.innerHeight;
              const target = max * (i * 0.25 + 0.05);
              window.scrollTo({ top: target, behavior: 'smooth' });
            }}
            className="w-2 h-2 rounded-full border border-current transition-all"
            style={{ color: 'var(--metal-light)' }}
            aria-label={`Beat ${i + 1}`}
          />
        ))}
      </div>

      {/* Bottom blend */}
      <div
        ref={blendRef}
        className="absolute inset-x-0 bottom-0 h-32 pointer-events-none"
        style={{
          opacity: 0,
          background: 'linear-gradient(to bottom, transparent, var(--bg-paper))',
        }}
      />
    </div>
  );
}
