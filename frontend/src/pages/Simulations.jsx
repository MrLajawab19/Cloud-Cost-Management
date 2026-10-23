// src/pages/Simulations.jsx — FR-4 What-If Simulations page
import { useState, useEffect, useCallback, useMemo } from 'react'
import {
  CheckCircle, Zap, AlertTriangle, TrendingUp, TrendingDown,
  Info, RefreshCw, ShoppingBasket, Plus, Trash2, ArrowRight,
  ShieldAlert, ShieldCheck, DollarSign
} from 'lucide-react'
import { recommendationsAPI, simulationsAPI, predictionsAPI } from '../api/client'
import { useAuth } from '../contexts/AuthContext'

// ── Helpers ───────────────────────────────────────────────────────
const SVC_COLORS = { EC2: '#ec7211', RDS: '#0073bb', S3: '#1d8102', Lambda: '#6366f1', AzureVM: '#0089d6' }

function fmt(v) {
  if (v == null || v === 'Cost unavailable') return 'Cost unavailable'
  const n = Number(v)
  if (isNaN(n)) return 'Cost unavailable'
  return `$${n.toFixed(2)}`
}

function fmtPct(v) {
  if (v == null || v === 'Cost unavailable') return 'N/A'
  const n = Number(v)
  if (isNaN(n)) return 'N/A'
  return `${n.toFixed(1)}%`
}

// ── Before/After bar ──────────────────────────────────────────────
function SimBar({ baseline, simulated, uncertainty }) {
  const b = typeof baseline === 'number' ? baseline : 0
  const s = typeof simulated === 'number' ? simulated : 0
  const u = typeof uncertainty === 'number' ? uncertainty : 0

  const max = Math.max(b, 0.01)
  const simPct = Math.min((s / max) * 100, 100)
  const uncPct = Math.min((u / max) * 100, 8)

  return (
    <div style={{ margin: '14px 0' }}>
      {/* Baseline bar */}
      <div style={{ marginBottom: 6 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12, color: '#64748b', marginBottom: 4, fontWeight: 500 }}>
          <span>Current forecast (baseline)</span>
          <span style={{ fontWeight: 700, color: '#1e293b' }}>{fmt(baseline)}/mo</span>
        </div>
        <div style={{ height: 10, background: '#f1f5f9', borderRadius: 5, overflow: 'hidden' }}>
          <div style={{ height: '100%', width: '100%', background: '#cbd5e1', borderRadius: 5 }} />
        </div>
      </div>

      {/* Simulated bar — animated */}
      <div>
        <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12, color: '#64748b', marginBottom: 4, fontWeight: 500 }}>
          <span>After applying change</span>
          <span style={{ fontWeight: 700, color: '#059669' }}>{fmt(simulated)}/mo</span>
        </div>
        <div style={{ height: 10, background: '#f1f5f9', borderRadius: 5, overflow: 'hidden', position: 'relative' }}>
          <div style={{
            height: '100%',
            width: `${simPct}%`,
            background: 'linear-gradient(90deg, #10b981, #059669)',
            borderRadius: 5,
            transition: 'width 0.8s cubic-bezier(0.25, 1, 0.5, 1)',
          }} />
          {/* Uncertainty band */}
          {u > 0 && (
            <div style={{
              position: 'absolute', top: 0, right: 0,
              height: '100%', width: `${uncPct}%`,
              background: 'rgba(245,158,11,0.15)',
              borderLeft: '1px dashed rgba(245,158,11,0.4)',
            }} title={`±${fmt(uncertainty)} forecast uncertainty`} />
          )}
        </div>
        {u > 0 && (
          <div style={{ fontSize: 11, color: '#94a3b8', marginTop: 4, textAlign: 'right' }}>
            ±{fmt(uncertainty)} forecast uncertainty band
          </div>
        )}
      </div>
    </div>
  )
}

