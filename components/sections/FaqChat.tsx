'use client';

import { useEffect, useRef, useState } from 'react';
import { ArrowRight } from 'lucide-react';
import Reveal from '@/components/Reveal';
import KiloAvatar from '@/components/KiloAvatar';
import { useReducedMotion } from '@/components/hooks';

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

/** Tiga titik "mengetik", lalu jawaban muncul kata demi kata. Jawaban yang sudah tampil penuh tidak diketik ulang. */
function Answer({ text, open, reduced }: { text: string; open: boolean; reduced: boolean }) {
  const words = text.split(' ');
  const [count, setCount] = useState(0);
  const done = useRef(false);

  useEffect(() => {
    if (!open) return;
    if (done.current || reduced) {
      done.current = true;
      setCount(words.length);
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
          done.current = true;
          clearInterval(iv);
        }
      }, WORD_MS);
    }, DOTS_MS);
    return () => {
      clearTimeout(t);
      clearInterval(iv);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, reduced, text]);

  return (
    <>
      <span className="sr-only">{text}</span>
      {count === 0 ? (
        <span className="fq-dots" aria-hidden="true">
          <i />
          <i />
          <i />
        </span>
      ) : (
        <span aria-hidden="true">{words.slice(0, count).join(' ')}</span>
      )}
    </>
  );
}

export default function FaqChat() {
  const reduced = useReducedMotion();
  const [openIdx, setOpenIdx] = useState<number | null>(null);
  const chatRef = useRef<HTMLDivElement>(null);
  const touched = useRef(false);

  // Pertanyaan pertama terbuka sendiri begitu bagian ini terlihat, supaya orang langsung paham ini apa.
  useEffect(() => {
    const el = chatRef.current;
    if (!el) return;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const io = new IntersectionObserver(
      ([entry]) => {
        if (!entry.isIntersecting) return;
        io.disconnect();
        timer = setTimeout(() => {
          if (!touched.current) setOpenIdx(0);
        }, reduced ? 0 : 500);
      },
      { threshold: 0.5 },
    );
    io.observe(el);
    return () => {
      io.disconnect();
      clearTimeout(timer);
    };
  }, [reduced]);

  const toggle = (i: number) => {
    touched.current = true;
    setOpenIdx((cur) => (cur === i ? null : i));
  };

  return (
    <section id="faq" className="sheet-band faq-band" aria-labelledby="h-faq">
      <div className="sheet-w">
        <div className="fq-wrap">
          <Reveal className="fq-intro">
            <div className="sh-mark">
              <b>04</b>
              <span>FAQ</span>
            </div>
            <h2 id="h-faq" className="sh-title">
              Pertanyaan yang sering muncul
            </h2>
            <p className="sh-lead mt-5" style={{ justifySelf: 'start' }}>
              Pilih satu pertanyaan, lalu Si Kilo menjawab tepat di bawahnya. Belum ketemu jawabannya? Coba langsung di simulator.
            </p>
            <a className="fq-link" href="#simulator-section">
              Buka simulator <ArrowRight size={16} aria-hidden="true" />
            </a>
          </Reveal>

          <Reveal delay={80}>
            <div ref={chatRef} className="fq" role="group" aria-label="Pertanyaan dan jawaban bersama Si Kilo">
              {FAQS.map((f, i) => {
                const open = openIdx === i;
                return (
                  <div key={f.q} className="fq-item">
                    <button
                      type="button"
                      className="fq-q"
                      aria-expanded={open}
                      aria-controls={`fq-a-${i}`}
                      id={`fq-q-${i}`}
                      onClick={() => toggle(i)}
                    >
                      {f.q}
                    </button>
                    <div id={`fq-a-${i}`} role="region" aria-labelledby={`fq-q-${i}`} className={`fq-ans ${open ? 'open' : ''}`}>
                      <div className="fq-ans-in">
                        <div className="fq-msg">
                          <span className="fq-av" aria-hidden="true">
                            <KiloAvatar />
                          </span>
                          <p>
                            <Answer text={f.a} open={open} reduced={reduced} />
                          </p>
                        </div>
                      </div>
                    </div>
                  </div>
                );
              })}

              <div className={`fq-ans fq-rest ${openIdx === null ? 'open' : ''}`} aria-hidden={openIdx !== null}>
                <div className="fq-ans-in">
                  <div className="fq-msg">
                    <span className="fq-av" aria-hidden="true">
                      <KiloAvatar />
                    </span>
                    <p>Pilih salah satu pertanyaan di atas, nanti saya jawab.</p>
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
