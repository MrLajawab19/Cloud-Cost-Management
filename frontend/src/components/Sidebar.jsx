// src/components/Sidebar.jsx — Premium sidebar with badges
import { NavLink, useLocation } from 'react-router-dom'
import { useState, useEffect } from 'react'
import {
  LayoutDashboard, Server, DollarSign,
  Lightbulb, TrendingUp, CloudCog, ChevronRight
} from 'lucide-react'
import { recommendationsAPI } from '../api/client'

const navItems = [
  { to: '/',                icon: LayoutDashboard, label: 'Dashboard',       end: true  },
  { to: '/resources',       icon: Server,          label: 'Resources'                   },
  { to: '/costs',           icon: DollarSign,      label: 'Cost Analysis'               },
  { to: '/recommendations', icon: Lightbulb,       label: 'Recommendations', badge: true },
  { to: '/predictions',     icon: TrendingUp,      label: 'ML Predictions'              },
]

export default function Sidebar() {
  const location  = useLocation()
  const [recCount, setRecCount] = useState(0)

  useEffect(() => {
    recommendationsAPI.summary()
      .then(r => setRecCount(r.data.total_recommendations || 0))
      .catch(() => {})
  }, [])

  return (
    <aside className="sidebar">
      {/* Brand */}
      <div className="sidebar-brand">
        <div className="brand-icon">
          <CloudCog size={20} color="white" strokeWidth={1.8} />
        </div>
        <div className="brand-text">
          <div className="brand-name">CloudCost</div>
          <div className="brand-sub">Management · v1.0</div>
        </div>
      </div>

      {/* Nav */}
      <nav className="sidebar-nav">
        <div className="nav-group-label">Menu</div>
        {navItems.map(({ to, icon: Icon, label, end, badge }) => (
          <NavLink
            key={to}
            to={to}
            end={end}
            className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`}
          >
            <Icon className="nav-icon" strokeWidth={1.8} />
            {label}
            {badge && recCount > 0 && (
              <span className="nav-badge">{recCount}</span>
            )}
          </NavLink>
        ))}
      </nav>

      {/* Footer */}
      <div className="sidebar-footer">
        <div className="status-pill">
          <span className="status-dot" />
          All systems live
        </div>
      </div>
    </aside>
  )
}
