// src/components/TopBar.jsx
import { useState, useEffect, useRef } from 'react'
import { useLocation } from 'react-router-dom'
import { Bell, User, Settings, RefreshCw, CloudCog, Menu, LogOut, ExternalLink, Globe, Plus, Database, Trash2, Moon, Sun } from 'lucide-react'
import { healthAPI, costsAPI, recommendationsAPI, accountsAPI } from '../api/client'
import { useAuth } from '../contexts/AuthContext'
import AddAccountModal from './AddAccountModal'

const PAGE_TITLES = {
  '/': { title: 'Overview', sub: '' },
  '/resources': { title: 'Resource Inventory', sub: '' },
  '/costs': { title: 'Cost Analysis', sub: '' },
  '/recommendations': { title: 'Recommendations', sub: '' },
  '/predictions': { title: 'ML Predictions', sub: '' },
}

export default function TopBar({ toggleSidebar }) {
  const location = useLocation()
  const { title } = PAGE_TITLES[location.pathname] || { title: 'Dashboard' }

  const { user, logout, accounts, activeAccount, switchAccount, deleteAccount } = useAuth()
  
  const [health, setHealth] = useState(null)
  const [cost, setCost] = useState(0)
  const [refreshing, setRefreshing] = useState(false)
  const [showAddAccount, setShowAddAccount] = useState(false)
  
  // Dropdown states
  const [activeMenu, setActiveMenu] = useState(null) // 'settings', 'profile', 'notifications', 'account', or null
  const menuRef = useRef(null)

  const [isDarkMode, setIsDarkMode] = useState(() => {
    return localStorage.getItem('theme') === 'dark'
  })

  useEffect(() => {
    if (isDarkMode) {
      document.documentElement.setAttribute('data-theme', 'dark')
      localStorage.setItem('theme', 'dark')
    } else {
      document.documentElement.removeAttribute('data-theme')
      localStorage.setItem('theme', 'light')
    }
  }, [isDarkMode])

  const loadData = async () => {
    if (!activeAccount) return;
    try {
      const [h, c] = await Promise.all([healthAPI.check(), costsAPI.summary()])
      setHealth(h.data)
      setCost(c.data.total_monthly_cost_usd || 0)
    } catch (e) {
      console.error("TopBar data load failed:", e)
    }
  }

  useEffect(() => { loadData() }, [activeAccount])

  // Close dropdowns if clicked outside
  useEffect(() => {
    function handleClickOutside(event) {
      if (menuRef.current && !menuRef.current.contains(event.target)) {
        setActiveMenu(null)
      }
    }
    document.addEventListener("mousedown", handleClickOutside)
    return () => document.removeEventListener("mousedown", handleClickOutside)
  }, [menuRef])

  const handleRefresh = async () => {
    setRefreshing(true)
    try {
      await accountsAPI.sync()
      await recommendationsAPI.refresh()
      await loadData()
      window.location.reload()
    } catch (e) {
      console.error("Sync failed:", e)
    }
    setTimeout(() => setRefreshing(false), 800)
  }

  const toggleMenu = (menu) => {
    setActiveMenu(activeMenu === menu ? null : menu)
  }

  return (
    <header className="topbar">
      <div className="topbar-brand">
        <button className="icon-btn" style={{ marginRight: '8px' }} onClick={toggleSidebar}>
          <Menu size={20} color="white" />
        </button>
        <CloudCog size={20} color="#ec7211" strokeWidth={2} />
        <div className="topbar-brand-name">AWS CloudCost</div>
      </div>

      <div className="topbar-breadcrumb">
        <div className="topbar-page-title">{title}</div>
      </div>

      <div className="topbar-actions" ref={menuRef}>
        {health?.demo_mode && (
          <div className="demo-badge">Demo Mode</div>
        )}
        
        {/* Account Switcher */}
        <div style={{ position: 'relative', marginRight: '16px' }}>
          <button 
            className="icon-btn" 
            style={{ padding: '4px 12px', width: 'auto', borderRadius: '4px', background: 'rgba(255,255,255,0.1)' }}
            onClick={() => toggleMenu('account')}
          >
            <Database size={14} style={{ marginRight: '6px' }} />
            <span style={{ fontSize: '13px', fontWeight: 500 }}>
              {activeAccount ? activeAccount.name : 'No Account'}
            </span>
          </button>
          
          {activeMenu === 'account' && (
            <div className="dropdown-menu">
              <div className="dropdown-header">AWS Accounts</div>
              {accounts.map(acc => (
                <div 
                  key={acc.id} 
                  className={`dropdown-item ${activeAccount?.id === acc.id ? 'active' : ''}`}
                  style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', paddingRight: '8px' }}
                >
                  <div 
                    style={{ flex: 1, display: 'flex', justifyContent: 'space-between', cursor: 'pointer', padding: '8px 0', paddingRight: '8px' }}
                    onClick={() => { switchAccount(acc.id); setActiveMenu(null) }}
                  >
                    <span>{acc.name}</span>
                    <span style={{ fontSize: 11, color: 'var(--text-secondary)' }}>{acc.region}</span>
                  </div>
                  <div
                    onClick={(e) => {
                      e.stopPropagation();
                      if (window.confirm("Are you sure you want to remove this AWS account?")) {
                        deleteAccount(acc.id);
                        setActiveMenu(null);
                      }
                    }}
                    style={{ cursor: 'pointer', display: 'flex', alignItems: 'center', color: 'var(--text-secondary)', padding: '4px' }}
                    title="Remove Account"
                    onMouseEnter={(e) => e.currentTarget.style.color = '#ff4d4f'}
                    onMouseLeave={(e) => e.currentTarget.style.color = 'var(--text-secondary)'}
                  >
                    <Trash2 size={14} />
                  </div>
                </div>
              ))}
              <div className="dropdown-divider" />
              <div 
                className="dropdown-item" 
                style={{ display: 'flex', alignItems: 'center', gap: 8, color: 'var(--accent-primary)' }}
                onClick={() => { setShowAddAccount(true); setActiveMenu(null) }}
              >
                <Plus size={14} /> Add AWS Account
              </div>
            </div>
          )}
        </div>

        <div className="topbar-metric" style={{ marginRight: '8px' }}>
          <div className="topbar-metric-label">Est. Monthly:</div>
          <div className="topbar-metric-value">${cost.toFixed(2)}</div>
        </div>

        <div className="topbar-divider" />

        <button 
          className={`icon-btn ${refreshing ? 'spinning' : ''}`} 
          onClick={handleRefresh}
          title="Force Sync AWS"
          style={{ display: 'flex', alignItems: 'center', gap: 6, padding: '4px 12px', width: 'auto', borderRadius: '4px', background: 'rgba(236,114,17,0.1)', color: '#ec7211' }}
        >
          <RefreshCw size={14} />
          <span style={{ fontSize: '12px', fontWeight: 600 }}>Sync</span>
        </button>
        
        {/* Settings */}
        <div style={{ position: 'relative', marginLeft: '8px' }}>
          <button className="icon-btn" onClick={() => toggleMenu('settings')}>
            <Settings size={15} color={activeMenu === 'settings' ? 'white' : '#aab7b8'} />
          </button>

          {activeMenu === 'settings' && (
            <div className="dropdown-menu dropdown-menu-right">
              <div className="dropdown-header">Settings</div>
              <div className="dropdown-item" style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <Globe size={14} /> Global Region: <strong>{activeAccount?.region || 'N/A'}</strong>
              </div>
              <div className="dropdown-divider" />
              <a href="https://console.aws.amazon.com" target="_blank" rel="noreferrer" style={{ textDecoration: 'none' }}>
                <div className="dropdown-item" style={{ display: 'flex', alignItems: 'center', gap: 8, color: 'var(--brand-aws-blue)' }}>
                  <ExternalLink size={14} /> Open AWS Console
                </div>
              </a>
            </div>
          )}
        </div>
        
        {/* Profile */}
        <div style={{ position: 'relative', marginLeft: '8px' }}>
          <div 
            style={{ 
              width: 28, height: 28, borderRadius: '50%', background: activeMenu === 'profile' ? '#1d8102' : '#3b4859', 
              display: 'flex', alignItems: 'center', justifyContent: 'center', cursor: 'pointer',
              transition: 'background 0.2s'
            }}
            onClick={() => toggleMenu('profile')}
          >
            <User size={14} color="white" />
          </div>

          {activeMenu === 'profile' && (
            <div className="dropdown-menu dropdown-menu-right">
              <div className="dropdown-header" style={{ paddingBottom: 8 }}>
                <div style={{ fontWeight: 700, fontSize: 14 }}>{user?.email || 'User'}</div>
              </div>
              <div className="dropdown-divider" />
              <div className="dropdown-item" style={{ display: 'flex', alignItems: 'center', gap: 8 }} onClick={() => { setIsDarkMode(!isDarkMode); setActiveMenu(null); }}>
                {isDarkMode ? <Sun size={14} /> : <Moon size={14} />} {isDarkMode ? 'Light Mode' : 'Night Mode'}
              </div>
              <div className="dropdown-divider" />
              <div className="dropdown-item" style={{ display: 'flex', alignItems: 'center', gap: 8, color: 'var(--color-danger)' }} onClick={logout}>
                <LogOut size={14} /> Sign Out
              </div>
            </div>
          )}
        </div>

      </div>

      {showAddAccount && (
        <AddAccountModal onClose={() => setShowAddAccount(false)} />
      )}

      {refreshing && (
        <div className="page-loading-overlay">
          <RefreshCw size={40} className="spinner-icon" />
          <div className="loading-text">Syncing AWS Resources...</div>
        </div>
      )}
    </header>
  )
}
