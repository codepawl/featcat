/** Inline tab nav: underline-on-active pattern shared by Groups detail,
 *  Features detail, and Similarity. Generic over tab id type so callers
 *  preserve type-safety on `value`/`onChange`.
 *
 *  Keyboard accessibility: ArrowLeft/ArrowRight cycle through tabs and call
 *  onChange (focus + activation move together — "automatic activation"
 *  Tab pattern, easier for keyboard users than the manual variant).
 *
 *  URL sync: opt-in via `syncToUrl`. When enabled, the active tab id is
 *  reflected in `?tab=...` (or a custom param). Restored on mount.
 *
 *  Audit reference: Pattern 12 (Tab navigation).
 */

import { useEffect, useRef } from 'react'
import { useSearchParams } from 'react-router-dom'
import type { LucideIcon } from 'lucide-react'
import type { ReactNode } from 'react'

export interface TabDefinition<T extends string> {
  id: T
  label: string
  icon?: LucideIcon
  badge?: ReactNode
}

export interface TabsProps<T extends string> {
  tabs: TabDefinition<T>[]
  value: T
  onChange: (id: T) => void
  size?: 'default' | 'compact'
  /** When set, the active tab is mirrored into the URL search params. */
  syncToUrl?: boolean | { param: string }
  className?: string
}

const PADDING: Record<NonNullable<TabsProps<string>['size']>, string> = {
  default: 'px-3 py-2 text-[13px]',
  compact: 'px-2.5 py-1.5 text-[12px]',
}

export function Tabs<T extends string>({
  tabs,
  value,
  onChange,
  size = 'default',
  syncToUrl,
  className,
}: TabsProps<T>) {
  const param = syncToUrl === true ? 'tab' : syncToUrl ? syncToUrl.param : null
  // Hooks must be called unconditionally; useSearchParams is cheap when unused.
  const [searchParams, setSearchParams] = useSearchParams()
  const restoredRef = useRef(false)

  // Restore from URL on first mount (after first render so `onChange` exists).
  useEffect(() => {
    if (!param || restoredRef.current) return
    const fromUrl = searchParams.get(param) as T | null
    if (fromUrl && tabs.some((t) => t.id === fromUrl) && fromUrl !== value) {
      onChange(fromUrl)
    }
    restoredRef.current = true
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const select = (id: T) => {
    onChange(id)
    if (param) {
      const next = new URLSearchParams(searchParams)
      next.set(param, id)
      setSearchParams(next, { replace: true })
    }
  }

  const buttonsRef = useRef<Array<HTMLButtonElement | null>>([])

  const focusTab = (idx: number) => {
    // Defer until after the state update so the re-rendered tab is focusable.
    requestAnimationFrame(() => buttonsRef.current[idx]?.focus())
  }

  const onKeyDown = (e: React.KeyboardEvent<HTMLButtonElement>) => {
    // Derive position from the current `value` prop, not from a captured
    // index — focus may have drifted between renders (e.g. when the test
    // harness or screen reader keeps focus on the previously-active tab).
    const currentIdx = tabs.findIndex((t) => t.id === value)
    if (e.key === 'ArrowRight' || e.key === 'ArrowLeft') {
      e.preventDefault()
      const delta = e.key === 'ArrowRight' ? 1 : -1
      const nextIdx = (currentIdx + delta + tabs.length) % tabs.length
      select(tabs[nextIdx].id)
      focusTab(nextIdx)
    } else if (e.key === 'Home') {
      e.preventDefault()
      select(tabs[0].id)
      focusTab(0)
    } else if (e.key === 'End') {
      e.preventDefault()
      const last = tabs.length - 1
      select(tabs[last].id)
      focusTab(last)
    }
  }

  return (
    <div
      role="tablist"
      className={`flex items-center gap-1 border-b border-[var(--border-subtle)] ${className ?? ''}`}
    >
      {tabs.map((entry, idx) => {
        const active = entry.id === value
        const Icon = entry.icon
        return (
          <button
            key={entry.id}
            ref={(el) => {
              buttonsRef.current[idx] = el
            }}
            role="tab"
            aria-selected={active}
            tabIndex={active ? 0 : -1}
            onClick={() => select(entry.id)}
            onKeyDown={onKeyDown}
            className={`flex items-center gap-1.5 ${PADDING[size]} font-medium border-b-2 -mb-[1px] transition-colors ${
              active
                ? 'border-brand text-brand'
                : 'border-transparent text-[var(--text-tertiary)] hover:text-[var(--text-primary)]'
            }`}
          >
            {Icon && <Icon size={14} strokeWidth={1.8} />}
            <span>{entry.label}</span>
            {entry.badge !== undefined && entry.badge !== null && (
              <span className="ml-1">{entry.badge}</span>
            )}
          </button>
        )
      })}
    </div>
  )
}
