/**
 * Si Kilo — Procedural 3D Mascot
 * Smart energy meter AI agent built entirely from Three.js primitives.
 * No external 3D model files (.glb/.obj/.gltf) are used.
 */

import * as THREE from 'three';
import { RoundedBoxGeometry } from 'three/examples/jsm/geometries/RoundedBoxGeometry.js';

export type MoodState = 'idle' | 'shocked' | 'scanning' | 'happy';

interface MascotRefs {
  root: THREE.Group;
  body: THREE.Group;
  bodyMesh: THREE.Mesh;
  facePanel: THREE.Mesh;
  eyeLeft: THREE.Mesh;
  eyeRight: THREE.Mesh;
  pupilLeft: THREE.Mesh;
  pupilRight: THREE.Mesh;
  catchlightLeft: THREE.Mesh;
  catchlightRight: THREE.Mesh;
  blushLeft: THREE.Mesh;
  blushRight: THREE.Mesh;
  mouth: THREE.Mesh;
  mouthCircle: THREE.Mesh;
  antennaPole: THREE.Mesh;
  antennaGem: THREE.Mesh;
  visorLeft: THREE.Mesh;
  visorRight: THREE.Mesh;
  armRight: THREE.Group;
  shadowPlane: THREE.Mesh;
}

interface MascotState {
  currentRotY: number;
  currentRotX: number;
  targetRotY: number;
  targetRotX: number;
  mood: MoodState;
  jumpOffset: number;
  jumpVelocity: number;
  eyeScaleTarget: number;
  eyeScaleCurrent: number;
}

export interface MascotKilo {
  refs: MascotRefs;
  state: MascotState;
  update: (delta: number, time: number) => void;
  setMood: (mood: MoodState) => void;
  setPointer: (x: number, y: number) => void;
  dispose: () => void;
}

// ─── Material Helpers ────────────────────────────────────────────────────────

function clay(color: number, roughness = 0.5, metalness = 0.0): THREE.MeshStandardMaterial {
  return new THREE.MeshStandardMaterial({ color, roughness, metalness });
}

// ─── Geometry Builders ───────────────────────────────────────────────────────

function buildBody(): THREE.Mesh {
  const geo = new RoundedBoxGeometry(1.2, 1.4, 0.9, 4, 0.22);
  const mat = clay(0xFFA726, 0.35, 0.05);
  const mesh = new THREE.Mesh(geo, mat);
  mesh.castShadow = true;
  return mesh;
}

function buildFacePanel(): THREE.Mesh {
  const geo = new RoundedBoxGeometry(0.9, 0.78, 0.05, 2, 0.08);
  const mat = clay(0xFFF8E7, 0.2, 0.0);
  const mesh = new THREE.Mesh(geo, mat);
  mesh.position.set(0, 0.05, 0.46);
  mesh.castShadow = false;
  return mesh;
}

function buildEye(side: -1 | 1): { sphere: THREE.Mesh; pupil: THREE.Mesh; catchlight: THREE.Mesh } {
  const sphere = new THREE.Mesh(
    new THREE.SphereGeometry(0.075, 16, 16),
    clay(0xFFF8E7, 0.15, 0.0),
  );
  sphere.position.set(side * 0.22, 0.12, 0.50);

  const pupil = new THREE.Mesh(
    new THREE.SphereGeometry(0.055, 12, 12),
    clay(0x1F2937, 0.1, 0.0),
  );
  pupil.position.set(0, 0, 0.03);

  const catchlight = new THREE.Mesh(
    new THREE.SphereGeometry(0.022, 8, 8),
    new THREE.MeshStandardMaterial({ color: 0xFFFFFF, roughness: 0.05, metalness: 0.0 }),
  );
  catchlight.position.set(0.02, 0.02, 0.055);

  sphere.add(pupil, catchlight);
  return { sphere, pupil, catchlight };
}

