export function ThemeToggle() {
  const toggle = () => {
    const isDark = document.documentElement.classList.toggle('dark');
    localStorage.setItem('featcat-theme', isDark ? 'dark' : 'light');
  };
  return (
    <button onClick={toggle} className="p-1.5 rounded-md text-[var(--text-secondary)] hover:bg-[var(--bg-tertiary)] hover:text-[var(--text-primary)] transition-colors" title="Toggle theme">
      <span className="dark:hidden">&#9790;</span>
      <span className="hidden dark:inline">&#9788;</span>
    </button>
  );
}
