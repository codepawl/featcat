import type { Config } from 'tailwindcss'

export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        accent: { DEFAULT: '#F59E0B', subtle: '#FEF3C7', emphasis: '#D97706', muted: '#F59E0B10' },
      },
      fontFamily: {
        sans: ['Plus Jakarta Sans', '-apple-system', 'BlinkMacSystemFont', 'Segoe UI', 'sans-serif'],
        mono: ['JetBrains Mono', 'SF Mono', 'Fira Code', 'Consolas', 'monospace'],
      },
      animation: {
        'fade-in': 'fadeIn 0.35s cubic-bezier(0.16, 1, 0.3, 1)',
        'slide-up': 'slideUp 0.35s cubic-bezier(0.16, 1, 0.3, 1)',
        'breathe': 'breathe 2s ease-in-out infinite',
        'shimmer': 'shimmer 1.8s infinite',
        'modal-in': 'modalIn 0.25s cubic-bezier(0.16, 1, 0.3, 1)',
        'modal-out': 'modalOut 0.15s ease-in forwards',
        'glow-pulse': 'glowPulse 2s ease-in-out infinite',
      },
      keyframes: {
        fadeIn: { from: { opacity: '0', transform: 'translateY(6px)' }, to: { opacity: '1', transform: 'translateY(0)' } },
        slideUp: { from: { opacity: '0', transform: 'translateY(10px)' }, to: { opacity: '1', transform: 'translateY(0)' } },
        breathe: { '0%, 100%': { opacity: '1', transform: 'scale(1)' }, '50%': { opacity: '0.5', transform: 'scale(0.85)' } },
        shimmer: { from: { backgroundPosition: '200% 0' }, to: { backgroundPosition: '-200% 0' } },
        modalIn: { from: { opacity: '0', transform: 'scale(0.96) translateY(8px)' }, to: { opacity: '1', transform: 'scale(1) translateY(0)' } },
        modalOut: { from: { opacity: '1', transform: 'scale(1)' }, to: { opacity: '0', transform: 'scale(0.96)' } },
        glowPulse: { '0%, 100%': { boxShadow: '0 0 8px rgba(245, 158, 11, 0.2)' }, '50%': { boxShadow: '0 0 16px rgba(245, 158, 11, 0.4)' } },
      },
    },
  },
  plugins: [],
} satisfies Config
