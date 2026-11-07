'use client';

import { useEffect, useRef, useState, useCallback } from 'react';
import * as THREE from 'three';
import { type MascotKilo, type MoodState, createMascotKilo } from '@/components/3d/MascotKilo';

// ─── Types ────────────────────────────────────────────────────────────────────

interface MoodButton {
  key: MoodState;
  label: string;
  color: string;
  activeColor: string;
}

const MOOD_BUTTONS: MoodButton[] = [
  {
    key: 'idle',
    label: 'Idle',
    color: 'bg-[var(--bg-surface)] text-[var(--metal-mid)] border border-[var(--border-medium)]',
    activeColor: 'bg-[var(--metal-dark)] text-white border border-[var(--metal-dark)]',
  },
  {
    key: 'shocked',
    label: '⚡ Beban Puncak',
    color: 'bg-[var(--grid-alert-bg)] text-[var(--grid-alert)] border border-[var(--grid-alert)]',
    activeColor: 'bg-[var(--grid-alert)] text-white border border-[var(--grid-alert)]',
  },
  {
    key: 'scanning',
    label: '🔍 Scan NILM',
    color: 'bg-[var(--eco-light)] text-[var(--eco-dark)] border border-[var(--eco-primary)]',
    activeColor: 'bg-[var(--eco-primary)] text-white border border-[var(--eco-primary)]',
  },
  {
    key: 'happy',
    label: '☀️ Hemat Surya',
    color: 'bg-[var(--solar-light)] text-[var(--solar-dark)] border border-[var(--solar-primary)]',
    activeColor: 'bg-[var(--solar-primary)] text-white border border-[var(--solar-primary)]',
  },
];

// ─── Component ────────────────────────────────────────────────────────────────