function buildBlush(side: -1 | 1): THREE.Mesh {
  const geo = new THREE.CylinderGeometry(0.07, 0.07, 0.01, 16);
  const mat = new THREE.MeshStandardMaterial({
    color: 0xFF8A65,
    roughness: 0.6,
    transparent: true,
    opacity: 0.85,
  });
  const mesh = new THREE.Mesh(geo, mat);
  mesh.rotation.x = Math.PI / 2;
  mesh.position.set(side * 0.32, -0.04, 0.49);
  return mesh;
}

function buildMouth(): THREE.Mesh {
  const geo = new THREE.TorusGeometry(0.08, 0.018, 8, 16, Math.PI);
  const mat = clay(0x1F2937, 0.3);
  const mesh = new THREE.Mesh(geo, mat);
  mesh.rotation.z = Math.PI;
  mesh.position.set(0, -0.08, 0.50);
  return mesh;
}

function buildMouthCircle(): THREE.Mesh {
  const geo = new THREE.TorusGeometry(0.04, 0.016, 8, 16);
  const mat = clay(0x1F2937, 0.3);
  const mesh = new THREE.Mesh(geo, mat);
  mesh.position.set(0, -0.08, 0.50);
  mesh.visible = false;
  return mesh;
}

function buildAntennaPole(): THREE.Mesh {
  const geo = new THREE.CylinderGeometry(0.03, 0.035, 0.28, 10);
  const mat = new THREE.MeshStandardMaterial({ color: 0x4B5563, roughness: 0.4, metalness: 0.8 });
  const mesh = new THREE.Mesh(geo, mat);
  mesh.position.set(0, 0.82, 0);
  mesh.castShadow = true;
  return mesh;
}

function buildAntennaGem(): THREE.Mesh {
  const geo = new THREE.OctahedronGeometry(0.13);
  const mat = new THREE.MeshStandardMaterial({
    color: 0x2FBF71,
    emissive: new THREE.Color(0x2FBF71),
    emissiveIntensity: 1.2,
    roughness: 0.2,
    metalness: 0.1,
  });
  const mesh = new THREE.Mesh(geo, mat);
  mesh.position.set(0, 1.02, 0);
  mesh.castShadow = false;
  return mesh;
}

function buildVisor(side: -1 | 1): THREE.Mesh {
  const geo = new THREE.BoxGeometry(0.18, 0.09, 0.02);
  const mat = new THREE.MeshStandardMaterial({
    color: 0x2FBF71,
    transparent: true,
    opacity: 0.55,
    roughness: 0.1,
    metalness: 0.3,
    emissive: new THREE.Color(0x2FBF71),
    emissiveIntensity: 0.4,
  });
  const mesh = new THREE.Mesh(geo, mat);
  mesh.position.set(side * 0.22, 0.12, 0.54);
  mesh.visible = false;
  return mesh;
}

function buildRightArm(): THREE.Group {
  const group = new THREE.Group();

  // Upper arm cylinder
  const upperGeo = new THREE.CylinderGeometry(0.055, 0.065, 0.42, 10);
  const upperMat = clay(0xFFA726, 0.4, 0.05);
  const upper = new THREE.Mesh(upperGeo, upperMat);
  upper.rotation.z = -Math.PI / 4;
  upper.position.set(0, 0, 0);
  upper.castShadow = true;

  // CT-Clamp sensor body (split-core transformer shape)
  const clampGroup = new THREE.Group();

  const clampBodyGeo = new THREE.BoxGeometry(0.22, 0.14, 0.1);
  const clampMat = clay(0x111827, 0.5, 0.2);
  const clampBody = new THREE.Mesh(clampBodyGeo, clampMat);
  clampBody.castShadow = true;

  // Cable hole (through geometry via small inner cylinder)
  const holeGeo = new THREE.CylinderGeometry(0.028, 0.028, 0.14, 12);
  const holeMat = new THREE.MeshStandardMaterial({ color: 0x374151, roughness: 0.8 });
  const hole = new THREE.Mesh(holeGeo, holeMat);
  hole.rotation.x = Math.PI / 2;
  hole.position.set(0, 0, 0.001);

  // Split line (visual indicator)
  const splitGeo = new THREE.BoxGeometry(0.24, 0.008, 0.012);
  const splitMat = new THREE.MeshStandardMaterial({ color: 0x6B7280, roughness: 0.3, metalness: 0.6 });
  const split = new THREE.Mesh(splitGeo, splitMat);

  clampGroup.add(clampBody, hole, split);
  clampGroup.position.set(0.08, -0.26, 0.04);

  group.add(upper, clampGroup);
  group.position.set(0.68, -0.1, 0.1);
  return group;
}

