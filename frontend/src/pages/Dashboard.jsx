// src/pages/Dashboard.jsx — Main dashboard with summary cards, charts, and tables
import { useState, useEffect } from 'react'
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, BarChart, Bar, Cell, PieChart, Pie, Legend
} from 'recharts'
import {
  DollarSign, Server, AlertTriangle, TrendingUp,
  Zap, Package, Database, Cloud
} from 'lucide-react'
import { costsAPI, resourcesAPI, recommendationsAPI } from '../api/client'

// ── Service colors ───────────────────────────────────────────────
const SERVICE_COLORS = {
  EC2: '#f97316', S3: '#22c55e', RDS: '#3b82f6', Lambda: '#a78bfa',
}

// ── Custom Tooltip ───────────────────────────────────────────────
const CustomTooltip = ({ active, payload, label }) => {
  if (active && payload?.length) {
    return (
      <div style={{
        background: 'rgba(13,20,39,0.95)', border: '1px solid rgba(255,255,255,0.1)',
        borderRadius: 8, padding: '10px 14px', fontSize: 12,
      }}>
        <p style={{ color: '#94a3b8', marginBottom: 4 }}>{label}</p>
        <p style={{ color: '#6366f1', fontWeight: 700 }}>
          ${(payload[0]?.value || 0).toFixed(4)}/day
        </p>
      </div>
    )
  }
  return null
}

// ── Summary Card ─────────────────────────────────────────────────
function SummaryCard({ icon: Icon, label, value, sub, color, gradient }) {
  return (
    <div className="summary-card animate-in">
      <div className="card-icon" style={{ background: gradient || 'rgba(99,102,241,0.15)' }}>
        <Icon size={20} color={color || '#6366f1'} />
      </div>
      <div className="card-label">{label}</div>
      <div className="card-value">{value}</div>
      {sub && <div className="card-sub">{sub}</div>}
    </div>
  )
}