export default function MascotTestPage() {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const sceneRef = useRef<{
    renderer: THREE.WebGLRenderer;
    scene: THREE.Scene;
    camera: THREE.PerspectiveCamera;
    mascot: MascotKilo;
    animId: number;
    clock: THREE.Clock;
  } | null>(null);

  const [activeMood, setActiveMood] = useState<MoodState>('idle');
  const [wireframe, setWireframe] = useState(false);

  // ── Init Three.js ──────────────────────────────────────────

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    // Renderer
    const renderer = new THREE.WebGLRenderer({
      canvas,
      antialias: true,
      alpha: false,
    });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.setSize(canvas.clientWidth, canvas.clientHeight);
    renderer.shadowMap.enabled = true;
    renderer.shadowMap.type = THREE.PCFSoftShadowMap;
    renderer.setClearColor(0xFBF9F4, 1);
    renderer.outputColorSpace = THREE.SRGBColorSpace;
    renderer.toneMapping = THREE.ACESFilmicToneMapping;
    renderer.toneMappingExposure = 1.1;

    // Scene
    const scene = new THREE.Scene();
    scene.background = new THREE.Color(0xFBF9F4);

    // Camera — PerspectiveCamera FOV 35, isometric-like position
    const camera = new THREE.PerspectiveCamera(
      35,
      canvas.clientWidth / canvas.clientHeight,
      0.1,
      100,
    );
    camera.position.set(4, 3, 5);
    camera.lookAt(0, 0.4, 0);

    // ── Lighting (Clay Style) ────────────────────────────────

    const hemi = new THREE.HemisphereLight(0xFFFFFF, 0xE8E2D5, 0.75);
    scene.add(hemi);

    const sun = new THREE.DirectionalLight(0xFFFFFF, 1.6);
    sun.position.set(6, 8, 6);
    sun.castShadow = true;
    sun.shadow.mapSize.set(1024, 1024);
    sun.shadow.camera.near = 0.5;
    sun.shadow.camera.far = 30;
    sun.shadow.camera.left = -4;
    sun.shadow.camera.right = 4;
    sun.shadow.camera.top = 4;
    sun.shadow.camera.bottom = -4;
    sun.shadow.bias = -0.0001;
    scene.add(sun);

    // Soft fill light from front-left
    const fill = new THREE.DirectionalLight(0xFFE6C7, 0.5);
    fill.position.set(-3, 2, 4);
    scene.add(fill);

    // Rim light from back
    const rim = new THREE.DirectionalLight(0xD2F5E1, 0.35);
    rim.position.set(-2, 4, -5);
    scene.add(rim);

    // ── Mascot ───────────────────────────────────────────────

    const mascot = createMascotKilo();
    scene.add(mascot.refs.root);

    // ── Animation Loop ───────────────────────────────────────

    const clock = new THREE.Clock();
    let animId = 0;

    function animate() {
      animId = requestAnimationFrame(animate);
      const delta = clock.getDelta();
      const time = clock.getElapsedTime();
      mascot.update(delta, time);
      renderer.render(scene, camera);
    }

    animate();

    sceneRef.current = { renderer, scene, camera, mascot, animId, clock };

    // ── Resize handler ───────────────────────────────────────

    function onResize() {
      if (!canvas) return;
      const w = canvas.clientWidth;
      const h = canvas.clientHeight;
      renderer.setSize(w, h, false);
      camera.aspect = w / h;
      camera.updateProjectionMatrix();
    }

    window.addEventListener('resize', onResize);

    return () => {
      cancelAnimationFrame(animId);
      window.removeEventListener('resize', onResize);
      mascot.dispose();
      renderer.dispose();
      sceneRef.current = null;
    };
  }, []);

  // ── Mouse pointer tracking ────────────────────────────────

  const handleMouseMove = useCallback((e: React.MouseEvent<HTMLCanvasElement>) => {
    if (!canvasRef.current || !sceneRef.current) return;
    const rect = canvasRef.current.getBoundingClientRect();
    const x = ((e.clientX - rect.left) / rect.width) * 2 - 1;
    const y = -((e.clientY - rect.top) / rect.height) * 2 + 1;
    sceneRef.current.mascot.setPointer(x, y);
  }, []);

  // ── Mood selector ─────────────────────────────────────────

  const handleMood = useCallback((mood: MoodState) => {
    setActiveMood(mood);
    if (sceneRef.current) {
      sceneRef.current.mascot.setMood(mood);
    }
  }, []);

  // ── Wireframe toggle ──────────────────────────────────────

  const handleWireframe = useCallback(() => {
    setWireframe((prev) => {
      const next = !prev;
      if (sceneRef.current) {
        sceneRef.current.scene.traverse((obj) => {
          if (obj instanceof THREE.Mesh) {
            const mats = Array.isArray(obj.material) ? obj.material : [obj.material];
            mats.forEach((m) => {
              if (m instanceof THREE.MeshStandardMaterial) {
                m.wireframe = next;
              }
            });
          }
        });
      }
      return next;
    });
  }, []);

  // ─────────────────────────────────────────────────────────────────────────

  return (
    <div
      style={{ background: 'var(--bg-paper)' }}
      className="relative w-full h-screen flex flex-col overflow-hidden"
    >
      {/* Header */}
      <header className="absolute top-0 left-0 right-0 z-10 flex items-center justify-between px-6 pt-5 pb-4 pointer-events-none">
        <div>
          <span
            className="kicker block mb-1"
            style={{ color: 'var(--eco-primary)' }}
          >
            Nota Listrik · UNS Hackathon 2026
          </span>
          <h1
            className="heading text-2xl"
            style={{ color: 'var(--metal-dark)' }}
          >
            Si Kilo — Test Bench
          </h1>
        </div>
        <div
          className="text-right"
          style={{ color: 'var(--metal-light)', fontSize: '0.72rem' }}
        >
          <p className="metric">THREE.js Procedural</p>
          <p className="metric">No External Models</p>
        </div>
      </header>

      {/* Three.js Canvas */}
      <canvas
        ref={canvasRef}
        className="w-full h-full block cursor-crosshair"
        onMouseMove={handleMouseMove}
        style={{ touchAction: 'none' }}
      />

      {/* Mood state label */}
      <div
        className="absolute top-24 left-1/2 -translate-x-1/2 pointer-events-none"
      >
        <span
          className="metric text-xs px-3 py-1 rounded-full border"
          style={{
            background: 'var(--bg-surface)',
            borderColor: 'var(--border-medium)',
            color: 'var(--metal-mid)',
          }}
        >
          mood: {activeMood}
        </span>
      </div>

      {/* Bottom Controls */}
      <div className="absolute bottom-6 left-0 right-0 flex justify-center gap-3 px-4 flex-wrap">
        {MOOD_BUTTONS.map((btn) => (
          <button
            key={btn.key}
            onClick={() => handleMood(btn.key)}
            className={[
              'px-4 py-2.5 rounded-full text-sm font-semibold transition-all duration-200',
              activeMood === btn.key ? btn.activeColor : btn.color,
              'hover:scale-105 active:scale-95 shadow-sm',
            ].join(' ')}
            style={{ fontFamily: 'var(--font-display)' }}
          >
            {btn.label}
          </button>
        ))}

        {/* Divider */}
        <div
          className="w-px mx-1"
          style={{ background: 'var(--border-medium)' }}
        />

        {/* Wireframe toggle */}
        <button
          onClick={handleWireframe}
          className={[
            'px-4 py-2.5 rounded-full text-sm font-semibold transition-all duration-200',
            wireframe
              ? 'bg-[var(--metal-dark)] text-white'
              : 'bg-[var(--bg-surface)] text-[var(--metal-mid)] border border-[var(--border-medium)]',
            'hover:scale-105 active:scale-95 shadow-sm',
          ].join(' ')}
          style={{ fontFamily: 'var(--font-display)' }}
        >
          Wireframe
        </button>
      </div>

      {/* Interaction hint */}
      <div
        className="absolute bottom-20 left-1/2 -translate-x-1/2 pointer-events-none"
        style={{ color: 'var(--metal-light)', fontSize: '0.7rem' }}
      >
        <p className="text-center">Gerakkan kursor untuk eye-tracking</p>
      </div>
    </div>
  );
}
