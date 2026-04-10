import { useState, useEffect, useRef } from 'react'
import { Search } from 'lucide-react'

interface Props {
  placeholder?: string
  onSearch: (value: string) => void
  delay?: number
  className?: string
}

export function SearchInput({ placeholder = 'Search...', onSearch, delay = 300, className = '' }: Props) {
  const [value, setValue] = useState('')
  const timer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined)

  useEffect(() => {
    clearTimeout(timer.current)
    timer.current = setTimeout(() => onSearch(value), delay)
    return () => clearTimeout(timer.current)
  }, [value, delay, onSearch])

  return (
    <div className={`relative ${className}`}>
      <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-[var(--text-tertiary)]" />
      <input
        type="text"
        value={value}
        onChange={(e) => setValue(e.target.value)}
        placeholder={placeholder}
        className="w-full bg-[var(--bg-primary)] border border-[var(--border-default)] rounded-lg pl-9 pr-3 py-2 text-[13px] text-[var(--text-primary)] focus:border-accent focus:ring-2 focus:ring-accent/20 outline-none transition-all"
      />
    </div>
  )
}
