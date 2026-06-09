import { lazy, Suspense, useCallback, useEffect, useState } from 'react'
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { Layout } from './components/Layout'
import { api, clearAuthToken, setAuthToken, type AuthState } from './api'
import { AuthProvider } from './auth'

const Dashboard = lazy(() => import('./pages/Dashboard').then((m) => ({ default: m.Dashboard })))
const Features = lazy(() => import('./pages/Features').then((m) => ({ default: m.Features })))
const BusinessMetrics = lazy(() => import('./pages/BusinessMetrics').then((m) => ({ default: m.BusinessMetrics })))
const Entities = lazy(() => import('./pages/Entities').then((m) => ({ default: m.Entities })))
const EntityRelationships = lazy(() => import('./pages/EntityRelationships').then((m) => ({ default: m.EntityRelationships })))
const FeatureViews = lazy(() => import('./pages/FeatureViews').then((m) => ({ default: m.FeatureViews })))
const FeatureSets = lazy(() => import('./pages/FeatureSets').then((m) => ({ default: m.FeatureSets })))
const Groups = lazy(() => import('./pages/Groups').then((m) => ({ default: m.Groups })))
const GroupDetail = lazy(() => import('./pages/GroupDetail').then((m) => ({ default: m.GroupDetail })))
const Sources = lazy(() => import('./pages/Sources').then((m) => ({ default: m.Sources })))
const Similarity = lazy(() => import('./pages/Similarity').then((m) => ({ default: m.Similarity })))
const Lineage = lazy(() => import('./pages/Lineage').then((m) => ({ default: m.Lineage })))
const Monitoring = lazy(() => import('./pages/Monitoring').then((m) => ({ default: m.Monitoring })))
const Jobs = lazy(() => import('./pages/Jobs').then((m) => ({ default: m.Jobs })))
const DatasetBuilds = lazy(() => import('./pages/DatasetBuilds').then((m) => ({ default: m.DatasetBuilds })))
const MaterializationSchedules = lazy(() => import('./pages/MaterializationSchedules').then((m) => ({ default: m.MaterializationSchedules })))
const Audit = lazy(() => import('./pages/Audit').then((m) => ({ default: m.Audit })))
const Chat = lazy(() => import('./pages/Chat').then((m) => ({ default: m.Chat })))
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
  const [auth, setAuth] = useState<AuthState | null>(null)
  const [authLoading, setAuthLoading] = useState(true)

  const refreshAuth = useCallback(async () => {
    try {
      const state = await api.auth.me()
      setAuth(state)
    } catch {
      setAuth({ authenticated: false, required: false, user: null })
    } finally {
      setAuthLoading(false)
    }
  }, [])

  const signInWithToken = useCallback(async (token: string) => {
    setAuthLoading(true)
    setAuthToken(token)
    try {
      const state = await api.auth.me()
      setAuth(state)
    } catch (e) {
      clearAuthToken()
      setAuth({ authenticated: false, required: false, user: null })
      throw e instanceof Error ? e : new Error('Sign in failed')
    } finally {
      setAuthLoading(false)
    }
  }, [])

  const signOut = useCallback(async () => {
    setAuthLoading(true)
    clearAuthToken()
    try {
      const state = await api.auth.me()
      setAuth(state)
    } catch {
      setAuth({ authenticated: false, required: false, user: null })
    } finally {
      setAuthLoading(false)
    }
  }, [])

  useEffect(() => {
    // Preload all lazy route code chunks when the browser is idle to speed up navigation
    const preloadRoutes = [
      () => import('./pages/Dashboard'),
      () => import('./pages/Features'),
      () => import('./pages/BusinessMetrics'),
      () => import('./pages/Entities'),
      () => import('./pages/EntityRelationships'),
      () => import('./pages/FeatureViews'),
      () => import('./pages/FeatureSets'),
      () => import('./pages/Groups'),
      () => import('./pages/GroupDetail'),
      () => import('./pages/Sources'),
      () => import('./pages/Similarity'),
      () => import('./pages/Lineage'),
      () => import('./pages/Monitoring'),
      () => import('./pages/Jobs'),
      () => import('./pages/DatasetBuilds'),
      () => import('./pages/MaterializationSchedules'),
      () => import('./pages/Audit'),
      () => import('./pages/Chat'),
      () => import('./pages/Help'),
      () => import('./pages/Search'),
    ]
    const trigger = () => {
      preloadRoutes.forEach((fn) => fn().catch(() => {}))
    }
    if ('requestIdleCallback' in window) {
      window.requestIdleCallback(trigger)
    } else {
      setTimeout(trigger, 1000)
    }
  }, [])

  useEffect(() => {
    void refreshAuth()
  }, [refreshAuth])

  return (
    <AuthProvider
      value={{
        auth,
        loading: authLoading,
        refreshAuth,
        signInWithToken,
        signOut,
      }}
    >
      <BrowserRouter>
        <Layout>
          <Suspense fallback={<RouteFallback />}>
            <Routes>
              <Route path="/" element={<Dashboard />} />
              <Route path="/search" element={<SearchPage />} />
              <Route path="/features" element={<Features />} />
              <Route path="/features/:name" element={<Features />} />
              <Route path="/business-metrics" element={<BusinessMetrics />} />
              <Route path="/business-metrics/:name" element={<BusinessMetrics />} />
              <Route path="/entities" element={<Entities />} />
              <Route path="/entities/:name" element={<Entities />} />
              <Route path="/entity-relationships" element={<EntityRelationships />} />
              <Route path="/entity-relationships/:name" element={<EntityRelationships />} />
              <Route path="/feature-views" element={<FeatureViews />} />
              <Route path="/feature-views/:name" element={<FeatureViews />} />
              <Route path="/feature-sets" element={<FeatureSets />} />
              <Route path="/feature-sets/:name" element={<FeatureSets />} />
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
              <Route path="/online/materializations" element={<Navigate to="/online/materialization-schedules?tab=runs" replace />} />
              <Route path="/online/materialization-schedules" element={<MaterializationSchedules />} />
              <Route path="/jobs" element={<Jobs />} />
              <Route path="/chat" element={<Chat />} />
              <Route path="/help" element={<Help />} />
              {ComponentsDemo && <Route path="/dev/components" element={<ComponentsDemo />} />}
            </Routes>
          </Suspense>
        </Layout>
      </BrowserRouter>
    </AuthProvider>
  )
}
