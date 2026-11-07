'use client';

import { useEffect, useRef } from 'react';

const PATH = 'M20 600C9 540 31 500 20 440C9 380 9 340 20 280C31 220 31 180 20 120C9 60 15 40 20 22';
const BULBS = [0.1, 0.22, 0.34, 0.46, 0.58, 0.7, 0.82];

/** Kabel listrik di tepi kiri yang "menyala" seiring halaman di-scroll (padanan vine EcoPatch). Hanya di layar lebar. */
export default function PowerVine() {
  const rootRef = useRef<HTMLDivElement>(null);
  const wireRef = useRef<SVGPathElement>(null);
  const inRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const sheet = rootRef.current?.closest('.sheet') as HTMLElement | null;
    const wire = wireRef.current;
    const inner = inRef.current;
    if (!sheet || !wire || !inner) return;
    const bulbs = Array.from(inner.querySelectorAll<SVGElement>('.pv-bulb'));
    let queued = false;
    const update = () => {
      queued = false;
      if (!wire.getBoundingClientRect().height) return;
      const r = sheet.getBoundingClientRect();
      const p = Math.max(0, Math.min(1, (window.innerHeight - r.top) / r.height));
      wire.style.strokeDashoffset = (1 - p).toFixed(4);
      const gone = Math.max(0, Math.min(1, (window.innerHeight - r.bottom) / (window.innerHeight * 0.22)));
      inner.style.opacity = (1 - gone).toFixed(3);
      inner.style.transform = `translateY(${(gone * 40).toFixed(1)}px)`;
      bulbs.forEach((b) => b.classList.toggle('on', p >= Number(b.dataset.t)));
    };
    const onScroll = () => {
      if (queued) return;
      queued = true;
      requestAnimationFrame(update);
    };
    window.addEventListener('scroll', onScroll, { passive: true });
    window.addEventListener('resize', onScroll);
    update();
    return () => {
      window.removeEventListener('scroll', onScroll);
      window.removeEventListener('resize', onScroll);
    };
  }, []);

  return (
    <div ref={rootRef} className="pvine" aria-hidden="true">
      <div ref={inRef} className="pvine-in">
        <svg viewBox="0 0 40 600" preserveAspectRatio="xMidYMax meet">
          <path className="pv-track" d={PATH} />
          <path ref={wireRef} className="pv-wire" pathLength={1} d={PATH} />
          {BULBS.map((t, i) => (
            <circle key={t} className="pv-bulb" data-t={t} cx={i % 2 ? 29 : 11} cy={570 - t * 540} r={5.5} />
          ))}
          <circle className="pv-bulb top" data-t={0.97} cx={20} cy={20} r={7} />
        </svg>
      </div>
    </div>
  );
}
