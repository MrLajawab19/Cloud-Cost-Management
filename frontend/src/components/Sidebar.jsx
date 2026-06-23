// src/components/Sidebar.jsx
import { NavLink } from 'react-router-dom'
import {
  LayoutDashboard, Server, DollarSign,
  Lightbulb, TrendingUp, Cloud
} from 'lucide-react'
import './Sidebar.css'

const navItems = [
  { to: '/',               icon: LayoutDashboard, label: 'Dashboard'       },
  { to: '/resources',      icon: Server,          label: 'Resources'        },
  { to: '/costs',          icon: DollarSign,      label: 'Cost Analysis'    },
  { to: '/recommendations',icon: Lightbulb,       label: 'Recommendations'  },
  { to: '/predictions',    icon: TrendingUp,      label: 'ML Predictions'   },
]

export default function Sidebar() {
  return (
    <aside className="sidebar">
      {/* Logo */}
      <div className="sidebar-logo">
        <div className="logo-icon">
          <Cloud size={20} color="white" />
        </div>
        <div className="logo-text">
          <span className="logo-title">CloudCost</span>
          <span className="logo-sub">Management</span>
        </div>
      </div>

      {/* Navigation */}
      <nav className="sidebar-nav">
        <span className="nav-section-label">Navigation</span>
        {navItems.map(({ to, icon: Icon, label }) => (
          <NavLink
            key={to}
            to={to}
            end={to === '/'}
            className={({ isActive }) => `nav-link ${isActive ? 'active' : ''}`}
          >
            <Icon className="nav-icon" size={18} />
            {label}
          </NavLink>
        ))}
      </nav>

      {/* Footer */}
      <div className="sidebar-footer">
        <div className="version-badge">
          <span className="dot" />
          v1.0.0 · Live
        </div>
      </div>
    </aside>
  )
}
