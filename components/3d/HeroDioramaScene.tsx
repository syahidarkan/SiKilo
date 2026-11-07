'use client';

import React, { useEffect, useRef } from 'react';
import * as THREE from 'three';
import { buildEnv }    from './diorama/buildEnv';
import { buildShops }  from './diorama/buildShops';
import { buildCables, tickParticles } from './diorama/buildCables';
import { createMascotKilo, type MoodState } from './MascotKilo';

// ── Helpers ───────────────────────────────────────────────────────────────────
function smoothstep(t: number, e0 = 0, e1 = 1): number {
  const x = Math.max(0, Math.min(1, (t - e0) / (e1 - e0)));
  return x * x * (3 - 2 * x);
}

function lerp(a: number, b: number, t: number): number {
  return a + (b - a) * t;
}

// ── Camera keyframes (sp → target) ────────────────────────────────────────────
interface CamKF { sp: number; lx: number; ly: number; lz: number; zoom: number }
const CAM_KF: CamKF[] = [
  { sp: 0.00, lx:  0.0,   ly: 2.0, lz: 2.0,  zoom: 0.88 },  // 0: overview
  { sp: 0.17, lx: -9.0,   ly: 2.0, lz: 1.5,  zoom: 1.85 },  // 1: kelontong shop
  { sp: 0.30, lx: -11.75, ly: 2.5, lz: 2.1,  zoom: 2.70 },  // 2: kelontong meter
  { sp: 0.42, lx:  0.0,   ly: 2.0, lz: 1.5,  zoom: 1.85 },  // 3: konveksi shop
  { sp: 0.54, lx: -2.75,  ly: 2.5, lz: 2.1,  zoom: 2.70 },  // 4: konveksi meter
  { sp: 0.67, lx: +9.0,   ly: 2.0, lz: 1.5,  zoom: 1.85 },  // 5: laundry shop
  { sp: 0.79, lx: +6.25,  ly: 2.5, lz: 2.1,  zoom: 2.70 },  // 6: laundry meter
  { sp: 0.90, lx:  0.0,   ly: 2.5, lz: 2.0,  zoom: 0.95 },  // 7: finale
  { sp: 1.00, lx:  0.0,   ly: 2.5, lz: 2.0,  zoom: 0.95 },  // anchor
];

function getCamTarget(sp: number): CamKF {
  let i = 0;
  while (i < CAM_KF.length - 2 && sp > CAM_KF[i + 1].sp) i++;
  const a = CAM_KF[i], b = CAM_KF[i + 1];
  const range = b.sp - a.sp;
  const t = range < 0.001 ? 1 : smoothstep((sp - a.sp) / range);
  return {
    sp,
    lx:   lerp(a.lx,   b.lx,   t),
    ly:   lerp(a.ly,   b.ly,   t),
    lz:   lerp(a.lz,   b.lz,   t),
    zoom: lerp(a.zoom, b.zoom, t),
  };
}

// ── Mascot waypoints per sub-beat (0–7) ───────────────────────────────────────
const MASCOT_POS: [number, number, number][] = [
  [ 0.0,  0.53, 3.4],   // 0: trotoar center, shocked
  [-9.0,  1.11, 1.5],   // 1: Kelontong counter, shocked
  [-11.75,1.55, 2.0],   // 2: Kelontong meter, scanning
  [-0.5,  1.11, 0.8],   // 3: Konveksi sewing table, shocked
  [-2.75, 1.55, 2.0],   // 4: Konveksi meter, scanning
  [ 9.0,  0.65, 1.8],   // 5: Laundry baskets, shocked
  [ 6.25, 1.55, 2.0],   // 6: Laundry meter, scanning
  [ 0.0,  0.53, 3.4],   // 7: trotoar center, happy
];

const MASCOT_MOODS: MoodState[] = [
  'shocked','shocked','scanning','shocked','scanning','shocked','scanning','happy',
];

function getSubBeat(sp: number): number {
  if (sp < 0.15) return 0;
  if (sp < 0.28) return 1;
  if (sp < 0.40) return 2;
  if (sp < 0.52) return 3;
  if (sp < 0.65) return 4;
  if (sp < 0.76) return 5;
  if (sp < 0.88) return 6;
  return 7;
}

