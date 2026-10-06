// src/components/Sidebar.jsx
import { NavLink } from 'react-router-dom'
import { useState, useEffect } from 'react'
import {
  LayoutDashboard, Server, DollarSign,
  Lightbulb, TrendingUp, AlertTriangle, FlaskConical, X
} from 'lucide-react'
import { recommendationsAPI, anomaliesAPI } from '../api/client'

const navItems = [
  { to: '/',                icon: LayoutDashboard, label: 'Dashboard',       end: true  },
  { to: '/resources',       icon: Server,          label: 'Resources'                   },
  { to: '/costs',           icon: DollarSign,      label: 'Cost Analysis'               },
  { to: '/recommendations', icon: Lightbulb,       label: 'Recommendations', badge: 'rec' },
  { to: '/predictions',     icon: TrendingUp,      label: 'ML Predictions'              },
  { to: '/anomalies',       icon: AlertTriangle,   label: 'Anomalies',       badge: 'anom' },
  { to: '/simulations',     icon: FlaskConical,    label: 'What-If'                     },
]

export default function Sidebar({ isOpen, closeSidebar }) {
  const [recCount,  setRecCount]  = useState(0)
  const [anomCount, setAnomCount] = useState(0)

  useEffect(() => {
    recommendationsAPI.summary()
      .then(r => setRecCount(r.data.total_recommendations || 0))
      .catch(() => {})
    anomaliesAPI.getSummary({ days: 30 })
      .then(r => setAnomCount(r.data.critical_count || 0))
      .catch(() => {})
  }, [])

  return (
    <aside className={`sidebar ${isOpen ? 'open' : ''}`}>
      {/* Brand area used for a close button in mobile/drawer mode */}
      <div className="sidebar-brand" style={{ display: 'flex', justifyContent: 'flex-end', padding: '10px' }}>
        <button className="icon-btn" style={{ color: 'var(--text-1)' }} onClick={closeSidebar}>
          <X size={20} />
        </button>
      </div>

      {/* Nav */}
      <nav className="sidebar-nav">
        <div className="nav-group-label" style={{ paddingLeft: '20px' }}>Cloud Services</div>
        {navItems.map(({ to, icon: Icon, label, end, badge }) => (
          <NavLink
            key={to}
            to={to}
            end={end}
            className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`}
            style={{ paddingLeft: '20px' }}
          >
            <Icon className="nav-icon" strokeWidth={1.8} />
            {label}
            {badge && badge === 'rec'  && recCount  > 0 && (
              <span className="nav-badge">{recCount}</span>
            )}
            {badge && badge === 'anom' && anomCount > 0 && (
              <span className="nav-badge" style={{ background: '#f87171' }}>{anomCount}</span>
            )}
          </NavLink>
        ))}
      </nav>

      {/* Footer */}
      <div className="sidebar-footer">
        <div className="status-pill">
          <span className="status-dot" />
          us-east-1
        </div>
      </div>
    </aside>
  )
}
