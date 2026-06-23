// src/pages/Costs.jsx — Detailed cost analysis page
import { useState, useEffect } from 'react'
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, LineChart, Line, Cell
} from 'recharts'
import { DollarSign, TrendingUp } from 'lucide-react'
import { costsAPI } from '../api/client'

const SERVICE_COLORS = {
  EC2: '#f97316', S3: '#22c55e', RDS: '#3b82f6', Lambda: '#a78bfa',
}

const TooltipStyle = {
  background: 'rgba(13,20,39,0.95)',
  border: '1px solid rgba(255,255,255,0.1)',
  borderRadius: 8, fontSize: 12,
}

export default function Costs() {
  const [summary,   setSummary]   = useState(null)
  const [trend,     setTrend]     = useState([])
  const [byService, setByService] = useState([])
  const [trendDays, setTrendDays] = useState(30)
  const [loading,   setLoading]   = useState(true)

  const load = async () => {
    setLoading(true)
    try {
      const [s, t, bs] = await Promise.all([
        costsAPI.summary(),
        costsAPI.trend(trendDays),
        costsAPI.byService(),
      ])
      setSummary(s.data)
      setTrend(t.data.trend || [])
      setByService(bs.data)
    } catch (e) { console.error(e) }
    finally { setLoading(false) }
  }

  useEffect(() => { load() }, [trendDays])

  return (
    <div className="page-content">
      <h1 className="page-title">Cost Analysis</h1>
      <p className="page-subtitle">Breakdown of your AWS spending by service and over time</p>

      {/* Summary Row */}
      {summary && (
        <div className="summary-cards" style={{ marginBottom: 'var(--space-xl)' }}>
          {[
            { label: 'Total Monthly', value: `$${summary.total_monthly_cost_usd.toFixed(2)}` },
            { label: 'Total Resources', value: summary.total_resources },
            { label: 'Idle Resources', value: summary.idle_resources },
            { label: 'Potential Savings', value: `$${summary.potential_savings_usd.toFixed(2)}/mo` },
          ].map(({ label, value }) => (
            <div key={label} className="summary-card">
              <div className="card-label">{label}</div>
              <div className="card-value" style={{ fontSize: 22 }}>{value}</div>
            </div>
          ))}
        </div>
      )}

      <div className="grid-2">
        {/* Cost by Service Bar Chart */}
        <div className="card">
          <div className="section-header">
            <span className="section-title">
              <DollarSign size={16} className="icon" />
              Monthly Cost by Service
            </span>
          </div>
          {byService.length > 0 ? (
            <ResponsiveContainer width="100%" height={240}>
              <BarChart data={byService} margin={{ top: 5, right: 10, left: 0, bottom: 5 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" />
                <XAxis dataKey="service" tick={{ fill: '#64748b', fontSize: 12 }} />
                <YAxis tick={{ fill: '#64748b', fontSize: 11 }} tickFormatter={v => `$${v}`} width={50} />
                <Tooltip
                  formatter={v => [`$${v.toFixed(2)}`, 'Monthly Cost']}
                  contentStyle={TooltipStyle}
                />
                <Bar dataKey="total_cost_usd" radius={[6, 6, 0, 0]}>
                  {byService.map(entry => (
                    <Cell key={entry.service} fill={SERVICE_COLORS[entry.service] || '#6366f1'} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          ) : (
            <div className="empty-state"><p>No data</p></div>
          )}
        </div>

        {/* Daily Cost Trend with range selector */}
        <div className="card">
          <div className="section-header">
            <span className="section-title">
              <TrendingUp size={16} className="icon" />
              Daily Spending Trend
            </span>
            <select
              className="filter-select"
              value={trendDays}
              onChange={e => setTrendDays(Number(e.target.value))}
            >
              <option value={7}>7 days</option>
              <option value={14}>14 days</option>
              <option value={30}>30 days</option>
              <option value={60}>60 days</option>
              <option value={90}>90 days</option>
            </select>
          </div>
          {trend.length > 0 ? (
            <ResponsiveContainer width="100%" height={240}>
              <LineChart data={trend} margin={{ top: 5, right: 10, left: 0, bottom: 5 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" />
                <XAxis
                  dataKey="date"
                  tick={{ fill: '#64748b', fontSize: 10 }}
                  tickFormatter={v => v.slice(5)}
                  interval="preserveStartEnd"
                />
                <YAxis
                  tick={{ fill: '#64748b', fontSize: 10 }}
                  tickFormatter={v => `$${v.toFixed(3)}`}
                  width={60}
                />
                <Tooltip
                  formatter={v => [`$${v.toFixed(4)}`, 'Daily Cost']}
                  contentStyle={TooltipStyle}
                />
                <Line
                  type="monotone" dataKey="cost"
                  stroke="url(#costGradient)" strokeWidth={2.5}
                  dot={false} activeDot={{ r: 4, fill: '#6366f1' }}
                />
                <defs>
                  <linearGradient id="costGradient" x1="0" y1="0" x2="1" y2="0">
                    <stop offset="0%"   stopColor="#6366f1" />
                    <stop offset="100%" stopColor="#8b5cf6" />
                  </linearGradient>
                </defs>
              </LineChart>
            </ResponsiveContainer>
          ) : (
            <div className="empty-state">
              <p>No trend data yet — comes from daily cost snapshots.</p>
            </div>
          )}
        </div>
      </div>

      {/* Service breakdown table */}
      <div className="card" style={{ marginTop: 'var(--space-lg)' }}>
        <div className="section-header">
          <span className="section-title">Service Cost Breakdown</span>
        </div>
        <div className="data-table-wrap">
          <table className="data-table">
            <thead>
              <tr>
                <th>Service</th>
                <th>Resources</th>
                <th style={{ textAlign: 'right' }}>Monthly Cost</th>
                <th style={{ textAlign: 'right' }}>% of Total</th>
              </tr>
            </thead>
            <tbody>
              {byService.map(s => {
                const totalCost = byService.reduce((a, b) => a + b.total_cost_usd, 0)
                const pct = totalCost > 0 ? (s.total_cost_usd / totalCost * 100).toFixed(1) : '0.0'
                return (
                  <tr key={s.service}>
                    <td style={{ fontWeight: 600, color: SERVICE_COLORS[s.service] || '#6366f1' }}>
                      {s.service}
                    </td>
                    <td style={{ color: 'var(--text-secondary)' }}>{s.resource_count}</td>
                    <td style={{ textAlign: 'right', fontWeight: 700 }}>${s.total_cost_usd.toFixed(2)}</td>
                    <td style={{ textAlign: 'right', color: 'var(--text-muted)' }}>{pct}%</td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}
