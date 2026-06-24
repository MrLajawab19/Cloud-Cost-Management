// src/App.jsx — Root app with routing
import { useState } from 'react'
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import Sidebar from './components/Sidebar'
import TopBar  from './components/TopBar'
import Dashboard       from './pages/Dashboard'
import Resources       from './pages/Resources'
import Costs           from './pages/Costs'
import Recommendations from './pages/Recommendations'
import Predictions     from './pages/Predictions'
import Login           from './pages/Login'
import Register        from './pages/Register'
import { AuthProvider, useAuth } from './contexts/AuthContext'

function ProtectedRoute({ children }) {
  const { user, loading } = useAuth()
  if (loading) return <div className="loading-screen">Loading...</div>
  if (!user) return <Navigate to="/login" />
  return children
}

function MainLayout() {
  const [isSidebarOpen, setIsSidebarOpen] = useState(false)

  const toggleSidebar = () => setIsSidebarOpen(!isSidebarOpen)
  const closeSidebar = () => setIsSidebarOpen(false)

  return (
    <div className="app-layout">
      <Sidebar isOpen={isSidebarOpen} closeSidebar={closeSidebar} />
      <div className={`main-content ${isSidebarOpen ? 'sidebar-open' : ''}`}>
        <TopBar toggleSidebar={toggleSidebar} />
        <Routes>
          <Route path="/"                index element={<Dashboard />}       />
          <Route path="/resources"       element={<Resources />}       />
          <Route path="/costs"           element={<Costs />}           />
          <Route path="/recommendations" element={<Recommendations />} />
          <Route path="/predictions"     element={<Predictions />}     />
        </Routes>
      </div>
    </div>
  )
}

export default function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route path="/register" element={<Register />} />
          <Route path="/*" element={
            <ProtectedRoute>
              <MainLayout />
            </ProtectedRoute>
          } />
        </Routes>
      </AuthProvider>
    </BrowserRouter>
  )
}
