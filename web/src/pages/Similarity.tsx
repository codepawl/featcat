import { lazy, Suspense, useMemo } from 'react'
import { useTranslation } from 'react-i18next'
import { useSearchParams } from 'react-router-dom'
import { Network, Grid3x3 } from 'lucide-react'
import { Skeleton } from '../components/Skeleton'
import { Tabs, type TabDefinition } from '../components/Tabs'

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

  const tabs = useMemo<TabDefinition<SimilarityTab>[]>(
    () => [
      { id: 'graph', label: t('tabs.graph'), icon: Network },
      { id: 'matrix', label: t('tabs.matrix'), icon: Grid3x3 },
    ],
    [t],
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

      {/* URL sync is managed here (delete `?tab=` when on the default `graph`
          tab) rather than via `syncToUrl` because we want a clean URL for
          the default state. The Tabs component still handles WAI-ARIA roles
          + keyboard navigation. */}
      <div className="px-4 mt-3">
        <Tabs<SimilarityTab>
          tabs={tabs}
          value={tab}
          onChange={setTab}
          size="compact"
        />
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