export default function Dashboard() {
  const [summary,   setSummary]   = useState(null)
  const [trend,     setTrend]     = useState([])
  const [byService, setByService] = useState([])
  const [topRes,    setTopRes]    = useState([])
  const [recSummary,setRecSummary]= useState(null)
  const [loading,   setLoading]   = useState(true)

  const loadData = async () => {
    setLoading(true)
    try {
      const [s, t, bs, tr, rs] = await Promise.all([
        costsAPI.summary(),
        costsAPI.trend(30),
        costsAPI.byService(),
        costsAPI.topResources(6),
        recommendationsAPI.summary(),
      ])
      setSummary(s.data)
      setTrend(t.data.trend || [])
      setByService(bs.data)
      setTopRes(tr.data)
      setRecSummary(rs.data)
    } catch (e) {
      console.error('Dashboard load error:', e)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { loadData() }, [])

  if (loading) {
    return (
      <div className="page-content">
        <div className="spinner-wrap" style={{ marginTop: 80 }}>
          <div className="spinner" />
          <span>Loading dashboard…</span>
        </div>
      </div>
    )
  }

  return (
    <div className="page-content">
      <h1 className="page-title">Cloud Cost Overview</h1>
      <p className="page-subtitle">Real-time AWS resource usage and cost estimates</p>

      {/* ── Summary Cards ──────────────────────────────────────── */}
      <div className="summary-cards">
        <SummaryCard
          icon={DollarSign}
          label="Est. Monthly Cost"
          value={`$${(summary?.total_monthly_cost_usd || 0).toFixed(2)}`}
          sub="Based on current usage"
          color="#6366f1"
          gradient="rgba(99,102,241,0.15)"
        />
        <SummaryCard
          icon={Server}
          label="Total Resources"
          value={summary?.total_resources || 0}
          sub={`${summary?.idle_resources || 0} idle`}
          color="#06b6d4"
          gradient="rgba(6,182,212,0.12)"
        />
        <SummaryCard
          icon={TrendingUp}
          label="Potential Savings"
          value={`$${(summary?.potential_savings_usd || 0).toFixed(2)}/mo`}
          sub="From idle resources"
          color="#10b981"
          gradient="rgba(16,185,129,0.12)"
        />
        <SummaryCard
          icon={AlertTriangle}
          label="Recommendations"
          value={recSummary?.total_recommendations || 0}
          sub={`$${(recSummary?.total_potential_savings_usd || 0).toFixed(2)} savings possible`}
          color="#f59e0b"
          gradient="rgba(245,158,11,0.12)"
        />
      </div>

      {/* ── Cost Trend + Service Breakdown ─────────────────────── */}
      <div className="grid-2" style={{ marginBottom: 'var(--space-lg)' }}>
        {/* Cost Trend Line Chart */}
        <div className="card">
          <div className="section-header">
            <span className="section-title">
              <TrendingUp size={16} className="icon" />
              Daily Cost Trend (30 days)
            </span>
          </div>
          {trend.length > 0 ? (
            <ResponsiveContainer width="100%" height={220}>
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
                  tickFormatter={v => `$${v.toFixed(2)}`}
                  width={55}
                />
                <Tooltip content={<CustomTooltip />} />
                <Line
                  type="monotone" dataKey="cost"
                  stroke="#6366f1" strokeWidth={2.5}
                  dot={false} activeDot={{ r: 5, fill: '#6366f1' }}
                />
              </LineChart>
            </ResponsiveContainer>
          ) : (
            <div className="empty-state">
              <TrendingUp size={32} color="var(--text-muted)" />
              <p>No trend data yet. Data builds up over time.</p>
            </div>
          )}
        </div>

        {/* Cost by Service Pie Chart */}
        <div className="card">
          <div className="section-header">
            <span className="section-title">
              <Package size={16} className="icon" />
              Cost by Service
            </span>
          </div>
          {byService.length > 0 ? (
            <ResponsiveContainer width="100%" height={220}>
              <PieChart>
                <Pie
                  data={byService}
                  dataKey="total_cost_usd"
                  nameKey="service"
                  cx="50%" cy="50%"
                  outerRadius={80}
                  label={({ service, percent }) =>
                    `${service} ${(percent * 100).toFixed(0)}%`
                  }
                  labelLine={false}
                >
                  {byService.map((entry) => (
                    <Cell
                      key={entry.service}
                      fill={SERVICE_COLORS[entry.service] || '#6366f1'}
                    />
                  ))}
                </Pie>
                <Tooltip
                  formatter={(v) => [`$${v.toFixed(2)}`, 'Monthly Cost']}
                  contentStyle={{
                    background: 'rgba(13,20,39,0.95)',
                    border: '1px solid rgba(255,255,255,0.1)',
                    borderRadius: 8, fontSize: 12,
                  }}
                />
                <Legend
                  iconType="circle"
                  iconSize={8}
                  formatter={(v) => <span style={{ color: '#94a3b8', fontSize: 12 }}>{v}</span>}
                />
              </PieChart>
            </ResponsiveContainer>
          ) : (
            <div className="empty-state">
              <Package size={32} color="var(--text-muted)" />
              <p>No cost data available.</p>
            </div>
          )}
        </div>
      </div>

      {/* ── Top Resources Table ─────────────────────────────────── */}
      <div className="card">
        <div className="section-header">
          <span className="section-title">
            <Zap size={16} className="icon" />
            Top Resources by Cost
          </span>
        </div>
        <div className="data-table-wrap">
          <table className="data-table">
            <thead>
              <tr>
                <th>Resource</th>
                <th>Service</th>
                <th>Type</th>
                <th>Region</th>
                <th>Status</th>
                <th style={{ textAlign: 'right' }}>Monthly Cost</th>
              </tr>
            </thead>
            <tbody>
              {topRes.length === 0 ? (
                <tr><td colSpan={6} style={{ textAlign: 'center', padding: 32, color: 'var(--text-muted)' }}>No data</td></tr>
              ) : topRes.map((r) => (
                <tr key={r.resource_id}>
                  <td className="resource-name" title={r.resource_name}>{r.resource_name}</td>
                  <td>
                    <span style={{ color: SERVICE_COLORS[r.service_type] || '#6366f1', fontWeight: 600 }}>
                      {r.service_type}
                    </span>
                  </td>
                  <td style={{ color: 'var(--text-muted)' }}>{r.resource_type || '—'}</td>
                  <td style={{ color: 'var(--text-muted)' }}>{r.region}</td>
                  <td>
                    <span className={`badge badge-${r.status}`}>{r.status}</span>
                  </td>
                  <td style={{ textAlign: 'right', fontWeight: 700, color: 'var(--text-primary)' }}>
                    ${r.monthly_cost.toFixed(2)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}
