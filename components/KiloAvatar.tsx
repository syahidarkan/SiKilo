import { useId } from 'react';

/** Si Kilo as a little smart meter. Pupils follow --gx/--gy, set by useGaze on a parent element. */
export default function KiloAvatar({ className = '' }: { className?: string }) {
  const id = useId();
  return (
    <svg className={`kilo-av ${className}`} viewBox="0 0 120 124" aria-hidden="true">
      <defs>
        <linearGradient id={`${id}-b`} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#FFB85C" />
          <stop offset="1" stopColor="#FF9E2C" />
        </linearGradient>
      </defs>
      <ellipse cx="60" cy="116" rx="34" ry="5" fill="#1F2937" opacity="0.12" />
      <g className="kilo-body">
        <path d="M60 20 V8" stroke="#4B5563" strokeWidth="4" strokeLinecap="round" />
        <circle className="kilo-gem" cx="60" cy="6" r="5.5" fill="#2FBF71" />
        <rect x="14" y="20" width="92" height="90" rx="26" fill={`url(#${id}-b)`} />
        <rect x="14" y="94" width="92" height="16" rx="8" fill="#D97706" opacity="0.28" />
        <circle cx="25" cy="31" r="2.6" fill="#D97706" opacity="0.7" />
        <circle cx="95" cy="31" r="2.6" fill="#D97706" opacity="0.7" />
        <rect x="26" y="36" width="68" height="46" rx="16" fill="#1F2937" />
        <g className="kilo-gaze">
          <g className="kilo-eyes">
            <circle cx="46" cy="56" r="7" fill="#2FBF71" />
            <circle cx="74" cy="56" r="7" fill="#2FBF71" />
            <circle cx="48" cy="54" r="2.2" fill="#D2F5E1" />
            <circle cx="76" cy="54" r="2.2" fill="#D2F5E1" />
          </g>
        </g>
        <path d="M52 69 Q60 76 68 69" stroke="#2FBF71" strokeWidth="3.4" strokeLinecap="round" fill="none" />
        <ellipse cx="36" cy="68" rx="5" ry="3" fill="#FF8FA8" opacity="0.7" />
        <ellipse cx="84" cy="68" rx="5" ry="3" fill="#FF8FA8" opacity="0.7" />
        <rect x="44" y="90" width="32" height="12" rx="6" fill="#FBF9F4" opacity="0.92" />
        <path d="M50 96 H58" stroke="#FF9E2C" strokeWidth="3" strokeLinecap="round" />
        <path d="M62 96 H70" stroke="#2FBF71" strokeWidth="3" strokeLinecap="round" />
      </g>
    </svg>
  );
}
