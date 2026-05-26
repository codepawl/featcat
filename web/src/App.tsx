import { lazy, Suspense } from 'react'
import { BrowserRouter, Routes, Route } from 'react-router-dom'
import { Layout } from './components/Layout'

const Dashboard = lazy(() => import('./pages/Dashboard').then((m) => ({ default: m.Dashboard })))
const Features = lazy(() => import('./pages/Features').then((m) => ({ default: m.Features })))
const Groups = lazy(() => import('./pages/Groups').then((m) => ({ default: m.Groups })))
const GroupDetail = lazy(() => import('./pages/GroupDetail').then((m) => ({ default: m.GroupDetail })))
const Sources = lazy(() => import('./pages/Sources').then((m) => ({ default: m.Sources })))
const Similarity = lazy(() => import('./pages/Similarity').then((m) => ({ default: m.Similarity })))
const Lineage = lazy(() => import('./pages/Lineage').then((m) => ({ default: m.Lineage })))
const Monitoring = lazy(() => import('./pages/Monitoring').then((m) => ({ default: m.Monitoring })))
const Jobs = lazy(() => import('./pages/Jobs').then((m) => ({ default: m.Jobs })))
const DatasetBuilds = lazy(() => import('./pages/DatasetBuilds').then((m) => ({ default: m.DatasetBuilds })))
const MaterializationRuns = lazy(() => import('./pages/MaterializationRuns').then((m) => ({ default: m.MaterializationRuns })))
const MaterializationSchedules = lazy(() => import('./pages/MaterializationSchedules').then((m) => ({ default: m.MaterializationSchedules })))
const Audit = lazy(() => import('./pages/Audit').then((m) => ({ default: m.Audit })))
const Chat = lazy(() => import('./pages/Chat').then((m) => ({ default: m.Chat })))
const Settings = lazy(() => import('./pages/Settings').then((m) => ({ default: m.Settings })))
const Actions = lazy(() => import('./pages/Actions').then((m) => ({ default: m.Actions })))
const Help = lazy(() => import('./pages/Help').then((m) => ({ default: m.Help })))
const SearchPage = lazy(() => import('./pages/Search').then((m) => ({ default: m.Search })))
// Dev-only demo page. The conditional keeps `import('./pages/_dev/Components')`
// inside a `false` branch in prod, so esbuild dead-code-eliminates the chunk
// (verified by checking the built `featcat/server/static/assets/` output).
const ComponentsDemo = import.meta.env.DEV
  ? lazy(() => import('./pages/_dev/Components').then((m) => ({ default: m.Components })))
  : null

function RouteFallback() {
  return (
    <div className="flex items-center justify-center h-64 text-sm text-[var(--text-muted)]">
      Loading…
    </div>
  )
}

export default function App() {
  return (
    <BrowserRouter>
      <Layout>
        <Suspense fallback={<RouteFallback />}>
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/search" element={<SearchPage />} />
            <Route path="/features" element={<Features />} />
            <Route path="/features/:name" element={<Features />} />
            <Route path="/groups" element={<Groups />} />
            <Route path="/groups/:name" element={<GroupDetail />} />
            <Route path="/sources" element={<Sources />} />
            <Route path="/sources/:name" element={<Sources />} />
            <Route path="/similarity" element={<Similarity />} />
            <Route path="/lineage" element={<Lineage />} />
            <Route path="/audit" element={<Audit />} />
            <Route path="/monitoring" element={<Monitoring />} />
            <Route path="/actions" element={<Actions />} />
            <Route path="/datasets/builds" element={<DatasetBuilds />} />
            <Route path="/online/materializations" element={<MaterializationRuns />} />
            <Route path="/online/materialization-schedules" element={<MaterializationSchedules />} />
            <Route path="/jobs" element={<Jobs />} />
            <Route path="/chat" element={<Chat />} />
            <Route path="/settings" element={<Settings />} />
            <Route path="/help" element={<Help />} />
            {ComponentsDemo && <Route path="/dev/components" element={<ComponentsDemo />} />}
          </Routes>
        </Suspense>
      </Layout>
    </BrowserRouter>
  )
}
