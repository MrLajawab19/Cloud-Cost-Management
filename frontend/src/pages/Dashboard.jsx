// src/pages/Dashboard.jsx
import { useState, useEffect } from 'react'
import {
  AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip as RechartsTooltip,
  ResponsiveContainer, PieChart, Pie, Cell, Legend
} from 'recharts'
import { DollarSign, Server, AlertTriangle, TrendingUp, Cpu, HardDrive, ShieldAlert, CheckCircle } from 'lucide-react'
import { costsAPI, recommendationsAPI } from '../api/client'

const SERVICE_COLORS = {
  EC2: '#ec7211', S3: '#1d8102', RDS: '#0073bb', Lambda: '#6366f1',
}

const CustomTooltip = ({ active, payload, label }) => {
  if (active && payload && payload.length) {
    return (
      <div className="chart-tooltip">
        <div className="chart-tooltip-label">{label || payload[0].name}</div>
        <div className="chart-tooltip-value">
          ${Number(payload[0].value).toFixed(2)}
        </div>
      </div>
    );
  }
  return null;
}

export default function Dashboard() {
  const [loading, setLoading] = useState(true)
  const [data, setData] = useState({
    summary: null,
    trend: [],
    byService: [],
    topResources: [],
    recsSummary: null,
    recList: []
  })

  useEffect(() => {
    async function load() {
      try {
        const [sum, tr, bs, top, recSum, rList] = await Promise.all([
          costsAPI.summary(),
          costsAPI.trend(30),
          costsAPI.byService(),
          costsAPI.topResources(5),
          recommendationsAPI.summary(),
          recommendationsAPI.list()
        ])
        setData({
          summary: sum.data,
          trend: tr.data.trend || [],
          byService: bs.data,
          topResources: top.data,
          recsSummary: recSum.data,
          recList: rList.data || []
        })
      } catch (e) {
        console.error(e)
      } finally {
        setLoading(false)
      }
    }
    load()
  }, [])

  if (loading) {
    return (
      <div className="page-content">
        <div className="page-title" style={{ marginBottom: 'var(--s-4)' }}>Overview</div>
        <div style={{ color: 'var(--text-2)' }}>Gathering metrics...</div>
      </div>
    )
  }

  const { summary, trend, byService, topResources, recsSummary, recList } = data
  const highPriorityCount = (recsSummary?.by_severity?.critical || 0) + (recsSummary?.by_severity?.high || 0)

  return (
    <div className="page-content">
      <div className="page-header">
        <div className="page-title">Overview</div>
        <div className="page-subtitle">Real-time AWS resource usage and cost estimates</div>
      </div>
      
      {/* Metric Cards - 6 columns to fill space */}
      <div className="metric-grid">
        <div className="metric-card">
          <div className="metric-top">
            <div className="metric-label">Est. Monthly Cost</div>
            <div className="metric-trend up">Live</div>
          </div>
          <div className="metric-value">${summary?.total_monthly_cost_usd?.toFixed(2) || '0.00'}</div>
          <div className="metric-sub">Based on current usage</div>
        </div>

        <div className="metric-card">
          <div className="metric-top">
            <div className="metric-label">Total Resources</div>
          </div>
          <div className="metric-value" style={{ color: 'var(--brand-aws-blue)' }}>{summary?.resource_count || 0}</div>
          <div className="metric-sub">{summary?.idle_resources || 0} idle</div>
        </div>

        <div className="metric-card">
          <div className="metric-top">
            <div className="metric-label">Potential Savings</div>
          </div>
          <div className="metric-value" style={{ color: 'var(--color-success)' }}>${recsSummary?.total_potential_savings_usd?.toFixed(2) || '0.00'}</div>
          <div className="metric-sub">From idle resources</div>
        </div>

        <div className="metric-card">
          <div className="metric-top">
            <div className="metric-label">Recommendations</div>
          </div>
          <div className="metric-value" style={{ color: 'var(--text-1)' }}>{recsSummary?.total_recommendations || 0}</div>
          <div className="metric-sub">{recsSummary?.by_severity?.high || 0} high priority</div>
        </div>

        <div className="metric-card">
          <div className="metric-top">
            <div className="metric-label">Monitored Services</div>
          </div>
          <div className="metric-value" style={{ color: 'var(--text-1)' }}>{byService.length}</div>
          <div className="metric-sub">Across all regions</div>
        </div>

        <div className="metric-card">
          <div className="metric-top">
            <div className="metric-label">Critical Issues</div>
          </div>
          <div className="metric-value" style={{ color: highPriorityCount > 0 ? 'var(--color-danger)' : 'var(--color-success)' }}>
            {highPriorityCount}
          </div>
          <div className="metric-sub">{highPriorityCount > 0 ? 'Requires attention' : 'All clear'}</div>
        </div>
      </div>

      {/* Charts */}
      <div className="grid-2">
        {/* Trend Chart */}
        <div className="card">
          <div className="card-header">
            <div className="card-title">Daily Cost Trend (30 Days)</div>
          </div>
          <div style={{ height: 200 }}>
            {trend.length > 0 ? (
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={trend} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
                  <defs>
                    <linearGradient id="trendGrad" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="var(--brand-aws-blue)" stopOpacity={0.2}/>
                      <stop offset="95%" stopColor="var(--brand-aws-blue)" stopOpacity={0}/>
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="var(--glass-border)" />
                  <XAxis dataKey="date" axisLine={false} tickLine={false} tick={{ fontSize: 11, fill: 'var(--text-3)' }} dy={10} />
                  <YAxis axisLine={false} tickLine={false} tick={{ fontSize: 11, fill: 'var(--text-3)' }} dx={-10} tickFormatter={(v) => `$${v}`} />
                  <RechartsTooltip content={<CustomTooltip />} />
                  <Area type="monotone" dataKey="total_cost_usd" stroke="var(--brand-aws-blue)" strokeWidth={2} fillOpacity={1} fill="url(#trendGrad)" />
                </AreaChart>
              </ResponsiveContainer>
            ) : (
              <div className="empty-state">
                <div className="empty-sub">Gathering trend data... (requires multiple days of history)</div>
              </div>
            )}
          </div>
        </div>

        {/* Pie Chart */}
        <div className="card">
          <div className="card-header">
            <div className="card-title">Cost by Service</div>
          </div>
          <div style={{ height: 200 }}>
            {byService.length > 0 ? (
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie
                    data={byService}
                    dataKey="total_cost_usd"
                    nameKey="service"
                    cx="50%"
                    cy="45%"
                    innerRadius={60}
                    outerRadius={85}
                    paddingAngle={2}
                    stroke="none"
                  >
                    {byService.map((entry, index) => (
                      <Cell key={`cell-${index}`} fill={SERVICE_COLORS[entry.service] || 'var(--brand-aws-blue)'} />
                    ))}
                  </Pie>
                  <RechartsTooltip content={<CustomTooltip />} />
                  <Legend wrapperStyle={{ fontSize: '11px', color: 'var(--text-2)' }} iconType="circle" iconSize={8} />
                </PieChart>
              </ResponsiveContainer>
            ) : (
              <div className="empty-state">
                <div className="empty-sub">No service data available.</div>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Bottom Section: Top Resources (Left) and Action Items (Right) */}
      <div className="grid-2-1">
        {/* Top Resources Table */}
        <div className="card" style={{ padding: 0 }}>
          <div className="card-header" style={{ padding: 'var(--s-5) var(--s-5) 0', borderBottom: 'none' }}>
            <div className="card-title">Top Resources by Cost</div>
          </div>
          <div className="table-wrap" style={{ border: 'none', borderTop: '1px solid var(--glass-border)', borderRadius: 0 }}>
            <table className="data-table">
              <thead>
                <tr>
                  <th>Resource Name</th>
                  <th>Service</th>
                  <th>Region</th>
                  <th>Status</th>
                  <th style={{ textAlign: 'right' }}>Cost</th>
                </tr>
              </thead>
              <tbody>
                {topResources.length > 0 ? topResources.slice(0, 5).map(r => (
                  <tr key={r.resource_id}>
                    <td className="td-primary">
                      <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
                        <span>{r.resource_name || r.resource_id}</span>
                        <span className="td-mono">{r.resource_id}</span>
                      </div>
                    </td>
                    <td><span className={`chip chip-${r.service_type.toLowerCase()}`}>{r.service_type}</span></td>
                    <td>{r.region}</td>
                    <td><span className={`badge badge-${r.status.toLowerCase()}`}>{r.status}</span></td>
                    <td style={{ textAlign: 'right', fontWeight: 700 }}>
                      ${(r.estimated_monthly_cost || 0).toFixed(2)}
                    </td>
                  </tr>
                )) : (
                  <tr>
                    <td colSpan={5} style={{ textAlign: 'center', padding: 'var(--s-6)' }}>
                      <div className="empty-sub">No resources tracked yet.</div>
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>

        {/* Action Items List */}
        <div className="card">
          <div className="card-header">
            <div className="card-title">Action Items</div>
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--s-3)' }}>
            {recList.length > 0 ? recList.slice(0, 4).map(r => (
              <div key={r.id} style={{ display: 'flex', alignItems: 'flex-start', gap: '10px', borderBottom: '1px solid var(--glass-border)', paddingBottom: '12px' }}>
                <ShieldAlert size={16} color={r.severity === 'critical' || r.severity === 'high' ? 'var(--color-danger)' : 'var(--color-warning)'} style={{ marginTop: 2 }} />
                <div style={{ flex: 1 }}>
                  <div style={{ fontSize: '13px', fontWeight: 700, color: 'var(--brand-aws-blue)', marginBottom: 2 }}>{r.issue}</div>
                  <div style={{ fontSize: '12px', color: 'var(--text-2)' }}>{r.resource_name || r.resource_id}</div>
                </div>
                <div style={{ fontSize: '13px', fontWeight: 700, color: 'var(--color-success)' }}>
                  +${r.potential_savings_usd.toFixed(2)}
                </div>
              </div>
            )) : (
              <div className="empty-state" style={{ padding: '20px' }}>
                <CheckCircle size={32} color="var(--color-success)" style={{ marginBottom: 10 }} />
                <div className="empty-sub">No action items required. Your infrastructure is optimized!</div>
              </div>
            )}
          </div>
        </div>
      </div>

    </div>
  )
}
