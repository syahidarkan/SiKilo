'use client';

import { useEffect, useId, useRef, useState } from 'react';
import Reveal from '@/components/Reveal';
import KiloAvatar from '@/components/KiloAvatar';
import { useGaze, useReducedMotion } from '@/components/hooks';

const FAQS = [
  {
    q: 'Apa itu NOTA LISTRIK dan kenapa saya butuh ini?',
    a: 'NOTA LISTRIK adalah AI Energy Dispatcher yang membantu usahamu membaca tagihan listrik seperti akuntan, mengelola jadwal mesin seperti manajer, dan menyiapkan rapor kelayakan PLTS untuk bank. Kalau tagihan listrikmu lebih dari Rp500.000/bulan, kamu butuh ini.',
  },
  {
    q: 'Bagaimana Si Kilo mendeteksi mesin yang boros?',
    a: 'Si Kilo menggunakan teknologi NILM (Non-Intrusive Load Monitoring), tanpa perlu pasang sensor di tiap mesin. Cukup satu titik pantau di panel utama, Si Kilo "membaca" sidik jari daya setiap mesin dari pola arus listriknya.',
  },
  {
    q: 'Berapa lama sampai balik modal PLTS?',
    a: 'Rata-rata UMKM binaan kami mencapai break-even dalam 2.8–4.2 tahun. Dengan AI Dispatcher yang mengoptimalkan pemakaian saat sinar matahari paling terik, payback period bisa lebih pendek 20–30% dibanding instalasi PLTS konvensional.',
  },
  {
    q: 'Apakah datanya bisa dipakai untuk pengajuan pinjaman bank?',
    a: 'Ya! Energy Credit Scorecard dari NOTA LISTRIK sudah diformat sesuai standar penilaian kelayakan green financing. Data konsumsi terukur, proyeksi penghematan, dan PBP tersaji dalam laporan yang siap dilampirkan ke Bank BRI, BNI, atau lembaga pembiayaan UMKM lainnya.',
  },
];

const DOTS_MS = 800;
const WORD_MS = 42;

/** Dots first, then the answer types out word by word. Closing mid-way restarts it; a finished answer stays. */
function Answer({ text, open, reduced }: { text: string; open: boolean; reduced: boolean }) {
  const words = text.split(' ');
  const [count, setCount] = useState(0);
  const done = useRef(false);

  useEffect(() => {
    if (!open || done.current) return;
    if (reduced) {
      setCount(words.length);
      done.current = true;
      return;
    }
    setCount(0);
    let k = 0;
    let iv: ReturnType<typeof setInterval> | undefined;
    const t = setTimeout(() => {
      iv = setInterval(() => {
        k++;
        setCount(k);
        if (k >= words.length) {
          clearInterval(iv);
          done.current = true;
        }
      }, WORD_MS);
    }, DOTS_MS);
    return () => {
      clearTimeout(t);
      clearInterval(iv);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, text, reduced]);

  return count === 0 ? (
    <span className="faq-dots" aria-hidden="true">
      <i />
      <i />
      <i />
    </span>
  ) : (
    <>
      <span className="sr-only">{text}</span>
      <span aria-hidden="true">{words.slice(0, count).join(' ')}</span>
    </>
  );
}

export default function FaqChat() {
  const [openIdx, setOpenIdx] = useState<number | null>(null);
  const reduced = useReducedMotion();
  const sectionRef = useRef<HTMLElement>(null);
  const chatRef = useRef<HTMLDivElement>(null);
  const baseId = useId();

  // The first question opens by itself once the chat is in view, so the section shows what it is.
  useEffect(() => {
    const el = chatRef.current;
    if (!el) return;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const io = new IntersectionObserver(
      ([entry]) => {
        if (!entry.isIntersecting) return;
        io.disconnect();
        timer = setTimeout(() => setOpenIdx((cur) => cur ?? 0), reduced ? 0 : 500);
      },
      { threshold: 0.5 },
    );
    io.observe(el);
    return () => {
      io.disconnect();
      clearTimeout(timer);
    };
  }, [reduced]);

  useGaze(sectionRef, reduced);

  const toggle = (i: number) => setOpenIdx((cur) => (cur === i ? null : i));

  return (
    <section
      id="faq"
      ref={sectionRef}
      className="py-24 md:py-32"
      style={{ background: 'var(--bg-paper)' }}
      aria-labelledby="h-faq"
    >
      <div className="max-w-5xl mx-auto px-4">
        <div className="grid md:grid-cols-[1fr_1.6fr] gap-12 md:gap-16 items-start">
          {/* Left - intro */}
          <Reveal className="md:sticky md:top-24">
            <span
              className="inline-flex items-center gap-1.5 text-xs font-bold tracking-widest uppercase mb-5 px-3 py-1 rounded-full"
              style={{ background: 'var(--solar-light)', color: 'var(--solar-dark)' }}
            >
              FAQ
            </span>
            <h2
              id="h-faq"
              className="text-3xl md:text-4xl font-extrabold leading-tight mb-4"
              style={{ color: 'var(--metal-dark)', fontFamily: 'var(--font-display)', letterSpacing: '-0.03em' }}
            >
              Tanya langsung
              <br />
              Si Kilo
            </h2>
            <p className="text-sm leading-relaxed" style={{ color: 'var(--metal-mid)' }}>
              Klik pertanyaannya, Si Kilo yang jawab. Satu per satu, seperti ngobrol.
            </p>
          </Reveal>

          {/* Right - chat */}
          <Reveal delay={80}>
            <div ref={chatRef} className="faq-chat">
              {FAQS.map((faq, i) => {
                const open = openIdx === i;
                const ansId = `${baseId}-ans-${i}`;
                return (
                  <div key={i} className="faq-qa">
                    <button
                      type="button"
                      className="faq-q"
                      aria-expanded={open}
                      aria-controls={ansId}
                      onClick={() => toggle(i)}
                    >
                      {faq.q}
                    </button>
                    <div id={ansId} className={`faq-ans ${open ? 'open' : ''}`}>
                      <div className="faq-ans-in">
                        <div className="faq-msg">
                          <KiloAvatar className="faq-avatar" />
                          <p>
                            <Answer text={faq.a} open={open} reduced={reduced} />
                          </p>
                        </div>
                      </div>
                    </div>
                  </div>
                );
              })}

              {/* Hint, only while nothing is open */}
              <div className={`faq-ans faq-rest ${openIdx === null ? 'open' : ''}`} aria-hidden="true">
                <div className="faq-ans-in">
                  <div className="faq-msg">
                    <KiloAvatar className="faq-avatar" />
                    <p>Klik salah satu, nanti Si Kilo yang jawab</p>
                  </div>
                </div>
              </div>
            </div>
          </Reveal>
        </div>
      </div>
    </section>
  );
}
