// src/pages/Costs.jsx — Detailed cost analysis page
import { useState, useEffect } from 'react'
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip as RechartsTooltip,
  ResponsiveContainer, LineChart, Line, Cell
} from 'recharts'
import { DollarSign, TrendingUp, Calendar, Filter } from 'lucide-react'
import { costsAPI } from '../api/client'

const SERVICE_COLORS = {
  EC2: '#f97316', S3: '#22c55e', RDS: '#3b82f6', Lambda: '#a78bfa',
}

const CustomTooltip = ({ active, payload, label }) => {
  if (active && payload && payload.length) {
    return (
      <div className="chart-tooltip">
        <div className="chart-tooltip-label">{label}</div>
        <div className="chart-tooltip-value">
          ${Number(payload[0].value).toFixed(2)}
        </div>
      </div>
    );
  }
  return null;
}

export default function Costs() {
  const [summary,   setSummary]   = useState(null)
  const [trend,     setTrend]     = useState([])
  const [byService, setByService] = useState([])
  const [trendDays, setTrendDays] = useState(30)
  const [loading,   setLoading]   = useState(true)

  useEffect(() => {
    async function load() {
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
      } catch (e) {
        console.error(e)
      } finally {
        setLoading(false)
      }
    }
    load()
  }, [trendDays])

  if (loading) {
    return (
      <div className="page-content">
        <div className="loading-wrap">
          <div className="spinner" />
          <div className="loading-text">Analyzing costs…</div>
        </div>
      </div>
    )
  }

  return (
    <div className="page-content animate-up">
      {/* Summary Row */}
      {summary && (
        <div className="metric-grid">
          {[
            { label: 'Total Monthly', value: `$${summary.total_monthly_cost_usd.toFixed(2)}`, sub: 'Current run rate', trend: 'up' },
            { label: 'Total Resources', value: summary.total_resources, sub: 'Tracked assets', trend: 'neutral' },
            { label: 'Idle Resources', value: summary.idle_resources, sub: 'Action required', trend: 'down' },
            { label: 'Potential Savings', value: `$${summary.potential_savings_usd.toFixed(2)}`, sub: 'Per month', trend: 'up' },
          ].map(({ label, value, sub, trend }, i) => (
            <div key={label} className={`metric-card stagger-${i+1}`}>
              <div className="metric-label">{label}</div>
              <div className="metric-value">{value}</div>
              <div className="metric-sub">
                <span className={`metric-trend ${trend}`} style={{ width: 6, height: 6, padding: 0, display: 'inline-block' }} />
                {sub}
              </div>
            </div>
          ))}
        </div>
      )}

      <div className="grid-2">
        {/* Cost by Service Bar Chart */}
        <div className="card stagger-2">
          <div className="card-header">
            <div className="card-title">
              <div className="card-title-icon"><DollarSign size={16} /></div>
              Monthly Cost by Service
            </div>
          </div>
          <div style={{ height: 200 }}>
            {byService.length > 0 ? (
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={byService} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" vertical={false} />
                  <XAxis dataKey="service" tick={{ fill: '#64748b', fontSize: 11 }} axisLine={false} tickLine={false} dy={10} />
                  <YAxis tick={{ fill: '#64748b', fontSize: 11 }} tickFormatter={v => `$${v}`} axisLine={false} tickLine={false} />
                  <RechartsTooltip content={<CustomTooltip />} cursor={{ fill: 'rgba(255,255,255,0.03)' }} />
                  <Bar dataKey="total_cost_usd" radius={[6, 6, 0, 0]}>
                    {byService.map(entry => (
                      <Cell key={entry.service} fill={SERVICE_COLORS[entry.service] || '#6366f1'} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            ) : (
              <div className="empty-state">
                <div className="empty-sub">No service data available.</div>
              </div>
            )}
          </div>
        </div>

        {/* Daily Cost Trend */}
        <div className="card stagger-3">
          <div className="card-header">
            <div className="card-title">
              <div className="card-title-icon" style={{ background: 'rgba(16,185,129,0.12)', color: '#34d399' }}>
                <TrendingUp size={16} />
              </div>
              Daily Spending Trend
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--s-2)', background: 'rgba(255,255,255,0.03)', padding: '4px 6px', borderRadius: 'var(--r-sm)' }}>
              <Calendar size={13} color="var(--text-3)" />
              <select
                style={{ background: 'transparent', border: 'none', color: 'var(--text-1)', fontSize: 12, outline: 'none', cursor: 'pointer' }}
                value={trendDays}
                onChange={e => setTrendDays(Number(e.target.value))}
              >
                <option value={7}>Last 7 days</option>
                <option value={14}>Last 14 days</option>
                <option value={30}>Last 30 days</option>
                <option value={60}>Last 60 days</option>
                <option value={90}>Last 90 days</option>
              </select>
            </div>
          </div>
          <div style={{ height: 200 }}>
            {trend.length > 0 ? (
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={trend} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" vertical={false} />
                  <XAxis
                    dataKey="date"
                    tick={{ fill: '#64748b', fontSize: 11 }}
                    tickFormatter={v => v.slice(5)}
                    axisLine={false}
                    tickLine={false}
                    dy={10}
                  />
                  <YAxis
                    tick={{ fill: '#64748b', fontSize: 11 }}
                    tickFormatter={v => `$${v.toFixed(2)}`}
                    axisLine={false}
                    tickLine={false}
                  />
                  <RechartsTooltip content={<CustomTooltip />} />
                  <Line
                    type="monotone" dataKey="cost"
                    stroke="url(#costGradient)" strokeWidth={3}
                    dot={false} activeDot={{ r: 5, fill: '#6366f1', stroke: '#080d1a', strokeWidth: 2 }}
                  />
                  <defs>
                    <linearGradient id="costGradient" x1="0" y1="0" x2="1" y2="0">
                      <stop offset="0%"   stopColor="#6366f1" />
                      <stop offset="100%" stopColor="#ec4899" />
                    </linearGradient>
                  </defs>
                </LineChart>
              </ResponsiveContainer>
            ) : (
              <div className="empty-state">
                <div className="empty-sub">Gathering trend data...</div>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Service Breakdown Table */}
      <div className="card stagger-4" style={{ padding: 0 }}>
        <div className="card-header" style={{ padding: 'var(--s-6) var(--s-6) 0' }}>
          <div className="card-title">
            <div className="card-title-icon" style={{ background: 'rgba(34,197,94,0.12)', color: '#4ade80' }}><Filter size={16} /></div>
            Service Cost Breakdown
          </div>
        </div>
        <div className="table-wrap" style={{ marginTop: 'var(--s-4)' }}>
          <table className="data-table">
            <thead>
              <tr>
                <th>Service</th>
                <th>Resource Count</th>
                <th style={{ textAlign: 'right' }}>Monthly Cost</th>
                <th style={{ textAlign: 'right' }}>% of Total Spend</th>
              </tr>
            </thead>
            <tbody>
              {byService.map((s, i) => {
                const totalCost = byService.reduce((a, b) => a + b.total_cost_usd, 0)
                const pct = totalCost > 0 ? (s.total_cost_usd / totalCost * 100) : 0
                return (
                  <tr key={s.service}>
                    <td>
                      <span className={`chip chip-${s.service.toLowerCase()}`}>
                        {s.service}
                      </span>
                    </td>
                    <td>{s.resource_count}</td>
                    <td style={{ textAlign: 'right', fontWeight: 700, color: 'var(--text-1)' }}>
                      ${s.total_cost_usd.toFixed(2)}
                    </td>
                    <td style={{ width: 250, paddingRight: 'var(--s-6)' }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--s-3)', justifyContent: 'flex-end' }}>
                        <span style={{ fontSize: 12, color: 'var(--text-3)', width: 40, textAlign: 'right' }}>{pct.toFixed(1)}%</span>
                        <div style={{ width: 100, height: 4, background: 'var(--glass-bg-h)', borderRadius: 2, overflow: 'hidden' }}>
                          <div style={{ width: `${pct}%`, height: '100%', background: SERVICE_COLORS[s.service] || '#6366f1' }} />
                        </div>
                      </div>
                    </td>
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
