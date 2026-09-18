// src/pages/Predictions.jsx — FR-2 Explainable Forecasting Dashboard
import { useState, useEffect } from 'react'
import {
  ComposedChart, AreaChart, Area, Line, XAxis, YAxis, CartesianGrid,
  Tooltip as RechartsTooltip, ResponsiveContainer, ReferenceLine,
  Legend, BarChart, Bar, Cell,
} from 'recharts'
import {
  TrendingUp, Brain, Database, Target, Award, Info,
  BarChart2, Layers, Zap,
} from 'lucide-react'
import { predictionsAPI } from '../api/client'

// ── Service colour palette ────────────────────────────────────────
const SVC_COLORS = {
  EC2:    '#ec7211',
  RDS:    '#0073bb',
  S3:     '#1d8102',
  Lambda: '#6366f1',
}
const SVC_COLOR_DEFAULT = '#94a3b8'

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
            ${typeof entry.value === 'number' ? entry.value.toFixed(4) : entry.value}
          </span>
        </div>
      ))}
    </div>
  )
}

// ── Loading / Error states ────────────────────────────────────────
const Loading = () => (
  <div className="page-content">
    <div className="loading-wrap">
      <div className="spinner" />
      <div className="loading-text">Running ML models on historical data…</div>
    </div>
  </div>
)

const ErrorState = ({ msg }) => (
  <div className="page-content">
    <div className="empty-state">
      <div className="empty-icon"><Info size={24} /></div>
      <div className="empty-title">Prediction Error</div>
      <div className="empty-sub">{msg}</div>
    </div>
  </div>
)

// ── Model Comparison Card ─────────────────────────────────────────
function ModelComparisonCard({ comparison }) {
  if (!comparison) {
    return (
      <div className="card stagger-2" style={{ display: 'flex', flexDirection: 'column', gap: 'var(--s-3)' }}>
        <div className="card-header">
          <div className="card-title">
            <div className="card-title-icon" style={{ background: 'rgba(99,102,241,0.12)', color: '#818cf8' }}>
              <Award size={16} />
            </div>
            Model Comparison
          </div>
        </div>
        <div className="info-alert" style={{ margin: 0 }}>
          <Info size={14} className="info-alert-icon" />
          <div>Need ≥ 10 days of data to compare models. Collecting more history…</div>
        </div>
      </div>
    )
  }

  const { winner, poly_mape, poly_rmse, hw_mape, hw_rmse, held_out_days } = comparison
  const polyWins = winner === 'Polynomial Regression'

  const ModelRow = ({ label, mape, rmse, isWinner }) => (
    <div style={{
      display: 'flex', alignItems: 'center', gap: 'var(--s-3)',
      padding: 'var(--s-3) var(--s-4)',
      borderRadius: 10,
      background: isWinner ? 'rgba(52,211,153,0.08)' : 'rgba(255,255,255,0.03)',
      border: isWinner ? '1px solid rgba(52,211,153,0.2)' : '1px solid transparent',
    }}>
      <div style={{ flex: 1 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <span style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-1)' }}>{label}</span>
          {isWinner && (
            <span style={{
              fontSize: 10, fontWeight: 700, color: '#34d399',
              background: 'rgba(52,211,153,0.15)', borderRadius: 4,
              padding: '2px 6px', letterSpacing: '0.05em',
            }}>WINNER</span>
          )}
        </div>
      </div>
      <div style={{ textAlign: 'right' }}>
        <div style={{ fontSize: 12, color: 'var(--text-3)' }}>MAPE</div>
        <div style={{ fontSize: 14, fontWeight: 700, color: isWinner ? '#34d399' : 'var(--text-1)' }}>
          {mape === 999 ? 'N/A' : `${mape.toFixed(1)}%`}
        </div>
      </div>
      <div style={{ width: 1, height: 32, background: 'var(--glass-border)' }} />
      <div style={{ textAlign: 'right', minWidth: 70 }}>
        <div style={{ fontSize: 12, color: 'var(--text-3)' }}>RMSE</div>
        <div style={{ fontSize: 14, fontWeight: 700, color: 'var(--text-1)' }}>
          ${rmse === 999 ? 'N/A' : rmse.toFixed(3)}
        </div>
      </div>
    </div>
  )

  return (
    <div className="card stagger-2" style={{ display: 'flex', flexDirection: 'column', gap: 'var(--s-3)' }}>
      <div className="card-header">
        <div className="card-title">
          <div className="card-title-icon" style={{ background: 'rgba(99,102,241,0.12)', color: '#818cf8' }}>
            <Award size={16} />
          </div>
          Model Comparison
          <span style={{ marginLeft: 'auto', fontSize: 11, color: 'var(--text-3)', fontWeight: 400 }}>
            Eval on {held_out_days}-day held-out window
          </span>
        </div>
      </div>
      <ModelRow label="Polynomial Regression" mape={poly_mape} rmse={poly_rmse} isWinner={polyWins} />
      <ModelRow label="Holt-Winters ES" mape={hw_mape} rmse={hw_rmse} isWinner={!polyWins} />
      <div style={{ fontSize: 11, color: 'var(--text-3)', paddingTop: 2 }}>
        MAPE = Mean Absolute % Error. RMSE = Root Mean Squared Error. Lower is better.
        Forecast uses the lower-MAPE model.
      </div>
    </div>
  )
}

// ── Attribution Bar ───────────────────────────────────────────────
function AttributionBars({ perService }) {
  if (!perService?.length) return null
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--s-2)' }}>
      {perService.map(s => {
        const color = SVC_COLORS[s.service] || SVC_COLOR_DEFAULT
        return (
          <div key={s.service}>
            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                <span style={{ width: 8, height: 8, borderRadius: '50%', background: color }} />
                <span style={{ fontSize: 12, color: 'var(--text-2)', fontWeight: 600 }}>{s.service}</span>
              </div>
              <div style={{ fontSize: 12, color: 'var(--text-1)', fontWeight: 700 }}>
                ${s.monthly_estimate_usd.toFixed(2)}&nbsp;
                <span style={{ color: 'var(--text-3)', fontWeight: 400 }}>({s.attribution_pct}%)</span>
              </div>
            </div>
            <div style={{ height: 6, borderRadius: 3, background: 'rgba(255,255,255,0.06)', overflow: 'hidden' }}>
              <div style={{
                height: '100%', width: `${s.attribution_pct}%`,
                background: color, borderRadius: 3,
                transition: 'width 0.8s cubic-bezier(0.16,1,0.3,1)',
              }} />
            </div>
          </div>
        )
      })}
    </div>
  )
}

