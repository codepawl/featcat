import { useEffect } from 'react'
import { useTranslation } from 'react-i18next'
import { useGlossary } from '../hooks/useGlossary'
import { Skeleton } from '../components/Skeleton'

const SECTION_KEYS = [
  'health_score',
  'health_grade',
  'quality_score',
  'completeness',
  'psi',
  'drift_severity',
  'monitoring_status',
  'action_item',
] as const

export function Help() {
  const { t } = useTranslation(['help', 'glossary'])
  const terms = useGlossary()

  useEffect(() => {
    if (window.location.hash) {
      const el = document.getElementById(window.location.hash.slice(1))
      if (el) el.scrollIntoView({ behavior: 'smooth', block: 'start' })
    }
  }, [terms])

  if (Object.keys(terms).length === 0) {
    return <Skeleton className="h-64" />
  }

  const bucketLabel = t('thresholds_columns.bucket', { ns: 'glossary', defaultValue: 'Bucket' })
  const meaningLabel = t('thresholds_columns.meaning', { ns: 'glossary', defaultValue: 'Meaning' })

  return (
    <div className="grid grid-cols-1 lg:grid-cols-[200px_1fr] gap-8">
      <aside className="lg:sticky lg:top-4 lg:self-start text-[13px]">
        <h3 className="text-xs font-semibold uppercase text-[var(--text-tertiary)] tracking-wide mb-2">
          {t('toc.title', { ns: 'help' })}
        </h3>
        <nav className="flex flex-col gap-1">
          {SECTION_KEYS.map((key) => {
            const term = terms[key]
            if (!term) return null
            return (
              <a key={key} href={`#${key}`} className="text-[var(--text-secondary)] hover:text-brand transition-colors">
                {term.label}
              </a>
            )
          })}
        </nav>
      </aside>

      <div className="max-w-2xl space-y-8">
        <header>
          <h1 className="text-2xl font-semibold">{t('page.title', { ns: 'help' })}</h1>
          <p className="text-[13px] text-[var(--text-tertiary)] mt-1">
            {t('page.subtitle', { ns: 'help' })}
          </p>
        </header>

        {SECTION_KEYS.map((key) => {
          const term = terms[key]
          if (!term) return null
          const introKey = `terms.${key}.intro` as 'terms.health_score.intro'
          const intro = t(introKey, { ns: 'glossary', defaultValue: '' })
          return (
            <section key={key} id={key} className="border-t border-[var(--border-subtle)] pt-6 scroll-mt-6">
              <h2 className="text-base font-semibold mb-1">{term.label}</h2>
              {intro && <p className="text-[12px] text-[var(--text-tertiary)] mb-2 italic">{intro}</p>}
              <p className="text-[14px] text-[var(--text-secondary)] leading-relaxed">{term.description}</p>

              {term.formula && (
                <div className="mt-3 px-3 py-2 rounded bg-[var(--bg-secondary)] font-mono text-[12px] text-[var(--text-secondary)]">
                  <span className="text-[var(--text-tertiary)] mr-2">
                    {t('common.formula_label', { ns: 'help' })}:
                  </span>
                  {term.formula}
                </div>
              )}

              {term.thresholds && term.thresholds.length > 0 && (
                <div className="mt-3 border border-[var(--border-subtle)] rounded-lg overflow-hidden">
                  <table className="w-full text-[12px]">
                    <thead className="bg-[var(--bg-secondary)] text-[var(--text-tertiary)]">
                      <tr>
                        <th className="text-left px-3 py-1.5 font-medium">{bucketLabel}</th>
                        <th className="text-left px-3 py-1.5 font-medium">{meaningLabel}</th>
                      </tr>
                    </thead>
                    <tbody>
                      {term.thresholds.map((thr, i) => (
                        <tr key={i} className="border-t border-[var(--border-subtle)]">
                          <td className="px-3 py-1.5 font-mono">{thr.grade ?? thr.range ?? thr.severity}</td>
                          <td className="px-3 py-1.5 text-[var(--text-secondary)]">
                            {thr.label ?? thr.meaning ?? (thr.min !== undefined ? `≥ ${thr.min}` : '')}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}

              {term.values && (
                <dl className="mt-3 space-y-1.5">
                  {Object.entries(term.values).map(([k, v]) => (
                    <div key={k} className="flex gap-3 text-[13px]">
                      <dt className="font-mono text-[var(--text-primary)] shrink-0">{k}</dt>
                      <dd className="text-[var(--text-secondary)]">{v}</dd>
                    </div>
                  ))}
                </dl>
              )}
            </section>
          )
        })}
      </div>
    </div>
  )
}
