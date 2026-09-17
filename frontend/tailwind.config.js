/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      colors: {
        // Retro 16-bit palette
        ink: {
          950: '#090d16',
          900: '#0b1120',
          800: '#0f172a',
          700: '#1e293b',
          600: '#334155',
        },
        amber: { retro: '#f59e0b' },
        emerald: { retro: '#10b981' },
        cyan: { retro: '#06b6d4' },
        rose: { retro: '#f43f5e' },
      },
      fontFamily: {
        pixel: ['"Press Start 2P"', '"Zen Maru Gothic"', 'cursive', 'monospace'],
        mono: ['"Silkscreen"', '"Zen Maru Gothic"', 'monospace'],
        sans: ['Inter', '"Zen Maru Gothic"', 'system-ui', 'sans-serif'],
        jp: ['"Zen Maru Gothic"', 'Inter', 'system-ui', 'sans-serif'],
      },
      boxShadow: {
        'pixel': '4px 4px 0 0 #000',
        'pixel-sm': '2px 2px 0 0 #000',
        'glow-amber': '0 0 12px rgba(245,158,11,0.6)',
        'glow-emerald': '0 0 12px rgba(16,185,129,0.6)',
        'glow-cyan': '0 0 12px rgba(6,182,212,0.6)',
      },
      keyframes: {
        bob: {
          '0%,100%': { transform: 'translateY(0)' },
          '50%': { transform: 'translateY(-2px)' },
        },
        blink: {
          '0%,49%': { opacity: 1 },
          '50%,100%': { opacity: 0.2 },
        },
        type: {
          '0%': { transform: 'translateY(0)' },
          '25%': { transform: 'translateY(-1px) rotate(-2deg)' },
          '50%': { transform: 'translateY(0)' },
          '75%': { transform: 'translateY(-1px) rotate(2deg)' },
          '100%': { transform: 'translateY(0)' },
        },
        spin: {
          '0%': { transform: 'rotate(0deg)' },
          '100%': { transform: 'rotate(360deg)' },
        },
        stamp: {
          '0%,100%': { transform: 'rotate(0deg) scale(1)' },
          '50%': { transform: 'rotate(-12deg) scale(1.1)' },
        },
      },
      animation: {
        bob: 'bob 2s ease-in-out infinite',
        blink: 'blink 1.1s steps(1) infinite',
        type: 'type 0.5s ease-in-out infinite',
        spin: 'spin 1.2s linear infinite',
        stamp: 'stamp 1.4s ease-in-out infinite',
      },
    },
  },
  plugins: [],
}
