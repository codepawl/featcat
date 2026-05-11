import { lazy, Suspense, useMemo } from 'react'
import { useTranslation } from 'react-i18next'
import { useSearchParams } from 'react-router-dom'
import { Network, Grid3x3 } from 'lucide-react'
import { Skeleton } from '../components/Skeleton'

const SimilarityGraph = lazy(() =>
  import('./similarity/SimilarityGraph').then((m) => ({ default: m.SimilarityGraph })),
)
const SimilarityMatrix = lazy(() =>
  import('./similarity/SimilarityMatrix').then((m) => ({ default: m.SimilarityMatrix })),
)

type SimilarityTab = 'graph' | 'matrix'

const VALID_TABS: SimilarityTab[] = ['graph', 'matrix']

function isValidTab(value: string | null): value is SimilarityTab {
  return value !== null && (VALID_TABS as string[]).includes(value)
}

export function Similarity() {
  const { t } = useTranslation('similarity')
  const [searchParams, setSearchParams] = useSearchParams()

  const rawTab = searchParams.get('tab')
  const tab: SimilarityTab = isValidTab(rawTab) ? rawTab : 'graph'

  const tabs = useMemo(
    () =>
      [
        { id: 'graph' as const, labelKey: 'tabs.graph' as const, icon: Network },
        { id: 'matrix' as const, labelKey: 'tabs.matrix' as const, icon: Grid3x3 },
      ],
    [],
  )

  const setTab = (next: SimilarityTab) => {
    const params = new URLSearchParams(searchParams)
    if (next === 'graph') {
      params.delete('tab')
    } else {
      params.set('tab', next)
    }
    setSearchParams(params, { replace: true })
  }

  return (
    <div className="flex flex-col h-full">
      <div className="flex items-baseline justify-between px-4 pt-4">
        <h1 className="text-lg font-semibold text-[var(--text-primary)]">{t('page.title')}</h1>
      </div>

      <div className="flex gap-1 px-4 mt-3 border-b border-[var(--border-subtle)]">
        {tabs.map((entry) => {
          const Icon = entry.icon
          const active = tab === entry.id
          return (
            <button
              key={entry.id}
              type="button"
              onClick={() => setTab(entry.id)}
              className={`flex items-center gap-1.5 px-3 py-2 text-[12px] font-medium border-b-2 transition-colors ${
                active
                  ? 'border-brand text-brand'
                  : 'border-transparent text-[var(--text-tertiary)] hover:text-[var(--text-primary)]'
              }`}
              aria-current={active ? 'page' : undefined}
            >
              <Icon size={13} />
              {t(entry.labelKey)}
            </button>
          )
        })}
      </div>

      <div className="flex-1 min-h-0">
        <Suspense fallback={<Skeleton className="m-4 h-64" />}>
          {tab === 'graph' && <SimilarityGraph />}
          {tab === 'matrix' && <SimilarityMatrix />}
        </Suspense>
      </div>
    </div>
  )
}