// ── Per-Service Stacked Area Chart ────────────────────────────────
function PerServiceChart({ perService }) {
  if (!perService?.length) return (
    <div className="empty-state">
      <div className="empty-sub">No per-service breakdown available yet.</div>
    </div>
  )

  // Merge all service forecasts into one array keyed by date
  const dateMap = {}
  perService.forEach(s => {
    s.forecast.forEach(f => {
      if (!dateMap[f.date]) dateMap[f.date] = { date: f.date }
      dateMap[f.date][s.service] = f.cost
    })
  })
  const chartData = Object.values(dateMap).sort((a, b) => a.date.localeCompare(b.date))
  const services  = perService.map(s => s.service)

  return (
    <ResponsiveContainer width="100%" height="100%">
      <AreaChart data={chartData} margin={{ top: 10, right: 10, left: -10, bottom: 0 }}>
        <defs>
          {services.map(svc => (
            <linearGradient key={svc} id={`grad-${svc}`} x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%"  stopColor={SVC_COLORS[svc] || SVC_COLOR_DEFAULT} stopOpacity={0.35} />
              <stop offset="95%" stopColor={SVC_COLORS[svc] || SVC_COLOR_DEFAULT} stopOpacity={0.05} />
            </linearGradient>
          ))}
        </defs>
        <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" vertical={false} />
        <XAxis
          dataKey="date" tick={{ fill: '#64748b', fontSize: 11 }}
          tickFormatter={v => v.slice(5)} axisLine={false} tickLine={false} dy={10}
          interval={Math.floor(chartData.length / 6)}
        />
        <YAxis
          tick={{ fill: '#64748b', fontSize: 11 }}
          tickFormatter={v => `$${v.toFixed(2)}`}
          axisLine={false} tickLine={false} width={65}
        />
        <RechartsTooltip content={<ChartTooltip />}
          cursor={{ stroke: 'rgba(255,255,255,0.08)', strokeWidth: 1 }} />
        <Legend
          wrapperStyle={{ fontSize: '11.5px', color: '#94a3b8', paddingTop: 16 }}
          iconType="circle" iconSize={8}
        />
        {services.map(svc => (
          <Area
            key={svc}
            type="monotone"
            dataKey={svc}
            name={svc}
            stackId="1"
            stroke={SVC_COLORS[svc] || SVC_COLOR_DEFAULT}
            strokeWidth={1.5}
            fill={`url(#grad-${svc})`}
            dot={false}
          />
        ))}
      </AreaChart>
    </ResponsiveContainer>
  )
}

