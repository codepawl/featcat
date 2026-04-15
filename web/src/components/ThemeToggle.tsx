import { Sun, Moon } from 'lucide-react'

export function ThemeToggle() {
  const toggle = () => {
    const isDark = document.documentElement.classList.toggle('dark')
    localStorage.setItem('featcat-theme', isDark ? 'dark' : 'light')
  }
  return (
    <button
      onClick={toggle}
      className="p-1.5 rounded-lg text-[var(--text-tertiary)] hover:bg-[var(--bg-tertiary)] hover:text-accent transition-all duration-200"
      title="Toggle theme"
    >
      <Moon size={16} strokeWidth={1.8} className="dark:hidden" />
      <Sun size={16} strokeWidth={1.8} className="hidden dark:block" />
    </button>
  )
}
