// src/pages/Dashboard.jsx — Hero dashboard
import { useState, useEffect } from 'react'
import {
  AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip as RechartsTooltip,
  ResponsiveContainer, PieChart, Pie, Cell, Legend
} from 'recharts'
import { DollarSign, Server, AlertTriangle, TrendingUp, Cpu, HardDrive } from 'lucide-react'
import { costsAPI, resourcesAPI, recommendationsAPI } from '../api/client'

const SERVICE_COLORS = {
  EC2: '#f97316', S3: '#22c55e', RDS: '#3b82f6', Lambda: '#a78bfa',
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
    recs: null
  })

  useEffect(() => {
    async function load() {
      try {
        const [sum, tr, bs, top, rec] = await Promise.all([
          costsAPI.summary(),
          costsAPI.trend(30),
          costsAPI.byService(),
          costsAPI.topResources(),
          recommendationsAPI.summary()
        ])
        setData({
          summary: sum.data,
          trend: tr.data.trend || [],
          byService: bs.data,
          topResources: top.data,
          recs: rec.data
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
        <div className="loading-wrap">
          <div className="spinner" />
          <div className="loading-text">Analyzing cloud metrics…</div>
        </div>
      </div>
    )
  }

  const { summary, trend, byService, topResources, recs } = data

  return (
    <div className="page-content">
      {/* Page Header is omitted since TopBar handles titles, but we can keep an optional intro or just go straight to content */}
      
      {/* Metric Cards */}
      <div className="metric-grid">
        <div className="metric-card animate-up stagger-1">
          <div className="metric-card-glow" style={{ background: 'var(--brand-violet)' }} />
          <div className="metric-top">
            <div className="metric-icon" style={{ background: 'rgba(124,58,237,0.12)', color: '#a78bfa' }}>
              <DollarSign size={20} />
            </div>
            <div className="metric-trend up">Live</div>
          </div>
          <div className="metric-label">Est. Monthly Cost</div>
          <div className="metric-value">${summary?.total_monthly_cost_usd?.toFixed(2) || '0.00'}</div>
          <div className="metric-sub">Based on current usage</div>
        </div>

        <div className="metric-card animate-up stagger-2">
          <div className="metric-card-glow" style={{ background: 'var(--brand-blue)' }} />
          <div className="metric-top">
            <div className="metric-icon" style={{ background: 'rgba(59,130,246,0.12)', color: '#60a5fa' }}>
              <Server size={20} />
            </div>
          </div>
          <div className="metric-label">Total Resources</div>
          <div className="metric-value">{summary?.total_resources || 0}</div>
          <div className="metric-sub">{summary?.idle_resources || 0} idle</div>
        </div>

        <div className="metric-card animate-up stagger-3">
          <div className="metric-card-glow" style={{ background: 'var(--color-success)' }} />
          <div className="metric-top">
            <div className="metric-icon" style={{ background: 'rgba(16,185,129,0.12)', color: '#34d399' }}>
              <TrendingUp size={20} />
            </div>
            {summary?.potential_savings_usd > 0 && (
              <div className="metric-trend up">+{(summary.potential_savings_usd / summary.total_monthly_cost_usd * 100).toFixed(1)}% possible</div>
            )}
          </div>
          <div className="metric-label">Potential Savings</div>
          <div className="metric-value" style={{ color: '#34d399' }}>
            ${summary?.potential_savings_usd?.toFixed(2) || '0.00'}
          </div>
          <div className="metric-sub">From idle resources</div>
        </div>

        <div className="metric-card animate-up stagger-4">
          <div className="metric-card-glow" style={{ background: 'var(--color-warning)' }} />
          <div className="metric-top">
            <div className="metric-icon" style={{ background: 'rgba(245,158,11,0.12)', color: '#fbbf24' }}>
              <AlertTriangle size={20} />
            </div>
            {recs?.total_recommendations > 0 && (
              <div className="metric-trend down">{recs.by_severity?.high || 0} high priority</div>
            )}
          </div>
          <div className="metric-label">Recommendations</div>
          <div className="metric-value" style={{ color: '#fbbf24' }}>{recs?.total_recommendations || 0}</div>
          <div className="metric-sub">${recs?.total_potential_savings_usd?.toFixed(2) || '0.00'} savings possible</div>
        </div>
      </div>

      <div className="grid-2-1">
        {/* Trend Chart */}
        <div className="card animate-up stagger-2">
          <div className="card-header">
            <div className="card-title">
              <div className="card-title-icon"><TrendingUp size={16} /></div>
              Daily Cost Trend (30 Days)
            </div>
          </div>
          <div style={{ height: 260 }}>
            {trend.length > 0 ? (
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={trend} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
                  <defs>
                    <linearGradient id="trendGrad" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="#7c3aed" stopOpacity={0.3}/>
                      <stop offset="95%" stopColor="#7c3aed" stopOpacity={0}/>
                    </linearGradient>
                  </defs>
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
                    tickFormatter={v => `$${v}`}
                    axisLine={false}
                    tickLine={false}
                  />
                  <RechartsTooltip content={<CustomTooltip />} />
                  <Area 
                    type="monotone" 
                    dataKey="cost" 
                    stroke="#7c3aed" 
                    strokeWidth={3}
                    fillOpacity={1} 
                    fill="url(#trendGrad)" 
                  />
                </AreaChart>
              </ResponsiveContainer>
            ) : (
              <div className="empty-state" style={{ padding: '40px 20px' }}>
                <div className="empty-sub">Gathering trend data... (requires multiple days of history)</div>
              </div>
            )}
          </div>
        </div>

        {/* Pie Chart */}
        <div className="card animate-up stagger-3">
          <div className="card-header">
            <div className="card-title">
              <div className="card-title-icon" style={{ background: 'rgba(8,145,178,0.12)', color: '#0891b2' }}><Cpu size={16} /></div>
              Cost by Service
            </div>
          </div>
          <div style={{ height: 260 }}>
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
                    paddingAngle={3}
                    stroke="none"
                  >
                    {byService.map((entry, index) => (
                      <Cell key={`cell-${index}`} fill={SERVICE_COLORS[entry.service] || '#6366f1'} />
                    ))}
                  </Pie>
                  <RechartsTooltip content={<CustomTooltip />} />
                  <Legend 
                    wrapperStyle={{ fontSize: '11.5px', color: '#94a3b8' }} 
                    iconType="circle"
                    iconSize={8}
                  />
                </PieChart>
              </ResponsiveContainer>
            ) : (
              <div className="empty-state" style={{ padding: '40px 20px' }}>
                <div className="empty-sub">No service data available.</div>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Top Resources Table */}
      <div className="card animate-up stagger-4" style={{ padding: 0 }}>
        <div className="card-header" style={{ padding: 'var(--s-6) var(--s-6) 0' }}>
          <div className="card-title">
            <div className="card-title-icon" style={{ background: 'rgba(239,68,68,0.12)', color: '#ef4444' }}><HardDrive size={16} /></div>
            Top Resources by Cost
          </div>
        </div>
        <div className="table-wrap" style={{ marginTop: 'var(--s-4)' }}>
          <table className="data-table">
            <thead>
              <tr>
                <th>Resource Name</th>
                <th>Service</th>
                <th>Type</th>
                <th>Region</th>
                <th>Status</th>
                <th style={{ textAlign: 'right' }}>Monthly Cost</th>
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
                  <td>{r.resource_type || '—'}</td>
                  <td>{r.region}</td>
                  <td><span className={`badge badge-${r.status.toLowerCase()}`}><span className="badge-dot" />{r.status}</span></td>
                  <td style={{ textAlign: 'right', fontWeight: 700, color: 'var(--text-1)' }}>
                    ${(r.estimated_monthly_cost || 0).toFixed(2)}
                  </td>
                </tr>
              )) : (
                <tr>
                  <td colSpan={6} style={{ textAlign: 'center', padding: 'var(--s-10)' }}>
                    <div className="empty-sub" style={{ margin: '0 auto' }}>No resources tracked yet.</div>
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}
