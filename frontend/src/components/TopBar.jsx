// src/components/TopBar.jsx — Refined top bar with health checks
import { useState, useEffect } from 'react'
import { useLocation } from 'react-router-dom'
import { Bell, User, Settings, RefreshCw } from 'lucide-react'
import { healthAPI, costsAPI } from '../api/client'

const PAGE_TITLES = {
  '/': { title: 'Overview', sub: 'Real-time AWS resource usage and cost estimates' },
  '/resources': { title: 'Resource Inventory', sub: 'All tracked AWS resources across your account' },
  '/costs': { title: 'Cost Analysis', sub: 'Breakdown of your AWS spending by service and over time' },
  '/recommendations': { title: 'Recommendations', sub: 'Unused and underutilized resources flagged for review' },
  '/predictions': { title: 'ML Predictions', sub: 'Machine learning forecast based on historical spending' },
}

export default function TopBar() {
  const location = useLocation()
  const { title, sub } = PAGE_TITLES[location.pathname] || { title: 'Dashboard', sub: '' }

  const [health, setHealth] = useState(null)
  const [cost, setCost] = useState(0)
  const [refreshing, setRefreshing] = useState(false)

  const loadData = async () => {
    try {
      const [h, c] = await Promise.all([healthAPI.check(), costsAPI.summary()])
      setHealth(h.data)
      setCost(c.data.total_monthly_cost_usd || 0)
    } catch (e) {
      console.error("TopBar data load failed:", e)
    }
  }

  useEffect(() => { loadData() }, [])

  const handleRefresh = async () => {
    setRefreshing(true)
    await loadData()
    setTimeout(() => setRefreshing(false), 800)
  }

  return (
    <header className="topbar">
      <div className="topbar-breadcrumb">
        <div className="topbar-page-title">{title}</div>
        <div className="topbar-page-sub">{sub}</div>
      </div>

      <div className="topbar-actions">
        {health?.demo_mode && (
          <div className="demo-badge">Demo Mode</div>
        )}
        
        <div className="topbar-metric" style={{ marginRight: 'var(--s-3)' }}>
          <div className="topbar-metric-label">Est. Monthly</div>
          <div className="topbar-metric-value">${cost.toFixed(2)}</div>
        </div>

        <div className="topbar-divider" />

        <button 
          className={`icon-btn ${refreshing ? 'spinning' : ''}`} 
          onClick={handleRefresh}
          title="Refresh Data"
        >
          <RefreshCw size={15} />
        </button>
        <button className="icon-btn">
          <Bell size={15} />
        </button>
        <button className="icon-btn">
          <Settings size={15} />
        </button>
        
        <div style={{ marginLeft: 'var(--s-2)', width: 34, height: 34, borderRadius: 'var(--r-md)', background: 'var(--grad-main)', display: 'flex', alignItems: 'center', justifyContent: 'center', boxShadow: 'var(--shadow-sm)', cursor: 'pointer' }}>
          <User size={16} color="white" />
        </div>
      </div>
    </header>
  )
}
