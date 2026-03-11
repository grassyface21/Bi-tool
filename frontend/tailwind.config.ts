import type { Config } from 'tailwindcss'

const config: Config = {
  content: [
    './app/**/*.{js,ts,jsx,tsx,mdx}',
    './components/**/*.{js,ts,jsx,tsx,mdx}',
  ],
  theme: {
    extend: {
      colors: {
        bg: '#f5f7fa',
        surface: '#ffffff',
        accent: '#6366f1',
        text: '#111827',
        muted: '#6b7280',
        border: '#e5e7eb',
      },
      fontFamily: {
        heading: ['Bebas Neue', 'sans-serif'],
        sans: ['DM Sans', 'sans-serif'],
        mono: ['DM Mono', 'monospace'],
      },
      keyframes: {
        'fade-in': {
          from: { opacity: '0', transform: 'translateY(8px)' },
          to: { opacity: '1', transform: 'translateY(0)' },
        },
        'slide-in': {
          from: { transform: 'translateX(100%)' },
          to: { transform: 'translateX(0)' },
        },
        pulse: {
          '0%, 100%': { opacity: '1' },
          '50%': { opacity: '0.4' },
        },
      },
      animation: {
        'fade-in': 'fade-in 0.2s ease-out',
        'slide-in': 'slide-in 0.3s ease-out',
        pulse: 'pulse 1.5s ease-in-out infinite',
      },
    },
  },
  plugins: [],
}

export default config
