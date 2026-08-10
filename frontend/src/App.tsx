import { Routes, Route, Navigate } from 'react-router-dom'
import Layout from './components/Layout'
import Home from './pages/Home'
import Dashboard from './pages/Dashboard'
import Chat from './pages/Chat'
import Reports from './pages/Reports'
import Members from './pages/Members'
import MetricInput from './pages/MetricInput'
import Settings from './pages/Settings'
import CheckupRecommend from './pages/CheckupRecommend'
import Summaries from './pages/Summaries'
import Assess from './pages/Assess'

export default function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<Home />} />
        <Route path="/home" element={<Home />} />
        <Route path="/dashboard" element={<Dashboard />} />
        <Route path="/chat" element={<Chat />} />
        <Route path="/reports" element={<Reports />} />
        <Route path="/members" element={<Members />} />
        <Route path="/metric-input" element={<MetricInput />} />
        <Route path="/settings" element={<Settings />} />
        <Route path="/checkup" element={<CheckupRecommend />} />
        <Route path="/summaries" element={<Summaries />} />
        <Route path="/assess" element={<Assess />} />
        <Route path="*" element={<Navigate to="/dashboard" replace />} />
      </Route>
    </Routes>
  )
}
