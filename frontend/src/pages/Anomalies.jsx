// src/pages/Anomalies.jsx — FR-3 Anomaly Detection Dashboard
import { useState, useEffect, useCallback } from 'react'
import {
  ComposedChart, Bar, Line, XAxis, YAxis, CartesianGrid,
  Tooltip as RechartsTooltip, ResponsiveContainer, ReferenceLine, Legend,
} from 'recharts'
import {
  AlertTriangle, Zap, ShieldAlert, CheckCircle, RefreshCw,
  TrendingUp, TrendingDown, Activity, Info,
} from 'lucide-react'
import { anomaliesAPI } from '../api/client'

// ── Colour helpers ────────────────────────────────────────────────
const SVC_COLORS = { EC2: '#ec7211', RDS: '#0073bb', S3: '#1d8102', Lambda: '#6366f1' }
const SEV_COLOR  = { warning: '#fbbf24', critical: '#f87171' }
const DIR_ICON   = {
  spike: <TrendingUp  size={13} style={{ marginRight: 4 }} />,
  drop:  <TrendingDown size={13} style={{ marginRight: 4 }} />,
}

// ── Shared tooltip ────────────────────────────────────────────────
const ChartTooltip = ({ active, payload, label }) => {
  if (!active || !payload?.length) return null
  return (
    <div className="chart-tooltip">
      <div className="chart-tooltip-label">{label}</div>
      {payload.map((entry, i) => (
        <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 3 }}>
          <span style={{ width: 8, height: 8, borderRadius: '50%', background: entry.color, flexShrink: 0 }} />
          <span style={{ color: 'var(--text-3)', fontSize: 11 }}>{entry.name}:</span>
          <span style={{ color: 'var(--text-1)', fontWeight: 700 }}>
            {typeof entry.value === 'number' ? `$${entry.value.toFixed(4)}` : entry.value}
          </span>
        </div>
      ))}
    </div>
  )
}

// ── Severity badge ────────────────────────────────────────────────
function SeverityBadge({ severity }) {
  const color = SEV_COLOR[severity] || 'var(--text-3)'
  return (
    <span style={{
      fontSize: 10, fontWeight: 700, letterSpacing: '0.05em',
      color, background: `${color}22`, border: `1px solid ${color}44`,
      borderRadius: 4, padding: '2px 7px', textTransform: 'uppercase',
    }}>
      {severity}
    </span>
  )
}

// ── Metric card ───────────────────────────────────────────────────
function MetricCard({ icon, label, value, sub, accentColor, stagger }) {
  return (
    <div className={`metric-card stagger-${stagger}`}>
      <div className="metric-top">
        <div className="metric-icon" style={{ background: `${accentColor}1a`, color: accentColor }}>
          {icon}
        </div>
      </div>
      <div className="metric-label">{label}</div>
      <div className="metric-value" style={{ color: accentColor }}>{value}</div>
      <div className="metric-sub">{sub}</div>
    </div>
  )
}

// ── Loading / Error states ────────────────────────────────────────
const Loading = () => (
  <div className="page-content">
    <div className="loading-wrap">
      <div className="spinner" />
      <div className="loading-text">Running anomaly detection…</div>
    </div>
  </div>
)

const ErrorState = ({ msg }) => (
  <div className="page-content">
    <div className="empty-state">
      <div className="empty-icon"><Info size={24} /></div>
      <div className="empty-title">Anomaly Error</div>
      <div className="empty-sub">{msg}</div>
    </div>
  </div>
)

