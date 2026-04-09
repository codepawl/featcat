import { BrowserRouter, Routes, Route } from 'react-router-dom'
import { Layout } from './components/Layout'
import { Dashboard } from './pages/Dashboard'
import { Features } from './pages/Features'
import { Monitoring } from './pages/Monitoring'
import { Jobs } from './pages/Jobs'
import { Chat } from './pages/Chat'

export default function App() {
  return (
    <BrowserRouter>
      <Layout>
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/features" element={<Features />} />
          <Route path="/features/:name" element={<Features />} />
          <Route path="/monitoring" element={<Monitoring />} />
          <Route path="/jobs" element={<Jobs />} />
          <Route path="/chat" element={<Chat />} />
        </Routes>
      </Layout>
    </BrowserRouter>
  )
}
