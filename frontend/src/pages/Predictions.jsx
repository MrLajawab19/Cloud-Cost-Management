// src/pages/Predictions.jsx — ML-based 30-day cost forecast
import { useState, useEffect } from 'react'
import {
  ComposedChart, Line, Area, XAxis, YAxis, CartesianGrid,
  Tooltip as RechartsTooltip, ResponsiveContainer, ReferenceLine, Legend
} from 'recharts'
import { TrendingUp, Brain, Info, Database } from 'lucide-react'
import { predictionsAPI } from '../api/client'

const CustomTooltip = ({ active, payload, label }) => {
  if (active && payload && payload.length) {
    return (
      <div className="chart-tooltip">
        <div className="chart-tooltip-label">{label}</div>
        {payload.map((entry, index) => (
          <div key={`item-${index}`} style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 4 }}>
            <span style={{ width: 8, height: 8, borderRadius: '50%', background: entry.color }} />
            <span style={{ color: 'var(--text-3)', fontSize: 11 }}>{entry.name === 'actual' ? 'Historical' : 'Forecast'}: </span>
            <span style={{ color: 'var(--text-1)', fontWeight: 700 }}>${Number(entry.value).toFixed(4)}</span>
          </div>
        ))}
      </div>
    );
  }
  return null;
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
      <div className="loading-wrap">
        <div className="spinner" />
        <div className="loading-text">Running ML models on historical data…</div>
      </div>
    </div>
  )

  if (error) return (
    <div className="page-content">
      <div className="empty-state">
        <div className="empty-icon"><Info size={24} /></div>
        <div className="empty-title">Prediction Error</div>
        <div className="empty-sub">{error}</div>
      </div>
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
    <div className="page-content animate-up">
      {/* Model info cards */}
      <div className="metric-grid">
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
            ${(monthlyEstimate || 0).toFixed(2)}
          </div>
          <div className="metric-sub">Forecast for next month</div>
        </div>
        
        <div className="metric-card stagger-2">
          <div className="metric-top">
            <div className="metric-icon" style={{ background: 'rgba(59,130,246,0.12)', color: '#60a5fa' }}>
              <Brain size={20} />
            </div>
          </div>
          <div className="metric-label">Model Engine</div>
          <div className="metric-value" style={{ fontSize: 22, marginTop: 4 }}>
            {model.type || 'N/A'}
          </div>
          <div className="metric-sub">Machine learning algorithm</div>
        </div>
        
        <div className="metric-card stagger-3">
          <div className="metric-top">
            <div className="metric-icon" style={{ background: 'rgba(16,185,129,0.12)', color: '#34d399' }}>
              <Database size={20} />
            </div>
          </div>
          <div className="metric-label">Training Data</div>
          <div className="metric-value">{model.training_days || 0}</div>
          <div className="metric-sub">Historical data points used</div>
        </div>
        
        {model.r2_score != null && (
          <div className="metric-card stagger-4">
            <div className="metric-top">
              <div className="metric-icon" style={{ background: 'rgba(239,68,68,0.12)', color: '#f87171' }}>
                <TrendingUp size={20} />
              </div>
            </div>
            <div className="metric-label">Model Confidence (R²)</div>
            <div className="metric-value" style={{ color: model.r2_score > 0.8 ? '#34d399' : '#fbbf24' }}>
              {(model.r2_score * 100).toFixed(1)}%
            </div>
            <div className="metric-sub">Accuracy score</div>
          </div>
        )}
      </div>

      {/* Note if not enough data */}
      {model.note && (
        <div className="info-alert stagger-2">
          <Info size={16} className="info-alert-icon" />
          <div>{model.note}</div>
        </div>
      )}

      <div className="grid-2-1">
        {/* Combined Historical + Forecast Chart */}
        <div className="card stagger-3">
          <div className="card-header">
            <div className="card-title">
              <div className="card-title-icon" style={{ background: 'rgba(124,58,237,0.12)', color: '#a78bfa' }}>
                <Brain size={16} />
              </div>
              Spend Trajectory (Historical + Forecast)
            </div>
          </div>
          <div style={{ height: 250 }}>
            <ResponsiveContainer width="100%" height="100%">
              <ComposedChart data={chartData} margin={{ top: 10, right: 10, left: -10, bottom: 0 }}>
                <defs>
                  <linearGradient id="forecastGrad" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%"  stopColor="#a78bfa" stopOpacity={0.4} />
                    <stop offset="95%" stopColor="#a78bfa" stopOpacity={0}   />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" vertical={false} />
                <XAxis
                  dataKey="date"
                  tick={{ fill: '#64748b', fontSize: 11 }}
                  tickFormatter={v => v.slice(5)}
                  axisLine={false} tickLine={false} dy={10}
                  interval={Math.floor(chartData.length / 8)}
                />
                <YAxis
                  tick={{ fill: '#64748b', fontSize: 11 }}
                  tickFormatter={v => `$${v.toFixed(2)}`}
                  axisLine={false} tickLine={false} width={65}
                />
                <RechartsTooltip content={<CustomTooltip />} cursor={{ stroke: 'rgba(255,255,255,0.1)', strokeWidth: 1, strokeDasharray: '3 3' }} />
                <Legend
                  wrapperStyle={{ fontSize: '11.5px', color: '#94a3b8', paddingTop: 20 }}
                  iconType="circle"
                  iconSize={8}
                />
                <ReferenceLine x={today} stroke="rgba(124,58,237,0.5)" strokeDasharray="4 4" label={{ value: 'Today', fill: '#c4b5fd', fontSize: 10, position: 'insideTopLeft' }} />
                
                {/* Historical Line */}
                <Line
                  type="monotone" dataKey="actual" name="Historical Spend"
                  stroke="#3b82f6" strokeWidth={3}
                  dot={false} activeDot={{ r: 5, fill: '#3b82f6', stroke: '#080d1a', strokeWidth: 2 }}
                  connectNulls={false}
                />
                
                {/* Forecast Area */}
                <Area
                  type="monotone" dataKey="forecast" name="ML Forecast"
                  stroke="#a78bfa" strokeWidth={2.5} strokeDasharray="6 4"
                  fill="url(#forecastGrad)"
                  dot={false} activeDot={{ r: 5, fill: '#a78bfa', stroke: '#080d1a', strokeWidth: 2 }}
                  connectNulls={false}
                />
              </ComposedChart>
            </ResponsiveContainer>
          </div>
        </div>

        {/* Forecast table */}
        {data.forecast?.length > 0 && (
          <div className="card stagger-4" style={{ padding: 0 }}>
            <div className="card-header" style={{ padding: 'var(--s-6) var(--s-6) 0' }}>
              <div className="card-title">Forecast Data Table</div>
            </div>
            <div className="table-wrap" style={{ maxHeight: 250, overflowY: 'auto', marginTop: 'var(--s-4)' }}>
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Date</th>
                    <th style={{ textAlign: 'right' }}>Daily Estimate</th>
                  </tr>
                </thead>
                <tbody>
                  {data.forecast.map(f => (
                    <tr key={f.date}>
                      <td style={{ color: 'var(--text-3)' }}>{f.date}</td>
                      <td style={{ textAlign: 'right', fontWeight: 600, color: 'var(--text-1)' }}>
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
    </div>
  )
}
