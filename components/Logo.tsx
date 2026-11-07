import { useId } from 'react';

/**
 * Tanda WASKITA: sebuah mata ("waskita" berarti cermat dan awas) dengan iris berupa matahari
 * berisi petir. Artinya membaca listrik tiap mesin, menangkap matahari, dan menjaga tagihan.
 */
export function LogoMark({ size = 32, className = '' }: { size?: number; className?: string }) {
  const id = useId().replace(/:/g, '');
  return (
    <svg className={className} width={size} height={size} viewBox="0 0 64 64" role="img" aria-label="WASKITA" style={{ display: 'block', flex: 'none' }}>
      <defs>
        <linearGradient id={`${id}g`} x1="8" y1="14" x2="58" y2="52" gradientUnits="userSpaceOnUse">
          <stop stopColor="#17803F" />
          <stop offset="1" stopColor="#43DB98" />
        </linearGradient>
        <linearGradient id={`${id}s`} x1="0" y1="0" x2="0" y2="1">
          <stop stopColor="#FFC25C" />
          <stop offset="1" stopColor="#FF8A00" />
        </linearGradient>
      </defs>
      <path d="M3 32C11 17 21 10.5 32 10.5S53 17 61 32C53 47 43 53.5 32 53.5S11 47 3 32Z" fill={`url(#${id}g)`} />
      <path d="M9 30C15.5 20 23 15.5 32 15.5" stroke="#fff" strokeOpacity=".28" strokeWidth="2.4" strokeLinecap="round" fill="none" />
      <circle cx="32" cy="32" r="14" fill={`url(#${id}s)`} />
      <circle cx="32" cy="32" r="14" fill="none" stroke="#fff" strokeOpacity=".5" strokeWidth="1.5" />
      <path d="M35.2 21.2 25.4 33.9h5.5l-1.7 8.9 9.6-12.9h-5.6Z" fill="#fff" />
    </svg>
  );
}
