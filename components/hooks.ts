'use client';

import { useEffect, useRef, useState, type RefObject } from 'react';

export function useReducedMotion() {
  const [reduced, setReduced] = useState(false);
  useEffect(() => {
    const mq = window.matchMedia('(prefers-reduced-motion: reduce)');
    setReduced(mq.matches);
    const on = () => setReduced(mq.matches);
    mq.addEventListener('change', on);
    return () => mq.removeEventListener('change', on);
  }, []);
  return reduced;
}

/** Every `.kilo-av` inside `root` looks toward the pointer (sets --gx/--gy on it). */
export function useGaze(root: RefObject<HTMLElement | null>, reduced: boolean) {
  useEffect(() => {
    if (reduced) return;
    const el = root.current;
    if (!el) return;
    let px = 0;
    let py = 0;
    let queued = false;
    const gaze = () => {
      queued = false;
      el.querySelectorAll<SVGElement>('.kilo-av').forEach((av) => {
        const r = av.getBoundingClientRect();
        if (!r.width || r.bottom < 0 || r.top > window.innerHeight) return;
        const dx = px - (r.left + r.width * 0.5);
        const dy = py - (r.top + r.height * 0.45);
        const d = Math.hypot(dx, dy) || 1;
        const k = Math.min(1, d / 260);
        av.style.setProperty('--gx', `${((dx / d) * 5 * k).toFixed(1)}px`);
        av.style.setProperty('--gy', `${((dy / d) * 3.5 * k).toFixed(1)}px`);
      });
    };
    const onMove = (e: PointerEvent) => {
      if (e.pointerType === 'touch') return;
      px = e.clientX;
      py = e.clientY;
      if (!queued) {
        queued = true;
        requestAnimationFrame(gaze);
      }
    };
    window.addEventListener('pointermove', onMove, { passive: true });
    return () => window.removeEventListener('pointermove', onMove);
  }, [root, reduced]);
}

/** Calls `fn` once, the first time `ref` is at least `threshold` visible. */
export function useOnceInView(ref: RefObject<HTMLElement | null>, fn: () => void, threshold = 0.3) {
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const io = new IntersectionObserver(
      ([entry]) => {
        if (!entry.isIntersecting) return;
        io.disconnect();
        fn();
      },
      { threshold },
    );
    io.observe(el);
    return () => io.disconnect();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ref, threshold]);
}

/** Eases a displayed number toward `target`, starting from 0 on mount. */
export function useCountUp(target: number, reduced: boolean, ms = 700) {
  const [v, setV] = useState(0);
  const from = useRef(0);
  useEffect(() => {
    if (reduced) {
      setV(target);
      from.current = target;
      return;
    }
    const start = performance.now();
    const a = from.current;
    let raf = 0;
    const tick = (t: number) => {
      const k = Math.min(1, (t - start) / ms);
      const cur = a + (target - a) * (1 - Math.pow(1 - k, 3));
      setV(cur);
      from.current = cur;
      if (k < 1) raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [target, reduced, ms]);
  return v;
}
