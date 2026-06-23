// src/pages/Predictions.jsx — ML-based 30-day cost forecast
import { useState, useEffect } from 'react'
import {
  ComposedChart, Line, Area, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer, ReferenceLine, Legend
} from 'recharts'
import { TrendingUp, Brain, Info } from 'lucide-react'
import { predictionsAPI } from '../api/client'

const TooltipStyle = {
  background: 'rgba(13,20,39,0.95)',
  border: '1px solid rgba(255,255,255,0.1)',
  borderRadius: 8, fontSize: 12,
}

export default function Predictions() {
  const [data,    setData]    = useState(null)
  const [loading, setLoading] = useState(true)
  const [error,   setError]   = useState(null)

  useEffect(() => {
    predictionsAPI.get()
      .then(r => setData(r.data))
      .catch(e => setError('Failed to load predictions.'))
      .finally(() => setLoading(false))
  }, [])

  if (loading) return (
    <div className="page-content">
      <div className="spinner-wrap" style={{ marginTop: 80 }}>
        <div className="spinner" />
        <span>Running ML model…</span>
      </div>
    </div>
  )

  if (error) return (
    <div className="page-content">
      <div className="card empty-state">{error}</div>
    </div>
  )

  // Merge historical + forecast into one chart dataset
  const today = new Date().toISOString().slice(0, 10)
  const chartData = [
    ...(data.historical || []).map(d => ({
      date: d.date,
      actual: d.cost,
      forecast: null,
    })),
    ...(data.forecast || []).map(d => ({
      date: d.date,
      actual: null,
      forecast: d.cost,
    })),
  ]

  const model = data.model_info || {}
  const monthlyEstimate = data.monthly_estimate_usd

  return (
    <div className="page-content">
      <h1 className="page-title">ML Cost Predictions</h1>
      <p className="page-subtitle">Machine learning forecast for the next 30 days based on historical spending</p>

      {/* Model info cards */}
      <div className="summary-cards" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', marginBottom: 'var(--space-xl)' }}>
        <div className="summary-card">
          <div className="card-label">30-Day Forecast Total</div>
          <div className="card-value" style={{ color: '#6366f1' }}>
            ${(monthlyEstimate || 0).toFixed(2)}
          </div>
          <div className="card-sub">Predicted next month</div>
        </div>
        <div className="summary-card">
          <div className="card-label">Model Type</div>
          <div className="card-value" style={{ fontSize: 14, marginTop: 8 }}>
            {model.type || 'N/A'}
          </div>
        </div>
        <div className="summary-card">
          <div className="card-label">Training Days</div>
          <div className="card-value">{model.training_days || 0}</div>
          <div className="card-sub">Historical data points</div>
        </div>
        {model.r2_score != null && (
          <div className="summary-card">
            <div className="card-label">R² Score</div>
            <div className="card-value" style={{ color: model.r2_score > 0.8 ? 'var(--color-success)' : 'var(--color-warning)' }}>
              {(model.r2_score * 100).toFixed(1)}%
            </div>
            <div className="card-sub">Model accuracy</div>
          </div>
        )}
      </div>

      {/* Note if not enough data */}
      {model.note && (
        <div style={{
          background: 'rgba(59,130,246,0.1)', border: '1px solid rgba(59,130,246,0.25)',
          borderRadius: 'var(--radius-md)', padding: 'var(--space-md)',
          display: 'flex', gap: 'var(--space-sm)', alignItems: 'flex-start',
          marginBottom: 'var(--space-lg)', fontSize: 13, color: 'var(--color-info)',
        }}>
          <Info size={16} style={{ flexShrink: 0, marginTop: 1 }} />
          {model.note}
        </div>
      )}

      {/* Combined Historical + Forecast Chart */}
      <div className="card">
        <div className="section-header">
          <span className="section-title">
            <Brain size={16} className="icon" />
            Historical Spend + 30-Day Forecast
          </span>
        </div>
        <ResponsiveContainer width="100%" height={350}>
          <ComposedChart data={chartData} margin={{ top: 10, right: 20, left: 0, bottom: 10 }}>
            <defs>
              <linearGradient id="forecastGrad" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%"  stopColor="#8b5cf6" stopOpacity={0.3} />
                <stop offset="95%" stopColor="#8b5cf6" stopOpacity={0}   />
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" />
            <XAxis
              dataKey="date"
              tick={{ fill: '#64748b', fontSize: 10 }}
              tickFormatter={v => v.slice(5)}
              interval={Math.floor(chartData.length / 8)}
            />
            <YAxis
              tick={{ fill: '#64748b', fontSize: 10 }}
              tickFormatter={v => `$${v.toFixed(3)}`}
              width={65}
            />
            <Tooltip
              formatter={(v, name) => [`$${(v || 0).toFixed(4)}`, name === 'actual' ? 'Historical' : 'Forecast']}
              contentStyle={TooltipStyle}
            />
            <Legend
              formatter={v => <span style={{ color: '#94a3b8', fontSize: 12 }}>
                {v === 'actual' ? 'Historical' : 'ML Forecast'}
              </span>}
            />
            <ReferenceLine x={today} stroke="rgba(255,255,255,0.2)" strokeDasharray="4 4" label={{ value: 'Today', fill: '#64748b', fontSize: 10 }} />
            <Line
              type="monotone" dataKey="actual"
              stroke="#6366f1" strokeWidth={2.5}
              dot={false} activeDot={{ r: 4 }}
              connectNulls={false}
            />
            <Area
              type="monotone" dataKey="forecast"
              stroke="#8b5cf6" strokeWidth={2.5} strokeDasharray="6 3"
              fill="url(#forecastGrad)"
              dot={false}
              connectNulls={false}
            />
          </ComposedChart>
        </ResponsiveContainer>
      </div>

      {/* Forecast table */}
      {data.forecast?.length > 0 && (
        <div className="card" style={{ marginTop: 'var(--space-lg)' }}>
          <div className="section-header">
            <span className="section-title">Forecast Detail</span>
          </div>
          <div className="data-table-wrap" style={{ maxHeight: 300, overflowY: 'auto' }}>
            <table className="data-table">
              <thead>
                <tr>
                  <th>Date</th>
                  <th style={{ textAlign: 'right' }}>Predicted Daily Cost</th>
                  <th style={{ textAlign: 'right' }}>Predicted Monthly Rate</th>
                </tr>
              </thead>
              <tbody>
                {data.forecast.map(f => (
                  <tr key={f.date}>
                    <td style={{ color: 'var(--text-secondary)' }}>{f.date}</td>
                    <td style={{ textAlign: 'right', fontWeight: 600 }}>${f.cost.toFixed(4)}</td>
                    <td style={{ textAlign: 'right', color: 'var(--text-muted)' }}>
                      ${(f.cost * 30).toFixed(2)}/mo
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