// ── Story beats for card overlay (5 cards) ───────────────────────────────────
interface Beat {
  kicker: string;
  kickerColor: string;
  heading: string;
  subtitle: string;
  cta?: boolean;
}

const STORY_BEATS: Beat[] = [
  {
    kicker: '01 MASALAH ENERGI',
    kickerColor: '#EF4444',
    heading: 'Tiga usaha, tiga cara\nlistrik terbuang',
    subtitle: 'Dari pendingin freezer non-stop hingga setrika uap, tagihan membengkak tanpa tahu peralatan mana yang bocor daya.',
  },
  {
    kicker: '02 DETEKSI KELONTONG',
    kickerColor: 'var(--eco-primary)',
    heading: 'Temukan kompresor bocor\ntanpa bongkar mesin',
    subtitle: 'Sensor jepit membaca sidik jari arus listrik meteran induk. NILM langsung identifikasi kompresor freezer yang boros.',
  },
  {
    kicker: '03 OPTIMASI KONVEKSI',
    kickerColor: 'var(--eco-primary)',
    heading: 'Cegah trip beban puncak\ndengan jadwal cerdas',
    subtitle: 'AI mengatur jadwal boiler setrika uap agar tidak bertabrakan dengan motor jahit—memangkas tagihan daya kVA.',
  },
  {
    kicker: '04 SINERGI SURYA LAUNDRY',
    kickerColor: '#F59E0B',
    heading: 'Nyalakan pengering saat\nproduksi surya puncak',
    subtitle: 'Sesuai Permen ESDM 2/2024, daya surya diserap 100% mandiri oleh mesin pengering besar di jam terik.',
  },
  {
    kicker: '05 HASIL TERUKUR',
    kickerColor: 'var(--solar-primary)',
    heading: 'Kawasan UMKM hemat energi,\nsiap pembiayaan bank',
    subtitle: 'Rapor energi presisi membuktikan penghematan nyata—dasar kelayakan instalasi PLTS atap tanpa tebak-tebakan.',
    cta: true,
  },
];

const CARD_RANGES: [number, number][] = [
  [0.00, 0.17],
  [0.15, 0.42],
  [0.40, 0.67],
  [0.65, 0.90],
  [0.88, 1.00],
];

function beatOpacity(sp: number, s: number, e: number, fade = 0.04): number {
  if (sp < s || sp > e) return 0;
  const halfFade = fade;
  if (sp < s + halfFade) return (sp - s) / halfFade;
  if (sp > e - halfFade) return (e - sp) / halfFade;
  return 1;
}

