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
  { sp: 0.00, lx:  0.0,   ly: 2.0, lz: 1.0,  zoom: 0.90 },  // 0: overview
  { sp: 0.17, lx: -9.0,   ly: 1.4, lz: 0.0,  zoom: 2.00 },  // 1: kelontong shop interior
  { sp: 0.30, lx: -11.75, ly: 3.5, lz: 3.1,  zoom: 3.60 },  // 2: kelontong meter+cable
  { sp: 0.42, lx:  0.0,   ly: 1.4, lz: 0.0,  zoom: 2.00 },  // 3: konveksi shop interior
  { sp: 0.54, lx: -2.75,  ly: 3.5, lz: 3.1,  zoom: 3.60 },  // 4: konveksi meter+cable
  { sp: 0.67, lx: +9.0,   ly: 1.4, lz: 0.0,  zoom: 2.00 },  // 5: laundry shop interior
  { sp: 0.79, lx: +6.25,  ly: 3.5, lz: 3.1,  zoom: 3.60 },  // 6: laundry meter+cable
  { sp: 0.90, lx:  0.0,   ly: 2.0, lz: 2.0,  zoom: 0.95 },  // 7: finale
  { sp: 1.00, lx:  0.0,   ly: 2.0, lz: 2.0,  zoom: 0.95 },  // anchor
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
  [-9.0,  0.90, 1.0],   // 1: Kelontong inside counter, shocked
  [-11.75,2.80, 3.0],   // 2: Kelontong cable clamp wall
  [ 0.0,  0.90, 1.0],   // 3: Konveksi sewing table, shocked
  [ -2.75,2.80, 3.0],   // 4: Konveksi cable clamp wall
  [ 9.0,  0.65, 1.5],   // 5: Laundry baskets, shocked
  [ 6.25, 2.80, 3.0],   // 6: Laundry cable clamp wall
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
      camera.position.set(lookAt.x + 11, lookAt.y + 7, lookAt.z + 11);
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
    // Remove floating shadow disc under mascot
    mascot.refs.shadowPlane.visible = false;

    // ── Collect drop-cable stubs for toggling during clamp beats ──
    const dropStubs: THREE.Mesh[] = [];
    shops.group.traverse((o) => {
      if (o instanceof THREE.Mesh && (o.userData as { isDropStub?: boolean }).isDropStub) {
        dropStubs.push(o);
      }
    });

    // ── Dynamic split-cable lines (span→mascot, mascot→meter) ─
    const splitLineMat = new THREE.LineBasicMaterial({ color: 0x1A1A1A, linewidth: 2 });
    const splitPos1 = new Float32Array(6);
    const splitPos2 = new Float32Array(6);
    const splitBuf1 = new THREE.BufferAttribute(splitPos1, 3);
    const splitBuf2 = new THREE.BufferAttribute(splitPos2, 3);
    const splitGeo1 = new THREE.BufferGeometry();
    const splitGeo2 = new THREE.BufferGeometry();
    splitGeo1.setAttribute('position', splitBuf1);
    splitGeo2.setAttribute('position', splitBuf2);
    const splitLine1 = new THREE.Line(splitGeo1, splitLineMat);
    const splitLine2 = new THREE.Line(splitGeo2, splitLineMat.clone() as THREE.LineBasicMaterial);
    splitLine1.visible = false;
    splitLine2.visible = false;
    scene.add(splitLine1, splitLine2);

    // ── Steam particles (mascot shocked state) ───────────────
    const STEAM_N = 36;
    const steamPts   = new Float32Array(STEAM_N * 3);
    const steamVelX  = new Float32Array(STEAM_N);
    const steamVelZ  = new Float32Array(STEAM_N);
    const steamT     = new Float32Array(STEAM_N);
    for (let i = 0; i < STEAM_N; i++) {
      steamT[i]    = 1.1; // force reset on first frame → all spawn at head
      steamVelX[i] = (Math.random() - 0.5) * 0.9;
      steamVelZ[i] = (Math.random() - 0.5) * 0.9;
    }
    const steamGeo = new THREE.BufferGeometry();
    steamGeo.setAttribute('position', new THREE.BufferAttribute(steamPts, 3));
    const steamMat = new THREE.PointsMaterial({
      size: 0.22, color: 0xDDDDDD, transparent: true, opacity: 0.70,
      depthWrite: false,
    });
    const steamPoints = new THREE.Points(steamGeo, steamMat);
    scene.add(steamPoints);

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

      // ── Mascot scale: constant apparent size regardless of zoom ──
      const mascotScale = 0.90 / Math.max(currentZoom, 0.5);
      mascot.refs.root.scale.setScalar(mascotScale);

      // ── Clamping beats: arm pose, face wall, split cables ────────
      const isClamping = subBeat === 2 || subBeat === 4 || subBeat === 6;
      const isShocked  = MASCOT_MOODS[subBeat] === 'shocked';
      const meterPositions = [shops.meterPos1, shops.meterPos2, shops.meterPos3];
      const shopIdx = subBeat === 2 ? 0 : subBeat === 4 ? 1 : 2;

      if (isClamping) {
        // Arm reaches toward cable
        mascot.refs.armRight.rotation.z = lerp(mascot.refs.armRight.rotation.z, -1.6, 0.06);
        mascot.refs.armRight.rotation.x = lerp(mascot.refs.armRight.rotation.x,  0.8, 0.06);
        // Face wall (-z direction)
        mascot.refs.root.rotation.y += (0 - mascot.refs.root.rotation.y) * 0.08;

        // Show split-cable (span→mascot→meter), hide static stub
        splitLine1.visible = true;
        splitLine2.visible = true;
        dropStubs.forEach((m) => { m.visible = false; });
        const mp = meterPositions[shopIdx];
        const clampX = currentMascotPos.x;
        const clampY = currentMascotPos.y + 0.5 * mascotScale;
        const clampZ = currentMascotPos.z - 0.2;
        splitPos1.set([mp.x, 6.68, 3.80, clampX, clampY, clampZ]);
        splitBuf1.needsUpdate = true;
        splitPos2.set([clampX, clampY, clampZ, mp.x, mp.y + 0.3, mp.z + 0.05]);
        splitBuf2.needsUpdate = true;
      } else {
        mascot.refs.armRight.rotation.z = lerp(mascot.refs.armRight.rotation.z, 0, 0.06);
        mascot.refs.armRight.rotation.x = lerp(mascot.refs.armRight.rotation.x, 0, 0.06);
        // Hide split-cable, show static stub
        splitLine1.visible = false;
        splitLine2.visible = false;
        dropStubs.forEach((m) => { m.visible = true; });
        // Face camera
        const faceDir = new THREE.Vector3(
          camera.position.x - currentMascotPos.x,
          0,
          camera.position.z - currentMascotPos.z,
        );
        if (faceDir.lengthSq() > 0.01) {
          const angle = Math.atan2(faceDir.x, faceDir.z);
          mascot.refs.root.rotation.y += (angle - mascot.refs.root.rotation.y) * 0.08;
        }
      }

      // ── Body colour: red when shocked, orange otherwise ──────────
      const bodyMat = mascot.refs.bodyMesh.material as THREE.MeshStandardMaterial;
      const faceMat = mascot.refs.facePanel.material as THREE.MeshStandardMaterial;
      if (isShocked) {
        bodyMat.color.setHex(0xCC2222);
        bodyMat.emissive.setHex(0x660000);
        bodyMat.emissiveIntensity = 0.25 + Math.sin(time * 9) * 0.15;
        faceMat.color.setHex(0xFFBBBB);
      } else {
        bodyMat.color.setHex(0xFFA726);
        bodyMat.emissive.setHex(0x000000);
        bodyMat.emissiveIntensity = 0;
        faceMat.color.setHex(0xFFF8E7);
      }

      // ── Steam effect when shocked ────────────────────────────────
      steamPoints.visible = isShocked;
      if (isShocked) {
        const headY = currentMascotPos.y + 1.4 * mascotScale;
        for (let i = 0; i < STEAM_N; i++) {
          steamT[i] += delta * 1.1;
          if (steamT[i] > 1) {
            steamT[i] = 0;
            steamPts[i * 3]     = currentMascotPos.x + (Math.random() - 0.5) * 0.4;
            steamPts[i * 3 + 1] = headY;
            steamPts[i * 3 + 2] = currentMascotPos.z + (Math.random() - 0.5) * 0.3;
            steamVelX[i] = (Math.random() - 0.5) * 0.9;
            steamVelZ[i] = (Math.random() - 0.5) * 0.9;
          }
          steamPts[i * 3]     += steamVelX[i] * delta * 0.5;
          steamPts[i * 3 + 1] += (1.0 + steamT[i] * 0.6) * delta;
          steamPts[i * 3 + 2] += steamVelZ[i] * delta * 0.5;
        }
        steamMat.opacity = 0.55 + Math.sin(time * 3) * 0.15;
        (steamPoints.geometry.getAttribute('position') as THREE.BufferAttribute).needsUpdate = true;
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
