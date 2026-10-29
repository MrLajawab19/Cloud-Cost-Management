// src/components/TopBar.jsx
import React, { useState, useEffect, useRef } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import {
  Bell, User, Settings, RefreshCw, CloudCog, Menu, LogOut,
  ExternalLink, Globe, Plus, Database, Trash2, Moon, Sun,
  AlertTriangle, Lightbulb, Zap
} from 'lucide-react'
import { healthAPI, costsAPI, recommendationsAPI, accountsAPI, notificationsAPI } from '../api/client'
import { useAuth } from '../contexts/AuthContext'
import AddAccountModal from './AddAccountModal'

class NotificationErrorBoundary extends React.Component {
  constructor(props) {
    super(props)
    this.state = { hasError: false }
  }
  static getDerivedStateFromError() {
    return { hasError: true }
  }
  componentDidCatch(error, errorInfo) {
    console.error("NotificationErrorBoundary caught error:", error, errorInfo)
  }
  render() {
    if (this.state.hasError) {
      return (
        <div style={{ position: 'relative', marginLeft: '8px' }}>
          <button className="icon-btn" title="Notifications unavailable">
            <Bell size={15} color="#aab7b8" />
          </button>
        </div>
      )
    }
    return this.props.children
  }
}

const PAGE_TITLES = {
  '/': { title: 'Overview', sub: '' },
  '/resources': { title: 'Resource Inventory', sub: '' },
  '/costs': { title: 'Cost Analysis', sub: '' },
  '/recommendations': { title: 'Recommendations', sub: '' },
  '/predictions': { title: 'ML Predictions', sub: '' },
  '/simulations': { title: 'What-If Simulations', sub: '' },
  '/live-data-lab': { title: 'Live Data Lab', sub: '' },
}

