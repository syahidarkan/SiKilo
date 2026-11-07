'use client';

import { useEffect, useRef, useState, type ReactNode } from 'react';
import { Plug, Clock, Smartphone, ClipboardList, Check, CheckCheck, Sun } from 'lucide-react';
import SectionHead from '@/components/SectionHead';
import KiloAvatar from '@/components/KiloAvatar';

/* ───────── util kecil ───────── */

/** true sebentar setelah komponen terpasang, supaya transisi CSS sempat berjalan */
function useArrived(delay = 60) {
  const [on, setOn] = useState(false);
  useEffect(() => {
    const t = setTimeout(() => setOn(true), delay);
    return () => clearTimeout(t);
  }, [delay]);
  return on;
}

/** menghitung naik dari 0 ke target */
function useCountUp(target: number, ms = 1100) {
  const [v, setV] = useState(0);
  useEffect(() => {
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
      setV(target);
      return;
    }
    let raf = 0;
    const t0 = performance.now();
    const tick = (t: number) => {
      const k = Math.min(1, (t - t0) / ms);
      setV(Math.round(target * (1 - Math.pow(1 - k, 3))));
      if (k < 1) raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [target, ms]);
  return v;
}

const tint = (c: string, pct: number) => `color-mix(in srgb, ${c} ${pct}%, var(--panel))`;
const ink = (c: string) => `color-mix(in srgb, ${c} 78%, var(--metal-dark))`;

/* ───────── demo 1: jejak beban ───────── */

const LOADS = [
  { name: 'Kompresor freezer', w: 85 },
  { name: 'Setrika uap', w: 62 },
  { name: 'Mesin cuci', w: 48 },
  { name: 'Lampu LED', w: 12 },
] as const;

function DemoBeban({ color }: { color: string }) {
  const on = useArrived();
  const total = useCountUp(LOADS.reduce((s, l) => s + l.w, 0));
  return (
    <div className="ft-win">
      <div className="ft-win-bar">
        <span>Beban toko sekarang</span>
        <span className="ft-live"><i /> langsung</span>
      </div>
      <div className="ft-total">
        <b>{total}</b> <span>W</span>
      </div>
      <div className="space-y-3.5 mt-5">
        {LOADS.map((l, i) => (
          <div key={l.name}>
            <div className="flex items-center justify-between text-xs mb-1.5">
              <span className="flex items-center gap-2" style={{ color: 'var(--metal-dark)', fontWeight: 600 }}>
                {l.name}
                {i === 0 && <span className="ft-tag" style={{ background: tint(color, 16), color: ink(color) }}>Paling boros</span>}
              </span>
              <span style={{ fontFamily: 'var(--font-mono)', fontWeight: 700, color: 'var(--metal-dark)' }}>{l.w} W</span>
            </div>
            <div className="ft-track">
              <div
                className="ft-fill"
                style={{
                  width: on ? `${l.w}%` : '0%',
                  background: i === 0 ? color : tint(color, 38),
                  transitionDelay: `${0.1 + i * 0.12}s`,
                }}
              />
            </div>
          </div>
        ))}
      </div>
      <p className="ft-note">Satu sensor di panel mengenali tiap mesin dari pola arusnya.</p>
    </div>
  );
}

/* ───────── demo 2: jadwal digeser ke jam matahari ───────── */

const H0 = 6;
const SPAN = 12;
const LANES = [
  { name: 'Mesin cuci', from: [6, 8], to: [10, 12], move: true },
  { name: 'Pengering', from: [8, 10], to: [11, 13], move: true },
  { name: 'Setrika uap', from: [7, 9], to: [12, 14], move: true },
  { name: 'Kompresor', from: [14, 16], to: [14, 16], move: false },
] as const;
const pos = (r: readonly [number, number]) => ({ left: `${((r[0] - H0) / SPAN) * 100}%`, width: `${((r[1] - r[0]) / SPAN) * 100}%` });

function DemoJadwal({ color }: { color: string }) {
  const after = useArrived(900);
  return (
    <div className="ft-win">
      <div className="ft-win-bar">
        <span>Jadwal mesin hari ini</span>
        <span className="ft-live" style={{ color: after ? 'var(--eco-dark)' : 'var(--metal-mid)' }}>{after ? 'Sudah diatur' : 'Sebelum diatur'}</span>
      </div>
      <div className="ft-sched">
        <div className="ft-sun" aria-hidden="true">
          <Sun size={14} /> <span>Jam matahari</span>
        </div>
        {LANES.map((l, i) => (
          <div key={l.name} className="ft-lane">
            <span className="ft-lane-name">{l.name}</span>
            <div className="ft-lane-track">
              <div
                className="ft-block"
                style={{
                  ...pos(after ? l.to : l.from),
                  background: l.move ? color : 'var(--metal-light)',
                  transitionDelay: `${i * 0.12}s`,
                }}
              />
            </div>
          </div>
        ))}
        <div className="ft-hours" aria-hidden="true">
          {[6, 9, 12, 15, 18].map((h) => (
            <span key={h} className={h === 9 || h === 15 ? 'ft-h-mid' : ''} style={{ left: `${((h - H0) / SPAN) * 100}%` }}>{String(h).padStart(2, '0')}.00</span>
          ))}
        </div>
      </div>
      <p className="ft-note">Mesin yang bisa ditunda dipindah ke jam terik, saat panel surya menghasilkan paling banyak.</p>
    </div>
  );
}

/* ───────── demo 3: WhatsApp ───────── */

const CHAT: { me?: boolean; text: string }[] = [
  { text: 'Matahari terik pukul 10.00 sampai 14.00. Cuci dan setrika bisa dinyalakan sekarang.' },
  { me: true, text: 'Oke, jalankan.' },
  { text: 'Siap. Tagihan pekan ini juga lebih rendah daripada pekan lalu.' },
];

function DemoWA() {
  const [n, setN] = useState(0);
  const [typing, setTyping] = useState(false);
  useEffect(() => {
    const timers: ReturnType<typeof setTimeout>[] = [];
    let t = 500;
    CHAT.forEach((m, i) => {
      if (!m.me) timers.push(setTimeout(() => setTyping(true), t));
      t += m.me ? 900 : 1100;
      timers.push(setTimeout(() => { setTyping(false); setN(i + 1); }, t));
    });
    return () => timers.forEach(clearTimeout);
  }, []);
  return (
    <div className="ft-phone">
      <div className="ft-phone-head">
        <KiloAvatar />
        <div>
          <b>Si Kilo</b>
          <span>{typing ? 'sedang mengetik…' : 'online'}</span>
        </div>
      </div>
      <div className="ft-phone-body">
        {CHAT.slice(0, n).map((m, i) => (
          <div key={i} className={`ft-bub ${m.me ? 'me' : ''}`}>
            {m.text}
            {m.me && <CheckCheck size={13} className="ft-ticks" />}
          </div>
        ))}
        {typing && (
          <div className="ft-bub typing" aria-hidden="true">
            <i /><i /><i />
          </div>
        )}
      </div>
    </div>
  );
}

/* ───────── demo 4: rapor kelayakan ───────── */

function DemoRapor({ color }: { color: string }) {
  const on = useArrived(200);
  return (
    <div className="ft-win ft-doc">
      <div className="ft-win-bar">
        <span>Rapor kelayakan PLTS</span>
        <span style={{ fontFamily: 'var(--font-mono)' }}>Lamia Laundry</span>
      </div>
      <div className="ft-stamp-row">
        <div className="ft-stamp" style={{ color: 'var(--eco-dark)', opacity: on ? 1 : 0, transform: on ? 'rotate(-6deg) scale(1)' : 'rotate(-6deg) scale(1.8)' }}>
          <Check size={16} strokeWidth={3} /> LAYAK
        </div>
      </div>
      {([['Konsumsi terukur', '482 kWh per bulan'], ['PLTS optimal', '3,2 kWp'], ['Hemat per tahun', 'Rp17.040.000']] as const).map(([k, v], i) => (
        <div key={k} className="ft-row" style={{ opacity: on ? 1 : 0, transform: on ? 'none' : 'translateY(8px)', transitionDelay: `${0.1 + i * 0.1}s` }}>
          <span>{k}</span>
          <b>{v}</b>
        </div>
      ))}
      <div className="mt-4">
        <div className="flex justify-between text-xs mb-1.5">
          <span style={{ color: 'var(--metal-mid)' }}>Balik modal</span>
          <b style={{ fontFamily: 'var(--font-mono)', color: 'var(--metal-dark)' }}>3,2 tahun</b>
        </div>
        <div className="ft-track">
          <div className="ft-fill" style={{ width: on ? '32%' : '0%', background: color, transitionDelay: '0.5s' }} />
        </div>
        <p className="ft-note" style={{ marginTop: 8 }}>Siap dilampirkan saat mengajukan pembiayaan.</p>
      </div>
    </div>
  );
}

/* ───────── data langkah ───────── */

type Step = { id: string; label: string; title: string; body: string; color: string; icon: ReactNode; demo: (c: string) => ReactNode };

const STEPS: Step[] = [
  { id: '01', label: 'Tahu', title: 'Kenali mesin yang boros', color: '#DC2626', icon: <Plug size={18} />, body: 'Satu sensor di panel sudah cukup untuk melihat mesin mana yang paling banyak menyedot listrik.', demo: (c) => <DemoBeban color={c} /> },
  { id: '02', label: 'Atur', title: 'Jadwal yang lebih cerdas', color: '#C2410C', icon: <Clock size={18} />, body: 'Mesin yang bisa ditunda dijadwalkan ulang ke jam terik, supaya listrik surya langsung terpakai.', demo: (c) => <DemoJadwal color={c} /> },
  { id: '03', label: 'Hemat', title: 'Laporan lewat WhatsApp', color: '#15803D', icon: <Smartphone size={18} />, body: 'Rekomendasi harian dan ringkasan penghematan dikirim ke WhatsApp, tanpa perlu membuka aplikasi lain.', demo: () => <DemoWA /> },
  { id: '04', label: 'Punya PLTS', title: 'Rapor untuk bank', color: '#B45309', icon: <ClipboardList size={18} />, body: 'Data pemakaian yang terukur disusun menjadi rapor kelayakan PLTS yang bisa Anda lampirkan saat mengajukan pembiayaan.', demo: (c) => <DemoRapor color={c} /> },
];

/* ───────── bagian utama ───────── */

export default function FeatureCards() {
  const [active, setActive] = useState(0);
  const [paused, setPaused] = useState(false);
  const [seen, setSeen] = useState(false);
  const root = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const el = root.current;
    if (!el || typeof IntersectionObserver === 'undefined') {
      setSeen(true);
      return;
    }
    const io = new IntersectionObserver(([e]) => setSeen(e.isIntersecting), { threshold: 0.35 });
    io.observe(el);
    return () => io.disconnect();
  }, []);

  const step = STEPS[active];
  const run = seen && !paused;

  return (
    <section id="fitur" className="sheet-band">
      <div className="sheet-w">
        <SectionHead
          n="03"
          label="Fitur"
          title="Dari pembacaan beban sampai rapor untuk bank"
          lead="Empat tahap yang saling menyambung. Pilih satu tahap untuk melihat contoh tampilannya."
        />

        <div
          ref={root}
          className="ft-show"
          onMouseEnter={() => setPaused(true)}
          onMouseLeave={() => setPaused(false)}
          onFocusCapture={() => setPaused(true)}
          onBlurCapture={() => setPaused(false)}
        >
          <div className="ft-tabs" role="tablist" aria-label="Tahap fitur">
            {STEPS.map((s, i) => (
              <button
                key={s.id}
                role="tab"
                id={`ft-tab-${i}`}
                aria-selected={i === active}
                aria-controls="ft-panel"
                className={`ft-tab ${i === active ? 'on' : ''}`}
                style={{ ['--c' as string]: s.color }}
                onClick={() => setActive(i)}
              >
                <span className="ft-tab-ico" aria-hidden="true">{s.icon}</span>
                <span className="ft-tab-lbl">{s.label}</span>
                <span className="ft-tab-txt">
                  <small>{s.id} · {s.label}</small>
                  <strong>{s.title}</strong>
                  <span className="ft-tab-body">{s.body}</span>
                </span>
                {i === active && (
                  <span
                    className="ft-prog"
                    style={{ animationPlayState: run ? 'running' : 'paused' }}
                    onAnimationEnd={() => setActive((a) => (a + 1) % STEPS.length)}
                  />
                )}
              </button>
            ))}
          </div>

          <div className="ft-mcopy">
            <strong>{step.title}</strong>
            <p>{step.body}</p>
          </div>

          <div
            id="ft-panel"
            role="tabpanel"
            aria-labelledby={`ft-tab-${active}`}
            className="ft-stage"
            style={{ ['--c' as string]: step.color }}
          >
            <div className="ft-stage-in" key={step.id}>
              {step.demo(step.color)}
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
