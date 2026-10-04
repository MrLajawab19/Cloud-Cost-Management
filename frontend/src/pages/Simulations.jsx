// src/pages/Simulations.jsx — FR-4 What-If Simulations page
import { useState, useEffect, useCallback } from 'react'
import { CheckCircle, Zap, AlertTriangle, TrendingUp, TrendingDown, Info, RefreshCw } from 'lucide-react'
import { recommendationsAPI, simulationsAPI } from '../api/client'

// ── Helpers ───────────────────────────────────────────────────────
const SVC_COLORS = { EC2: '#ec7211', RDS: '#0073bb', S3: '#1d8102', Lambda: '#6366f1' }

function fmt(v) { return `$${Number(v ?? 0).toFixed(2)}` }

// ── Before/After bar ──────────────────────────────────────────────
function SimBar({ baseline, simulated, uncertainty }) {
  const max = Math.max(baseline, 0.01)
  const basePct = 100
  const simPct  = Math.min((simulated / max) * 100, 100)
  const uncPct  = Math.min((uncertainty / max) * 100, 8)

  return (
    <div style={{ margin: '14px 0' }}>
      {/* Baseline bar */}
      <div style={{ marginBottom: 6 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11, color: 'var(--text-3)', marginBottom: 3 }}>
          <span>Current forecast (baseline)</span>
          <span style={{ fontWeight: 700, color: 'var(--text-2)' }}>{fmt(baseline)}/mo</span>
        </div>
        <div style={{ height: 10, background: 'rgba(255,255,255,0.06)', borderRadius: 5, overflow: 'hidden' }}>
          <div style={{ height: '100%', width: '100%', background: 'rgba(100,116,139,0.4)', borderRadius: 5 }} />
        </div>
      </div>

      {/* Simulated bar — animated */}
      <div>
        <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11, color: 'var(--text-3)', marginBottom: 3 }}>
          <span>After applying recommendation</span>
          <span style={{ fontWeight: 700, color: '#34d399' }}>{fmt(simulated)}/mo</span>
        </div>
        <div style={{ height: 10, background: 'rgba(255,255,255,0.06)', borderRadius: 5, overflow: 'hidden', position: 'relative' }}>
          <div style={{
            height: '100%',
            width: `${simPct}%`,
            background: 'linear-gradient(90deg, #34d399, #059669)',
            borderRadius: 5,
            transition: 'width 0.8s cubic-bezier(0.25, 1, 0.5, 1)',
          }} />
          {/* Uncertainty band */}
          <div style={{
            position: 'absolute', top: 0, right: 0,
            height: '100%', width: `${uncPct}%`,
            background: 'rgba(251,191,36,0.2)',
            borderLeft: '1px dashed rgba(251,191,36,0.4)',
          }} title={`±${fmt(uncertainty)} forecast uncertainty`} />
        </div>
        <div style={{ fontSize: 10, color: 'var(--text-4)', marginTop: 3, textAlign: 'right' }}>
          ±{fmt(uncertainty)} forecast uncertainty band
        </div>
      </div>
    </div>
  )
}

