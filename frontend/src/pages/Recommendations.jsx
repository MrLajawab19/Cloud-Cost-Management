// src/pages/Recommendations.jsx — Cleanup recommendations page
import { useState, useEffect } from 'react'
import { Lightbulb, CheckCircle, Search, Filter, DollarSign } from 'lucide-react'
import { recommendationsAPI } from '../api/client'

export default function Recommendations() {
  const [recs,      setRecs]      = useState([])
  const [summary,   setSummary]   = useState(null)
  const [loading,   setLoading]   = useState(true)
  const [filter,    setFilter]    = useState({ severity: '', service_type: '' })

  const load = async () => {
    setLoading(true)
    try {
      const params = {}
      if (filter.severity)     params.severity     = filter.severity
      if (filter.service_type) params.service_type = filter.service_type
      const [r, s] = await Promise.all([
        recommendationsAPI.list(params),
        recommendationsAPI.summary(),
      ])
      setRecs(r.data)
      setSummary(s.data)
    } catch (e) { console.error(e) }
    finally { setLoading(false) }
  }

  const handleResolve = async (id) => {
    try {
      await recommendationsAPI.resolve(id)
      setRecs(prev => prev.filter(r => r.id !== id))
      setSummary(prev => ({
        ...prev,
        total_recommendations: prev.total_recommendations - 1,
      }))
    } catch (e) { console.error(e) }
  }

  useEffect(() => { load() }, [filter])

  if (loading && !summary) {
    return (
      <div className="page-content">
        <div className="loading-wrap">
          <div className="spinner" />
          <div className="loading-text">Scanning for issues…</div>
        </div>
      </div>
    )
  }

  return (
    <div className="page-content animate-up">
      {/* Summary row */}
      {summary && (
        <div className="metric-grid" style={{ gridTemplateColumns: 'repeat(4, 1fr)' }}>
          <div className="metric-card stagger-1">
            <div className="metric-label">Total Issues</div>
            <div className="metric-value">{summary.total_recommendations}</div>
            <div className="metric-sub">Action items</div>
          </div>
          <div className="metric-card stagger-2">
            <div className="metric-label">Potential Savings</div>
            <div className="metric-value" style={{ color: '#34d399' }}>
              ${(summary.total_potential_savings_usd || 0).toFixed(2)}
            </div>
            <div className="metric-sub">Monthly reduction</div>
          </div>
          <div className="metric-card stagger-3">
            <div className="metric-label">High Priority</div>
            <div className="metric-value" style={{ color: '#ef4444' }}>
              {summary.by_severity?.high || 0}
            </div>
            <div className="metric-sub">Requires attention</div>
          </div>
          <div className="metric-card stagger-4">
            <div className="metric-label">Quick Wins</div>
            <div className="metric-value" style={{ color: '#60a5fa' }}>
              {(summary.by_severity?.low || 0) + (summary.by_severity?.medium || 0)}
            </div>
            <div className="metric-sub">Low hanging fruit</div>
          </div>
        </div>
      )}

      {/* Filter bar */}
      <div className="filter-bar stagger-2">
        <div className="filter-group">
          <Filter size={14} color="var(--text-3)" />
          <span className="filter-bar-label" style={{ marginLeft: 'var(--s-1)' }}>Filters</span>
        </div>
        <div className="topbar-divider" style={{ height: 20, margin: '0 var(--s-2)' }} />
        
        <div className="filter-group">
          <select
            className="select-input"
            value={filter.severity}
            onChange={e => setFilter(f => ({ ...f, severity: e.target.value }))}
          >
            <option value="">All Severities</option>
            <option value="critical">Critical</option>
            <option value="high">High</option>
            <option value="medium">Medium</option>
            <option value="low">Low</option>
          </select>
        </div>
        <div className="filter-group">
          <select
            className="select-input"
            value={filter.service_type}
            onChange={e => setFilter(f => ({ ...f, service_type: e.target.value }))}
          >
            <option value="">All Services</option>
            <option value="EC2">EC2</option>
            <option value="S3">S3</option>
            <option value="RDS">RDS</option>
            <option value="Lambda">Lambda</option>
          </select>
        </div>
      </div>

      {/* Recommendations list */}
      {recs.length === 0 ? (
        <div className="card stagger-3">
          <div className="empty-state">
            <div className="empty-icon" style={{ color: 'var(--color-success)', background: 'rgba(16,185,129,0.1)' }}>
              <CheckCircle size={28} />
            </div>
            <div className="empty-title">All clear!</div>
            <div className="empty-sub">Your cloud infrastructure is fully optimized. No recommendations at this time.</div>
          </div>
        </div>
      ) : (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(400px, 1fr))', gap: 'var(--s-5)' }}>
          {recs.map((rec, i) => (
            <div key={rec.id} className={`rec-card stagger-${(i % 4) + 1}`}>
              <div className="rec-card-header">
                <div className={`rec-severity-bar ${rec.severity}`} />
                <div style={{ flex: 1 }}>
                  <div className="rec-card-meta" style={{ marginBottom: 'var(--s-2)' }}>
                    <span className={`badge badge-${rec.severity}`}>
                      {rec.severity.toUpperCase()}
                    </span>
                    <span className={`chip chip-${rec.service_type.toLowerCase()}`}>
                      {rec.service_type}
                    </span>
                    <span style={{ fontSize: 11, color: 'var(--text-4)' }}>{rec.region}</span>
                  </div>
                  <div className="rec-card-title">{rec.issue}</div>
                </div>
              </div>

              <div className="rec-card-body">
                <div className="rec-card-desc">{rec.description}</div>
                <div className="rec-action-box" style={{ marginTop: 'var(--s-4)' }}>
                  <strong>Action Plan:</strong> {rec.action}
                </div>
              </div>

              <div className="rec-footer">
                {rec.potential_savings_usd > 0 ? (
                  <div className="savings-chip">
                    <DollarSign size={14} />
                    Save ${rec.potential_savings_usd.toFixed(2)}/mo
                  </div>
                ) : (
                  <div style={{ fontSize: 12, color: 'var(--text-4)' }}>
                    Performance optimization (no direct cost)
                  </div>
                )}
                <button
                  className="btn btn-success btn-sm"
                  onClick={() => handleResolve(rec.id)}
                >
                  <CheckCircle size={14} />
                  Mark Resolved
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
