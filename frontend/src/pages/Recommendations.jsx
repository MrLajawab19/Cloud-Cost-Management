// src/pages/Recommendations.jsx — Cleanup recommendations page
import { useState, useEffect } from 'react'
import { Lightbulb, CheckCircle, Search, Filter, DollarSign, Zap, Lock, AlertTriangle, ShieldAlert } from 'lucide-react'
import { recommendationsAPI, remediationAPI, resourcesAPI } from '../api/client'
import { useAuth } from '../contexts/AuthContext'
import { SimulationModal } from './Simulations'

export default function Recommendations() {
  const { activeAccount } = useAuth()
  const [recs,          setRecs]          = useState([])
  const [summary,       setSummary]       = useState(null)
  const [loading,       setLoading]       = useState(true)
  const [filter,        setFilter]        = useState({ severity: '', service_type: '' })
  const [simulatingId,  setSimulatingId]  = useState(null)  // rec id being simulated

  // Remediation states
  const [remediation,     setRemediation]     = useState({ escalations: [], logs: [] })
  const [fastForwarding,  setFastForwarding]  = useState(false)
  const [resourceCount,   setResourceCount]   = useState(null)

  const loadRemediation = async () => {
    try {
      const [remRes, resSummary] = await Promise.all([
        remediationAPI.status().catch(() => ({ data: { escalations: [], logs: [] } })),
        resourcesAPI.summary().catch(() => ({ data: { total_resources: 0 } })),
      ])
      setRemediation(remRes.data || { escalations: [], logs: [] })
      setResourceCount(resSummary.data?.total_resources ?? 0)
    } catch (e) {
      console.error("Failed to load remediation:", e)
    }
  }

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
      setRecs(r.data || [])
      setSummary(s.data)
      await loadRemediation()
    } catch (e) { console.error(e) }
    finally { setLoading(false) }
  }

  const handleResolve = async (id) => {
    try {
      await recommendationsAPI.resolve(id)
      setRecs(prev => prev.filter(r => r.id !== id))
      setSummary(prev => ({
        ...prev,
        total_recommendations: Math.max(0, (prev?.total_recommendations || 1) - 1),
      }))
      await loadRemediation()
    } catch (e) { console.error(e) }
  }

  const handleFastForward = async () => {
    if (!activeAccount?.id || fastForwarding) return
    setFastForwarding(true)
    try {
      await remediationAPI.fastForward(activeAccount.id)
      await Promise.all([load(), loadRemediation()])
    } catch (e) {
      console.error("Fast forward failed:", e)
    } finally {
      setFastForwarding(false)
    }
  }

  useEffect(() => { load() }, [filter, activeAccount?.id])

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
      {/* Synthetic Pricing Banner */}
      {recs.some(r => r.action === "Purchase Savings Plan") && (
        <div className="warning-banner stagger-1" style={{ marginBottom: 20, background: 'rgba(234, 179, 8, 0.1)', color: '#ca8a04', border: '1px solid rgba(234, 179, 8, 0.2)', padding: '12px 16px', borderRadius: 8, display: 'flex', gap: 12, alignItems: 'center' }}>
          <AlertTriangle size={18} />
          <div style={{ fontSize: 13 }}>
            <strong>Synthetic Data Caveat:</strong> Savings Plan pricing and break-even points are based on synthetic seed pricing tables, not live AWS Pricing API data.
          </div>
        </div>
      )}

      {/* Summary row */}
      {summary && (
        <div className="metric-grid" style={{ gridTemplateColumns: 'repeat(4, 1fr)' }}>
          <div className="metric-card stagger-1">
            <div className="metric-label">Total Issues</div>
            <div className="metric-value">{summary.total_recommendations || 0}</div>
            <div className="metric-sub">Action items</div>
          </div>
          <div className="metric-card stagger-2">
            <div className="metric-label">Potential Savings</div>
            <div className="metric-value" style={{ color: '#34d399' }}>
              {summary.total_potential_savings_usd != null ? `$${summary.total_potential_savings_usd.toFixed(2)}` : 'Cost unavailable'}
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
          <Filter size={15} style={{ color: 'var(--text-4)' }} />
          <span style={{ fontSize: 12, color: 'var(--text-3)', fontWeight: 600 }}>Filter:</span>

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
            <option value="AzureVM">AzureVM</option>
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
            <div className="empty-title">
              {resourceCount === 0 ? "No resources" : "All clear!"}
            </div>
            <div className="empty-sub">
              {resourceCount === 0
                ? "No resources found in this account"
                : "Your cloud infrastructure is fully optimized. No recommendations at this time."}
            </div>
          </div>
        </div>
      ) : (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(400px, 1fr))', gap: 'var(--s-5)' }}>
          {recs.map((rec, i) => (
            <div key={rec.id} className={`rec-card stagger-${(i % 4) + 1}`}>
              <div className="rec-card-header">
                <div className={`rec-severity-bar ${rec.severity}`} />
                <div style={{ flex: 1 }}>
                  <div className="rec-card-meta" style={{ marginBottom: 'var(--s-2)', display: 'flex', gap: '6px', alignItems: 'center', flexWrap: 'wrap' }}>
                    <span className={`badge badge-${rec.severity}`}>
                      {rec.severity?.toUpperCase()}
                    </span>
                    <span className={`chip chip-${rec.service_type?.toLowerCase()}`}>
                      {rec.service_type}
                    </span>
                    {rec.remediation_type && (
                      <span style={{
                        fontSize: '11px',
                        padding: '2px 6px',
                        borderRadius: '4px',
                        background: 'rgba(99, 102, 241, 0.15)',
                        color: '#818cf8',
                        border: '1px solid rgba(99, 102, 241, 0.3)',
                        fontWeight: 500,
                        textTransform: 'capitalize'
                      }}>
                        {rec.remediation_type}
                      </span>
                    )}
                    <span style={{
                      fontSize: '11px',
                      padding: '2px 6px',
                      borderRadius: '4px',
                      background: rec.is_resolved ? 'rgba(16, 185, 129, 0.15)' : 'rgba(239, 68, 68, 0.15)',
                      color: rec.is_resolved ? '#34d399' : '#f87171',
                      border: `1px solid ${rec.is_resolved ? 'rgba(16, 185, 129, 0.3)' : 'rgba(239, 68, 68, 0.3)'}`,
                      fontWeight: 500
                    }}>
                      {rec.is_resolved ? 'Resolved' : 'Active'}
                    </span>
                    <span style={{ fontSize: 11, color: 'var(--text-4)' }}>{rec.region}</span>
                  </div>
                  <div className="rec-card-title">{rec.issue}</div>
                </div>
              </div>

              <div className="rec-card-body">
                <div className="rec-card-desc">{rec.description}</div>
                <div className="rec-action-box" style={{ marginTop: 'var(--s-4)', display: 'flex', alignItems: 'center', gap: 6 }}>
                  {rec.action === "Purchase Savings Plan" && <Lock size={14} style={{color: '#8b5cf6'}} />}
                  <div><strong>Action Plan:</strong> {rec.action}</div>
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
                <div style={{ display: 'flex', gap: 6 }}>
                  {rec.potential_savings_usd > 0 && (
                    <button
                      id={`sim-inline-${rec.id}`}
                      className="btn btn-sm"
                      onClick={() => setSimulatingId(rec.id)}
                      style={{
                        background: 'rgba(52,211,153,0.1)',
                        border: '1px solid rgba(52,211,153,0.25)',
                        color: '#34d399',
                      }}
                      title="Project cost impact before acting"
                    >
                      <Zap size={13} />
                      Simulate
                    </button>
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
            </div>
          ))}
        </div>
      )}

      {/* Remediation & Escalations Section (FR-7) */}
      <div className="card stagger-4" style={{ marginTop: 'var(--s-6)' }}>
        <div className="card-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 12 }}>
          <div>
            <div className="card-title" style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <Zap size={18} color="#ec7211" />
              Automated Remediation & Escalation Status
            </div>
            <div style={{ fontSize: 12, color: 'var(--text-3)', marginTop: 2 }}>
              FR-7 auto-stop and auto-resize lifecycle tracking
            </div>
          </div>
          {activeAccount?.is_demo && (
            <button
              className="btn btn-sm"
              onClick={handleFastForward}
              disabled={fastForwarding}
              style={{
                background: 'rgba(234, 179, 8, 0.15)',
                color: '#eab308',
                border: '1px solid rgba(234, 179, 8, 0.3)',
                fontWeight: 600,
                display: 'flex',
                alignItems: 'center',
                gap: 6,
              }}
            >
              <Zap size={14} />
              {fastForwarding ? 'Fast-forwarding...' : 'Fast-forward demo'}
            </button>
          )}
        </div>

        {/* Escalations List */}
        <div style={{ marginTop: 'var(--s-4)' }}>
          <div style={{ fontSize: 13, fontWeight: 700, marginBottom: 'var(--s-2)', color: 'var(--text-1)' }}>
            Active Escalations ({remediation.escalations?.length || 0})
          </div>
          {remediation.escalations && remediation.escalations.length > 0 ? (
            <div className="table-wrap" style={{ border: 'none', borderTop: '1px solid var(--glass-border)', borderRadius: 0 }}>
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Resource / Issue</th>
                    <th>Stage</th>
                    <th>Time Remaining</th>
                    <th>Anomaly Status</th>
                  </tr>
                </thead>
                <tbody>
                  {remediation.escalations.map((esc, idx) => (
                    <tr key={esc.recommendation_id || idx}>
                      <td className="td-primary">
                        <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
                          <span>{esc.resource_name || 'Resource'}</span>
                          <span style={{ fontSize: 11, color: 'var(--text-3)' }}>{esc.issue}</span>
                        </div>
                      </td>
                      <td>
                        <span className={`badge badge-${esc.stage === 'resolved' ? 'running' : 'stopped'}`} style={{ textTransform: 'capitalize' }}>
                          {esc.stage || esc.status}
                        </span>
                      </td>
                      <td style={{ fontSize: 12, color: 'var(--text-2)' }}>
                        {esc.stage === 'resolved' ? 'Completed' : `${esc.hours_remaining ?? 0}h remaining`}
                      </td>
                      <td>
                        {esc.held ? (
                          <div style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
                            <span style={{
                              padding: '2px 6px',
                              borderRadius: 4,
                              background: 'rgba(239, 68, 68, 0.15)',
                              color: '#f87171',
                              border: '1px solid rgba(239, 68, 68, 0.3)',
                              fontSize: 10,
                              fontWeight: 700,
                            }}>
                              HELD
                            </span>
                            <span style={{ fontSize: 11, color: '#f87171' }}>
                              {esc.held_reason || 'Active anomaly'}
                            </span>
                          </div>
                        ) : (
                          <span style={{ fontSize: 11, color: '#34d399' }}>Eligible (No anomalies)</span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <div style={{ fontSize: 12, color: 'var(--text-3)', padding: '12px 0' }}>
              No pending escalations for this account.
            </div>
          )}
        </div>

        {/* Audit Logs */}
        <div style={{ marginTop: 'var(--s-5)', borderTop: '1px solid var(--glass-border)', paddingTop: 'var(--s-4)' }}>
          <div style={{ fontSize: 13, fontWeight: 700, marginBottom: 'var(--s-2)', color: 'var(--text-1)' }}>
            Remediation Audit Logs ({remediation.logs?.length || 0})
          </div>
          {remediation.logs && remediation.logs.length > 0 ? (
            <div className="table-wrap" style={{ border: 'none', borderTop: '1px solid var(--glass-border)', borderRadius: 0 }}>
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Timestamp</th>
                    <th>Resource</th>
                    <th>Action</th>
                    <th>Status</th>
                    <th>Trigger Reason</th>
                  </tr>
                </thead>
                <tbody>
                  {remediation.logs.map((log, idx) => (
                    <tr key={idx}>
                      <td style={{ fontSize: 11, color: 'var(--text-3)' }}>
                        {log.created_at ? new Date(log.created_at).toLocaleString() : '—'}
                      </td>
                      <td className="td-primary">{log.resource_name || 'Resource'}</td>
                      <td>
                        <span style={{
                          padding: '2px 6px',
                          borderRadius: 4,
                          fontSize: 10,
                          fontWeight: 600,
                          background: 'rgba(99, 102, 241, 0.15)',
                          color: '#818cf8',
                          textTransform: 'uppercase',
                        }}>
                          {log.action_type}
                        </span>
                      </td>
                      <td>
                        <span style={{
                          padding: '2px 6px',
                          borderRadius: 4,
                          fontSize: 10,
                          fontWeight: 600,
                          background: log.status === 'simulated' ? 'rgba(52, 211, 153, 0.15)' : 'rgba(96, 165, 250, 0.15)',
                          color: log.status === 'simulated' ? '#34d399' : '#60a5fa',
                          textTransform: 'uppercase',
                        }}>
                          {log.status}
                        </span>
                      </td>
                      <td style={{ fontSize: 11, color: 'var(--text-2)' }}>
                        {log.trigger_reason}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <div style={{ fontSize: 12, color: 'var(--text-3)', padding: '12px 0' }}>
              No remediation actions executed yet.
            </div>
          )}
        </div>
      </div>

      {/* Simulation modal */}
      {simulatingId && (
        <SimulationModal recId={simulatingId} onClose={() => setSimulatingId(null)} />
      )}

    </div>
  )
}