// ── Main Component ────────────────────────────────────────────────
export default function Predictions() {
  const [data,    setData]    = useState(null)
  const [loading, setLoading] = useState(true)
  const [error,   setError]   = useState(null)
  const [view,    setView]    = useState('combined')  // 'combined' | 'models'

  useEffect(() => {
    predictionsAPI.get()
      .then(r => setData(r.data))
      .catch(() => setError('Failed to load predictions. Make sure the backend is running.'))
      .finally(() => setLoading(false))
  }, [])

  if (loading) return <Loading />
  if (error)   return <ErrorState msg={error} />

  const {
    historical = [], forecast = [], forecast_poly = [], forecast_hw = [],
    per_service_forecast = [], model_comparison, monthly_estimate_usd,
    model_info = {},
  } = data

  const today = new Date().toISOString().slice(0, 10)

  // ── Combined Historical + Forecast chart data ─────────────────
  const combinedData = [
    ...historical.map(d => ({ date: d.date, actual: d.cost, forecast: null, poly: null, hw: null })),
    ...forecast.map((d, i) => ({
      date: d.date,
      actual:   null,
      forecast: d.cost,
      poly:     forecast_poly[i]?.cost ?? null,
      hw:       forecast_hw[i]?.cost   ?? null,
    })),
  ]

  const mape = model_comparison
    ? (model_comparison.winner_key === 'hw' ? model_comparison.hw_mape : model_comparison.poly_mape)
    : null

  const hasSufficientData = historical.length >= 7

  return (
    <div className="page-content animate-up">

      {/* ── Page Header ─────────────────────────────────────────── */}
      <div className="page-header">
        <div className="page-title">Cost Predictions</div>
        <div className="page-subtitle">
          ML-powered 30-day spend forecast with per-service attribution (FR-2)
        </div>
      </div>

      {/* ── Low-data warning ────────────────────────────────────── */}
      {model_info.note && (
        <div className="info-alert stagger-1">
          <Info size={14} className="info-alert-icon" />
          <div>{model_info.note}</div>
        </div>
      )}

      {/* ── Metric Cards ─────────────────────────────────────────── */}
      <div className="metric-grid">

        {/* Predicted total */}
        <div className="metric-card stagger-1">
          <div className="metric-card-glow" style={{ background: 'var(--brand-violet)' }} />
          <div className="metric-top">
            <div className="metric-icon" style={{ background: 'rgba(124,58,237,0.12)', color: '#a78bfa' }}>
              <TrendingUp size={20} />
            </div>
            <div className="metric-trend neutral">30-Day Outlook</div>
          </div>
          <div className="metric-label">Predicted Total</div>
          <div className="metric-value" style={{ color: '#c4b5fd' }}>
            ${(monthly_estimate_usd || 0).toFixed(2)}
          </div>
          <div className="metric-sub">Next 30 days (winning model)</div>
        </div>

        {/* Best model */}
        <div className="metric-card stagger-2">
          <div className="metric-top">
            <div className="metric-icon" style={{ background: 'rgba(99,102,241,0.12)', color: '#818cf8' }}>
              <Award size={20} />
            </div>
          </div>
          <div className="metric-label">Best Model</div>
          <div className="metric-value" style={{ fontSize: 18, marginTop: 4 }}>
            {model_comparison?.winner || (model_info.type === 'flat_average' ? 'Flat Average' : 'Polynomial')}
          </div>
          <div className="metric-sub">
            {model_comparison ? `Lower MAPE on ${model_comparison.held_out_days}-day eval` : 'Insufficient data for comparison'}
          </div>
        </div>

        {/* MAPE */}
        <div className="metric-card stagger-3">
          <div className="metric-top">
            <div className="metric-icon" style={{ background: 'rgba(16,185,129,0.12)', color: '#34d399' }}>
              <Target size={20} />
            </div>
          </div>
          <div className="metric-label">Forecast MAPE</div>
          <div className="metric-value" style={{
            color: mape == null ? 'var(--text-3)' : mape < 10 ? '#34d399' : mape < 25 ? '#fbbf24' : '#f87171'
          }}>
            {mape == null ? '—' : mape === 999 ? 'N/A' : `${mape.toFixed(1)}%`}
          </div>
          <div className="metric-sub">Mean Absolute % Error on held-out window</div>
        </div>

        {/* Training days */}
        <div className="metric-card stagger-4">
          <div className="metric-top">
            <div className="metric-icon" style={{ background: 'rgba(59,130,246,0.12)', color: '#60a5fa' }}>
              <Database size={20} />
            </div>
          </div>
          <div className="metric-label">Training Data</div>
          <div className="metric-value">{model_info.training_days || 0}</div>
          <div className="metric-sub">Days of historical cost records</div>
        </div>

      </div>

      {/* ── Row 2: Main Chart + Model Comparison ─────────────────── */}
      <div className="grid-2-1">

        {/* Main forecast chart */}
        <div className="card stagger-3">
          <div className="card-header" style={{ flexWrap: 'wrap', gap: 'var(--s-2)' }}>
            <div className="card-title">
              <div className="card-title-icon" style={{ background: 'rgba(124,58,237,0.12)', color: '#a78bfa' }}>
                <Brain size={16} />
              </div>
              Spend Trajectory — Historical + Forecast
            </div>
            <div style={{ display: 'flex', gap: 6, marginLeft: 'auto' }}>
              {['combined', 'models'].map(v => (
                <button key={v} onClick={() => setView(v)} style={{
                  fontSize: 11, padding: '4px 10px', borderRadius: 6, border: 'none',
                  cursor: 'pointer', fontWeight: 600,
                  background: view === v ? 'rgba(124,58,237,0.25)' : 'rgba(255,255,255,0.05)',
                  color: view === v ? '#c4b5fd' : 'var(--text-3)',
                }}>
                  {v === 'combined' ? 'Best Model' : 'Both Models'}
                </button>
              ))}
            </div>
          </div>

          <div style={{ height: 260 }}>
            <ResponsiveContainer width="100%" height="100%">
              <ComposedChart data={combinedData} margin={{ top: 10, right: 10, left: -10, bottom: 0 }}>
                <defs>
                  <linearGradient id="forecastGrad" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%"  stopColor="#a78bfa" stopOpacity={0.35} />
                    <stop offset="95%" stopColor="#a78bfa" stopOpacity={0}    />
                  </linearGradient>
                  <linearGradient id="polyGrad" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%"  stopColor="#f59e0b" stopOpacity={0.2} />
                    <stop offset="95%" stopColor="#f59e0b" stopOpacity={0}   />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" vertical={false} />
                <XAxis
                  dataKey="date"
                  tick={{ fill: '#64748b', fontSize: 11 }}
                  tickFormatter={v => v.slice(5)}
                  axisLine={false} tickLine={false} dy={10}
                  interval={Math.floor(combinedData.length / 8)}
                />
                <YAxis
                  tick={{ fill: '#64748b', fontSize: 11 }}
                  tickFormatter={v => `$${v.toFixed(2)}`}
                  axisLine={false} tickLine={false} width={65}
                />
                <RechartsTooltip content={<ChartTooltip />}
                  cursor={{ stroke: 'rgba(255,255,255,0.1)', strokeWidth: 1, strokeDasharray: '3 3' }} />
                <Legend
                  wrapperStyle={{ fontSize: '11.5px', color: '#94a3b8', paddingTop: 16 }}
                  iconType="circle" iconSize={8}
                />
                <ReferenceLine
                  x={today}
                  stroke="rgba(124,58,237,0.4)"
                  strokeDasharray="4 4"
                  label={{ value: 'Today', fill: '#c4b5fd', fontSize: 10, position: 'insideTopLeft' }}
                />

                {/* Historical */}
                <Line
                  type="monotone" dataKey="actual" name="Historical"
                  stroke="#3b82f6" strokeWidth={2.5}
                  dot={false} activeDot={{ r: 4, fill: '#3b82f6', stroke: '#080d1a', strokeWidth: 2 }}
                  connectNulls={false}
                />

                {view === 'combined' ? (
                  /* Winning model forecast */
                  <Area
                    type="monotone" dataKey="forecast" name="Forecast (Winner)"
                    stroke="#a78bfa" strokeWidth={2.5} strokeDasharray="6 4"
                    fill="url(#forecastGrad)"
                    dot={false} activeDot={{ r: 4 }} connectNulls={false}
                  />
                ) : (
                  <>
                    <Area
                      type="monotone" dataKey="poly" name="Polynomial"
                      stroke="#f59e0b" strokeWidth={2} strokeDasharray="5 3"
                      fill="url(#polyGrad)"
                      dot={false} connectNulls={false}
                    />
                    <Line
                      type="monotone" dataKey="hw" name="Holt-Winters"
                      stroke="#34d399" strokeWidth={2} strokeDasharray="8 3"
                      dot={false} connectNulls={false}
                    />
                  </>
                )}
              </ComposedChart>
            </ResponsiveContainer>
          </div>
        </div>

        {/* Model comparison card */}
        <ModelComparisonCard comparison={model_comparison} />
      </div>

      {/* ── Row 3: Per-Service Breakdown (FR-2.1, FR-2.4, FR-2.5) ── */}
      <div className="grid-2">

        {/* Stacked area chart */}
        <div className="card stagger-4">
          <div className="card-header">
            <div className="card-title">
              <div className="card-title-icon" style={{ background: 'rgba(99,102,241,0.12)', color: '#818cf8' }}>
                <Layers size={16} />
              </div>
              Per-Service Forecast (30 Days)
              {per_service_forecast[0]?.is_normalized && (
                <span style={{
                  marginLeft: 8, fontSize: 10, padding: '2px 6px',
                  background: 'rgba(52,211,153,0.12)', color: '#34d399',
                  borderRadius: 4, fontWeight: 700,
                }}>NORMALIZED ✓</span>
              )}
            </div>
          </div>
          <div style={{ height: 230 }}>
            <PerServiceChart perService={per_service_forecast} />
          </div>
          <div style={{ fontSize: 11, color: 'var(--text-3)', marginTop: 'var(--s-2)' }}>
            Stacked area — per-service values are normalized to sum exactly to the headline total.
          </div>
        </div>

        {/* Attribution bars */}
        <div className="card stagger-4">
          <div className="card-header">
            <div className="card-title">
              <div className="card-title-icon" style={{ background: 'rgba(16,185,129,0.12)', color: '#34d399' }}>
                <BarChart2 size={16} />
              </div>
              Cost Attribution (FR-2.4)
            </div>
          </div>

          {per_service_forecast.length > 0 ? (
            <>
              <div style={{ marginBottom: 'var(--s-4)' }}>
                <AttributionBars perService={per_service_forecast} />
              </div>
              <div style={{
                borderTop: '1px solid var(--glass-border)',
                paddingTop: 'var(--s-3)',
                display: 'flex', flexDirection: 'column', gap: 'var(--s-2)',
              }}>
                {per_service_forecast.map(s => (
                  <div key={s.service} style={{
                    display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                  }}>
                    <span className={`chip chip-${s.service.toLowerCase()}`}>{s.service}</span>
                    <div style={{ textAlign: 'right' }}>
                      <span style={{ fontSize: 13, fontWeight: 700, color: 'var(--text-1)' }}>
                        ${s.monthly_estimate_usd.toFixed(2)}
                      </span>
                      <span style={{ fontSize: 11, color: 'var(--text-3)', marginLeft: 4 }}>/ 30d</span>
                    </div>
                  </div>
                ))}
              </div>
            </>
          ) : (
            <div className="empty-state" style={{ padding: '20px' }}>
              <Zap size={28} color="var(--text-3)" style={{ marginBottom: 10 }} />
              <div className="empty-sub">Per-service attribution requires ≥ 7 days of data per service.</div>
            </div>
          )}
        </div>
      </div>

      {/* ── Row 4: Forecast Data Table ───────────────────────────── */}
      {forecast?.length > 0 && (
        <div className="card stagger-4" style={{ padding: 0 }}>
          <div className="card-header" style={{ padding: 'var(--s-5) var(--s-5) 0' }}>
            <div className="card-title">
              <div className="card-title-icon" style={{ background: 'rgba(124,58,237,0.12)', color: '#a78bfa' }}>
                <TrendingUp size={16} />
              </div>
              Forecast Table — {model_info.type === 'holt_winters' ? 'Holt-Winters' : 'Polynomial Regression'} (Winner)
            </div>
          </div>
          <div className="table-wrap" style={{ maxHeight: 260, overflowY: 'auto', marginTop: 'var(--s-4)' }}>
            <table className="data-table">
              <thead>
                <tr>
                  <th>Date</th>
                  {per_service_forecast.map(s => (
                    <th key={s.service} style={{ textAlign: 'right' }}>{s.service}</th>
                  ))}
                  <th style={{ textAlign: 'right' }}>Daily Total</th>
                </tr>
              </thead>
              <tbody>
                {forecast.map((f, i) => (
                  <tr key={f.date}>
                    <td style={{ color: 'var(--text-3)' }}>{f.date}</td>
                    {per_service_forecast.map(s => (
                      <td key={s.service} style={{ textAlign: 'right', color: 'var(--text-2)' }}>
                        ${(s.forecast[i]?.cost ?? 0).toFixed(3)}
                      </td>
                    ))}
                    <td style={{ textAlign: 'right', fontWeight: 700, color: 'var(--text-1)' }}>
                      ${f.cost.toFixed(4)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

    </div>
  )
}