// ── Timeline chart ────────────────────────────────────────────────
function AnomalyTimeline({ anomalies }) {
  if (!anomalies?.length) return (
    <div className="empty-state">
      <div className="empty-sub">No anomalies to chart in this window.</div>
    </div>
  )

  // Group by date — sum absolute residuals per day, colour by worst severity
  const byDate = {}
  anomalies.forEach(a => {
    const d = a.record_date
    if (!byDate[d]) byDate[d] = { date: d, spike: 0, drop: 0, critical: false }
    if (a.direction === 'spike') byDate[d].spike += Math.abs(a.residual)
    else                         byDate[d].drop  += Math.abs(a.residual)
    if (a.severity === 'critical') byDate[d].critical = true
  })
  const data = Object.values(byDate).sort((a, b) => a.date.localeCompare(b.date))

  return (
    <ResponsiveContainer width="100%" height="100%">
      <ComposedChart data={data} margin={{ top: 10, right: 10, left: -10, bottom: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" vertical={false} />
        <XAxis dataKey="date" tick={{ fill: '#64748b', fontSize: 11 }}
          tickFormatter={v => v.slice(5)} axisLine={false} tickLine={false} dy={10}
          interval={Math.max(0, Math.floor(data.length / 8))} />
        <YAxis tick={{ fill: '#64748b', fontSize: 11 }}
          tickFormatter={v => `$${v.toFixed(1)}`} axisLine={false} tickLine={false} width={55} />
        <RechartsTooltip content={<ChartTooltip />}
          cursor={{ stroke: 'rgba(255,255,255,0.08)', strokeWidth: 1 }} />
        <Legend wrapperStyle={{ fontSize: '11.5px', color: '#94a3b8', paddingTop: 16 }}
          iconType="circle" iconSize={8} />
        <Bar dataKey="spike" name="Spike (|residual|)" fill="#f87171" fillOpacity={0.75} radius={[3,3,0,0]} />
        <Bar dataKey="drop"  name="Drop  (|residual|)" fill="#60a5fa" fillOpacity={0.75} radius={[3,3,0,0]} />
      </ComposedChart>
    </ResponsiveContainer>
  )
}

// ── Main Component ────────────────────────────────────────────────
export default function Anomalies() {
  const [data,      setData]      = useState(null)
  const [loading,   setLoading]   = useState(true)
  const [error,     setError]     = useState(null)
  const [refreshing,setRefreshing]= useState(false)
  const [days,      setDays]      = useState(30)
  const [sevFilter, setSevFilter] = useState('all')   // 'all' | 'warning' | 'critical'
  const [resolving, setResolving] = useState(null)    // id of in-progress resolve

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const params = { days, ...(sevFilter !== 'all' ? { severity: sevFilter } : {}) }
      const r = await anomaliesAPI.get(params)
      setData(r.data)
    } catch {
      setError('Failed to load anomalies. Make sure the backend is running.')
    } finally {
      setLoading(false)
    }
  }, [days, sevFilter])

  useEffect(() => { load() }, [load])

  const handleRefresh = async () => {
    setRefreshing(true)
    try {
      await anomaliesAPI.refresh()
      await load()
    } catch { /* silent */ } finally {
      setRefreshing(false)
    }
  }

  const handleResolve = async (id) => {
    setResolving(id)
    try {
      await anomaliesAPI.resolve(id)
      setData(prev => ({
        ...prev,
        anomalies: prev.anomalies.filter(a => a.id !== id),
        total: prev.total - 1,
        ...(prev.anomalies.find(a => a.id === id)?.severity === 'critical'
          ? { critical_count: prev.critical_count - 1 }
          : { warning_count: prev.warning_count - 1 }),
      }))
    } catch { /* silent */ } finally {
      setResolving(null)
    }
  }

  if (loading) return <Loading />
  if (error)   return <ErrorState msg={error} />

  const { anomalies = [], total = 0, warning_count = 0, critical_count = 0 } = data
  const topDriver = anomalies.reduce((acc, a) => {
    acc[a.driver_service] = (acc[a.driver_service] || 0) + 1
    return acc
  }, {})
  const topDriverName = Object.entries(topDriver).sort((a,b) => b[1]-a[1])[0]?.[0] || '—'

  return (
    <div className="page-content animate-up">

      {/* ── Header ───────────────────────────────────────────────── */}
      <div className="page-header">
        <div>
          <div className="page-title">Anomaly Detection</div>
          <div className="page-subtitle">
            Z-score + IQR detection against FR-2 forecast baseline (FR-3)
          </div>
        </div>
        <div style={{ display: 'flex', gap: 8, marginLeft: 'auto', alignItems: 'center' }}>
          {/* Window selector */}
          {[7, 14, 30, 60].map(d => (
            <button key={d} onClick={() => setDays(d)} style={{
              fontSize: 11, padding: '4px 10px', borderRadius: 6, border: 'none',
              cursor: 'pointer', fontWeight: 600,
              background: days === d ? 'rgba(248,113,113,0.2)' : 'rgba(255,255,255,0.05)',
              color: days === d ? '#f87171' : 'var(--text-3)',
            }}>{d}d</button>
          ))}
          <button onClick={handleRefresh} disabled={refreshing} style={{
            display: 'flex', alignItems: 'center', gap: 5,
            fontSize: 11, padding: '5px 12px', borderRadius: 6, border: 'none',
            cursor: 'pointer', fontWeight: 600,
            background: 'rgba(255,255,255,0.07)', color: 'var(--text-2)',
          }}>
            <RefreshCw size={13} style={{ animation: refreshing ? 'spin 1s linear infinite' : 'none' }} />
            {refreshing ? 'Running…' : 'Re-detect'}
          </button>
        </div>
      </div>

      {/* ── Metric Cards ─────────────────────────────────────────── */}
      <div className="metric-grid">
        <MetricCard icon={<Activity size={20} />}  label="Total Anomalies"
          value={total} sub={`Last ${days} days`} accentColor="#f87171" stagger={1} />
        <MetricCard icon={<ShieldAlert size={20} />} label="Critical"
          value={critical_count} sub="|z| ≥ 3.5σ" accentColor="#f87171" stagger={2} />
        <MetricCard icon={<AlertTriangle size={20} />} label="Warnings"
          value={warning_count} sub="2.5 ≤ |z| < 3.5σ" accentColor="#fbbf24" stagger={3} />
        <MetricCard icon={<Zap size={20} />} label="Top Driver"
          value={topDriverName} sub="Service with most anomalies" accentColor="#a78bfa" stagger={4} />
      </div>

      {/* ── Row 2: Timeline chart + filter bar ───────────────────── */}
      <div className="card stagger-3">
        <div className="card-header">
          <div className="card-title">
            <div className="card-title-icon" style={{ background: 'rgba(248,113,113,0.12)', color: '#f87171' }}>
              <Activity size={16} />
            </div>
            Anomaly Timeline — Residual Magnitude
          </div>
          <div style={{ marginLeft: 'auto', display: 'flex', gap: 6 }}>
            {['all', 'warning', 'critical'].map(f => (
              <button key={f} onClick={() => setSevFilter(f)} style={{
                fontSize: 11, padding: '4px 10px', borderRadius: 6, border: 'none',
                cursor: 'pointer', fontWeight: 600, textTransform: 'capitalize',
                background: sevFilter === f ? 'rgba(248,113,113,0.2)' : 'rgba(255,255,255,0.05)',
                color: sevFilter === f ? '#f87171' : 'var(--text-3)',
              }}>{f}</button>
            ))}
          </div>
        </div>
        <div style={{ height: 220 }}>
          <AnomalyTimeline anomalies={anomalies} />
        </div>
        <div style={{ fontSize: 11, color: 'var(--text-3)', marginTop: 'var(--s-2)' }}>
          Bar height = absolute residual (actual − forecast). Red = spike above forecast · Blue = drop below forecast.
        </div>
      </div>

      {/* ── Row 3: Anomaly feed table ─────────────────────────────── */}
      {anomalies.length > 0 ? (
        <div className="card stagger-4" style={{ padding: 0 }}>
          <div className="card-header" style={{ padding: 'var(--s-5) var(--s-5) 0' }}>
            <div className="card-title">
              <div className="card-title-icon" style={{ background: 'rgba(248,113,113,0.12)', color: '#f87171' }}>
                <ShieldAlert size={16} />
              </div>
              Anomaly Feed
              <span style={{
                marginLeft: 8, fontSize: 11, background: 'rgba(248,113,113,0.12)',
                color: '#f87171', borderRadius: 4, padding: '2px 7px', fontWeight: 700,
              }}>{anomalies.length}</span>
            </div>
          </div>
          <div className="table-wrap" style={{ maxHeight: 380, overflowY: 'auto', marginTop: 'var(--s-4)' }}>
            <table className="data-table">
              <thead>
                <tr>
                  <th>Date</th>
                  <th>Service</th>
                  <th style={{ textAlign: 'right' }}>Actual</th>
                  <th style={{ textAlign: 'right' }}>Forecast</th>
                  <th style={{ textAlign: 'right' }}>Deviation</th>
                  <th style={{ textAlign: 'right' }}>Z-score</th>
                  <th>Severity</th>
                  <th>Direction</th>
                  <th>Driver</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {anomalies.map(a => (
                  <tr key={a.id} style={{
                    background: a.severity === 'critical'
                      ? 'rgba(248,113,113,0.04)' : 'transparent',
                  }}>
                    <td style={{ color: 'var(--text-3)', fontFeatureSettings: '"tnum"' }}>{a.record_date}</td>
                    <td>
                      <span className={`chip chip-${a.service_type.toLowerCase()}`}>{a.service_type}</span>
                    </td>
                    <td style={{ textAlign: 'right', fontWeight: 700, color: 'var(--text-1)' }}>
                      ${a.actual_cost.toFixed(4)}
                    </td>
                    <td style={{ textAlign: 'right', color: 'var(--text-3)' }}>
                      ${a.forecast_cost.toFixed(4)}
                    </td>
                    <td style={{ textAlign: 'right', color: a.direction === 'spike' ? '#f87171' : '#60a5fa', fontWeight: 600 }}>
                      {a.direction === 'spike' ? '+' : '-'}{a.deviation_pct}%
                    </td>
                    <td style={{ textAlign: 'right', fontFeatureSettings: '"tnum"', color: 'var(--text-2)' }}>
                      {a.z_score > 0 ? '+' : ''}{a.z_score.toFixed(2)}σ
                    </td>
                    <td><SeverityBadge severity={a.severity} /></td>
                    <td>
                      <span style={{
                        display: 'flex', alignItems: 'center', fontSize: 12,
                        color: a.direction === 'spike' ? '#f87171' : '#60a5fa',
                      }}>
                        {DIR_ICON[a.direction]}{a.direction}
                      </span>
                    </td>
                    <td>
                      <span style={{
                        fontSize: 11, color: SVC_COLORS[a.driver_service] || 'var(--text-3)',
                        fontWeight: 600,
                      }}>{a.driver_service}</span>
                    </td>
                    <td>
                      <button
                        id={`resolve-btn-${a.id}`}
                        onClick={() => handleResolve(a.id)}
                        disabled={resolving === a.id}
                        title="Mark as resolved (dismissed anomaly won't resurface)"
                        style={{
                          display: 'flex', alignItems: 'center', gap: 4,
                          fontSize: 11, padding: '3px 8px', borderRadius: 5,
                          border: '1px solid rgba(52,211,153,0.2)',
                          background: 'rgba(52,211,153,0.07)', color: '#34d399',
                          cursor: resolving === a.id ? 'not-allowed' : 'pointer',
                          opacity: resolving === a.id ? 0.5 : 1,
                        }}
                      >
                        <CheckCircle size={11} />
                        {resolving === a.id ? '…' : 'Resolve'}
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {anomalies.length > 0 && (
            <div style={{ padding: 'var(--s-3) var(--s-5)', fontSize: 11, color: 'var(--text-3)' }}>
              Resolved anomalies are permanently dismissed and won't resurface on re-detection.
              They are retained by the Savings Optimizer (FR-6) and Auto-Remediation (FR-7) gate logic.
            </div>
          )}
        </div>
      ) : (
        <div className="card stagger-4">
          <div className="empty-state" style={{ padding: '40px 20px' }}>
            <CheckCircle size={40} color="var(--color-success)" style={{ marginBottom: 12 }} />
            <div className="empty-title">No Anomalies Detected</div>
            <div className="empty-sub">
              All {days}-day cost data is within ±2.5σ of the FR-2 forecast baseline.
              {days < 30 && ' Try a wider window to see more history.'}
            </div>
          </div>
        </div>
      )}

    </div>
  )
}
