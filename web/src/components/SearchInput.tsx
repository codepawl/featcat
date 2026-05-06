import { useState, useEffect, useRef } from 'react'
import { useTranslation } from 'react-i18next'
import { Search } from 'lucide-react'

interface Props {
  placeholder?: string
  onSearch: (value: string) => void
  delay?: number
  className?: string
}

export function SearchInput({ placeholder, onSearch, delay = 300, className = '' }: Props) {
  const { t } = useTranslation('common')
  const [value, setValue] = useState('')
  const timer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined)

  useEffect(() => {
    clearTimeout(timer.current)
    timer.current = setTimeout(() => onSearch(value), delay)
    return () => clearTimeout(timer.current)
  }, [value, delay, onSearch])

  return (
    <div className={`relative ${className}`}>
      <Search size={15} strokeWidth={1.8} className="absolute left-3 top-1/2 -translate-y-1/2 text-[var(--text-tertiary)]" />
      <input
        type="text"
        value={value}
        onChange={(e) => setValue(e.target.value)}
        placeholder={placeholder ?? t('placeholders.search')}
        className="w-full bg-[var(--bg-primary)] border border-[var(--border-subtle)] rounded-lg pl-9 pr-3 py-2 text-[13px] text-[var(--text-primary)] placeholder:text-[var(--text-tertiary)] focus:border-accent focus:ring-2 focus:ring-accent/15 outline-none transition-all duration-200"
      />
    </div>
  )
}
