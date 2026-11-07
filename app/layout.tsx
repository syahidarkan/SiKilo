import type { Metadata } from 'next';
import { Plus_Jakarta_Sans, JetBrains_Mono } from 'next/font/google';
import './globals.css';

const plusJakarta = Plus_Jakarta_Sans({
  variable: '--font-plus-jakarta',
  subsets: ['latin'],
  weight: ['300', '400', '500', '600', '700', '800'],
  display: 'swap',
});

const jetbrainsMono = JetBrains_Mono({
  variable: '--font-jetbrains-mono',
  subsets: ['latin'],
  weight: ['400', '500', '700'],
  display: 'swap',
});

export const metadata: Metadata = {
  title: 'WASKITA | Agen AI Pengatur Energi UMKM',
  description:
    'Platform AI Energy Dispatcher & Solar Right-Sizing untuk Sentra UMKM Indonesia. UNS Innovation Hackathon 2026, Energy Track.',
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html
      lang="id"
      suppressHydrationWarning
      className={`${plusJakarta.variable} ${jetbrainsMono.variable} h-full antialiased`}
    >
      <head>
        <script
          dangerouslySetInnerHTML={{
            __html: "try{var t=localStorage.getItem('waskita-theme');document.documentElement.dataset.theme=t==='dark'?'dark':'light'}catch(e){}",
          }}
        />
      </head>
      <body
        className="min-h-full flex flex-col"
        style={{
          fontFamily: 'var(--font-plus-jakarta), sans-serif',
          background: 'var(--bg-paper)',
        }}
      >
        {children}
      </body>
    </html>
  );
}
