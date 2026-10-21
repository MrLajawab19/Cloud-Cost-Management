// src/pages/Costs.jsx — Detailed cost analysis page
import { useState, useEffect } from 'react'
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip as RechartsTooltip,
  ResponsiveContainer, LineChart, Line, Cell
} from 'recharts'
import { DollarSign, TrendingUp, Calendar, Filter, ChevronDown, ChevronRight, AlertTriangle, Sparkles } from 'lucide-react'
import { costsAPI } from '../api/client'

const SERVICE_COLORS = {
  EC2: '#f97316', S3: '#22c55e', RDS: '#3b82f6', Lambda: '#a78bfa', AzureVM: '#0078d4'
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
  const [summary,     setSummary]     = useState(null)
  const [trend,       setTrend]       = useState([])
  const [byService,   setByService]   = useState([])
  const [explainData, setExplainData] = useState(null)
  const [expanded,    setExpanded]    = useState({})
  const [trendDays,   setTrendDays]   = useState(30)
  const [loading,     setLoading]     = useState(true)

  useEffect(() => {
    async function load() {
      setLoading(true)
      try {
        const [s, t, bs, ex] = await Promise.all([
          costsAPI.summary(),
          costsAPI.trend(trendDays),
          costsAPI.byService(),
          costsAPI.explain().catch(() => ({ data: { services: [] } })),
        ])
        setSummary(s.data)
        setTrend(t.data.trend || [])
        setByService(bs.data || [])
        setExplainData(ex.data)
      } catch (e) {
        console.error(e)
      } finally {
        setLoading(false)
      }
    }
    load()
  }, [trendDays])

  const toggleExpand = (srv) => {
    setExpanded(prev => ({ ...prev, [srv]: !prev[srv] }))
  }

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
            { label: 'Total Monthly', value: summary.total_monthly_cost_usd != null && !isNaN(summary.total_monthly_cost_usd) ? `$${summary.total_monthly_cost_usd.toFixed(2)}` : 'Cost unavailable', sub: 'Current run rate', trend: 'up' },
            { label: 'Total Resources', value: summary.total_resources, sub: 'Tracked assets', trend: 'neutral' },
            { label: 'Idle Resources', value: summary.idle_resources, sub: 'Action required', trend: 'down' },
            { label: 'Potential Savings', value: summary.potential_savings_usd != null && !isNaN(summary.potential_savings_usd) ? `$${summary.potential_savings_usd.toFixed(2)}` : 'Cost unavailable', sub: 'Per month', trend: 'up' },
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
                  <CartesianGrid strokeDasharray="3 3" stroke="var(--border-subtle)" vertical={false} />
                  <XAxis dataKey="service" tick={{ fill: 'var(--text-3)', fontSize: 11 }} axisLine={false} tickLine={false} />
                  <YAxis tick={{ fill: 'var(--text-3)', fontSize: 11 }} axisLine={false} tickLine={false} tickFormatter={v => `$${v}`} />
                  <RechartsTooltip content={<CustomTooltip />} />
                  <Bar dataKey="total_cost_usd" radius={[4, 4, 0, 0]}>
                    {byService.map(entry => (
                      <Cell key={entry.service} fill={SERVICE_COLORS[entry.service] || '#6366f1'} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            ) : (
              <div className="empty-state">
                <div className="empty-sub">No service data available</div>
              </div>
            )}
          </div>
        </div>

        {/* Daily Trend Line Chart */}
        <div className="card stagger-3">
          <div className="card-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <div className="card-title">
              <div className="card-title-icon"><TrendingUp size={16} /></div>
              Daily Cost Trend
            </div>
            <div className="filter-group" style={{ margin: 0 }}>
              <Calendar size={13} color="var(--text-3)" />
              <select
                className="select-input"
                style={{ padding: '2px 8px', fontSize: 12 }}
                value={trendDays}
                onChange={e => setTrendDays(Number(e.target.value))}
              >
                <option value={7}>7 Days</option>
                <option value={14}>14 Days</option>
                <option value={30}>30 Days</option>
                <option value={90}>90 Days</option>
              </select>
            </div>
          </div>
          <div style={{ height: 200 }}>
            {trend.length > 0 ? (
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={trend} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="var(--border-subtle)" vertical={false} />
                  <XAxis dataKey="date" tick={{ fill: 'var(--text-3)', fontSize: 10 }} axisLine={false} tickLine={false} />
                  <YAxis tick={{ fill: 'var(--text-3)', fontSize: 11 }} axisLine={false} tickLine={false} tickFormatter={v => `$${v}`} />
                  <RechartsTooltip content={<CustomTooltip />} />
                  <Line
                    type="monotone"
                    dataKey="cost"
                    stroke="#6366f1"
                    strokeWidth={2}
                    dot={{ fill: '#6366f1', r: 2 }}
                    activeDot={{ r: 4 }}
                  />
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
              {byService.map((s) => {
                const totalCost = byService.reduce((a, b) => a + (b.total_cost_usd || 0), 0)
                const pct = totalCost > 0 ? ((s.total_cost_usd || 0) / totalCost * 100) : 0
                return (
                  <tr key={s.service}>
                    <td>
                      <span className={`chip chip-${s.service.toLowerCase()}`}>
                        {s.service}
                      </span>
                    </td>
                    <td>{s.resource_count}</td>
                    <td style={{ textAlign: 'right', fontWeight: 700, color: 'var(--text-1)' }}>
                      {s.total_cost_usd != null && !isNaN(s.total_cost_usd) ? `$${s.total_cost_usd.toFixed(2)}` : 'Cost unavailable'}
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

      {/* Explainable Forecasting (Item C) */}
      <div className="card stagger-4" style={{ marginTop: 'var(--s-6)', padding: 'var(--s-6)' }}>
        <div style={{ marginBottom: 'var(--s-4)' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--s-2)' }}>
            <h2 style={{ fontSize: '18px', fontWeight: 700, margin: 0, color: 'var(--text-1)' }}>
              Explainable Forecasting
            </h2>
          </div>
          <p style={{ color: 'var(--text-3)', fontSize: '13px', margin: '4px 0 0 0' }}>
            Plain-English explanation of what drives each service's and resource's cost, with the 30-day service-level forecast.
          </p>
        </div>

        {/* Services List with Expandable Top Resources */}
        {explainData?.services?.length > 0 ? (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--s-4)' }}>
            {explainData.services.map(svc => {
              const isExp = expanded[svc.service] ?? true // default open
              return (
                <div
                  key={svc.service}
                  style={{
                    border: '1px solid var(--border-subtle, rgba(255, 255, 255, 0.08))',
                    borderRadius: 'var(--radius-md, 8px)',
                    overflow: 'hidden',
                    background: 'var(--glass-bg, rgba(255, 255, 255, 0.02))'
                  }}
                >
                  {/* Service Header Row */}
                  <div
                    onClick={() => toggleExpand(svc.service)}
                    style={{
                      padding: '14px 18px',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'space-between',
                      cursor: 'pointer',
                      background: 'rgba(255, 255, 255, 0.03)',
                      borderBottom: isExp ? '1px solid var(--border-subtle, rgba(255, 255, 255, 0.08))' : 'none',
                      userSelect: 'none'
                    }}
                  >
                    <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--s-3)' }}>
                      {isExp ? <ChevronDown size={18} color="var(--text-3)" /> : <ChevronRight size={18} color="var(--text-3)" />}
                      <span className={`chip chip-${svc.service.toLowerCase()}`} style={{ fontWeight: 600 }}>
                        {svc.service}
                      </span>
                      <span style={{ fontSize: '14px', fontWeight: 700, color: 'var(--text-1)' }}>
                        {svc.monthly_cost != null && !isNaN(svc.monthly_cost) ? `$${svc.monthly_cost.toFixed(2)}/mo` : 'Cost unavailable'}
                      </span>
                      <span style={{ fontSize: '12px', color: 'var(--text-3)' }}>
                        ({svc.share_of_total_pct != null && !isNaN(svc.share_of_total_pct) ? `${svc.share_of_total_pct.toFixed(1)}% of total` : '—'})
                      </span>
                      {svc.anomaly_note && (
                        <span className="badge badge-danger" style={{ fontSize: '10px', padding: '2px 6px', display: 'inline-flex', alignItems: 'center', gap: 4 }}>
                          <AlertTriangle size={10} /> Anomaly Active
                        </span>
                      )}
                    </div>

                    <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--s-4)', fontSize: '12px' }}>
                      <div style={{ textAlign: 'right' }}>
                        <span style={{ color: 'var(--text-3)', marginRight: 6 }}>30-Day Forecast:</span>
                        <strong style={{ color: 'var(--color-primary, #6366f1)' }}>
                          {svc.forecast_30d != null && !isNaN(svc.forecast_30d) ? `$${svc.forecast_30d.toFixed(2)}` : '—'}
                        </strong>
                        {svc.trend_vs_current_pct != null && !isNaN(svc.trend_vs_current_pct) && (
                          <span style={{ marginLeft: 6, color: svc.trend_vs_current_pct > 0 ? 'var(--color-danger, #ef4444)' : 'var(--color-success, #10b981)' }}>
                            ({svc.trend_vs_current_pct > 0 ? '+' : ''}{svc.trend_vs_current_pct.toFixed(1)}%)
                          </span>
                        )}
                      </div>
                    </div>
                  </div>

                  {/* Service Narrative */}
                  <div style={{ padding: '12px 18px', fontSize: '13px', color: 'var(--text-2)', lineHeight: 1.5, background: 'rgba(255, 255, 255, 0.015)' }}>
                    {svc.narrative}
                  </div>

                  {/* Expandable Top 5 Resources */}
                  {isExp && svc.top_resources && svc.top_resources.length > 0 && (
                    <div style={{ borderTop: '1px solid var(--border-subtle, rgba(255, 255, 255, 0.05))', padding: '12px 18px 16px' }}>
                      <div style={{ fontSize: '11px', fontWeight: 600, textTransform: 'uppercase', color: 'var(--text-3)', letterSpacing: '0.05em', marginBottom: '10px' }}>
                        Top Driver Resources ({svc.top_resources.length})
                      </div>
                      <div className="table-wrap">
                        <table className="data-table" style={{ fontSize: '12px' }}>
                          <thead>
                            <tr>
                              <th>Resource</th>
                              <th style={{ textAlign: 'right' }}>Monthly Cost</th>
                              <th style={{ textAlign: 'right' }}>% of Svc</th>
                              <th style={{ textAlign: 'right' }}>% of Total</th>
                              <th>Usage Narrative & Driver</th>
                              <th>Potential Saving</th>
                            </tr>
                          </thead>
                          <tbody>
                            {svc.top_resources.map(res => (
                              <tr key={res.resource_id}>
                                <td className="td-primary">
                                  <div style={{ fontWeight: 600 }}>{res.resource_name}</div>
                                  <div className="td-mono" style={{ fontSize: '10px' }}>{res.resource_id}</div>
                                </td>
                                <td style={{ textAlign: 'right', fontWeight: 700 }}>
                                  {res.monthly_cost != null && !isNaN(res.monthly_cost) ? `$${res.monthly_cost.toFixed(2)}` : 'Cost unavailable'}
                                </td>
                                <td style={{ textAlign: 'right', color: 'var(--text-3)' }}>
                                  {res.share_of_service_pct != null && !isNaN(res.share_of_service_pct) ? `${res.share_of_service_pct.toFixed(1)}%` : '—'}
                                </td>
                                <td style={{ textAlign: 'right', color: 'var(--text-3)' }}>
                                  {res.share_of_total_pct != null && !isNaN(res.share_of_total_pct) ? `${res.share_of_total_pct.toFixed(1)}%` : '—'}
                                </td>
                                <td style={{ color: 'var(--text-2)', maxWidth: '340px', lineHeight: 1.4 }}>
                                  {res.narrative}
                                </td>
                                <td>
                                  {res.potential_saving != null && !isNaN(res.potential_saving) && res.potential_saving > 0 ? (
                                    <span style={{ color: 'var(--color-success, #10b981)', fontWeight: 600 }}>
                                      ${res.potential_saving.toFixed(2)}/mo
                                      {res.recommendation_issue && (
                                        <div style={{ fontSize: '10px', color: 'var(--text-3)', fontWeight: 400 }}>
                                          {res.recommendation_issue}
                                        </div>
                                      )}
                                    </span>
                                  ) : (
                                    <span style={{ color: 'var(--text-3)' }}>—</span>
                                  )}
                                </td>
                              </tr>
                            ))}
                            {svc.other_resources && (
                              <tr style={{ background: 'rgba(255, 255, 255, 0.02)' }}>
                                <td colSpan={6} style={{ fontStyle: 'italic', color: 'var(--text-3)', padding: '8px 12px' }}>
                                  + {svc.other_resources.label} ({svc.other_resources.monthly_cost != null && !isNaN(svc.other_resources.monthly_cost) ? `$${svc.other_resources.monthly_cost.toFixed(2)}/mo` : 'Cost unavailable'})
                                </td>
                              </tr>
                            )}
                          </tbody>
                        </table>
                      </div>
                    </div>
                  )}
                </div>
              )
            })}
          </div>
        ) : (
          <div style={{ color: 'var(--text-3)', fontSize: '13px', fontStyle: 'italic' }}>
            No service breakdown available for this account.
          </div>
        )}

        {/* Footer Note */}
        <div style={{ marginTop: 'var(--s-4)', paddingTop: 'var(--s-3)', borderTop: '1px solid var(--border-subtle, rgba(255, 255, 255, 0.06))', fontSize: '11px', color: 'var(--text-3)' }}>
          Rule-based explanation from usage data; the forecast is service-level, not per resource.
        </div>
      </div>
    </div>
  )
}
