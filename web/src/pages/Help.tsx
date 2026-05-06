import { useEffect } from 'react'
import { useGlossary } from '../hooks/useGlossary'
import { Skeleton } from '../components/Skeleton'

const SECTIONS: { key: string; intro?: string }[] = [
  { key: 'health_score', intro: 'How "healthy" a feature is — combines docs, drift, usage, and hints.' },
  { key: 'health_grade' },
  { key: 'quality_score', intro: 'Discovery-time signal of metadata richness.' },
  { key: 'completeness' },
  { key: 'psi', intro: 'Industry-standard distribution shift metric used for drift detection.' },
  { key: 'drift_severity' },
  { key: 'monitoring_status' },
  { key: 'action_item', intro: 'How recommendations turn into trackable outcomes.' },
]

export function Help() {
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

  return (
    <div className="grid grid-cols-1 lg:grid-cols-[200px_1fr] gap-8">
      <aside className="lg:sticky lg:top-4 lg:self-start text-[13px]">
        <h3 className="text-xs font-semibold uppercase text-[var(--text-tertiary)] tracking-wide mb-2">On this page</h3>
        <nav className="flex flex-col gap-1">
          {SECTIONS.map((s) => {
            const t = terms[s.key]
            if (!t) return null
            return (
              <a key={s.key} href={`#${s.key}`} className="text-[var(--text-secondary)] hover:text-accent transition-colors">
                {t.label}
              </a>
            )
          })}
        </nav>
      </aside>

      <div className="max-w-2xl space-y-8">
        <header>
          <h1 className="text-2xl font-semibold">Help & Glossary</h1>
          <p className="text-[13px] text-[var(--text-tertiary)] mt-1">
            Definitions for every score, severity, and metric you'll see in featcat. Hover any{' '}
            <span className="font-mono text-[11px]">ⓘ</span> icon in the UI to peek at the same content inline.
          </p>
        </header>

        {SECTIONS.map((section) => {
          const term = terms[section.key]
          if (!term) return null
          return (
            <section key={section.key} id={section.key} className="border-t border-[var(--border-subtle)] pt-6 scroll-mt-6">
              <h2 className="text-base font-semibold mb-1">{term.label}</h2>
              {section.intro && (
                <p className="text-[12px] text-[var(--text-tertiary)] mb-2 italic">{section.intro}</p>
              )}
              <p className="text-[14px] text-[var(--text-secondary)] leading-relaxed">{term.description}</p>

              {term.formula && (
                <div className="mt-3 px-3 py-2 rounded bg-[var(--bg-secondary)] font-mono text-[12px] text-[var(--text-secondary)]">
                  {term.formula}
                </div>
              )}

              {term.thresholds && term.thresholds.length > 0 && (
                <div className="mt-3 border border-[var(--border-subtle)] rounded-lg overflow-hidden">
                  <table className="w-full text-[12px]">
                    <thead className="bg-[var(--bg-secondary)] text-[var(--text-tertiary)]">
                      <tr>
                        <th className="text-left px-3 py-1.5 font-medium">Bucket</th>
                        <th className="text-left px-3 py-1.5 font-medium">Meaning</th>
                      </tr>
                    </thead>
                    <tbody>
                      {term.thresholds.map((t, i) => (
                        <tr key={i} className="border-t border-[var(--border-subtle)]">
                          <td className="px-3 py-1.5 font-mono">{t.grade ?? t.range ?? t.severity}</td>
                          <td className="px-3 py-1.5 text-[var(--text-secondary)]">
                            {t.label ?? t.meaning ?? (t.min !== undefined ? `≥ ${t.min}` : '')}
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
