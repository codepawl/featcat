import { Sun, Moon } from 'lucide-react'

export function ThemeToggle() {
  const toggle = () => {
    const isDark = document.documentElement.classList.toggle('dark')
    localStorage.setItem('featcat-theme', isDark ? 'dark' : 'light')
  }
  return (
    <button onClick={toggle} className="p-1.5 rounded-md text-[var(--text-secondary)] hover:bg-[var(--bg-tertiary)] hover:text-[var(--text-primary)] transition-colors" title="Toggle theme">
      <Moon size={16} className="dark:hidden" />
      <Sun size={16} className="hidden dark:block" />
    </button>
  )
}
