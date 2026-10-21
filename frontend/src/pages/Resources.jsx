// src/pages/Resources.jsx — Full resource inventory with filters
import { useState, useEffect } from 'react'
import { Filter, Search } from 'lucide-react'
import { resourcesAPI } from '../api/client'

export default function Resources() {
  const [resources, setResources] = useState([])
  const [total,     setTotal]     = useState(0)
  const [loading,   setLoading]   = useState(true)
  const [sortDir,   setSortDir]   = useState('desc')
  const [filters,   setFilters]   = useState({
    service_type: '', status: '', idle_only: false,
  })

  const load = async () => {
    setLoading(true)
    try {
      const params = { sort: 'saving_desc' }
      if (filters.service_type) params.service_type = filters.service_type
      if (filters.status)       params.status       = filters.status
      if (filters.idle_only)    params.idle_only    = true
      const r = await resourcesAPI.list(params)
      setResources(r.data?.resources || [])
      setTotal(r.data?.total || 0)
    } catch (e) {
      console.error(e)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [filters])

  const toggleSort = () => {
    setSortDir(d => d === 'desc' ? 'asc' : 'desc')
  }

  const displayedResources = [...resources].sort((a, b) => {
    const valA = a.potential_saving_usd
    const valB = b.potential_saving_usd
    if (valA == null && valB == null) return 0
    if (valA == null) return 1
    if (valB == null) return -1
    return sortDir === 'desc' ? valB - valA : valA - valB
  })

  const totalSavings = displayedResources.reduce((sum, r) => {
    return sum + (typeof r.potential_saving_usd === 'number' && !isNaN(r.potential_saving_usd) ? r.potential_saving_usd : 0)
  }, 0)

  return (
    <div className="page-content animate-up">
      {/* Filters */}
      <div className="filter-bar">
        <div className="filter-group">
          <Filter size={14} color="var(--text-3)" />
          <span className="filter-bar-label" style={{ marginLeft: 'var(--s-1)' }}>Filters</span>
        </div>

        <div className="topbar-divider" style={{ height: 20, margin: '0 var(--s-2)' }} />

        <div className="filter-group">
          <select
            className="select-input"
            value={filters.service_type}
            onChange={e => setFilters(f => ({ ...f, service_type: e.target.value }))}
          >
            <option value="">All Services</option>
            <option value="EC2">EC2</option>
            <option value="S3">S3</option>
            <option value="RDS">RDS</option>
            <option value="Lambda">Lambda</option>
          </select>
        </div>

        <div className="filter-group">
          <select
            className="select-input"
            value={filters.status}
            onChange={e => setFilters(f => ({ ...f, status: e.target.value }))}
          >
            <option value="">All Statuses</option>
            <option value="running">Running</option>
            <option value="stopped">Stopped</option>
            <option value="available">Available</option>
            <option value="active">Active</option>
          </select>
        </div>

        <label className="toggle-filter" style={{ marginLeft: 'auto' }}>
          <input
            type="checkbox"
            checked={filters.idle_only}
            onChange={e => setFilters(f => ({ ...f, idle_only: e.target.checked }))}
          />
          Show Idle Resources Only
        </label>
      </div>

      {/* Summary line */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 'var(--s-3)' }}>
        <div style={{ fontSize: '13px', fontWeight: 600, color: 'var(--text-2)' }}>
          Total identified: <span style={{ color: 'var(--color-success, #10b981)', fontWeight: 700 }}>${totalSavings.toFixed(2)}</span>
        </div>
      </div>

      {/* Table */}
      <div className="card" style={{ padding: 0 }}>
        <div className="table-wrap">
          {loading ? (
            <div className="loading-wrap">
              <div className="spinner" />
              <div className="loading-text">Loading resources…</div>
            </div>
          ) : (
            <table className="data-table">
              <thead>
                <tr>
                  <th>Name / ID</th>
                  <th>Service</th>
                  <th>Type</th>
                  <th>Region</th>
                  <th>Status</th>
                  <th>CPU %</th>
                  <th>Storage (GB)</th>
                  <th
                    style={{ textAlign: 'right', cursor: 'pointer', userSelect: 'none' }}
                    onClick={toggleSort}
                    title="Click to toggle sort order"
                  >
                    <div style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}>
                      <span>Potential saving / mo</span>
                      <span style={{ fontSize: 10, color: 'var(--text-3)' }}>{sortDir === 'desc' ? '▼' : '▲'}</span>
                    </div>
                  </th>
                  <th style={{ textAlign: 'right' }}>Monthly Cost</th>
                </tr>
              </thead>
              <tbody>
                {displayedResources.length === 0 ? (
                  <tr>
                    <td colSpan={9}>
                      <div className="empty-state" style={{ padding: '40px 20px' }}>
                        <div className="empty-icon"><Search size={24} /></div>
                        <div className="empty-title">No resources found</div>
                        <div className="empty-sub">Try adjusting your filters</div>
                      </div>
                    </td>
                  </tr>
                ) : displayedResources.map(r => (
                  <tr key={r.resource_id}>
                    <td className="td-primary">
                      <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--s-2)' }}>
                          {r.resource_name || r.resource_id}
                          {r.is_idle && <span className="badge badge-idle" style={{ padding: '2px 6px', fontSize: 9 }}>IDLE</span>}
                        </div>
                        <div className="td-mono">{r.resource_id}</div>
                      </div>
                    </td>
                    <td>
                      <span className={`chip chip-${r.service_type.toLowerCase()}`}>
                        {r.service_type}
                      </span>
                    </td>
                    <td>{r.resource_type || '—'}</td>
                    <td>{r.region}</td>
                    <td>
                      <span className={`badge badge-${r.status.toLowerCase()}`}>
                        <span className="badge-dot" />
                        {r.status}
                      </span>
                    </td>
                    <td style={{ color: 'var(--text-3)' }}>
                      {r.cpu_utilization_avg != null && !isNaN(r.cpu_utilization_avg) ? (
                        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                          <div style={{ width: 40, height: 4, background: 'var(--glass-bg-h)', borderRadius: 2, overflow: 'hidden' }}>
                            <div style={{ width: `${Math.min(r.cpu_utilization_avg, 100)}%`, height: '100%', background: r.cpu_utilization_avg > 80 ? 'var(--color-danger)' : 'var(--color-info)' }} />
                          </div>
                          <span>{r.cpu_utilization_avg.toFixed(1)}%</span>
                        </div>
                      ) : '—'}
                    </td>
                    <td style={{ color: 'var(--text-3)' }}>
                      {r.storage_size_gb != null && !isNaN(r.storage_size_gb) ? r.storage_size_gb.toFixed(2) : '—'}
                    </td>
                    <td style={{ textAlign: 'right' }}>
                      {r.potential_saving_usd != null && !isNaN(r.potential_saving_usd) ? (
                        <div>
                          <div style={{ fontWeight: 700, color: r.potential_saving_usd > 0 ? 'var(--color-success, #10b981)' : 'var(--text-2)' }}>
                            ${r.potential_saving_usd.toFixed(2)}
                          </div>
                          {r.saving_issue && (
                            <div style={{ fontSize: 10, color: 'var(--text-3)', marginTop: 2 }}>
                              {r.saving_issue}
                            </div>
                          )}
                        </div>
                      ) : (
                        <span style={{ color: 'var(--text-3)' }}>-</span>
                      )}
                    </td>
                    <td style={{ textAlign: 'right', fontWeight: 700, color: r.estimated_monthly_cost != null && !isNaN(r.estimated_monthly_cost) ? 'var(--text-1)' : 'var(--text-3)' }}>
                      {r.estimated_monthly_cost != null && !isNaN(r.estimated_monthly_cost) ? (
                        <div>
                          <div>${r.estimated_monthly_cost.toFixed(2)}</div>
                          {r.cost_currency && r.cost_currency !== 'USD' && (
                            <div style={{ fontSize: 10, fontWeight: 400, color: 'var(--text-3)' }}>
                              converted from {r.cost_currency} at a fixed rate
                            </div>
                          )}
                        </div>
                      ) : 'Cost unavailable'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>
    </div>
  )
}