export default function TopBar({ toggleSidebar }) {
  const location = useLocation()
  const navigate = useNavigate()
  const { title } = PAGE_TITLES[location.pathname] || { title: 'Dashboard' }

  const { user, logout, accounts, activeAccount, switchAccount, deleteAccount, dataVersion } = useAuth()
  
  const [health, setHealth] = useState(null)
  const [cost, setCost] = useState(0)
  const [refreshing, setRefreshing] = useState(false)
  const [showAddAccount, setShowAddAccount] = useState(false)
  const [confirmDeleteId, setConfirmDeleteId] = useState(null)
  
  // Dropdown states
  const [activeMenu, setActiveMenu] = useState(null) // 'settings', 'profile', 'notifications', 'account', or null
  const menuRef = useRef(null)

  // Notification states
  const [notifications, setNotifications] = useState([])
  const storageKey = `read_notifs_${activeAccount?.id || 'all'}`
  const [readIds, setReadIds] = useState(() => {
    try {
      const raw = localStorage.getItem(`read_notifs_${activeAccount?.id || 'all'}`)
      const parsed = raw ? JSON.parse(raw) : []
      return Array.isArray(parsed) ? parsed : []
    } catch {
      return []
    }
  })

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

  useEffect(() => { loadData() }, [activeAccount, dataVersion])

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

  // Close dropdowns on Escape key
  useEffect(() => {
    function handleKeyDown(e) {
      if (e.key === 'Escape') {
        setActiveMenu(null)
      }
    }
    document.addEventListener('keydown', handleKeyDown)
    return () => document.removeEventListener('keydown', handleKeyDown)
  }, [])

  // Fetch notifications and prune read IDs
  const fetchNotifications = async () => {
    if (!activeAccount?.id) return
    try {
      const res = await notificationsAPI.list({ account_id: activeAccount.id, limit: 30 })
      const list = Array.isArray(res.data) ? res.data : []
      setNotifications(list)

      const validIds = new Set(list.map(e => e?.id).filter(Boolean))
      try {
        const raw = localStorage.getItem(storageKey)
        const currentRead = raw ? JSON.parse(raw) : []
        if (Array.isArray(currentRead)) {
          const pruned = currentRead.filter(id => validIds.has(id))
          localStorage.setItem(storageKey, JSON.stringify(pruned))
          setReadIds(pruned)
        }
      } catch (err) {
        console.error("Failed to prune read notification IDs:", err)
      }
    } catch (e) {
      console.error("Notifications fetch failed:", e)
    }
  }

  useEffect(() => {
    fetchNotifications()
    const interval = setInterval(() => {
      if (document.visibilityState === 'visible') {
        fetchNotifications()
      }
    }, 45000)
    return () => clearInterval(interval)
  }, [activeAccount?.id, dataVersion, storageKey])

  const markAsRead = (eventId, link) => {
    if (eventId) {
      try {
        const raw = localStorage.getItem(storageKey)
        const currentRead = raw ? JSON.parse(raw) : []
        const updated = Array.isArray(currentRead) && !currentRead.includes(eventId)
          ? [...currentRead, eventId]
          : currentRead
        localStorage.setItem(storageKey, JSON.stringify(updated))
        setReadIds(updated)
      } catch (err) {
        console.error("Failed to mark notification read:", err)
      }
    }
    setActiveMenu(null)
    if (link) {
      navigate(link)
    }
  }

  const markAllAsRead = (e) => {
    e.stopPropagation()
    const allIds = (Array.isArray(notifications) ? notifications : []).map(n => n?.id).filter(Boolean)
    try {
      localStorage.setItem(storageKey, JSON.stringify(allIds))
      setReadIds(allIds)
    } catch (err) {
      console.error("Failed to mark all notifications read:", err)
    }
  }

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

  const getNotificationIcon = (type, severity) => {
    if (severity === 'critical') {
      return <AlertTriangle size={15} color="#ef4444" />
    }
    if (severity === 'warning') {
      return <AlertTriangle size={15} color="#f59e0b" />
    }
    if (type === 'recommendation_created' || type === 'demo_injected') {
      return <Lightbulb size={15} color="#60a5fa" />
    }
    return <Zap size={15} color="#34d399" />
  }

  const getRelativeTime = (isoString) => {
    if (!isoString) return ''
    try {
      const diffSec = Math.floor((new Date() - new Date(isoString)) / 1000)
      if (diffSec < 60) return 'just now'
      if (diffSec < 3600) return `${Math.floor(diffSec / 60)}m ago`
      if (diffSec < 86400) return `${Math.floor(diffSec / 3600)}h ago`
      return `${Math.floor(diffSec / 86400)}d ago`
    } catch {
      return ''
    }
  }

  const unreadCount = (Array.isArray(notifications) ? notifications : []).filter(n => n?.id && !readIds.includes(n.id)).length
  const badgeText = unreadCount > 9 ? '9+' : unreadCount

  return (
    <header className="topbar">
      <div className="topbar-brand">
        <button className="icon-btn" style={{ marginRight: '8px' }} onClick={toggleSidebar}>
          <Menu size={20} color="white" />
        </button>
        <CloudCog size={20} color="#ec7211" strokeWidth={2} />
        <div className="topbar-brand-name">CloudCost</div>
      </div>

      <div className="topbar-breadcrumb">
        <div className="topbar-page-title">{title}</div>
      </div>

      <div className="topbar-actions" ref={menuRef}>
        {activeAccount?.is_demo && (
          <div className="demo-badge" style={{ backgroundColor: '#d97706', color: '#fff', border: '1px solid #b45309' }}>Demo Account</div>
        )}
        
        {/* Account Switcher */}
        <div style={{ position: 'relative', marginRight: '16px' }}>
          <button 
            className="icon-btn" 
            style={{ padding: '4px 12px', width: 'auto', borderRadius: '4px', background: 'rgba(255,255,255,0.1)', display: 'flex', alignItems: 'center', gap: '6px' }}
            onClick={() => toggleMenu('account')}
          >
            <Database size={14} />
            <span style={{ fontSize: '13px', fontWeight: 500 }}>
              {activeAccount ? activeAccount.name : 'No Account'}
            </span>
            {activeAccount && (
              <span style={{
                padding: '1px 5px',
                borderRadius: '3px',
                fontSize: '10px',
                fontWeight: 700,
                textTransform: 'uppercase',
                background: activeAccount.provider === 'azure' ? 'rgba(0, 120, 212, 0.25)' : 'rgba(236, 114, 17, 0.25)',
                color: activeAccount.provider === 'azure' ? '#60a5fa' : '#fb923c',
              }}>
                {activeAccount.provider === 'azure' ? 'Azure' : 'AWS'}
              </span>
            )}
            {activeAccount?.is_demo && (
              <span style={{
                padding: '1px 5px',
                borderRadius: '3px',
                fontSize: '10px',
                fontWeight: 700,
                background: 'rgba(245, 158, 11, 0.25)',
                color: '#fbbf24',
              }}>
                DEMO
              </span>
            )}
          </button>
          
          {activeMenu === 'account' && (
            <div className="dropdown-menu">
              <div className="dropdown-header">Cloud Accounts</div>
              {accounts.map(acc => (
                <div 
                  key={acc.id} 
                  className={`dropdown-item ${activeAccount?.id === acc.id ? 'active' : ''}`}
                  style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', paddingRight: '8px' }}
                >
                  <div 
                    style={{ flex: 1, display: 'flex', justifyContent: 'space-between', alignItems: 'center', cursor: 'pointer', padding: '8px 0', paddingRight: '8px', gap: '8px' }}
                    onClick={() => { switchAccount(acc.id); setActiveMenu(null) }}
                  >
                    <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                      <span style={{ fontWeight: 500 }}>{acc.name}</span>
                      <span style={{
                        padding: '1px 5px',
                        borderRadius: '3px',
                        fontSize: '9px',
                        fontWeight: 700,
                        textTransform: 'uppercase',
                        background: acc.provider === 'azure' ? 'rgba(0, 120, 212, 0.15)' : 'rgba(236, 114, 17, 0.15)',
                        color: acc.provider === 'azure' ? '#0078d4' : '#ec7211',
                      }}>
                        {acc.provider === 'azure' ? 'Azure' : 'AWS'}
                      </span>
                      {acc.is_demo && (
                        <span style={{
                          padding: '1px 5px',
                          borderRadius: '3px',
                          fontSize: '9px',
                          fontWeight: 700,
                          background: 'rgba(245, 158, 11, 0.2)',
                          color: '#d97706',
                        }}>
                          DEMO
                        </span>
                      )}
                    </div>
                    <span style={{ fontSize: 11, color: 'var(--text-secondary)' }}>{acc.region}</span>
                  </div>
                  {!acc.is_demo && (
                    confirmDeleteId === acc.id ? (
                      <div style={{ display: 'flex', gap: '12px', alignItems: 'center', padding: '4px 8px' }}>
                        <span 
                          onClick={(e) => {
                            e.stopPropagation();
                            deleteAccount(acc.id);
                            setConfirmDeleteId(null);
                            setActiveMenu(null);
                          }}
                          style={{ fontSize: 12, color: '#ff4d4f', cursor: 'pointer', fontWeight: 600 }}
                          title="Confirm Delete"
                        >
                          Yes, Delete
                        </span>
                        <span 
                          onClick={(e) => {
                            e.stopPropagation();
                            setConfirmDeleteId(null);
                          }}
                          style={{ fontSize: 12, color: 'var(--text-secondary)', cursor: 'pointer' }}
                          title="Cancel"
                        >
                          Cancel
                        </span>
                      </div>
                    ) : (
                      <div
                        onClick={(e) => {
                          e.stopPropagation();
                          setConfirmDeleteId(acc.id);
                        }}
                        style={{ cursor: 'pointer', display: 'flex', alignItems: 'center', color: 'var(--text-secondary)', padding: '4px' }}
                        title="Remove Account"
                        onMouseEnter={(e) => e.currentTarget.style.color = '#ff4d4f'}
                        onMouseLeave={(e) => e.currentTarget.style.color = 'var(--text-secondary)'}
                      >
                        <Trash2 size={14} />
                      </div>
                    )
                  )}
                </div>
              ))}
              <div className="dropdown-divider" />
              <div 
                className="dropdown-item" 
                style={{ display: 'flex', alignItems: 'center', gap: 8, color: 'var(--accent-primary)' }}
                onClick={() => { setShowAddAccount(true); setActiveMenu(null) }}
              >
                <Plus size={14} /> Add Cloud Account
              </div>
            </div>
          )}
        </div>

        <div className="topbar-metric" style={{ marginRight: '8px' }}>
          <div className="topbar-metric-label">Est. Monthly:</div>
          <div className="topbar-metric-value">{cost != null ? `$${cost.toFixed(2)}` : '-'}</div>
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
        
        {/* Notification Bell */}
        <NotificationErrorBoundary>
          <div style={{ position: 'relative', marginLeft: '8px' }}>
            <button 
              className="icon-btn" 
              onClick={() => toggleMenu('notifications')}
              title="Notifications"
              style={{ position: 'relative' }}
            >
              <Bell size={15} color={activeMenu === 'notifications' ? 'white' : '#aab7b8'} />
              {unreadCount > 0 && (
                <span style={{
                  position: 'absolute',
                  top: '-4px',
                  right: '-4px',
                  background: '#ef4444',
                  color: '#ffffff',
                  fontSize: '9px',
                  fontWeight: 700,
                  padding: '1px 4px',
                  borderRadius: '8px',
                  minWidth: '15px',
                  height: '15px',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  lineHeight: 1,
                  border: '1px solid rgba(0,0,0,0.4)',
                }}>
                  {badgeText}
                </span>
              )}
            </button>

            {activeMenu === 'notifications' && (
              <div 
                className="dropdown-menu dropdown-menu-right" 
                style={{ width: '340px', maxHeight: '420px', display: 'flex', flexDirection: 'column', padding: 0 }}
              >
                <div 
                  className="dropdown-header" 
                  style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '10px 14px', borderBottom: '1px solid var(--border-color, rgba(255,255,255,0.1))' }}
                >
                  <span style={{ fontWeight: 600, fontSize: '13px' }}>
                    Notifications {unreadCount > 0 ? `(${unreadCount})` : ''}
                  </span>
                  {unreadCount > 0 && (
                    <button
                      onClick={markAllAsRead}
                      style={{
                        background: 'transparent',
                        border: 'none',
                        color: 'var(--brand-aws-blue, #60a5fa)',
                        fontSize: '11px',
                        cursor: 'pointer',
                        fontWeight: 500,
                        padding: '2px 6px',
                      }}
                    >
                      Mark all as read
                    </button>
                  )}
                </div>

                <div style={{ overflowY: 'auto', maxHeight: '340px', flex: 1 }}>
                  {(!Array.isArray(notifications) || notifications.length === 0) ? (
                    <div style={{ padding: '24px 16px', textAlign: 'center', color: 'var(--text-secondary, #94a3b8)', fontSize: '12px' }}>
                      No notifications
                    </div>
                  ) : (
                    notifications.map((n = {}) => {
                      const isUnread = n.id && !readIds.includes(n.id)
                      return (
                        <div
                          key={n.id || Math.random()}
                          onClick={() => markAsRead(n.id, n.link)}
                          style={{
                            padding: '10px 14px',
                            borderBottom: '1px solid rgba(255,255,255,0.05)',
                            cursor: 'pointer',
                            background: isUnread ? 'rgba(99, 102, 241, 0.08)' : 'transparent',
                            display: 'flex',
                            gap: 10,
                            alignItems: 'flex-start',
                            transition: 'background 0.15s ease',
                          }}
                          onMouseEnter={(e) => { e.currentTarget.style.background = 'rgba(255,255,255,0.06)' }}
                          onMouseLeave={(e) => { e.currentTarget.style.background = isUnread ? 'rgba(99, 102, 241, 0.08)' : 'transparent' }}
                        >
                          <div style={{ marginTop: '2px', flexShrink: 0 }}>
                            {getNotificationIcon(n.type, n.severity)}
                          </div>
                          <div style={{ flex: 1, minWidth: 0 }}>
                            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', gap: 6 }}>
                              <div style={{ fontSize: '12px', fontWeight: isUnread ? 700 : 500, color: 'var(--text-primary, #f1f5f9)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                                {n.title || 'Notification'}
                              </div>
                              <span style={{ fontSize: '10px', color: 'var(--text-secondary, #64748b)', flexShrink: 0 }}>
                                {getRelativeTime(n.created_at)}
                              </span>
                            </div>
                            <div style={{ fontSize: '11px', color: 'var(--text-secondary, #94a3b8)', marginTop: '2px', lineHeight: 1.3 }}>
                              {n.message || ''}
                            </div>
                          </div>
                          {isUnread && (
                            <span style={{ width: '6px', height: '6px', borderRadius: '50%', background: '#60a5fa', marginTop: '6px', flexShrink: 0 }} />
                          )}
                        </div>
                      )
                    })
                  )}
                </div>
              </div>
            )}
          </div>
        </NotificationErrorBoundary>

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
          <div className="loading-text">Syncing Cloud Resources...</div>
        </div>
      )}
    </header>
  )
}