// ── Simulation Inline Modal (for Recommendations page integration) ─
export function SimulationModal({ recId, onClose }) {
  const [sim, setSim] = useState(null)
  const [err, setErr] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    simulationsAPI.get(recId)
      .then(r => setSim(r.data))
      .catch(() => setErr('Could not compute simulation. Backend may need more cost history.'))
      .finally(() => setLoading(false))
  }, [recId])

  return (
    <div style={{
      position: 'fixed', inset: 0, background: 'rgba(15, 23, 42, 0.6)', backdropFilter: 'blur(8px)',
      display: 'flex', alignItems: 'center', justifyContent: 'center',
      zIndex: 1000, padding: 20, animation: 'overlay-fade 0.2s ease-out'
    }} onClick={onClose}>
      <div style={{
        background: '#ffffff', borderRadius: 20, padding: 32,
        width: '100%', maxWidth: 580, boxShadow: '0 25px 50px -12px rgba(0,0,0,0.25)',
        border: '1px solid rgba(0,0,0,0.05)', animation: 'modal-pop 0.3s cubic-bezier(0.16, 1, 0.3, 1)'
      }} onClick={e => e.stopPropagation()}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 24 }}>
          <div style={{ fontSize: 20, fontWeight: 800, color: '#1e293b', letterSpacing: '-0.02em' }}>
            What-If Simulation
          </div>
          <button onClick={onClose} style={{
            background: '#f1f5f9', border: 'none', cursor: 'pointer',
            color: '#64748b', fontSize: 20, height: 32, width: 32, borderRadius: '50%',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            transition: 'all 0.2s'
          }} onMouseEnter={e => { e.currentTarget.style.background = '#e2e8f0'; e.currentTarget.style.color = '#0f172a' }}
             onMouseLeave={e => { e.currentTarget.style.background = '#f1f5f9'; e.currentTarget.style.color = '#64748b' }}
          >×</button>
        </div>

        {loading && (
          <div className="loading-wrap" style={{ padding: '30px 0' }}>
            <div className="spinner" />
            <div className="loading-text">Computing projection…</div>
          </div>
        )}
        {err && <div style={{ color: '#f87171', fontSize: 13, padding: '20px 0' }}>{err}</div>}
        {sim && (
          <div>
            <div className="card-title" style={{ gap: 8, color: '#1e293b', marginBottom: 12 }}>
              <span className={`chip chip-${sim.service_type?.toLowerCase()}`}>{sim.service_type}</span>
              {sim.resource_name}
            </div>
            <SimBar
              baseline={sim.baseline_30d_usd}
              simulated={sim.simulated_30d_usd}
              uncertainty={sim.uncertainty_band_usd}
            />
            <div style={{ display: 'flex', gap: 20, marginTop: 16 }}>
              <div>
                <div style={{ fontSize: 11, color: '#64748b' }}>Estimated Saving</div>
                <div style={{ fontSize: 22, fontWeight: 800, color: '#059669' }}>
                  {fmt(sim.delta_usd)}<span style={{ fontSize: 12, fontWeight: 400 }}>/mo</span>
                </div>
              </div>
              <div>
                <div style={{ fontSize: 11, color: '#64748b' }}>Reduction</div>
                <div style={{ fontSize: 22, fontWeight: 800, color: '#059669' }}>
                  {fmtPct(sim.delta_pct)}
                </div>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

// ── Main Page ─────────────────────────────────────────────────────
export default function Simulations() {
  const { activeAccount } = useAuth()

  // Recommendations state
  const [recs, setRecs] = useState([])
  const [sims, setSims] = useState({}) // recId → sim result
  const [loading, setLoading] = useState(true)
  const [simming, setSimming] = useState(new Set())
  const [error, setError] = useState(null)

  // Forecast state for summary strip
  const [forecast, setForecast] = useState(null)

  // Resource What-If state
  const [resources, setResources] = useState([])
  const [selectedResId, setSelectedResId] = useState('')
  const [selectedAction, setSelectedAction] = useState('stop')
  const [selectedTargetType, setSelectedTargetType] = useState('')
  const [simulatingResource, setSimulatingResource] = useState(false)
  const [resourceSimResult, setResourceSimResult] = useState(null)
  const [resourceSimError, setResourceSimError] = useState(null)

  // Scenario basket state
  const [scenarioBasket, setScenarioBasket] = useState([])

  // Load recommendations & forecast
  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const [recRes, forecastRes] = await Promise.all([
        recommendationsAPI.list().catch(() => ({ data: [] })),
        predictionsAPI.get().catch(() => ({ data: null }))
      ])
      const withSavings = (Array.isArray(recRes.data) ? recRes.data : []).filter(rec => (rec.potential_savings_usd || 0) > 0)
      setRecs(withSavings)
      setForecast(forecastRes.data)
    } catch {
      setError('Failed to load recommendations or forecast data.')
    } finally {
      setLoading(false)
    }
  }, [])

  // Load resource options when activeAccount changes
  const loadResourceOptions = useCallback(async () => {
    if (!activeAccount?.id) return
    try {
      const res = await simulationsAPI.getResourceOptions(activeAccount.id)
      const list = Array.isArray(res.data) ? res.data : []
      setResources(list)
      if (list.length > 0 && !selectedResId) {
        setSelectedResId(list[0].resource_id)
        const defAction = list[0].allowed_actions?.[0] || 'stop'
        setSelectedAction(defAction)
        if (list[0].target_types?.length > 0) {
          setSelectedTargetType(list[0].target_types[0])
        }
      }
    } catch (e) {
      console.error('Failed to load resource options', e)
    }
  }, [activeAccount?.id, selectedResId])

  useEffect(() => { load() }, [load])
  useEffect(() => { loadResourceOptions() }, [loadResourceOptions])

  // Current selected resource object
  const currentResource = useMemo(() => {
    return resources.find(r => r.resource_id === selectedResId) || null
  }, [resources, selectedResId])

  // Group resources by service
  const resourcesByService = useMemo(() => {
    const groups = {}
    for (const r of resources) {
      if (!groups[r.service_type]) groups[r.service_type] = []
      groups[r.service_type].push(r)
    }
    return groups
  }, [resources])

  // Update action & target type when resource selection changes
  const handleResourceChange = (resId) => {
    setSelectedResId(resId)
    setResourceSimResult(null)
    setResourceSimError(null)
    const target = resources.find(r => r.resource_id === resId)
    if (target) {
      const allowed = target.allowed_actions || []
      if (!allowed.includes(selectedAction)) {
        setSelectedAction(allowed[0] || 'stop')
      }
      if (target.target_types?.length > 0) {
        setSelectedTargetType(target.target_types[0])
      } else {
        setSelectedTargetType('')
      }
    }
  }

  // Handle single resource simulation
  const handleSimulateResource = async () => {
    if (!selectedResId) return
    setSimulatingResource(true)
    setResourceSimError(null)
    try {
      const payload = {
        resource_id: selectedResId,
        action: selectedAction,
        target_type: selectedAction === 'resize' ? selectedTargetType : undefined,
        account_id: activeAccount?.id,
      }
      const res = await simulationsAPI.simulateResource(payload)
      setResourceSimResult(res.data)
    } catch (e) {
      setResourceSimError(e.response?.data?.detail || 'Simulation failed for selected resource.')
    } finally {
      setSimulatingResource(false)
    }
  }

  // Basket handlers
  const handleAddToScenario = () => {
    if (!resourceSimResult) return
    const item = {
      id: `${resourceSimResult.resource_name}-${resourceSimResult.action}-${Date.now()}`,
      resource_name: resourceSimResult.resource_name,
      service_type: resourceSimResult.service_type,
      action: resourceSimResult.action,
      monthly_saving: typeof resourceSimResult.monthly_saving === 'number' ? resourceSimResult.monthly_saving : 0,
      annual_saving: typeof resourceSimResult.annual_saving === 'number' ? resourceSimResult.annual_saving : 0,
      remaining_cost: resourceSimResult.remaining_cost_after_action,
      is_unavailable: resourceSimResult.monthly_saving === 'Cost unavailable',
    }
    setScenarioBasket(prev => [...prev, item])
  }

  const handleRemoveFromScenario = (id) => {
    setScenarioBasket(prev => prev.filter(item => item.id !== id))
  }

  const handleClearScenario = () => {
    setScenarioBasket([])
  }

  // Basket totals
  const basketTotalMonthly = useMemo(() => {
    return scenarioBasket.reduce((sum, item) => sum + (item.monthly_saving || 0), 0)
  }, [scenarioBasket])

  const basketTotalAnnual = useMemo(() => {
    return scenarioBasket.reduce((sum, item) => sum + (item.annual_saving || 0), 0)
  }, [scenarioBasket])

  // Recommendations simulation handlers
  const simulateRec = async (recId) => {
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

  const simulateAllRecs = async () => {
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

  const totalIdentifiedSaving = useMemo(() => {
    return recs.reduce((sum, r) => sum + (r.potential_savings_usd || 0), 0)
  }, [recs])

  if (loading) return (
    <div className="page-content">
      <div className="loading-wrap">
        <div className="spinner" />
        <div className="loading-text">Loading simulation models…</div>
      </div>
    </div>
  )

  return (
    <div className="page-content animate-up" style={{ display: 'flex', flexDirection: 'column', gap: 'var(--s-6)' }}>

      {/* Top summary strip */}
      <div className="card" style={{
        background: 'linear-gradient(135deg, rgba(30, 41, 59, 0.95) 0%, rgba(15, 23, 42, 0.98) 100%)',
        color: '#ffffff',
        border: '1px solid rgba(255, 255, 255, 0.08)',
        borderRadius: '16px',
        padding: '24px 28px',
        boxShadow: '0 10px 25px -5px rgba(0, 0, 0, 0.3)'
      }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 16 }}>
          <div>
            <div style={{ fontSize: 22, fontWeight: 800, letterSpacing: '-0.02em', marginBottom: 4 }}>
              What-If Simulations
            </div>
            <div style={{ fontSize: 13, color: '#94a3b8' }}>
              Project cost impacts of resource lifecycle actions before taking them.
            </div>
          </div>
          <div style={{
            display: 'inline-flex', alignItems: 'center', gap: 8,
            fontSize: 12, fontWeight: 600, color: '#38bdf8',
            background: 'rgba(56, 189, 248, 0.1)', border: '1px solid rgba(56, 189, 248, 0.25)',
            borderRadius: 8, padding: '6px 12px'
          }}>
            <Info size={14} />
            Estimated from list prices; nothing is executed
          </div>
        </div>

        <div style={{
          display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))',
          gap: 20, marginTop: 24, paddingTop: 20, borderTop: '1px solid rgba(255, 255, 255, 0.1)'
        }}>
          <div>
            <div style={{ fontSize: 11, textTransform: 'uppercase', letterSpacing: '0.05em', color: '#94a3b8', fontWeight: 600 }}>
              Total Identified Savings
            </div>
            <div style={{ fontSize: 26, fontWeight: 800, color: '#34d399', marginTop: 4 }}>
              {fmt(totalIdentifiedSaving)}<span style={{ fontSize: 13, fontWeight: 500, color: '#94a3b8' }}>/mo</span>
            </div>
            <div style={{ fontSize: 11, color: '#64748b', marginTop: 2 }}>
              Across {recs.length} actionable recommendation{recs.length === 1 ? '' : 's'}
            </div>
          </div>

          <div>
            <div style={{ fontSize: 11, textTransform: 'uppercase', letterSpacing: '0.05em', color: '#94a3b8', fontWeight: 600 }}>
              Current 30-Day Forecast
            </div>
            <div style={{ fontSize: 26, fontWeight: 800, color: '#ffffff', marginTop: 4 }}>
              {fmt(forecast?.monthly_estimate_usd)}
            </div>
            <div style={{ fontSize: 11, color: '#64748b', marginTop: 2 }}>
              Normalized baseline model (winner: {forecast?.winner_model || 'Holt'})
            </div>
          </div>

          <div>
            <div style={{ fontSize: 11, textTransform: 'uppercase', letterSpacing: '0.05em', color: '#94a3b8', fontWeight: 600 }}>
              Forecast Trend
            </div>
            <div style={{
              fontSize: 18, fontWeight: 700, marginTop: 8,
              color: (forecast?.monthly_trend_pct ?? 0) > 0 ? '#f87171' : '#34d399',
              display: 'flex', alignItems: 'center', gap: 6
            }}>
              {(forecast?.monthly_trend_pct ?? 0) > 0 ? <TrendingUp size={18} /> : <TrendingDown size={18} />}
              {fmtPct(forecast?.monthly_trend_pct)} 30d trajectory
            </div>
            <div style={{ fontSize: 11, color: '#64748b', marginTop: 2 }}>
              Directional service pool velocity
            </div>
          </div>
        </div>
      </div>

      {/* SECTION: SIMULATE A CHANGE */}
      <div className="card" style={{ borderRadius: '16px', padding: '24px 28px' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20, flexWrap: 'wrap', gap: 12 }}>
          <div>
            <div style={{ fontSize: 18, fontWeight: 800, color: 'var(--text-1)' }}>
              Simulate a change
            </div>
            <div style={{ fontSize: 13, color: 'var(--text-3)' }}>
              Select any resource to model the financial impact of stopping, terminating, or resizing.
            </div>
          </div>
          <span style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-4)' }}>
            Label: Estimated from list prices; nothing is executed
          </span>
        </div>

        {/* Input Form Controls */}
        <div style={{
          display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))',
          gap: 20, background: 'var(--bg-2)', padding: '20px', borderRadius: '12px',
          border: '1px solid var(--border)'
        }}>
          {/* Resource select grouped by service */}
          <div>
            <label style={{ display: 'block', fontSize: 12, fontWeight: 700, color: 'var(--text-2)', marginBottom: 6 }}>
              Target Resource
            </label>
            <select
              id="resource-select"
              value={selectedResId}
              onChange={e => handleResourceChange(e.target.value)}
              style={{
                width: '100%', padding: '10px 12px', borderRadius: 8,
                background: 'var(--card-bg)', border: '1px solid var(--border)',
                color: 'var(--text-1)', fontSize: 13, fontWeight: 500
              }}
            >
              {Object.keys(resourcesByService).map(service => (
                <optgroup key={service} label={service}>
                  {resourcesByService[service].map(r => (
                    <option key={r.resource_id} value={r.resource_id}>
                      {r.name} ({r.resource_id}) — {r.status} — {r.monthly_cost != null ? fmt(r.monthly_cost) + '/mo' : 'Cost unavailable'}
                    </option>
                  ))}
                </optgroup>
              ))}
            </select>
          </div>

          {/* Action selection */}
          <div>
            <label style={{ display: 'block', fontSize: 12, fontWeight: 700, color: 'var(--text-2)', marginBottom: 8 }}>
              Simulated Action
            </label>
            <div style={{ display: 'flex', gap: 16, alignItems: 'center', marginTop: 4 }}>
              {(currentResource?.allowed_actions || ['stop', 'terminate', 'resize']).map(act => (
                <label key={act} style={{ display: 'inline-flex', alignItems: 'center', gap: 6, fontSize: 13, fontWeight: 600, color: 'var(--text-1)', cursor: 'pointer' }}>
                  <input
                    type="radio"
                    name="resource-action"
                    value={act}
                    checked={selectedAction === act}
                    onChange={() => {
                      setSelectedAction(act)
                      setResourceSimResult(null)
                    }}
                  />
                  {act === 'stop' ? 'Stop' : act === 'terminate' ? 'Terminate' : 'Resize'}
                </label>
              ))}
            </div>

            {/* Target type dropdown if resize */}
            {selectedAction === 'resize' && (
              <div style={{ marginTop: 12 }}>
                <label style={{ display: 'block', fontSize: 11, fontWeight: 600, color: 'var(--text-3)', marginBottom: 4 }}>
                  Target Instance Type
                </label>
                <select
                  id="target-type-select"
                  value={selectedTargetType}
                  onChange={e => setSelectedTargetType(e.target.value)}
                  style={{
                    width: '100%', padding: '8px 10px', borderRadius: 6,
                    background: 'var(--card-bg)', border: '1px solid var(--border)',
                    color: 'var(--text-1)', fontSize: 12
                  }}
                >
                  {(currentResource?.target_types || []).map(t => (
                    <option key={t} value={t}>{t}</option>
                  ))}
                </select>
              </div>
            )}
          </div>

          {/* Simulate Action Button */}
          <div style={{ display: 'flex', alignItems: 'flex-end' }}>
            <button
              id="simulate-resource-btn"
              onClick={handleSimulateResource}
              disabled={simulatingResource || !selectedResId}
              style={{
                width: '100%', padding: '12px 20px', borderRadius: 8,
                background: 'linear-gradient(135deg, #3b82f6, #1d4ed8)',
                border: 'none', color: '#ffffff', fontWeight: 700, fontSize: 14,
                cursor: simulatingResource ? 'not-allowed' : 'pointer',
                opacity: simulatingResource ? 0.7 : 1,
                display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8,
                boxShadow: '0 4px 12px rgba(59, 130, 246, 0.3)'
              }}
            >
              {simulatingResource ? (
                <>
                  <div className="spinner" style={{ width: 16, height: 16 }} />
                  Calculating...
                </>
              ) : (
                <>
                  <Zap size={16} />
                  Simulate
                </>
              )}
            </button>
          </div>
        </div>

        {/* Error message */}
        {resourceSimError && (
          <div style={{ marginTop: 16, padding: '12px 16px', background: '#fef2f2', border: '1px solid #fecaca', borderRadius: 8, color: '#dc2626', fontSize: 13 }}>
            {resourceSimError}
          </div>
        )}

        {/* Resource Simulation Result Card */}
        {resourceSimResult && (
          <div style={{
            marginTop: 24, padding: '24px', borderRadius: 14,
            background: 'var(--card-bg)', border: '1px solid rgba(16, 185, 129, 0.3)',
            boxShadow: '0 10px 25px -5px rgba(16, 185, 129, 0.08)'
          }}>
            {/* Header with reversibility badge */}
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16, flexWrap: 'wrap', gap: 10 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                <span className={`chip chip-${resourceSimResult.service_type?.toLowerCase()}`}>{resourceSimResult.service_type}</span>
                <span style={{ fontSize: 16, fontWeight: 800, color: 'var(--text-1)' }}>
                  {resourceSimResult.resource_name}
                </span>
                <span style={{ fontSize: 12, color: 'var(--text-3)', textTransform: 'capitalize' }}>
                  ({resourceSimResult.action})
                </span>
              </div>
              <div>
                {resourceSimResult.reversible ? (
                  <span style={{
                    display: 'inline-flex', alignItems: 'center', gap: 5,
                    padding: '4px 10px', borderRadius: 6, fontSize: 11, fontWeight: 700,
                    background: 'rgba(16, 185, 129, 0.1)', color: '#059669', border: '1px solid rgba(16, 185, 129, 0.3)'
                  }}>
                    <ShieldCheck size={13} /> Reversible
                  </span>
                ) : (
                  <span style={{
                    display: 'inline-flex', alignItems: 'center', gap: 5,
                    padding: '4px 10px', borderRadius: 6, fontSize: 11, fontWeight: 700,
                    background: 'rgba(239, 68, 68, 0.1)', color: '#dc2626', border: '1px solid rgba(239, 68, 68, 0.3)'
                  }}>
                    <ShieldAlert size={13} /> Irreversible
                  </span>
                )}
              </div>
            </div>

            {/* Cost Comparison Grid */}
            <div style={{
              display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))',
              gap: 16, padding: '16px', background: 'var(--bg-2)', borderRadius: 10,
              border: '1px solid var(--border)', marginBottom: 20
            }}>
              <div>
                <div style={{ fontSize: 11, color: 'var(--text-3)', fontWeight: 600 }}>Current Monthly Cost</div>
                <div style={{ fontSize: 20, fontWeight: 800, color: 'var(--text-1)', marginTop: 2 }}>
                  {fmt(resourceSimResult.current_monthly_cost)}
                </div>
              </div>
              <div>
                <div style={{ fontSize: 11, color: 'var(--text-3)', fontWeight: 600 }}>New Monthly Cost</div>
                <div style={{ fontSize: 20, fontWeight: 800, color: '#3b82f6', marginTop: 2 }}>
                  {fmt(resourceSimResult.new_monthly_cost)}
                </div>
              </div>
              <div>
                <div style={{ fontSize: 11, color: 'var(--text-3)', fontWeight: 600 }}>Monthly Saving</div>
                <div style={{ fontSize: 22, fontWeight: 800, color: '#059669', marginTop: 2 }}>
                  {fmt(resourceSimResult.monthly_saving)}
                </div>
              </div>
              <div>
                <div style={{ fontSize: 11, color: 'var(--text-3)', fontWeight: 600 }}>Annual Saving</div>
                <div style={{ fontSize: 20, fontWeight: 800, color: '#059669', marginTop: 2 }}>
                  {fmt(resourceSimResult.annual_saving)}
                </div>
              </div>
              <div>
                <div style={{ fontSize: 11, color: 'var(--text-3)', fontWeight: 600 }}>Remaining Cost</div>
                <div style={{ fontSize: 18, fontWeight: 700, color: 'var(--text-2)', marginTop: 2 }}>
                  {fmt(resourceSimResult.remaining_cost_after_action)}
                </div>
                <div style={{ fontSize: 10, color: 'var(--text-4)', marginTop: 2 }}>
                  {resourceSimResult.remaining_cost_reason}
                </div>
              </div>
            </div>

            {/* Service-level forecast impact */}
            <div style={{
              display: 'flex', justifyContent: 'space-between', alignItems: 'center',
              padding: '12px 16px', background: 'rgba(56, 189, 248, 0.05)',
              border: '1px solid rgba(56, 189, 248, 0.2)', borderRadius: 8, marginBottom: 16,
              flexWrap: 'wrap', gap: 8
            }}>
              <div style={{ fontSize: 12, color: 'var(--text-2)' }}>
                <strong>{resourceSimResult.service_type} Service Forecast:</strong>{' '}
                {fmt(resourceSimResult.service_forecast_before)} <ArrowRight size={12} style={{ display: 'inline', margin: '0 4px' }} />{' '}
                <strong style={{ color: '#059669' }}>{fmt(resourceSimResult.service_forecast_after)}</strong>
              </div>
              <span style={{ fontSize: 11, color: '#0284c7', fontWeight: 600 }}>
                Service-level estimate
              </span>
            </div>

            {/* Formula note */}
            {resourceSimResult.formula_note && (
              <div style={{ fontSize: 12, color: 'var(--text-3)', fontStyle: 'italic', marginBottom: 16 }}>
                Note: {resourceSimResult.formula_note}
              </div>
            )}

            {/* Side Effects & Risks */}
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: 16, marginBottom: 20 }}>
              {resourceSimResult.side_effects?.length > 0 && (
                <div style={{ padding: '14px', background: 'var(--bg-2)', borderRadius: 8, border: '1px solid var(--border)' }}>
                  <div style={{ fontSize: 12, fontWeight: 700, color: 'var(--text-1)', marginBottom: 6 }}>
                    Operational Side Effects
                  </div>
                  <ul style={{ margin: 0, paddingLeft: 18, fontSize: 12, color: 'var(--text-2)', lineHeight: 1.5 }}>
                    {resourceSimResult.side_effects.map((eff, i) => (
                      <li key={i}>{eff}</li>
                    ))}
                  </ul>
                </div>
              )}

              {resourceSimResult.risk_notes?.length > 0 && (
                <div style={{ padding: '14px', background: 'rgba(245, 158, 11, 0.05)', borderRadius: 8, border: '1px solid rgba(245, 158, 11, 0.25)' }}>
                  <div style={{ fontSize: 12, fontWeight: 700, color: '#b45309', marginBottom: 6, display: 'flex', alignItems: 'center', gap: 6 }}>
                    <AlertTriangle size={14} /> Risk Notes & Safety Checks
                  </div>
                  <ul style={{ margin: 0, paddingLeft: 18, fontSize: 12, color: '#92400e', lineHeight: 1.5 }}>
                    {resourceSimResult.risk_notes.map((note, i) => (
                      <li key={i}>{note}</li>
                    ))}
                  </ul>
                </div>
              )}
            </div>

            {/* Add to scenario button */}
            <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
              <button
                id="add-to-scenario-btn"
                onClick={handleAddToScenario}
                style={{
                  padding: '10px 18px', borderRadius: 8,
                  background: 'linear-gradient(135deg, #10b981, #059669)',
                  border: 'none', color: '#ffffff', fontWeight: 700, fontSize: 13,
                  cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 7,
                  boxShadow: '0 4px 12px rgba(16, 185, 129, 0.25)'
                }}
              >
                <Plus size={16} />
                Add to scenario
              </button>
            </div>
          </div>
        )}

        {/* SCENARIO BASKET */}
        {scenarioBasket.length > 0 && (
          <div style={{
            marginTop: 28, padding: '20px 24px', borderRadius: 12,
            background: 'linear-gradient(135deg, rgba(240, 253, 250, 0.8) 0%, rgba(204, 251, 241, 0.4) 100%)',
            border: '1px solid rgba(20, 184, 166, 0.3)'
          }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <ShoppingBasket size={20} color="#0d9488" />
                <span style={{ fontSize: 16, fontWeight: 800, color: '#134e4a' }}>
                  Scenario Basket ({scenarioBasket.length} simulated change{scenarioBasket.length === 1 ? '' : 's'})
                </span>
              </div>
              <button
                onClick={handleClearScenario}
                style={{
                  background: 'transparent', border: 'none', color: '#64748b',
                  fontSize: 12, fontWeight: 600, cursor: 'pointer', textDecoration: 'underline'
                }}
              >
                Clear scenario
              </button>
            </div>

            {/* Basket Items List */}
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8, marginBottom: 16 }}>
              {scenarioBasket.map(item => (
                <div key={item.id} style={{
                  display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                  padding: '10px 14px', background: '#ffffff', borderRadius: 8,
                  border: '1px solid rgba(0, 0, 0, 0.05)', fontSize: 13
                }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                    <span className={`chip chip-${item.service_type?.toLowerCase()}`}>{item.service_type}</span>
                    <strong style={{ color: '#1e293b' }}>{item.resource_name}</strong>
                    <span style={{ color: '#64748b', fontSize: 12, textTransform: 'capitalize' }}>({item.action})</span>
                  </div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
                    <span style={{ fontWeight: 700, color: '#059669' }}>
                      +{fmt(item.monthly_saving)}/mo
                    </span>
                    <button
                      onClick={() => handleRemoveFromScenario(item.id)}
                      style={{ background: 'transparent', border: 'none', cursor: 'pointer', color: '#94a3b8' }}
                      title="Remove"
                    >
                      <Trash2 size={15} />
                    </button>
                  </div>
                </div>
              ))}
            </div>

            {/* Combined Total Strip */}
            <div style={{
              display: 'flex', justifyContent: 'space-between', alignItems: 'center',
              paddingTop: 14, borderTop: '1px solid rgba(20, 184, 166, 0.2)',
              flexWrap: 'wrap', gap: 12
            }}>
              <span style={{ fontSize: 14, fontWeight: 700, color: '#134e4a' }}>
                Combined Scenario Impact
              </span>
              <div style={{ display: 'flex', gap: 24, alignItems: 'center' }}>
                <div>
                  <span style={{ fontSize: 11, color: '#0f766e', fontWeight: 600 }}>Combined Monthly:</span>{' '}
                  <strong style={{ fontSize: 18, color: '#0f766e' }}>{fmt(basketTotalMonthly)}/mo</strong>
                </div>
                <div>
                  <span style={{ fontSize: 11, color: '#0f766e', fontWeight: 600 }}>Combined Annual:</span>{' '}
                  <strong style={{ fontSize: 18, color: '#0f766e' }}>{fmt(basketTotalAnnual)}/yr</strong>
                </div>
              </div>
            </div>
          </div>
        )}
      </div>

      {/* SECTION: FROM RECOMMENDATIONS */}
      <div className="card" style={{ borderRadius: '16px', padding: '24px 28px' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12, flexWrap: 'wrap', gap: 12 }}>
          <div>
            <div style={{ fontSize: 18, fontWeight: 800, color: 'var(--text-1)' }}>
              From recommendations
            </div>
            <div style={{ fontSize: 13, color: 'var(--text-3)' }}>
              Evaluate proactive recommendations detected by the cleanup advisor and anomaly engine.
            </div>
          </div>
          {recs.length > 0 && (
            <button
              onClick={simulateAllRecs}
              disabled={simming.size > 0}
              style={{
                display: 'flex', alignItems: 'center', gap: 6,
                padding: '8px 16px', borderRadius: 8,
                background: 'linear-gradient(135deg, #34d399, #059669)',
                border: 'none', color: '#fff', fontWeight: 700, fontSize: 13,
                cursor: simming.size > 0 ? 'not-allowed' : 'pointer',
                opacity: simming.size > 0 ? 0.6 : 1,
              }}
            >
              <Zap size={14} />
              {simming.size > 0 ? 'Computing…' : 'Simulate All'}
            </button>
          )}
        </div>

        {/* ONE SINGLE DISCLAIMER AT THE TOP */}
        <div style={{
          display: 'flex', alignItems: 'center', gap: 8,
          fontSize: 12, color: '#92400e', background: '#fffbeb',
          border: '1px solid #fde68a', borderRadius: 8,
          padding: '10px 14px', marginBottom: 20
        }}>
          <AlertTriangle size={15} style={{ flexShrink: 0, color: '#d97706' }} />
          <span>
            Estimated from list prices; nothing is executed. Service-level approximation — actual savings depend on your full service resource pool.
          </span>
        </div>

        {error && (
          <div className="card" style={{ borderLeft: '3px solid #f87171', color: '#f87171', fontSize: 13, marginBottom: 16 }}>
            {error}
          </div>
        )}

        {recs.length === 0 ? (
          <div className="empty-state" style={{ padding: '40px 20px' }}>
            <CheckCircle size={36} color="var(--color-success)" style={{ marginBottom: 12 }} />
            <div className="empty-title">No recommendations to simulate</div>
            <div className="empty-sub">
              Simulations require at least one active recommendation with a savings estimate.
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
                      <span className={`badge badge-${rec.severity}`}>{rec.severity?.toUpperCase()}</span>
                      <span className={`chip chip-${rec.service_type?.toLowerCase()}`}>{rec.service_type}</span>
                      <span style={{ fontSize: 11, color: 'var(--text-4)' }}>{rec.region}</span>
                      <span style={{ marginLeft: 'auto', fontSize: 13, fontWeight: 700, color: '#34d399' }}>
                        {fmt(rec.potential_savings_usd)}/mo potential
                      </span>
                    </div>
                    <div style={{ fontSize: 14, fontWeight: 700, color: 'var(--text-1)', marginBottom: 4 }}>
                      {rec.issue}
                    </div>
                    {/* Showing resource name prominently */}
                    <div style={{ fontSize: 12, color: 'var(--text-3)', marginBottom: 12 }}>
                      Resource: <strong style={{ color: 'var(--text-2)' }}>{rec.resource_name || rec.resource_id}</strong>
                    </div>
                  </div>

                  {/* Simulate button or result */}
                  {!sim && !isSimming && (
                    <div style={{ padding: '0 20px 16px' }}>
                      <button
                        id={`sim-btn-${rec.id}`}
                        onClick={() => simulateRec(rec.id)}
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
                                <div style={{ fontSize: 20, fontWeight: 800, color: '#34d399' }}>{fmtPct(sim.delta_pct)}</div>
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
                          {/* Repeated per-card approx_note disclaimer removed per specification */}
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

    </div>
  )
}
