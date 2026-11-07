'use client';

import { useEffect, useRef, useState } from 'react';
import Reveal from '@/components/Reveal';
import { useReducedMotion } from '@/components/hooks';

/** Menghitung naik dari 0 ke target begitu `active` menjadi true. */
function useCountUp(target: number, active: boolean, reduced: boolean, ms = 1300) {
  const [v, setV] = useState(reduced ? target : 0);
  useEffect(() => {
    if (!active) return;
    if (reduced) {
      setV(target);
      return;
    }
    let raf = 0;
    const t0 = performance.now();
    const tick = (t: number) => {
      const k = Math.min(1, (t - t0) / ms);
      setV(target * (1 - Math.pow(1 - k, 3)));
      if (k < 1) raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [active, reduced, target, ms]);
  return v;
}

const fmt = (n: number, d: number) => n.toFixed(d).replace('.', ',');

export default function ProblemStats() {
  const reduced = useReducedMotion();
  const ref = useRef<HTMLElement>(null);
  const [seen, setSeen] = useState(false);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    if (typeof IntersectionObserver === 'undefined') {
      setSeen(true);
      return;
    }
    const io = new IntersectionObserver(
      ([e]) => {
        if (e.isIntersecting) {
          setSeen(true);
          io.disconnect();
        }
      },
      { threshold: 0, rootMargin: '0px 0px -25% 0px' },
    );
    io.observe(el);
    return () => io.disconnect();
  }, []);

  const one = useCountUp(1, seen, reduced, 700);
  const lo = useCountUp(2.8, seen, reduced);
  const hi = useCountUp(4.2, seen, reduced);

  return (
    <section id="masalah" ref={ref} className="ps-band" aria-labelledby="h-masalah">
      <div className="sheet-w">
        <Reveal>
          <h2 id="h-masalah" className="ps-title">
            Tagihannya nyata. <em>Dan sering terlambat disadari.</em>
          </h2>
        </Reveal>

        <div className="ps-grid">
          <Reveal delay={60} className="ps-stat">
            <p className="ps-num" aria-label="1 titik">
              <span aria-hidden="true">{Math.round(one)}</span>
              <small aria-hidden="true">titik</small>
            </p>
            <p className="ps-cap">ukur di panel utama sudah cukup untuk mengenali tiap mesin, tanpa memasang alat di setiap mesin</p>
          </Reveal>

          <Reveal delay={140} className="ps-stat">
            <p className="ps-num" aria-label="Rp0">
              <span aria-hidden="true">Rp0</span>
            </p>
            <p className="ps-cap">kredit untuk kelebihan listrik surya yang dikirim ke PLN sejak Permen ESDM No. 2 Tahun 2024, jadi waktu pemakaian yang menentukan</p>
          </Reveal>

          <Reveal delay={220} className="ps-stat">
            <p className="ps-num" aria-label="2,8 sampai 4,2 tahun">
              <span aria-hidden="true">{fmt(lo, 1)}–{fmt(hi, 1)}</span>
              <small aria-hidden="true">tahun</small>
            </p>
            <p className="ps-cap">perkiraan waktu balik modal PLTS pada profil UMKM yang diuji di simulator</p>
          </Reveal>
        </div>

        <p className="ps-note">Angka balik modal adalah perkiraan dari simulasi dan belum diverifikasi di lapangan.</p>
      </div>
    </section>
  );
}
