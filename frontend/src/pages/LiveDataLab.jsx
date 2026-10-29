// src/pages/LiveDataLab.jsx — Live Data Lab for Demo Accounts
import { useState, useEffect } from 'react'
import {
  Activity, AlertTriangle, TrendingUp, Lightbulb, ShieldCheck,
  RefreshCw, Play, RotateCcw, Info, CheckCircle2, ArrowRight, Zap
} from 'lucide-react'
import { demoAPI } from '../api/client'
import { useAuth } from '../contexts/AuthContext'

const SCENARIOS = [
  { id: 'normal_day',            name: 'Normal Day',            desc: 'Small seeded noise (<1%). Must not trigger any anomaly.' },
  { id: 'cost_spike',            name: 'Cost Spike',            desc: 'Single-day cost jump (+80% default). Causes an anomaly and locks optimiser.' },
  { id: 'sustained_drift',       name: 'Sustained Drift',       desc: 'Multi-day progressive spend drift (+%/day over N days).' },
  { id: 'cost_drop',             name: 'Cost Drop',             desc: 'Substantial downward drop in daily spend.' },
  { id: 'new_idle_resource',     name: 'New Idle Resource',     desc: 'Adds an unutilized instance (0.3-0.4% CPU, 250-300h) triggering stop rec.' },
  { id: 'new_oversized_resource',name: 'New Oversized Resource',desc: 'Adds an underutilized instance (~3% CPU) triggering resize recommendation.' },
  { id: 'new_service',           name: 'New Service',           desc: 'Adds a service with >= 14 days history to evaluate commitment options.' },
]