// ── Simulation Result Card ────────────────────────────────────────
function SimCard({ sim }) {
  const svcColor = SVC_COLORS[sim.service_type] || 'var(--text-3)'
  const trendUp  = sim.monthly_trend_rate > 0

  return (
    <div className="card" style={{
      border: `1px solid rgba(52,211,153,0.2)`,
      background: 'linear-gradient(135deg, rgba(52,211,153,0.03), rgba(0,0,0,0))',
    }}>
      {/* Header */}
      <div className="card-header" style={{ paddingBottom: 0 }}>
        <div className="card-title" style={{ gap: 8 }}>
          <span className={`chip chip-${sim.service_type.toLowerCase()}`}>{sim.service_type}</span>
          {sim.resource_name}
        </div>
        <span style={{ fontSize: 11, color: 'var(--text-4)', marginLeft: 'auto' }}>{sim.region}</span>
      </div>

      {/* Before/After bar */}
      <SimBar
        baseline={sim.baseline_30d_usd}
        simulated={sim.simulated_30d_usd}
        uncertainty={sim.uncertainty_band_usd}
      />

      {/* Delta summary */}
      <div style={{
        display: 'flex', gap: 20, padding: '12px 0',
        borderTop: '1px solid rgba(255,255,255,0.05)',
        borderBottom: '1px solid rgba(255,255,255,0.05)',
      }}>
        <div>
          <div style={{ fontSize: 11, color: 'var(--text-3)' }}>Estimated Saving</div>
          <div style={{ fontSize: 22, fontWeight: 800, color: '#34d399' }}>
            {fmt(sim.delta_usd)}<span style={{ fontSize: 12, fontWeight: 400, color: 'var(--text-3)' }}>/mo</span>
          </div>
        </div>
        <div>
          <div style={{ fontSize: 11, color: 'var(--text-3)' }}>Reduction</div>
          <div style={{ fontSize: 22, fontWeight: 800, color: '#34d399' }}>
            {(sim.delta_pct ?? 0).toFixed(1)}%
          </div>
        </div>
        {sim.upfront_cost_usd > 0 && (
          <div>
            <div style={{ fontSize: 11, color: 'var(--text-3)' }}>Cash Impact (Mo 1)</div>
            <div style={{ fontSize: 16, fontWeight: 700, color: '#f87171', marginTop: 4 }}>
              {fmt(sim.first_month_cash_impact_usd)}
            </div>
            <div style={{ fontSize: 10, color: 'var(--text-4)' }}>Breakeven: {sim.payback_days}d</div>
          </div>
        )}
        {sim.monthly_trend_rate !== 0 && (
          <div style={{ marginLeft: 'auto', textAlign: 'right' }}>
            <div style={{ fontSize: 11, color: 'var(--text-3)' }}>{sim.service_type} trend</div>
            <div style={{
              fontSize: 13, fontWeight: 700,
              color: trendUp ? '#f87171' : '#34d399',
              display: 'flex', alignItems: 'center', gap: 4, justifyContent: 'flex-end',
            }}>
              {trendUp ? <TrendingUp size={13} /> : <TrendingDown size={13} />}
              {trendUp ? '+' : ''}{fmt(sim.monthly_trend_rate)}/mo trend
            </div>
          </div>
        )}
      </div>

      {/* Approximation notice */}
      <div style={{
        marginTop: 10, fontSize: 11, color: '#fbbf24',
        background: 'rgba(251,191,36,0.06)', borderRadius: 5,
        padding: '6px 10px', display: 'flex', gap: 6, alignItems: 'flex-start',
      }}>
        <AlertTriangle size={11} style={{ marginTop: 1, flexShrink: 0 }} />
        <span>{sim.approx_note}</span>
      </div>
    </div>
  )
}

// ── Simulation inline modal (for Recommendations page integration) ─
export function SimulationModal({ recId, onClose }) {
  const [sim, setSim]   = useState(null)
  const [err, setErr]   = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    simulationsAPI.get(recId)
      .then(r => setSim(r.data))
      .catch(() => setErr('Could not compute simulation. Backend may need more cost history.'))
      .finally(() => setLoading(false))
  }, [recId])

  return (
    <div style={{
      position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.6)',
      display: 'flex', alignItems: 'center', justifyContent: 'center',
      zIndex: 1000, padding: 20,
    }} onClick={onClose}>
      <div style={{
        background: 'var(--surface-1)', borderRadius: 12, padding: 24,
        width: '100%', maxWidth: 520, boxShadow: '0 20px 60px rgba(0,0,0,0.5)',
        border: '1px solid var(--glass-border)',
      }} onClick={e => e.stopPropagation()}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
          <div style={{ fontSize: 15, fontWeight: 700, color: 'var(--text-1)' }}>
            What-If Simulation
          </div>
          <button onClick={onClose} style={{
            background: 'none', border: 'none', cursor: 'pointer',
            color: 'var(--text-3)', fontSize: 18, lineHeight: 1,
          }}>×</button>
        </div>

        {loading && (
          <div className="loading-wrap" style={{ padding: '30px 0' }}>
            <div className="spinner" />
            <div className="loading-text">Computing projection…</div>
          </div>
        )}
        {err && <div style={{ color: '#f87171', fontSize: 13, padding: '20px 0' }}>{err}</div>}
        {sim && <SimCard sim={sim} />}

        {sim && !sim.upfront_cost_usd && (
          <div style={{ fontSize: 11, color: 'var(--text-4)', marginTop: 12 }}>
            {sim.synthetic_data_note}
          </div>
        )}
      </div>
    </div>
  )
}

