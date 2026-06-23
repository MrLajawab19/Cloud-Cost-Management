// src/components/TopBar.jsx
import { useState, useEffect } from 'react'
import { useLocation } from 'react-router-dom'
import { RefreshCw, Activity } from 'lucide-react'
import { costsAPI, healthAPI } from '../api/client'
import './TopBar.css'

const PAGE_TITLES = {
  '/':               { title: 'Dashboard',         sub: 'Overview of your AWS cloud costs' },
  '/resources':      { title: 'Resource Inventory', sub: 'All tracked cloud resources'       },
  '/costs':          { title: 'Cost Analysis',      sub: 'Spending breakdown and trends'     },
  '/recommendations':{ title: 'Recommendations',    sub: 'Cleanup and saving opportunities'  },
  '/predictions':    { title: 'ML Predictions',     sub: '30-day cost forecast'              },
}

export default function TopBar({ onRefresh }) {
  const location  = useLocation()
  const pageInfo  = PAGE_TITLES[location.pathname] || PAGE_TITLES['/']

  const [totalCost, setTotalCost] = useState(null)
  const [demoMode,  setDemoMode]  = useState(false)
  const [refreshing, setRefreshing] = useState(false)

  useEffect(() => {
    costsAPI.summary().then(r => setTotalCost(r.data.total_monthly_cost_usd)).catch(() => {})
    healthAPI.check().then(r => setDemoMode(r.data.demo_mode)).catch(() => {})
  }, [])

  const handleRefresh = async () => {
    setRefreshing(true)
    if (onRefresh) await onRefresh()
    setTimeout(() => setRefreshing(false), 1000)
  }

  return (
    <header className="topbar">
      <div className="topbar-left">
        <span className="topbar-title">{pageInfo.title}</span>
        <span className="topbar-breadcrumb">{pageInfo.sub}</span>
      </div>

      <div className="topbar-right">
        {demoMode && (
          <span className="mode-badge">DEMO MODE</span>
        )}

        {totalCost !== null && (
          <div className="topbar-stat">
            <span className="stat-label">Est. Monthly</span>
            <span className="stat-value cost">${totalCost.toFixed(2)}</span>
          </div>
        )}

        <div className="topbar-stat">
          <span className="stat-label">Status</span>
          <span className="stat-value" style={{ fontSize: 13, color: 'var(--color-success)', display: 'flex', alignItems: 'center', gap: 4 }}>
            <Activity size={12} /> Live
          </span>
        </div>

        <button
          className={`refresh-btn ${refreshing ? 'refreshing' : ''}`}
          onClick={handleRefresh}
          title="Refresh data"
        >
          <RefreshCw size={13} className="refresh-icon" />
          Refresh
        </button>
      </div>
    </header>
  )
}