export default function LiveDataLab() {
  const { activeAccount, bumpDataVersion } = useAuth()

  const provider = (activeAccount?.provider || 'aws').toLowerCase()
  const isAws = provider === 'aws'
  const isDemo = Boolean(activeAccount?.is_demo)

  const [scenario,       setScenario]       = useState('cost_spike')
  const [service,        setService]        = useState(isAws ? 'EC2' : 'AzureVM')
  const [magnitude,      setMagnitude]      = useState(80)
  const [days,           setDays]           = useState(5)
  const [monthlyCost,    setMonthlyCost]    = useState(120)
  const [loading,        setLoading]        = useState(false)
  const [resetting,      setResetting]      = useState(false)
  const [result,         setResult]         = useState(null)
  const [lastInjectTime, setLastInjectTime] = useState(null)
  const [error,          setError]          = useState(null)
  const [successMsg,     setSuccessMsg]     = useState(null)

  useEffect(() => {
    if (!activeAccount?.id) {
      setResult(null)
      setLastInjectTime(null)
      return
    }
    const key = `demo_lab_inject_${activeAccount.id}`
    try {
      // Clear any stored inject from other accounts
      for (let i = sessionStorage.length - 1; i >= 0; i--) {
        const k = sessionStorage.key(i)
        if (k && k.startsWith('demo_lab_inject_') && k !== key) {
          sessionStorage.removeItem(k)
        }
      }
      const raw = sessionStorage.getItem(key)
      if (raw) {
        const parsed = JSON.parse(raw)
        if (parsed && parsed.accountId === activeAccount.id && parsed.result) {
          setResult(parsed.result)
          if (parsed.timestamp) {
            const d = new Date(parsed.timestamp)
            const hh = String(d.getHours()).padStart(2, '0')
            const mm = String(d.getMinutes()).padStart(2, '0')
            setLastInjectTime(`${hh}:${mm}`)
          }
        } else {
          sessionStorage.removeItem(key)
          setResult(null)
          setLastInjectTime(null)
        }
      } else {
        setResult(null)
        setLastInjectTime(null)
      }
    } catch (e) {
      console.error('Failed to parse cached injection result:', e)
      sessionStorage.removeItem(key)
      setResult(null)
      setLastInjectTime(null)
    }
  }, [activeAccount?.id])

  const handleInject = async () => {
    if (!activeAccount?.id) return
    setLoading(true)
    setError(null)
    setSuccessMsg(null)
    try {
      const payload = {
        scenario,
        service: (scenario === 'new_idle_resource' || scenario === 'new_oversized_resource') ? undefined : service,
        magnitude: (scenario === 'normal_day' || scenario === 'new_idle_resource' || scenario === 'new_oversized_resource' || scenario === 'new_service') ? undefined : Number(magnitude),
        days: scenario === 'sustained_drift' ? Number(days) : undefined,
        monthly_cost: scenario === 'new_service' ? Number(monthlyCost) : undefined,
      }
      const res = await demoAPI.inject(payload, { account_id: activeAccount.id })
      setResult(res.data)
      setSuccessMsg(`Scenario '${scenario}' applied live! Real engine pipeline executed.`)
      const ts = new Date().toISOString()
      const d = new Date(ts)
      const hh = String(d.getHours()).padStart(2, '0')
      const mm = String(d.getMinutes()).padStart(2, '0')
      setLastInjectTime(`${hh}:${mm}`)
      try {
        sessionStorage.setItem(
          `demo_lab_inject_${activeAccount.id}`,
          JSON.stringify({ accountId: activeAccount.id, result: res.data, timestamp: ts })
        )
      } catch (e) {
        console.error('Failed to cache injection result:', e)
      }
      bumpDataVersion()
    } catch (err) {
      console.error('Injection failed:', err)
      setError(err?.response?.data?.detail || 'Failed to inject scenario')
    } finally {
      setLoading(false)
    }
  }

  const handleReset = async () => {
    if (!activeAccount?.id) return
    if (!window.confirm(`Reset demo account '${activeAccount.name}' to its initial deterministic state?`)) return
    setResetting(true)
    setError(null)
    setSuccessMsg(null)
    try {
      await demoAPI.reset({ account_id: activeAccount.id })
      setResult(null)
      setLastInjectTime(null)
      try {
        sessionStorage.removeItem(`demo_lab_inject_${activeAccount.id}`)
      } catch (e) {}
      bumpDataVersion()
      setSuccessMsg(`Demo account '${activeAccount.name}' reset to initial clean state.`)
    } catch (err) {
      console.error('Reset failed:', err)
      setError(err?.response?.data?.detail || 'Failed to reset demo account')
    } finally {
      setResetting(false)
    }
  }

  if (!isDemo) {
    return (
      <div className="page-content animate-up">
        <div className="card" style={{ padding: '40px 20px', textAlign: 'center' }}>
          <AlertTriangle size={36} color="var(--color-warning, #f59e0b)" style={{ margin: '0 auto var(--s-3)' }} />
          <h2 style={{ fontSize: '18px', fontWeight: 700, margin: '0 0 var(--s-2)' }}>Live Data Lab Unavailable</h2>
          <p style={{ color: 'var(--text-3)', fontSize: '13px', maxWidth: '480px', margin: '0 auto' }}>
            The Live Data Lab is exclusive to simulated Demo accounts. Your active account (<strong>{activeAccount?.name || 'Current'}</strong>) has credentials or is not a recognized demo environment.
          </p>
        </div>
      </div>
    )
  }

  const before = result?.before
  const after  = result?.after
  const delta  = result?.delta

  return (
    <div className="page-content animate-up">
      {/* Title & Subtitle */}
      <div style={{ marginBottom: 'var(--s-4)' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--s-2)' }}>
          <Activity size={24} color="var(--color-primary, #6366f1)" />
          <h1 className="page-title" style={{ fontSize: '22px', fontWeight: 700, margin: 0 }}>
            Live Data Lab
          </h1>
          <span className="badge badge-info" style={{ textTransform: 'uppercase', fontSize: '10px' }}>
            {activeAccount.name} ({provider})
          </span>
        </div>
        <p className="page-subtitle" style={{ color: 'var(--text-3)', fontSize: '13px', marginTop: 'var(--s-1)' }}>
          Inject live test scenarios into this demo account to see how ML models, anomaly detection, recommendations, and commitment plans adapt in real time.
        </p>
      </div>

      {/* Mandatory Disclaimer Banner */}
      <div
        className="card"
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 'var(--s-3)',
          background: 'rgba(99, 102, 241, 0.08)',
          borderColor: 'rgba(99, 102, 241, 0.25)',
          padding: '12px 18px',
          marginBottom: 'var(--s-4)'
        }}
      >
        <Info size={20} color="var(--color-primary, #6366f1)" style={{ flexShrink: 0 }} />
        <span style={{ fontSize: '13px', color: 'var(--text-2)' }}>
          <strong>Injected inputs are synthetic; detection, forecasting and recommendations are computed live by the real engine</strong>.
          Changes immediately propagate across the Dashboard, Resources, Cost Analysis, and Anomaly Detection. A backend restart also resets.
        </span>
      </div>

      {/* Status Messages */}
      {error && (
        <div className="card" style={{ background: 'rgba(239, 68, 68, 0.1)', borderColor: 'rgba(239, 68, 68, 0.3)', padding: '12px 16px', marginBottom: 'var(--s-4)', color: 'var(--color-danger, #ef4444)', fontSize: '13px' }}>
          {error}
        </div>
      )}
      {successMsg && (
        <div className="card" style={{ background: 'rgba(16, 185, 129, 0.1)', borderColor: 'rgba(16, 185, 129, 0.3)', padding: '12px 16px', marginBottom: 'var(--s-4)', color: 'var(--color-success, #10b981)', fontSize: '13px', display: 'flex', alignItems: 'center', gap: '8px' }}>
          <CheckCircle2 size={16} />
          <span>{successMsg}</span>
        </div>
      )}

      {/* Control Panel Card */}
      <div className="card" style={{ padding: 'var(--s-4)', marginBottom: 'var(--s-4)' }}>
        <h2 style={{ fontSize: '16px', fontWeight: 700, margin: '0 0 var(--s-3)', color: 'var(--text-1)' }}>
          1. Select Scenario
        </h2>

        {/* Scenario Grid */}
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))', gap: 'var(--s-3)', marginBottom: 'var(--s-4)' }}>
          {SCENARIOS.map(sc => {
            const isSelected = scenario === sc.id
            return (
              <div
                key={sc.id}
                onClick={() => setScenario(sc.id)}
                style={{
                  cursor: 'pointer',
                  border: isSelected ? '2px solid var(--color-primary, #6366f1)' : '1px solid var(--border-subtle, rgba(255, 255, 255, 0.08))',
                  background: isSelected ? 'rgba(99, 102, 241, 0.1)' : 'var(--glass-bg, rgba(255, 255, 255, 0.02))',
                  borderRadius: 'var(--radius-md, 8px)',
                  padding: '12px 14px',
                  transition: 'all 0.2s ease',
                }}
              >
                <div style={{ fontWeight: 600, fontSize: '13px', color: isSelected ? 'var(--color-primary, #6366f1)' : 'var(--text-1)', marginBottom: '4px' }}>
                  {sc.name}
                </div>
                <div style={{ fontSize: '11px', color: 'var(--text-3)', lineHeight: 1.4 }}>
                  {sc.desc}
                </div>
              </div>
            )
          })}
        </div>

        {/* Scenario Parameters */}
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 'var(--s-4)', alignItems: 'center', background: 'rgba(255, 255, 255, 0.02)', padding: '14px 18px', borderRadius: 'var(--radius-md, 8px)', border: '1px solid var(--border-subtle, rgba(255, 255, 255, 0.05))', marginBottom: 'var(--s-4)' }}>
          {/* Service Selector */}
          {(scenario === 'cost_spike' || scenario === 'sustained_drift' || scenario === 'cost_drop' || scenario === 'new_service') && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
              <label style={{ fontSize: '12px', fontWeight: 600, color: 'var(--text-2)' }}>Target Service</label>
              <select
                className="select-input"
                value={service}
                onChange={e => setService(e.target.value)}
                style={{ width: '160px' }}
              >
                {isAws ? (
                  <>
                    <option value="EC2">EC2 Compute</option>
                    <option value="RDS">RDS Database</option>
                    <option value="S3">S3 Storage</option>
                    <option value="Lambda">Lambda Functions</option>
                  </>
                ) : (
                  <option value="AzureVM">Azure Virtual Machines</option>
                )}
              </select>
            </div>
          )}

          {/* Monthly Cost for new_service */}
          {scenario === 'new_service' && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '6px', minWidth: '160px' }}>
              <label style={{ fontSize: '12px', fontWeight: 600, color: 'var(--text-2)' }}>Monthly Spend ($)</label>
              <input
                type="number"
                min={10}
                max={5000}
                step={10}
                value={monthlyCost}
                onChange={e => setMonthlyCost(Number(e.target.value))}
                className="select-input"
                style={{ width: '130px' }}
              />
            </div>
          )}

          {/* Magnitude Slider */}
          {(scenario === 'cost_spike' || scenario === 'sustained_drift' || scenario === 'cost_drop') && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '6px', minWidth: '220px' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '12px', color: 'var(--text-2)' }}>
                <span style={{ fontWeight: 600 }}>
                  {scenario === 'cost_drop' ? 'Drop Magnitude' : scenario === 'sustained_drift' ? 'Daily Growth' : 'Spike Magnitude'}
                </span>
                <span style={{ fontWeight: 700, color: 'var(--color-primary, #6366f1)' }}>
                  {scenario === 'cost_drop' ? '-' : '+'}{magnitude}%
                </span>
              </div>
              <input
                type="range"
                min={scenario === 'sustained_drift' ? 1 : 10}
                max={scenario === 'sustained_drift' ? 25 : 200}
                step={scenario === 'sustained_drift' ? 1 : 5}
                value={magnitude}
                onChange={e => setMagnitude(Number(e.target.value))}
                style={{ accentColor: 'var(--color-primary, #6366f1)', cursor: 'pointer' }}
              />
            </div>
          )}

          {/* Days Slider */}
          {scenario === 'sustained_drift' && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '6px', minWidth: '160px' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '12px', color: 'var(--text-2)' }}>
                <span style={{ fontWeight: 600 }}>Duration</span>
                <span style={{ fontWeight: 700, color: 'var(--color-primary, #6366f1)' }}>{days} days</span>
              </div>
              <input
                type="range"
                min={2}
                max={14}
                value={days}
                onChange={e => setDays(Number(e.target.value))}
                style={{ accentColor: 'var(--color-primary, #6366f1)', cursor: 'pointer' }}
              />
            </div>
          )}

          {/* Action Buttons */}
          <div style={{ marginLeft: 'auto', display: 'flex', gap: 'var(--s-2)', alignItems: 'center' }}>
            <button
              className="btn btn-outline"
              onClick={handleReset}
              disabled={resetting || loading}
              style={{ display: 'flex', alignItems: 'center', gap: '6px' }}
            >
              <RotateCcw size={14} className={resetting ? 'spin' : ''} />
              {resetting ? 'Resetting…' : 'Reset Demo'}
            </button>
            <button
              className="btn btn-primary"
              onClick={handleInject}
              disabled={loading || resetting}
              style={{ display: 'flex', alignItems: 'center', gap: '6px' }}
            >
              <Play size={14} className={loading ? 'spin' : ''} />
              {loading ? 'Evaluating Pipeline…' : 'Inject & Run Engine'}
            </button>
          </div>
        </div>
      </div>

      {/* Before / After Comparison Panel */}
      {result && (
        <div style={{ marginBottom: 'var(--s-4)' }}>
          {lastInjectTime && (
            <div style={{ fontSize: '12px', color: 'var(--text-3)', marginBottom: 'var(--s-2)', fontWeight: 600 }}>
              Last injection: {lastInjectTime}
            </div>
          )}
          <div className="card" style={{ padding: 'var(--s-4)' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 'var(--s-4)' }}>
              <div>
                <h2 style={{ fontSize: '16px', fontWeight: 700, margin: 0, color: 'var(--text-1)' }}>
                  Live Pipeline Evaluation: Before vs. After
                </h2>
              <p style={{ fontSize: '12px', color: 'var(--text-3)', margin: '4px 0 0' }}>
                Scenario: <strong>{result.scenario}</strong> on account <strong>{result.provider.toUpperCase()}</strong>
              </p>
            </div>
            {delta?.winner_changed && (
              <span className="badge badge-warning" style={{ fontSize: '11px' }}>
                Winner Model Shifted!
              </span>
            )}
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: 'var(--s-4)' }}>
            {/* 1. Anomalies Card */}
            <div style={{ border: '1px solid var(--border-subtle, rgba(255, 255, 255, 0.08))', borderRadius: 'var(--radius-md, 8px)', padding: '14px', background: 'var(--glass-bg, rgba(255, 255, 255, 0.02))' }}>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '10px' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '6px', fontWeight: 600, fontSize: '13px' }}>
                  <AlertTriangle size={16} color="var(--color-danger, #ef4444)" />
                  <span>Anomalies</span>
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '13px', fontWeight: 700 }}>
                  <span>{before?.anomaly_count ?? 0}</span>
                  <ArrowRight size={12} color="var(--text-3)" />
                  <span style={{ color: (delta?.anomaly_count ?? 0) > 0 ? 'var(--color-danger, #ef4444)' : 'var(--text-1)' }}>
                    {after?.anomaly_count ?? 0}
                  </span>
                  {(delta?.anomaly_count ?? 0) !== 0 && (
                    <span className={`badge ${delta.anomaly_count > 0 ? 'badge-danger' : 'badge-success'}`} style={{ fontSize: '10px', padding: '1px 5px' }}>
                      {delta.anomaly_count > 0 ? `+${delta.anomaly_count}` : delta.anomaly_count}
                    </span>
                  )}
                </div>
              </div>

              {delta?.new_anomalies?.length > 0 ? (
                <div style={{ marginTop: '8px', fontSize: '12px' }}>
                  <div style={{ fontSize: '11px', color: 'var(--text-3)', marginBottom: '4px' }}>New Anomaly Detected:</div>
                  {delta.new_anomalies.map((a, i) => (
                    <div key={i} style={{ background: 'rgba(239, 68, 68, 0.1)', border: '1px solid rgba(239, 68, 68, 0.3)', borderRadius: '4px', padding: '6px 8px', marginBottom: '4px' }}>
                      <strong>{a.service}</strong> on {a.date}: z={a.z != null && !isNaN(a.z) ? `${a.z}σ` : '—'} ({a.severity})
                    </div>
                  ))}
                </div>
              ) : (
                <div style={{ fontSize: '12px', color: 'var(--text-3)', fontStyle: 'italic', marginTop: '6px' }}>
                  No new anomalies triggered.
                </div>
              )}
            </div>

            {/* 2. Forecast & ML Winner Card */}
            <div style={{ border: '1px solid var(--border-subtle, rgba(255, 255, 255, 0.08))', borderRadius: 'var(--radius-md, 8px)', padding: '14px', background: 'var(--glass-bg, rgba(255, 255, 255, 0.02))' }}>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '10px' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '6px', fontWeight: 600, fontSize: '13px' }}>
                  <TrendingUp size={16} color="var(--color-info, #3b82f6)" />
                  <span>30-Day Forecast</span>
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '13px', fontWeight: 700 }}>
                  <span>${before?.forecast?.total_30d != null && !isNaN(before.forecast.total_30d) ? before.forecast.total_30d.toFixed(2) : '0.00'}</span>
                  <ArrowRight size={12} color="var(--text-3)" />
                  <span style={{ color: (delta?.forecast_30d_delta ?? 0) > 0 ? 'var(--color-danger, #ef4444)' : 'var(--color-success, #10b981)' }}>
                    ${after?.forecast?.total_30d != null && !isNaN(after.forecast.total_30d) ? after.forecast.total_30d.toFixed(2) : '0.00'}
                  </span>
                </div>
              </div>

              <div style={{ fontSize: '12px', color: 'var(--text-2)', display: 'flex', flexDirection: 'column', gap: '4px', marginTop: '8px' }}>
                <div>
                  <span style={{ color: 'var(--text-3)' }}>Winning Model: </span>
                  <strong style={{ color: delta?.winner_changed ? 'var(--color-warning, #f59e0b)' : 'var(--text-1)' }}>
                    {after?.forecast?.winner || 'N/A'}
                  </strong>
                </div>
                <div style={{ fontSize: '11px', color: 'var(--text-3)' }}>
                  MAPE: Poly {after?.forecast?.poly_mape != null && !isNaN(after.forecast.poly_mape) ? `${after.forecast.poly_mape.toFixed(2)}%` : '—'} | Holt {after?.forecast?.hw_mape != null && !isNaN(after.forecast.hw_mape) ? `${after.forecast.hw_mape.toFixed(2)}%` : '—'}
                </div>
              </div>
            </div>

            {/* 3. Recommendations Card */}
            <div style={{ border: '1px solid var(--border-subtle, rgba(255, 255, 255, 0.08))', borderRadius: 'var(--radius-md, 8px)', padding: '14px', background: 'var(--glass-bg, rgba(255, 255, 255, 0.02))' }}>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '10px' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '6px', fontWeight: 600, fontSize: '13px' }}>
                  <Lightbulb size={16} color="var(--color-warning, #f59e0b)" />
                  <span>Recommendations</span>
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '13px', fontWeight: 700 }}>
                  <span>{before?.recommendation_count ?? 0}</span>
                  <ArrowRight size={12} color="var(--text-3)" />
                  <span>{after?.recommendation_count ?? 0}</span>
                  {(delta?.recommendations_added?.length ?? 0) > 0 && (
                    <span className="badge badge-success" style={{ fontSize: '10px', padding: '1px 5px' }}>
                      +{delta.recommendations_added.length}
                    </span>
                  )}
                </div>
              </div>

              {delta?.recommendations_added?.length > 0 ? (
                <div style={{ marginTop: '6px', fontSize: '12px' }}>
                  {delta.recommendations_added.map((r, i) => (
                    <div key={i} style={{ background: 'rgba(16, 185, 129, 0.1)', border: '1px solid rgba(16, 185, 129, 0.25)', borderRadius: '4px', padding: '6px 8px', marginBottom: '4px' }}>
                      <strong>{r.issue}</strong> on {r.resource}: ${r.savings != null && !isNaN(r.savings) ? r.savings.toFixed(2) : '0.00'}/mo
                    </div>
                  ))}
                </div>
              ) : (
                <div style={{ fontSize: '12px', color: 'var(--text-3)', fontStyle: 'italic', marginTop: '6px' }}>
                  No new recommendations added.
                </div>
              )}
            </div>

            {/* 4. Savings Optimiser Card */}
            <div style={{ border: '1px solid var(--border-subtle, rgba(255, 255, 255, 0.08))', borderRadius: 'var(--radius-md, 8px)', padding: '14px', background: 'var(--glass-bg, rgba(255, 255, 255, 0.02))' }}>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '10px' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '6px', fontWeight: 600, fontSize: '13px' }}>
                  <ShieldCheck size={16} color="var(--color-success, #10b981)" />
                  <span>Savings Optimiser</span>
                </div>
              </div>

              <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', fontSize: '12px' }}>
                {after?.savings_optimiser?.map((svc, i) => {
                  const bSvc = before?.savings_optimiser?.find(b => b.service === svc.service)
                  const hasChanged = bSvc && bSvc.recommended !== svc.recommended
                  const isNewPlan = !bSvc || Boolean(svc.is_new)
                  return (
                    <div
                      key={i}
                      style={{
                        padding: '6px 8px',
                        borderRadius: '4px',
                        background: isNewPlan ? 'rgba(16, 185, 129, 0.12)' : hasChanged ? 'rgba(245, 158, 11, 0.15)' : 'rgba(255, 255, 255, 0.02)',
                        border: isNewPlan ? '1px solid rgba(16, 185, 129, 0.3)' : hasChanged ? '1px solid rgba(245, 158, 11, 0.4)' : '1px solid var(--border-subtle, rgba(255, 255, 255, 0.05))'
                      }}
                    >
                      <div style={{ display: 'flex', justifyContent: 'space-between', fontWeight: 600 }}>
                        <span>{isNewPlan ? `New plan available: ${svc.service}` : `${svc.service}:`}</span>
                        <span style={{ color: svc.recommended === 'pay_as_you_go' ? 'var(--color-warning, #f59e0b)' : 'var(--color-success, #10b981)' }}>
                          {svc.recommended}
                        </span>
                      </div>
                      <div style={{ fontSize: '11px', color: 'var(--text-3)', marginTop: '2px', lineHeight: 1.3 }}>
                        {svc.reason}
                      </div>
                    </div>
                  )
                })}
              </div>
            </div>
          </div>
        </div>
      </div>
      )}
    </div>
  )
}
