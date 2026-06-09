import { useEffect, useMemo } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router-dom'
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

const QUICK_LINKS = [
    { to: '/', key: 'dashboard' },
  { to: '/monitoring', key: 'monitoring' },
  { to: '/features', key: 'features' },
  { to: '/actions', key: 'actions' },
  { to: '/audit', key: 'audit' },
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

  const sectionKeys = useMemo(() => {
    const available = new Set(Object.keys(terms))
    const ordered = SECTION_KEYS.filter((k) => available.has(k))
    const rest = Object.keys(terms)
      .filter((k) => !SECTION_KEYS.includes(k as (typeof SECTION_KEYS)[number]))
      .sort()
    return [...ordered, ...rest]
  }, [terms])

  const quickLinks = useMemo(
    () =>
      QUICK_LINKS.map((link) => ({
        ...link,
        label: t(`quick_links.${link.key}.label`, {
          defaultValue: link.to,
        }),
        description: t(`quick_links.${link.key}.description`, {
          defaultValue: '',
        }),
      })),
    [t]
  )

  if (sectionKeys.length === 0) {
    return <Skeleton className="h-64" />
  }

  const bucketLabel = t('thresholds_columns.bucket', { ns: 'glossary', defaultValue: 'Bucket' })
  const meaningLabel = t('thresholds_columns.meaning', { ns: 'glossary', defaultValue: 'Meaning' })

  return (
    <div className="grid grid-cols-1 lg:grid-cols-[220px_1fr] gap-8" id="top">
      <aside className="lg:sticky lg:top-4 lg:self-start text-[13px]">
        <h3 className="text-xs font-semibold uppercase text-[var(--text-tertiary)] tracking-wide mb-2">
          {t('toc.title', { ns: 'help' })}
        </h3>
        <nav className="flex flex-col gap-1">
          {sectionKeys.map((key) => {
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

        <section className="rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-secondary)] p-4">
          <h2 className="text-base font-semibold mb-2">{t('sections.quick_links', { ns: 'help' })}</h2>
          <p className="text-[13px] text-[var(--text-secondary)] leading-relaxed mb-3">
            {t('sections.quick_links_subtitle', { ns: 'help' })}
          </p>
          <div className="grid sm:grid-cols-2 gap-2">
            {quickLinks.map((link) => (
              <Link
                key={link.to}
                to={link.to}
                className="rounded-md border border-[var(--border-subtle)] bg-[var(--bg-primary)] p-3 text-[13px] hover:border-brand/60 hover:bg-[var(--bg-card)] transition-colors"
              >
                <span className="font-medium text-[var(--text-primary)]">{link.label}</span>
                {link.description && <p className="text-[var(--text-tertiary)] mt-1 leading-snug">{link.description}</p>}
              </Link>
            ))}
          </div>
        </section>

        <section className="border border-[var(--border-subtle)] rounded-lg p-4 space-y-2">
          <h2 className="text-base font-semibold">{t('sections.how_to_read', { ns: 'help' })}</h2>
          <p className="text-[13px] text-[var(--text-secondary)] leading-relaxed">
            {t('sections.how_to_read_body', { ns: 'help' })}
          </p>
          <ul className="text-[13px] text-[var(--text-tertiary)] list-disc pl-5 space-y-1">
            <li>{t('sections.how_to_read_item_1', { ns: 'help' })}</li>
            <li>{t('sections.how_to_read_item_2', { ns: 'help' })}</li>
            <li>{t('sections.how_to_read_item_3', { ns: 'help' })}</li>
          </ul>
        </section>

        {sectionKeys.map((key) => {
          const term = terms[key]
          if (!term) return null
          const introKey = `terms.${key}.intro` as 'terms.health_score.intro'
          const intro = t(introKey, { ns: 'glossary', defaultValue: '' })
          const whereKey = `term_context.${key}.where_seen` as const
          const whereText = t(whereKey, { ns: 'help', defaultValue: '' })
          const actionKey = `term_context.${key}.next_action` as const
          const actionText = t(actionKey, { ns: 'help', defaultValue: '' })
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

              {whereText && (
                <p className="mt-3 text-[12px] text-[var(--text-tertiary)]">
                  <span className="font-medium text-[var(--text-secondary)]">{t('term_context.label', { ns: 'help' })}</span>{' '}
                  {whereText}
                </p>
              )}
              {actionText && (
                <p className="mt-2 text-[12px] text-[var(--text-tertiary)]">
                  <span className="font-medium text-[var(--text-secondary)]">{t('term_context.next_action_label', { ns: 'help' })}</span>{' '}
                  {actionText}
                </p>
              )}

              <a href="#top" className="inline-block mt-3 text-[12px] text-brand hover:underline">
                {t('term_context.back_to_top', { ns: 'help' })}
              </a>
            </section>
          )
        })}
      </div>
    </div>
  )
}
