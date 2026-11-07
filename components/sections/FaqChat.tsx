'use client';

import { useEffect, useId, useRef, useState } from 'react';
import Reveal from '@/components/Reveal';
import KiloAvatar from '@/components/KiloAvatar';
import { useGaze, useReducedMotion } from '@/components/hooks';

const FAQS = [
  {
    q: 'Apa yang dikerjakan WASKITA?',
    a: 'WASKITA membaca pemakaian listrik tiap mesin dari satu titik ukur, menjadwalkan ulang mesin yang fleksibel ke jam matahari, dan menyusun rapor kelayakan PLTS untuk pengajuan ke bank. Tujuannya sederhana: tagihan Anda lebih ringan dan keputusan memasang PLTS lebih tepat.',
  },
  {
    q: 'Bagaimana Si Kilo tahu mesin mana yang boros?',
    a: 'Si Kilo memakai teknologi NILM (Non-Intrusive Load Monitoring). Cukup satu sensor di panel utama, tanpa memasang alat di setiap mesin. Setiap mesin memiliki pola arus yang khas, dan dari pola itulah Si Kilo mengenalinya.',
  },
  {
    q: 'Berapa lama PLTS balik modal?',
    a: 'Menurut simulasi, balik modal berkisar 2,8 sampai 4,2 tahun untuk profil UMKM yang kami uji. Angka ini perkiraan dari tiruan digital dan belum diverifikasi di lapangan. Untuk angka usaha Anda, silakan coba simulator.',
  },
  {
    q: 'Apakah datanya bisa dipakai untuk mengajukan pinjaman bank?',
    a: 'Rapor disusun dari data konsumsi yang terukur, perkiraan penghematan, dan waktu balik modal, dalam format PDF. Namun, penerimaannya tetap bergantung pada lembaga pembiayaan. Saat ini belum ada kerja sama resmi dengan bank mana pun.',
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
    <section id="faq" ref={sectionRef} className="sheet-band" aria-labelledby="h-faq">
      <div className="sheet-w">
        <div className="grid md:grid-cols-[1fr_1.5fr] gap-12 md:gap-20 items-start">
          {/* Left - intro */}
          <Reveal className="md:sticky md:top-24">
            <div className="sh-mark">
              <b>04</b>
              <span>FAQ</span>
            </div>
            <h2 id="h-faq" className="sh-title">
              Tanya langsung Si Kilo
            </h2>
            <p className="sh-lead mt-5" style={{ justifySelf: 'start' }}>
              Klik pertanyaannya, lalu Si Kilo yang menjawab. Satu per satu, seperti mengobrol.
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
                    <p>Klik salah satu pertanyaan, nanti Si Kilo yang menjawab.</p>
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