export default function HeroDioramaScene(): React.ReactElement {
  const mountRef   = useRef<HTMLDivElement>(null);
  const overlayRef = useRef<(HTMLDivElement | null)[]>([]);
  const ctaRef     = useRef<HTMLButtonElement | null>(null);

  useEffect(() => {
    if (!mountRef.current) return;
    const canvas = mountRef.current;
    const W = canvas.clientWidth, H = canvas.clientHeight;

    // ── Renderer ────────────────────────────────────────────────
    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: false });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.setSize(W, H);
    renderer.shadowMap.enabled = true;
    renderer.shadowMap.type = THREE.PCFSoftShadowMap;
    renderer.toneMapping = THREE.ACESFilmicToneMapping;
    renderer.toneMappingExposure = 1.1;
    renderer.domElement.style.position = 'absolute';
    renderer.domElement.style.top = '0';
    renderer.domElement.style.left = '0';
    renderer.domElement.style.zIndex = '0';
    canvas.appendChild(renderer.domElement);

    // ── Scene ────────────────────────────────────────────────────
    const scene = new THREE.Scene();
    scene.background = new THREE.Color(0xFBF9F4);
    scene.fog = new THREE.FogExp2(0xFBF9F4, 0.025);

    // ── Camera (orthographic) ────────────────────────────────────
    const aspect = W / H;
    const D_BASE = 11;
    let currentZoom = 0.88;
    let currentLook = new THREE.Vector3(0, 2.0, 2.0);

    const camera = new THREE.OrthographicCamera(
      -D_BASE * aspect / currentZoom, D_BASE * aspect / currentZoom,
       D_BASE / currentZoom, -D_BASE / currentZoom,
      0.1, 200,
    );
    function updateCamera(lookAt: THREE.Vector3, zoom: number): void {
      camera.left   = -D_BASE * aspect / zoom;
      camera.right  =  D_BASE * aspect / zoom;
      camera.top    =  D_BASE / zoom;
      camera.bottom = -D_BASE / zoom;
      camera.updateProjectionMatrix();
      camera.position.set(lookAt.x + 13, lookAt.y + 11, lookAt.z + 13);
      camera.lookAt(lookAt);
    }
    updateCamera(currentLook, currentZoom);

    // ── Lights ────────────────────────────────────────────────────
    const hemi = new THREE.HemisphereLight(0xFFF4E0, 0xC8D8A0, 0.65);
    scene.add(hemi);

    const sun = new THREE.DirectionalLight(0xFFF5E0, 1.3);
    sun.position.set(12, 20, 12);
    sun.castShadow = true;
    sun.shadow.mapSize.set(2048, 2048);
    sun.shadow.camera.near = 0.5;
    sun.shadow.camera.far  = 80;
    sun.shadow.camera.left   = -22;
    sun.shadow.camera.right  =  22;
    sun.shadow.camera.top    =  18;
    sun.shadow.camera.bottom = -6;
    scene.add(sun);

    const fill = new THREE.DirectionalLight(0xE0ECFF, 0.4);
    fill.position.set(-8, 8, -4);
    scene.add(fill);

    // ── Build scene objects ───────────────────────────────────────
    const env   = buildEnv(scene);
    const shops = buildShops(scene);
    const cables = buildCables(scene, [shops.meterPos1, shops.meterPos2, shops.meterPos3]);

    // ── Mascot ────────────────────────────────────────────────────
    const mascot = createMascotKilo();
    scene.add(mascot.refs.root);
    mascot.refs.root.position.set(0, 0.53, 3.4);
    mascot.setMood('shocked');

    // ── Scroll tracking ───────────────────────────────────────────
    let rawProgress  = 0;
    let smoothProgress = 0;

    function onScroll(): void {
      const scrollTrack = document.getElementById('scroll-track');
      if (!scrollTrack) return;
      const rect  = scrollTrack.getBoundingClientRect();
      const total = scrollTrack.clientHeight - window.innerHeight;
      rawProgress = Math.max(0, Math.min(1, -rect.top / total));
    }
    window.addEventListener('scroll', onScroll, { passive: true });

    // ── Resize ───────────────────────────────────────────────────
    const ro = new ResizeObserver(() => {
      const w = canvas.clientWidth, h = canvas.clientHeight;
      renderer.setSize(w, h);
      const asp = w / h;
      camera.left   = -D_BASE * asp / currentZoom;
      camera.right  =  D_BASE * asp / currentZoom;
      camera.top    =  D_BASE / currentZoom;
      camera.bottom = -D_BASE / currentZoom;
      camera.updateProjectionMatrix();
    });
    ro.observe(canvas);

    // ── Animation loop ───────────────────────────────────────────
    const clock = new THREE.Clock();
    let   time  = 0;
    let   animId = 0;
    let   prevSubBeat = -1;

    const targetPos   = new THREE.Vector3();
    const currentMascotPos = new THREE.Vector3(0, 0.53, 3.4);

    function animate(): void {
      animId = requestAnimationFrame(animate);
      const delta = Math.min(clock.getDelta(), 0.05);
      time += delta;

      // Smooth scroll
      smoothProgress += (rawProgress - smoothProgress) * 0.072;
      const sp = smoothProgress;

      // ── Sub-beat state ──────────────────────────────────────────
      const subBeat = getSubBeat(sp);
      const camKF   = getCamTarget(sp);

      // ── Camera lerp ─────────────────────────────────────────────
      currentLook.lerp(new THREE.Vector3(camKF.lx, camKF.ly, camKF.lz), 0.05);
      currentZoom += (camKF.zoom - currentZoom) * 0.05;
      updateCamera(currentLook, currentZoom);

      // ── Mascot movement ──────────────────────────────────────────
      const mp = MASCOT_POS[subBeat];
      targetPos.set(mp[0], mp[1], mp[2]);
      currentMascotPos.lerp(targetPos, 0.04);
      mascot.refs.root.position.copy(currentMascotPos);

      if (subBeat !== prevSubBeat) {
        mascot.setMood(MASCOT_MOODS[subBeat]);
        prevSubBeat = subBeat;
      }

      // ── Mascot rotation: face the camera roughly ─────────────────
      const faceDir = new THREE.Vector3(
        camera.position.x - currentMascotPos.x,
        0,
        camera.position.z - currentMascotPos.z,
      );
      if (faceDir.lengthSq() > 0.01) {
        const angle = Math.atan2(faceDir.x, faceDir.z);
        mascot.refs.root.rotation.y += (angle - mascot.refs.root.rotation.y) * 0.08;
      }

      // ── Meter LED animations ─────────────────────────────────────
      function updateMeter(
        indMesh: THREE.Mesh,
        fixed: boolean,
      ): void {
        const m = indMesh.material as THREE.MeshStandardMaterial;
        if (fixed) {
          m.color.setHex(0x2FBF71);
          m.emissive.setHex(0x2FBF71);
          m.emissiveIntensity = 2.0;
        } else {
          m.color.setHex(0xEF4444);
          m.emissive.setHex(0xEF4444);
          m.emissiveIntensity = Math.sin(time * 8) > 0 ? 2.8 : 0.4;
        }
      }
      updateMeter(shops.meterInd1, sp >= 0.28);
      updateMeter(shops.meterInd2, sp >= 0.52);
      updateMeter(shops.meterInd3, sp >= 0.76);

      // ── PV panel emergence ───────────────────────────────────────
      const pv1Scale = smoothstep(sp, 0.28, 0.42);
      const pv2Scale = smoothstep(sp, 0.52, 0.65);
      const pv3Scale = smoothstep(sp, 0.76, 0.88);
      shops.pvGroup1.scale.set(1, pv1Scale, 1);
      shops.pvGroup2.scale.set(1, pv2Scale, 1);
      shops.pvGroup3.scale.set(1, pv3Scale, 1);

      // ── Truck loop animation ─────────────────────────────────────
      env.truckRef.position.x = ((time * 2.5) % 36) - 18;
      env.truckRef.position.y = Math.sin(time * 16) * 0.015;

      // ── Drum rotation (laundry) ──────────────────────────────────
      for (const c of shops.drumGroup.children) {
        const data = c.userData as { drumCenter?: THREE.Vector3; drumAngle?: number };
        if (data.drumCenter && data.drumAngle !== undefined) {
          data.drumAngle += delta * 1.2;
          c.position.set(
            data.drumCenter.x + Math.cos(data.drumAngle) * 0.12,
            data.drumCenter.y + Math.sin(data.drumAngle) * 0.12,
            data.drumCenter.z,
          );
        }
      }

      // ── Particles ────────────────────────────────────────────────
      tickParticles(cables.particles, delta, sp);
      const geo = (cables.particles as unknown as Record<string, unknown>);
      const pointsMesh = cables.group.children.find(
        (c) => c instanceof THREE.Points,
      ) as THREE.Points | undefined;
      if (pointsMesh) {
        (pointsMesh.geometry.getAttribute('position') as THREE.BufferAttribute).array.set(cables.particles.pts);
        (pointsMesh.geometry.getAttribute('position') as THREE.BufferAttribute).needsUpdate = true;
      }

      // ── Sunset lighting in Act 5 ─────────────────────────────────
      if (sp > 0.88) {
        const st = smoothstep(sp, 0.88, 1.0);
        sun.color.setRGB(lerp(1.0, 1.0, st), lerp(0.96, 0.75, st), lerp(0.88, 0.45, st));
        hemi.color.setRGB(lerp(1.0, 1.0, st), lerp(0.96, 0.82, st), lerp(0.88, 0.60, st));
        (scene.background as THREE.Color).setRGB(
          lerp(0.98, 0.99, st), lerp(0.976, 0.90, st), lerp(0.957, 0.80, st),
        );
      } else {
        sun.color.setHex(0xFFF5E0);
        hemi.color.setHex(0xFFF4E0);
        (scene.background as THREE.Color).setHex(0xFBF9F4);
      }

      // ── Card overlay opacity ────────────────────────────────────
      overlayRef.current.forEach((el, i) => {
        if (!el) return;
        const [s, e] = CARD_RANGES[i];
        const op = beatOpacity(sp, s, e, 0.04);
        el.style.opacity = String(op);
        el.style.pointerEvents = op > 0.5 ? 'auto' : 'none';
      });

      // CTA button in beat 4
      if (ctaRef.current) {
        const ctaOp = smoothstep(sp, 0.90, 1.0);
        ctaRef.current.style.opacity = String(ctaOp);
        ctaRef.current.style.pointerEvents = ctaOp > 0.3 ? 'auto' : 'none';
      }

      // ── Update mascot ────────────────────────────────────────────
      mascot.update(delta, time);

      // ── Dot nav ───────────────────────────────────────────────────
      const dots = document.querySelectorAll<HTMLElement>('[data-beat-dot]');
      dots.forEach((d, i) => {
        const active = subBeat >= i * 2 && subBeat < (i + 1) * 2;
        d.style.background = active ? 'var(--eco-primary)' : 'rgba(255,255,255,0.4)';
        d.style.transform = active ? 'scale(1.3)' : 'scale(1)';
      });

      renderer.render(scene, camera);
    }

    animate();

    return () => {
      cancelAnimationFrame(animId);
      window.removeEventListener('scroll', onScroll);
      ro.disconnect();
      renderer.dispose();
      if (canvas.contains(renderer.domElement)) canvas.removeChild(renderer.domElement);
    };
  }, []);

  return (
    <div ref={mountRef} className="relative w-full h-full" style={{ overflow: 'hidden' }}>
      {/* Story card overlays — vertically centred on the left */}
      {STORY_BEATS.map((beat, i) => (
        <div
          key={i}
          ref={(el) => { overlayRef.current[i] = el; }}
          className="absolute left-6 md:left-10 top-1/2 -translate-y-1/2 max-w-xs md:max-w-sm pointer-events-none"
          style={{ opacity: i === 0 ? 1 : 0, transition: 'opacity 0.3s ease', zIndex: 20 }}
        >
          <div
            className="rounded-2xl px-5 py-4 md:px-6 md:py-5"
            style={{
              background: 'rgba(255,255,255,0.88)',
              backdropFilter: 'blur(12px)',
              WebkitBackdropFilter: 'blur(12px)',
              border: '1px solid rgba(255,255,255,0.6)',
              boxShadow: '0 8px 32px -8px rgba(0,0,0,0.12)',
            }}
          >
            <span
              className="inline-block text-xs font-bold tracking-widest uppercase mb-2"
              style={{ color: beat.kickerColor }}
            >
              {beat.kicker}
            </span>
            <p
              className="font-bold text-base md:text-lg leading-snug mb-2 whitespace-pre-line"
              style={{ color: 'var(--metal-dark)', fontFamily: 'var(--font-display)' }}
            >
              {beat.heading}
            </p>
            <p
              className="text-xs md:text-sm leading-relaxed"
              style={{ color: 'var(--metal-mid)' }}
            >
              {beat.subtitle}
            </p>
            {beat.cta && (
              <button
                ref={ctaRef}
                onClick={() => document.getElementById('simulator-section')?.scrollIntoView({ behavior: 'smooth' })}
                className="mt-4 w-full px-4 py-2.5 rounded-xl font-bold text-sm transition-all hover:scale-105 active:scale-95"
                style={{
                  background: 'linear-gradient(135deg, var(--solar-primary) 0%, var(--eco-primary) 100%)',
                  color: '#fff',
                  opacity: 0,
                  pointerEvents: 'none',
                  boxShadow: '0 4px 16px -4px rgba(255,167,38,0.4)',
                }}
              >
                Hitung Potensi Tokomu ↓
              </button>
            )}
          </div>
        </div>
      ))}

      {/* Beat dot navigation (right side) */}
      <div
        className="absolute right-4 md:right-6 top-1/2 -translate-y-1/2 flex flex-col gap-2.5"
        style={{ zIndex: 20 }}
      >
        {STORY_BEATS.map((_, i) => (
          <div
            key={i}
            data-beat-dot={i}
            className="rounded-full transition-all"
            style={{
              width: 8, height: 8,
              background: i === 0 ? 'var(--eco-primary)' : 'rgba(255,255,255,0.4)',
              boxShadow: '0 1px 4px rgba(0,0,0,0.2)',
              transition: 'background 0.3s, transform 0.2s',
            }}
          />
        ))}
      </div>
    </div>
  );
}
