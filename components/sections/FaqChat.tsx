'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
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

const DOTS_MS = 900;
const WORD_MS = 36;

const clock = () => new Date().toLocaleTimeString('id-ID', { hour: '2-digit', minute: '2-digit' }).replace(':', '.');

type Turn = { q: number; at: string };

/** Tiga titik "mengetik", lalu jawaban muncul kata demi kata. */
function Answer({ text, reduced, onTick }: { text: string; reduced: boolean; onTick: () => void }) {
  const words = text.split(' ');
  const [count, setCount] = useState(reduced ? words.length : 0);

  useEffect(() => {
    if (reduced) return;
    let k = 0;
    let iv: ReturnType<typeof setInterval> | undefined;
    const t = setTimeout(() => {
      iv = setInterval(() => {
        k++;
        setCount(k);
        if (k >= words.length) clearInterval(iv);
      }, WORD_MS);
    }, DOTS_MS);
    return () => {
      clearTimeout(t);
      clearInterval(iv);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [text, reduced]);

  useEffect(onTick, [count, onTick]);

  return count === 0 ? (
    <span className="faq-dots" aria-label="Si Kilo sedang mengetik">
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
  const reduced = useReducedMotion();
  const [thread, setThread] = useState<Turn[]>([]);
  const phoneRef = useRef<HTMLDivElement>(null);
  const bodyRef = useRef<HTMLDivElement>(null);
  const started = useRef(false);

  const scrollDown = useCallback(() => {
    const el = bodyRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, []);

  const ask = useCallback((i: number) => {
    setThread((t) => (t.some((x) => x.q === i) ? t : [...t, { q: i, at: clock() }]));
  }, []);

  // Pertanyaan pertama masuk sendiri begitu ponsel terlihat, supaya orang langsung paham ini apa.
  useEffect(() => {
    const el = phoneRef.current;
    if (!el) return;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const io = new IntersectionObserver(
      ([entry]) => {
        if (!entry.isIntersecting || started.current) return;
        started.current = true;
        io.disconnect();
        timer = setTimeout(() => ask(0), reduced ? 0 : 600);
      },
      { threshold: 0.5 },
    );
    io.observe(el);
    return () => {
      io.disconnect();
      clearTimeout(timer);
    };
  }, [ask, reduced]);

  useEffect(scrollDown, [thread.length, scrollDown]);

  const left = FAQS.map((f, i) => ({ ...f, i })).filter((f) => !thread.some((t) => t.q === f.i));

  return (
    <section id="faq" className="sheet-band faq-band" aria-labelledby="h-faq">
      <div className="sheet-w">
        <div className="grid md:grid-cols-[1fr_minmax(0,25rem)] gap-12 md:gap-20 items-center">
          <Reveal className="md:sticky md:top-24">
            <div className="sh-mark">
              <b>04</b>
              <span>FAQ</span>
            </div>
            <h2 id="h-faq" className="sh-title">
              Tanya langsung Si Kilo
            </h2>
            <p className="sh-lead mt-5" style={{ justifySelf: 'start' }}>
              Pilih satu pertanyaan, lalu Si Kilo yang menjawab. Di produk yang sebenarnya, Si Kilo mengirim ringkasan harian dengan cara yang sama, lewat WhatsApp.
            </p>
          </Reveal>

          <Reveal delay={80}>
            <div ref={phoneRef} className="wa" role="group" aria-label="Contoh percakapan dengan Si Kilo">
              <div className="wa-head">
                <span className="wa-av" aria-hidden="true"><KiloAvatar /></span>
                <div>
                  <b>Si Kilo</b>
                  <small>asisten energi WASKITA · online</small>
                </div>
              </div>

              <div ref={bodyRef} className="wa-body" aria-live="polite">
                <div className="wa-day">Hari ini</div>
                {thread.length === 0 && <div className="wa-empty">Pilih pertanyaan di bawah untuk memulai.</div>}
                {thread.map((t) => (
                  <div key={t.q} className="wa-turn">
                    <div className="wa-msg out">
                      <p>{FAQS[t.q].q}</p>
                      <time>{t.at} <span className="wa-tick">✓✓</span></time>
                    </div>
                    <div className="wa-msg in">
                      <p><Answer text={FAQS[t.q].a} reduced={reduced} onTick={scrollDown} /></p>
                    </div>
                  </div>
                ))}
              </div>

              <div className="wa-foot">
                {left.length > 0 ? (
                  <>
                    <span className="wa-hint">Balasan cepat</span>
                    <div className="wa-chips">
                      {left.map((f) => (
                        <button key={f.i} type="button" className="wa-chip" onClick={() => ask(f.i)}>
                          {f.q}
                        </button>
                      ))}
                    </div>
                  </>
                ) : (
                  <div className="wa-done">
                    <span>Semua pertanyaan sudah terjawab.</span>
                    <button type="button" className="wa-chip" onClick={() => setThread([])}>Ulangi dari awal</button>
                  </div>
                )}
              </div>
            </div>
          </Reveal>
        </div>
      </div>
    </section>
  );
}
