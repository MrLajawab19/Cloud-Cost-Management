// src/App.jsx — Root app with routing
import { BrowserRouter, Routes, Route } from 'react-router-dom'
import Sidebar from './components/Sidebar'
import TopBar  from './components/TopBar'
import Dashboard       from './pages/Dashboard'
import Resources       from './pages/Resources'
import Costs           from './pages/Costs'
import Recommendations from './pages/Recommendations'
import Predictions     from './pages/Predictions'

export default function App() {
  return (
    <BrowserRouter>
      <div className="app-layout">
        <Sidebar />
        <div className="main-content">
          <TopBar />
          <Routes>
            <Route path="/"                index element={<Dashboard />}       />
            <Route path="/resources"       element={<Resources />}       />
            <Route path="/costs"           element={<Costs />}           />
            <Route path="/recommendations" element={<Recommendations />} />
            <Route path="/predictions"     element={<Predictions />}     />
          </Routes>
        </div>
      </div>
    </BrowserRouter>
  )
}
