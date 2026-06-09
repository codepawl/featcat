/**
 * SearchBar — sticky-top-bar global search with debounced autocomplete.
 *
 * Drops in once via Layout; renders on every route. Internally controlled.
 * Submits route to `/search?q=...`; picking a suggestion routes to
 * `/features/<name>`.
 *
 * Usage:
 *   <SearchBar />            // default placeholder + width
 *   <SearchBar className="max-w-md" />  // optional layout overrides
 *
 * Keyboard:
 *   ArrowDown / ArrowUp  navigate suggestions
 *   Enter (no active)    submit -> /search?q=
 *   Enter (active row)   pick   -> /features/<name>
 *   Escape               close dropdown
 *
 * Suggestion source: `api.search.suggest(q, 5)` (the lightweight typeahead).
 * Cache for `/search` is invalidated on submit so the results page sees the
 * fresh hit list immediately.
 */
import { useEffect, useRef, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { Search as SearchIcon } from 'lucide-react'
import { api, invalidateCache } from '../api'

interface Suggestion {
  id: string
  name: string
  dtype: string
  source: string
  rank: number
}

const SUGGEST_DEBOUNCE_MS = 200
const SUGGEST_LIMIT = 5
const MIN_QUERY_LEN = 2

interface SearchBarProps {
  className?: string
  onSubmit?: () => void
}

export function SearchBar({ className, onSubmit }: SearchBarProps) {
  const { t } = useTranslation('search')
  const navigate = useNavigate()
  const [params] = useSearchParams()
  const urlQ = params.get('q') ?? ''

  const [input, setInput] = useState(urlQ)
  const [open, setOpen] = useState(false)
  const [suggestions, setSuggestions] = useState<Suggestion[]>([])
  const [active, setActive] = useState(-1)
  const wrapRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLInputElement>(null)
  const debounceRef = useRef<ReturnType<typeof setTimeout> | undefined>(undefined)

  // Refill from URL when ?q= is present (e.g. on /search?q=foo after a
  // back-nav). Stays put on routes without ?q= so unsubmitted typing is not
  // clobbered when the user clicks through to /features/...
  useEffect(() => {
    if (urlQ) setInput(urlQ)
  }, [urlQ])

  // Debounced typeahead.
  useEffect(() => {
    clearTimeout(debounceRef.current)
    const trimmed = input.trim()
    if (trimmed.length < MIN_QUERY_LEN) {
      setSuggestions([])
      return
    }
    debounceRef.current = setTimeout(() => {
      api.search
        .suggest(trimmed, SUGGEST_LIMIT)
        .then((res) => {
          setSuggestions(res)
          setActive(-1)
        })
        .catch(() => setSuggestions([]))
    }, SUGGEST_DEBOUNCE_MS)
    return () => clearTimeout(debounceRef.current)
  }, [input])

  // Close on outside click.
  useEffect(() => {
    const onDocClick = (e: MouseEvent) => {
      if (!wrapRef.current?.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', onDocClick)
    return () => document.removeEventListener('mousedown', onDocClick)
  }, [])

  const submit = (value: string) => {
    const trimmed = value.trim()
    if (!trimmed) return
    invalidateCache('/search')
    navigate(`/search?q=${encodeURIComponent(trimmed)}`)
    setOpen(false)
    onSubmit?.()
  }

  const pick = (name: string) => {
    navigate(`/features/${encodeURIComponent(name)}`)
    setOpen(false)
    onSubmit?.()
  }

  const handleKey = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (!open || suggestions.length === 0) {
      if (e.key === 'Enter') {
        e.preventDefault()
        submit(input)
      } else if (e.key === 'Escape') {
        setOpen(false)
      }
      return
    }
    if (e.key === 'ArrowDown') {
      e.preventDefault()
      setActive((i) => Math.min(i + 1, suggestions.length - 1))
    } else if (e.key === 'ArrowUp') {
      e.preventDefault()
      setActive((i) => Math.max(i - 1, -1))
    } else if (e.key === 'Enter') {
      e.preventDefault()
      if (active >= 0 && active < suggestions.length) {
        pick(suggestions[active].name)
      } else {
        submit(input)
      }
    } else if (e.key === 'Escape') {
      setOpen(false)
    }
  }

  const showDropdown = open && (suggestions.length > 0 || input.trim().length >= MIN_QUERY_LEN)

  return (
    <div ref={wrapRef} className={`flex items-center gap-2 ${className ?? 'w-full'}`}>
      <div className="relative flex-1">
        <SearchIcon
          size={16}
          strokeWidth={1.8}
          className="absolute left-3 top-1/2 -translate-y-1/2 text-[var(--text-tertiary)]"
        />
        <input
          ref={inputRef}
          type="text"
          value={input}
          onChange={(e) => {
            setInput(e.target.value)
            setOpen(true)
          }}
          onFocus={() => setOpen(true)}
          onKeyDown={handleKey}
          placeholder={t('input.placeholder')}
          role="combobox"
          aria-expanded={showDropdown}
          aria-autocomplete="list"
          aria-controls="searchbar-listbox"
          className="w-full bg-[var(--bg-primary)] border border-[var(--border-subtle)] rounded-lg pl-9 pr-3 py-2 text-sm text-[var(--text-primary)] placeholder:text-[var(--text-tertiary)] focus:border-brand focus:ring-2 focus:ring-brand/15 outline-none transition-all"
        />
        {showDropdown && (
          <div className="absolute z-30 left-0 right-0 mt-1 bg-[var(--bg-primary)] border border-[var(--border-subtle)] rounded-lg shadow-lg max-h-96 overflow-y-auto">
            {suggestions.length > 0 ? (
              <ul id="searchbar-listbox" role="listbox" className="py-1">
                {suggestions.map((s, i) => (
                  <li
                    key={s.id}
                    role="option"
                    aria-selected={i === active}
                    onMouseEnter={() => setActive(i)}
                    onMouseDown={(e) => {
                      e.preventDefault()
                      pick(s.name)
                    }}
                    className={`px-3 py-2 cursor-pointer text-sm border-b border-[var(--border-subtle)] last:border-b-0 ${
                      i === active ? 'bg-brand-muted text-brand' : 'hover:bg-[var(--bg-secondary)]'
                    }`}
                  >
                    <div className="flex items-center justify-between gap-3">
                      <span className="font-mono truncate">{s.name}</span>
                      <span className="text-[11px] text-[var(--text-tertiary)] shrink-0 font-mono">{s.dtype}</span>
                    </div>
                    <div className="text-[11px] text-[var(--text-tertiary)] truncate">{s.source}</div>
                  </li>
                ))}
              </ul>
            ) : null}
            <button
              type="button"
              onMouseDown={(e) => {
                e.preventDefault()
                submit(input)
              }}
              className="w-full text-left px-3 py-2 text-xs text-brand hover:bg-[var(--bg-secondary)] border-t border-[var(--border-subtle)]"
            >
              {t('dropdown.see_all', { query: input.trim() })}
            </button>
          </div>
        )}
      </div>
      <button
        type="button"
        onClick={() => submit(input)}
        className="px-4 py-2 text-sm font-medium bg-brand text-white rounded-lg hover:bg-brand-emphasis transition-colors shrink-0"
      >
        {t('button.search')}
      </button>
    </div>
  )
}