// ── Main Page ─────────────────────────────────────────────────────
export default function Simulations() {
  const [recs,     setRecs]     = useState([])
  const [sims,     setSims]     = useState({})       // recId → sim result
  const [loading,  setLoading]  = useState(true)
  const [simming,  setSimming]  = useState(new Set())
  const [error,    setError]    = useState(null)

  // Load recommendations with potential savings > 0
  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const r = await recommendationsAPI.list().catch(() => ({ data: [] }))
      const withSavings = (Array.isArray(r.data) ? r.data : []).filter(rec => (rec.potential_savings_usd || 0) > 0)
      setRecs(withSavings)
    } catch {
      setError('Failed to load recommendations.')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { load() }, [load])

  const simulate = async (recId) => {
    setSimming(prev => new Set([...prev, recId]))
    try {
      const r = await simulationsAPI.get(recId)
      setSims(prev => ({ ...prev, [recId]: r.data }))
    } catch {
      setSims(prev => ({ ...prev, [recId]: { error: 'Simulation failed. Ensure the backend has sufficient cost history.' } }))
    } finally {
      setSimming(prev => { const s = new Set(prev); s.delete(recId); return s })
    }
  }

  const simulateAll = async () => {
    const ids = recs.map(r => r.id)
    setSimming(new Set(ids))
    try {
      const r = await simulationsAPI.batch(ids).catch(() => ({ data: { simulations: [] } }))
      const map = {}
      for (const s of (r.data?.simulations || [])) {
        map[s.recommendation_id] = s
      }
      setSims(map)
    } catch {
      setError('Batch simulation failed.')
    } finally {
      setSimming(new Set())
    }
  }

  if (loading) return (
    <div className="page-content">
      <div className="loading-wrap">
        <div className="spinner" />
        <div className="loading-text">Loading recommendations…</div>
      </div>
    </div>
  )

  return (
    <div className="page-content animate-up">

      {/* Header */}
      <div className="page-header">
        <div>
          <div className="page-title">What-If Simulations</div>
          <div className="page-subtitle">
            Project cost impact of rightsizing actions before applying them (FR-4)
          </div>
          <div style={{
            marginTop: 8, display: 'inline-flex', alignItems: 'center', gap: 6,
            fontSize: 11, color: '#fbbf24',
            background: 'rgba(251,191,36,0.08)', border: '1px solid rgba(251,191,36,0.2)',
            borderRadius: 6, padding: '4px 10px',
          }}>
            <AlertTriangle size={11} />
            Service-level approximation — not a per-resource model.
            Actual savings depend on your full service resource pool.
            Figures based on synthetic seed data.
          </div>
        </div>
        {recs.length > 0 && (
          <button onClick={simulateAll} disabled={simming.size > 0} style={{
            display: 'flex', alignItems: 'center', gap: 6,
            marginLeft: 'auto', padding: '8px 16px', borderRadius: 8,
            background: 'linear-gradient(135deg, #34d399, #059669)',
            border: 'none', color: '#fff', fontWeight: 700, fontSize: 13,
            cursor: simming.size > 0 ? 'not-allowed' : 'pointer',
            opacity: simming.size > 0 ? 0.6 : 1,
          }}>
            <Zap size={14} />
            {simming.size > 0 ? 'Computing…' : 'Simulate All'}
          </button>
        )}
      </div>

      {error && (
        <div className="card" style={{ borderLeft: '3px solid #f87171', color: '#f87171', fontSize: 13 }}>
          {error}
        </div>
      )}

      {recs.length === 0 ? (
        <div className="card">
          <div className="empty-state" style={{ padding: '40px 20px' }}>
            <CheckCircle size={36} color="var(--color-success)" style={{ marginBottom: 12 }} />
            <div className="empty-title">No recommendations to simulate</div>
            <div className="empty-sub">
              Simulations require at least one active recommendation with a savings estimate.
              Run a sync or check the Recommendations page.
            </div>
          </div>
        </div>
      ) : (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(440px, 1fr))', gap: 'var(--s-5)' }}>
          {recs.map((rec, i) => {
            const sim = sims[rec.id]
            const isSimming = simming.has(rec.id)

            return (
              <div key={rec.id} className={`card stagger-${(i % 4) + 1}`} style={{ padding: 0 }}>
                {/* Recommendation header */}
                <div style={{ padding: '16px 20px 0' }}>
                  <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginBottom: 6 }}>
                    <span className={`badge badge-${rec.severity}`}>{rec.severity.toUpperCase()}</span>
                    <span className={`chip chip-${rec.service_type.toLowerCase()}`}>{rec.service_type}</span>
                    <span style={{ fontSize: 11, color: 'var(--text-4)' }}>{rec.region}</span>
                    <span style={{ marginLeft: 'auto', fontSize: 13, fontWeight: 700, color: '#34d399' }}>
                      {fmt(rec.potential_savings_usd)}/mo potential
                    </span>
                  </div>
                  <div style={{ fontSize: 14, fontWeight: 700, color: 'var(--text-1)', marginBottom: 4 }}>
                    {rec.issue}
                  </div>
                  <div style={{ fontSize: 12, color: 'var(--text-3)', marginBottom: 12 }}>
                    {rec.resource_name || rec.resource_id}
                  </div>
                </div>

                {/* Simulate button or result */}
                {!sim && !isSimming && (
                  <div style={{ padding: '0 20px 16px' }}>
                    <button
                      id={`sim-btn-${rec.id}`}
                      onClick={() => simulate(rec.id)}
                      style={{
                        width: '100%', padding: '8px', borderRadius: 8,
                        background: 'rgba(52,211,153,0.1)',
                        border: '1px solid rgba(52,211,153,0.25)',
                        color: '#34d399', fontWeight: 700, fontSize: 13,
                        cursor: 'pointer', display: 'flex', alignItems: 'center',
                        justifyContent: 'center', gap: 7,
                      }}
                    >
                      <Zap size={14} />
                      Run Simulation
                    </button>
                  </div>
                )}

                {isSimming && (
                  <div style={{ padding: '16px 20px', display: 'flex', alignItems: 'center', gap: 8, color: 'var(--text-3)', fontSize: 13 }}>
                    <div className="spinner" style={{ width: 16, height: 16 }} />
                    Computing projection…
                  </div>
                )}

                {sim && !isSimming && (
                  <div style={{ padding: '0 20px 20px' }}>
                    {sim.error ? (
                      <div style={{ fontSize: 12, color: '#f87171', padding: '8px 0' }}>{sim.error}</div>
                    ) : (
                      <>
                        <SimBar
                          baseline={sim.baseline_30d_usd}
                          simulated={sim.simulated_30d_usd}
                          uncertainty={sim.uncertainty_band_usd}
                        />
                        <div style={{ display: 'flex', gap: 20, marginBottom: 10 }}>
                          <div>
                            <div style={{ fontSize: 10, color: 'var(--text-4)' }}>ESTIMATED SAVING</div>
                            <div style={{ fontSize: 20, fontWeight: 800, color: '#34d399' }}>
                              {fmt(sim.delta_usd)}<span style={{ fontSize: 11, color: 'var(--text-3)', fontWeight: 400 }}>/mo</span>
                            </div>
                          </div>
                          {sim.upfront_cost_usd > 0 ? (
                            <div>
                              <div style={{ fontSize: 10, color: 'var(--text-4)' }}>CASH IMPACT (MO 1)</div>
                              <div style={{ fontSize: 16, fontWeight: 700, color: '#f87171', marginTop: 3 }}>
                                {fmt(sim.first_month_cash_impact_usd)}
                              </div>
                              <div style={{ fontSize: 10, color: 'var(--text-4)' }}>Breakeven: {sim.payback_days}d</div>
                            </div>
                          ) : (
                            <div>
                              <div style={{ fontSize: 10, color: 'var(--text-4)' }}>REDUCTION</div>
                              <div style={{ fontSize: 20, fontWeight: 800, color: '#34d399' }}>{(sim.delta_pct ?? 0).toFixed(1)}%</div>
                            </div>
                          )}
                          {sim.monthly_trend_rate !== 0 && (
                            <div style={{ marginLeft: 'auto', textAlign: 'right' }}>
                              <div style={{ fontSize: 10, color: 'var(--text-4)' }}>TREND</div>
                              <div style={{
                                fontSize: 13, fontWeight: 700,
                                color: sim.monthly_trend_rate > 0 ? '#f87171' : '#34d399',
                              }}>
                                {sim.monthly_trend_rate > 0 ? '+' : ''}{fmt(sim.monthly_trend_rate)}/mo
                              </div>
                            </div>
                          )}
                        </div>
                        <div style={{
                          fontSize: 11, color: '#fbbf24',
                          background: 'rgba(251,191,36,0.06)', borderRadius: 5,
                          padding: '5px 8px',
                        }}>
                          {sim.approx_note}
                        </div>
                      </>
                    )}
                  </div>
                )}
              </div>
            )
          })}
        </div>
      )}

    </div>
  )
}
