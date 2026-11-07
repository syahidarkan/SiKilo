import type { ReactNode } from 'react';
import Reveal from '@/components/Reveal';

/** Pembuka section ala EcoPatch: tanda bernomor + judul di kiri, satu kalimat kunci bergaris aksen di kanan. */
export default function SectionHead({
  n,
  label,
  title,
  lead,
  solo = false,
  id,
}: {
  n: string;
  label: string;
  title: ReactNode;
  lead?: ReactNode;
  solo?: boolean;
  id?: string;
}) {
  return (
    <Reveal>
      <header className={`sh ${solo ? 'sh-solo' : ''}`}>
        <div>
          <div className="sh-mark">
            <b>{n}</b>
            <span>{label}</span>
          </div>
          <h2 id={id} className="sh-title">
            {title}
          </h2>
        </div>
        {lead && <p className="sh-lead">{lead}</p>}
      </header>
    </Reveal>
  );
}