function buildShadowPlane(): THREE.Mesh {
  const geo = new THREE.CircleGeometry(0.95, 32);
  const mat = new THREE.MeshStandardMaterial({
    color: 0xF4EFE6,
    roughness: 1.0,
    metalness: 0.0,
  });
  const mesh = new THREE.Mesh(geo, mat);
  mesh.rotation.x = -Math.PI / 2;
  mesh.position.y = -0.71;
  mesh.receiveShadow = true;
  return mesh;
}

// ─── Main Factory ────────────────────────────────────────────────────────────

export function createMascotKilo(): MascotKilo {
  const root = new THREE.Group();
  root.position.y = 0;

  const body = new THREE.Group();
  body.position.y = 0;
  root.add(body);

  // Build all meshes
  const bodyMesh = buildBody();
  bodyMesh.position.y = 0;
  body.add(bodyMesh);

  const facePanel = buildFacePanel();
  bodyMesh.add(facePanel);

  const leftEye = buildEye(-1);
  const rightEye = buildEye(1);
  bodyMesh.add(leftEye.sphere, rightEye.sphere);

  const blushLeft = buildBlush(-1);
  const blushRight = buildBlush(1);
  bodyMesh.add(blushLeft, blushRight);

  const mouth = buildMouth();
  const mouthCircle = buildMouthCircle();
  bodyMesh.add(mouth, mouthCircle);

  const antennaPole = buildAntennaPole();
  const antennaGem = buildAntennaGem();
  bodyMesh.add(antennaPole, antennaGem);

  const visorLeft = buildVisor(-1);
  const visorRight = buildVisor(1);
  bodyMesh.add(visorLeft, visorRight);

  const armRight = buildRightArm();
  bodyMesh.add(armRight);

  const shadowPlane = buildShadowPlane();
  root.add(shadowPlane);

  const refs: MascotRefs = {
    root,
    body,
    bodyMesh,
    facePanel,
    eyeLeft: leftEye.sphere,
    eyeRight: rightEye.sphere,
    pupilLeft: leftEye.pupil,
    pupilRight: rightEye.pupil,
    catchlightLeft: leftEye.catchlight,
    catchlightRight: rightEye.catchlight,
    blushLeft,
    blushRight,
    mouth,
    mouthCircle,
    antennaPole,
    antennaGem,
    visorLeft,
    visorRight,
    armRight,
    shadowPlane,
  };

  const state: MascotState = {
    currentRotY: 0,
    currentRotX: 0,
    targetRotY: 0,
    targetRotX: 0,
    mood: 'idle',
    jumpOffset: 0,
    jumpVelocity: 0,
    eyeScaleTarget: 1.0,
    eyeScaleCurrent: 1.0,
  };

  // ── Mood setter ───────────────────────────────────────────

  function setMood(mood: MoodState) {
    state.mood = mood;

    // Reset visuals first
    refs.mouth.visible = true;
    refs.mouthCircle.visible = false;
    refs.visorLeft.visible = false;
    refs.visorRight.visible = false;
    state.eyeScaleTarget = 1.0;

    const gemMat = refs.antennaGem.material as THREE.MeshStandardMaterial;
    gemMat.color.set(0x2FBF71);
    gemMat.emissive.set(0x2FBF71);

    if (mood === 'idle') {
      // Mouth: normal smile (default)
      refs.mouth.rotation.z = Math.PI;
      (refs.mouth.material as THREE.MeshStandardMaterial).color.set(0x1F2937);
    } else if (mood === 'shocked') {
      // Eyes: big scale
      state.eyeScaleTarget = 1.4;
      // Mouth: round 'O'
      refs.mouth.visible = false;
      refs.mouthCircle.visible = true;
      // Antenna: fast red flicker handled in update
      gemMat.color.set(0xEF4444);
      gemMat.emissive.set(0xEF4444);
    } else if (mood === 'scanning') {
      // Visor holographic
      refs.visorLeft.visible = true;
      refs.visorRight.visible = true;
      // Antenna constant bright green
      gemMat.emissiveIntensity = 2.2;
    } else if (mood === 'happy') {
      // Eyes squint — handled via scaleY in update
      state.eyeScaleTarget = 0.6;
      // Jump trigger
      state.jumpVelocity = 0.07;
    }
  }

  // ── Update loop ───────────────────────────────────────────

  function update(delta: number, time: number) {
    // Breathing
    const breathSin = Math.sin(time * 2.4);
    refs.bodyMesh.position.y = breathSin * 0.035;
    refs.bodyMesh.scale.y = 1.0 + breathSin * 0.02;
    refs.bodyMesh.scale.x = 1.0 - breathSin * 0.01;

    // Pointer eye tracking (LERP)
    state.currentRotY += (state.targetRotY - state.currentRotY) * 0.08;
    state.currentRotX += (state.targetRotX - state.currentRotX) * 0.08;
    refs.body.rotation.y = state.currentRotY;
    refs.body.rotation.x = state.currentRotX;

    // Eye scale interpolation
    state.eyeScaleCurrent += (state.eyeScaleTarget - state.eyeScaleCurrent) * 0.1;
    const es = state.eyeScaleCurrent;
    const squintY = state.mood === 'happy' ? es * 0.5 : es;
    refs.eyeLeft.scale.set(es, squintY, es);
    refs.eyeRight.scale.set(es, squintY, es);

    // Antenna gem animation per mood
    const gemMat = refs.antennaGem.material as THREE.MeshStandardMaterial;
    if (state.mood === 'idle') {
      gemMat.emissiveIntensity = 0.6 + Math.sin(time * 1.8) * 0.3;
      refs.antennaGem.rotation.y += delta * 0.6;
    } else if (state.mood === 'shocked') {
      // Fast red flicker
      const flicker = Math.sin(time * 18) > 0 ? 1.8 : 0.4;
      gemMat.emissiveIntensity = flicker;
      refs.antennaGem.rotation.y += delta * 4.0;
    } else if (state.mood === 'scanning') {
      gemMat.emissiveIntensity = 2.2;
      refs.antennaGem.rotation.y += delta * 1.2;
    } else if (state.mood === 'happy') {
      gemMat.emissiveIntensity = 1.0 + Math.sin(time * 4.0) * 0.4;
      refs.antennaGem.rotation.y += delta * 2.5;
    }

    // Jump physics (happy mood)
    if (state.mood === 'happy') {
      state.jumpVelocity -= delta * 0.28;
      state.jumpOffset += state.jumpVelocity;
      if (state.jumpOffset < 0) {
        state.jumpOffset = 0;
        state.jumpVelocity = 0;
        // Re-trigger small bounce
        state.jumpVelocity = 0.03;
      }
      refs.body.position.y = state.jumpOffset;
    } else {
      refs.body.position.y += (-refs.body.position.y) * 0.15;
      state.jumpOffset = refs.body.position.y;
    }
  }

  function setPointer(x: number, y: number) {
    state.targetRotY = Math.max(-0.25, Math.min(0.25, x * 0.25));
    state.targetRotX = Math.max(-0.15, Math.min(0.15, -y * 0.15));
  }

  function dispose() {
    root.traverse((obj) => {
      if (obj instanceof THREE.Mesh) {
        obj.geometry.dispose();
        if (Array.isArray(obj.material)) {
          obj.material.forEach((m) => m.dispose());
        } else {
          obj.material.dispose();
        }
      }
    });
  }

  return { refs, state, update, setMood, setPointer, dispose };
}
