import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Info } from 'lucide-react'
import { Link } from 'react-router-dom'
import { useGlossary } from '../hooks/useGlossary'

interface Props {
  /** Glossary key, e.g. "health_score", "psi", "drift_severity". */
  name: string
  /** Optional override label; defaults to the glossary label. */
  children?: React.ReactNode
  /** Show only the icon (no label text). */
  iconOnly?: boolean
}

export function ScoreTooltip({ name, children, iconOnly }: Props) {
  const { t } = useTranslation('common')
  const glossary = useGlossary()
  const term = glossary[name]
  const [open, setOpen] = useState(false)

  if (!term) {
    return <span>{children ?? name}</span>
  }

  return (
    <span className="inline-flex items-center gap-1 relative">
      {!iconOnly && <span>{children ?? term.label}</span>}
      <button
        type="button"
        onMouseEnter={() => setOpen(true)}
        onMouseLeave={() => setOpen(false)}
        onFocus={() => setOpen(true)}
        onBlur={() => setOpen(false)}
        className="text-[var(--text-tertiary)] hover:text-brand transition-colors p-0.5 -m-0.5 rounded cursor-help"
        aria-label={t('tooltip.definition_of', { label: term.label })}
      >
        <Info size={12} strokeWidth={2} />
      </button>
      {open && (
        <span className="absolute top-full left-0 mt-1 z-50 w-72 max-w-[80vw] rounded-lg border border-[var(--border-default)] bg-[var(--bg-secondary)] shadow-lg p-3 text-left normal-case">
          <span className="block text-[12px] font-semibold mb-1">{term.label}</span>
          <span className="block text-[12px] text-[var(--text-secondary)] leading-snug">{term.description}</span>
          {term.formula && (
            <span className="block text-[11px] font-mono text-[var(--text-tertiary)] mt-2">
              {term.formula}
            </span>
          )}
          {term.thresholds && term.thresholds.length > 0 && (
            <span className="block mt-2 space-y-0.5">
              {term.thresholds.map((t, i) => (
                <span key={i} className="block text-[11px] text-[var(--text-secondary)]">
                  <span className="font-mono">{t.grade ?? t.range ?? t.severity}</span>
                  {' — '}
                  {t.label ?? t.meaning ?? `≥ ${t.min}`}
                </span>
              ))}
            </span>
          )}
          {term.values && (
            <span className="block mt-2 space-y-0.5">
              {Object.entries(term.values).map(([k, v]) => (
                <span key={k} className="block text-[11px] text-[var(--text-secondary)]">
                  <span className="font-mono">{k}</span> — {v}
                </span>
              ))}
            </span>
          )}
          <Link
            to={`/help#${name}`}
            className="block mt-2 text-[11px] text-brand hover:underline"
            onClick={(e) => e.stopPropagation()}
          >
            {t('tooltip.learn_more')}
          </Link>
        </span>
      )}
    </span>
  )
}
