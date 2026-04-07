import { useState, useEffect, useRef } from 'react';

interface Props {
  placeholder?: string;
  onSearch: (value: string) => void;
  delay?: number;
  className?: string;
}

export function SearchInput({ placeholder = 'Search...', onSearch, delay = 300, className = '' }: Props) {
  const [value, setValue] = useState('');
  const timer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);

  useEffect(() => {
    clearTimeout(timer.current);
    timer.current = setTimeout(() => onSearch(value), delay);
    return () => clearTimeout(timer.current);
  }, [value, delay, onSearch]);

  return (
    <input
      type="text"
      value={value}
      onChange={(e) => setValue(e.target.value)}
      placeholder={placeholder}
      className={`bg-[var(--bg-primary)] border border-[var(--border-default)] rounded-lg px-3 py-2 text-[13px] text-[var(--text-primary)] focus:border-accent focus:ring-2 focus:ring-accent/20 outline-none transition-all ${className}`}
    />
  );
}
