import { lazy, Suspense } from 'react'
import { BrowserRouter, Routes, Route } from 'react-router-dom'
import { Layout } from './components/Layout'

const Dashboard = lazy(() => import('./pages/Dashboard').then((m) => ({ default: m.Dashboard })))
const Features = lazy(() => import('./pages/Features').then((m) => ({ default: m.Features })))
const Groups = lazy(() => import('./pages/Groups').then((m) => ({ default: m.Groups })))
const Similarity = lazy(() => import('./pages/Similarity').then((m) => ({ default: m.Similarity })))
const Monitoring = lazy(() => import('./pages/Monitoring').then((m) => ({ default: m.Monitoring })))
const Jobs = lazy(() => import('./pages/Jobs').then((m) => ({ default: m.Jobs })))
const Audit = lazy(() => import('./pages/Audit').then((m) => ({ default: m.Audit })))
const Chat = lazy(() => import('./pages/Chat').then((m) => ({ default: m.Chat })))

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
            <Route path="/features" element={<Features />} />
            <Route path="/features/:name" element={<Features />} />
            <Route path="/groups" element={<Groups />} />
            <Route path="/similarity" element={<Similarity />} />
            <Route path="/audit" element={<Audit />} />
            <Route path="/monitoring" element={<Monitoring />} />
            <Route path="/jobs" element={<Jobs />} />
            <Route path="/chat" element={<Chat />} />
          </Routes>
        </Suspense>
      </Layout>
    </BrowserRouter>
  )
}
