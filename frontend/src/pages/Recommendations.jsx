// src/pages/Recommendations.jsx — Cleanup recommendations page
import { useState, useEffect } from 'react'
import { Lightbulb, CheckCircle, RefreshCw, Filter } from 'lucide-react'
import { recommendationsAPI } from '../api/client'

const SEVERITY_ORDER = { critical: 0, high: 1, medium: 2, low: 3 }

export default function Recommendations() {
  const [recs,      setRecs]      = useState([])
  const [summary,   setSummary]   = useState(null)
  const [loading,   setLoading]   = useState(true)
  const [refreshing,setRefreshing]= useState(false)
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

  const handleRefresh = async () => {
    setRefreshing(true)
    try {
      await recommendationsAPI.refresh()
      await load()
    } catch (e) { console.error(e) }
    finally { setRefreshing(false) }
  }

  useEffect(() => { load() }, [filter])

  return (
    <div className="page-content">
      <h1 className="page-title">Cleanup Recommendations</h1>
      <p className="page-subtitle">Unused and underutilized resources flagged for review</p>

      {/* Summary row */}
      {summary && (
        <div className="summary-cards" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', marginBottom: 'var(--space-xl)' }}>
          <div className="summary-card">
            <div className="card-label">Total Issues</div>
            <div className="card-value">{summary.total_recommendations}</div>
          </div>
          <div className="summary-card">
            <div className="card-label">Potential Savings</div>
            <div className="card-value" style={{ color: 'var(--color-success)', fontSize: 22 }}>
              ${(summary.total_potential_savings_usd || 0).toFixed(2)}/mo
            </div>
          </div>
          {Object.entries(summary.by_severity || {}).map(([sev, cnt]) => (
            <div key={sev} className="summary-card">
              <div className="card-label">Severity: {sev}</div>
              <div className="card-value" style={{ fontSize: 22 }}>{cnt}</div>
              <span className={`badge badge-${sev}`} style={{ marginTop: 4 }}>{sev}</span>
            </div>
          ))}
        </div>
      )}

      {/* Filter + Refresh bar */}
      <div className="filter-bar">
        <Filter size={14} color="var(--text-muted)" />
        <select
          className="filter-select"
          value={filter.severity}
          onChange={e => setFilter(f => ({ ...f, severity: e.target.value }))}
        >
          <option value="">All Severities</option>
          <option value="critical">Critical</option>
          <option value="high">High</option>
          <option value="medium">Medium</option>
          <option value="low">Low</option>
        </select>
        <select
          className="filter-select"
          value={filter.service_type}
          onChange={e => setFilter(f => ({ ...f, service_type: e.target.value }))}
        >
          <option value="">All Services</option>
          <option value="EC2">EC2</option>
          <option value="S3">S3</option>
          <option value="RDS">RDS</option>
          <option value="Lambda">Lambda</option>
        </select>
        <button
          className={`btn btn-ghost btn-sm ${refreshing ? 'refreshing' : ''}`}
          onClick={handleRefresh}
          style={{ marginLeft: 'auto' }}
        >
          <RefreshCw size={12} style={{ animation: refreshing ? 'spin 0.8s linear infinite' : 'none' }} />
          Re-scan
        </button>
      </div>

      {/* Recommendations list */}
      {loading ? (
        <div className="spinner-wrap"><div className="spinner" /><span>Loading recommendations…</span></div>
      ) : recs.length === 0 ? (
        <div className="card">
          <div className="empty-state">
            <CheckCircle size={40} color="var(--color-success)" />
            <h3 style={{ color: 'var(--text-primary)', marginTop: 12 }}>All clear!</h3>
            <p>No recommendations at this time.</p>
          </div>
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-md)' }}>
          {recs.map(rec => (
            <div key={rec.id} className="rec-card animate-in">
              <div className="rec-card-header">
                <div>
                  <span className={`badge badge-${rec.severity}`} style={{ marginRight: 8 }}>
                    {rec.severity}
                  </span>
                  <span className="rec-card-title">{rec.issue}</span>
                </div>
                <span style={{ fontSize: 12, color: 'var(--text-muted)', whiteSpace: 'nowrap' }}>
                  {rec.service_type} · {rec.region}
                </span>
              </div>

              <div className="rec-card-desc">{rec.description}</div>

              <div className="rec-card-action">
                💡 <strong>Action:</strong> {rec.action}
              </div>

              <div className="rec-card-footer">
                {rec.potential_savings_usd > 0 ? (
                  <span className="savings-amount">
                    Save ${rec.potential_savings_usd.toFixed(2)}/mo
                  </span>
                ) : (
                  <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>No direct cost</span>
                )}
                <button
                  className="btn btn-success btn-sm"
                  onClick={() => handleResolve(rec.id)}
                >
                  <CheckCircle size={12} />
                  Resolve
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
