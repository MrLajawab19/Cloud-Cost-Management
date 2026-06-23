// src/pages/Resources.jsx — Full resource inventory with filters
import { useState, useEffect } from 'react'
import { Server, Filter } from 'lucide-react'
import { resourcesAPI } from '../api/client'

const SERVICE_COLORS = {
  EC2: '#f97316', S3: '#22c55e', RDS: '#3b82f6', Lambda: '#a78bfa',
}

export default function Resources() {
  const [resources, setResources] = useState([])
  const [total,     setTotal]     = useState(0)
  const [loading,   setLoading]   = useState(true)
  const [filters,   setFilters]   = useState({
    service_type: '', status: '', idle_only: false,
  })

  const load = async () => {
    setLoading(true)
    try {
      const params = {}
      if (filters.service_type) params.service_type = filters.service_type
      if (filters.status)       params.status       = filters.status
      if (filters.idle_only)    params.idle_only    = true
      const r = await resourcesAPI.list(params)
      setResources(r.data.resources)
      setTotal(r.data.total)
    } catch (e) {
      console.error(e)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [filters])

  return (
    <div className="page-content">
      <h1 className="page-title">Resource Inventory</h1>
      <p className="page-subtitle">All {total} tracked AWS resources across your account</p>

      {/* Filters */}
      <div className="filter-bar">
        <Filter size={14} color="var(--text-muted)" />
        <select
          className="filter-select"
          value={filters.service_type}
          onChange={e => setFilters(f => ({ ...f, service_type: e.target.value }))}
        >
          <option value="">All Services</option>
          <option value="EC2">EC2</option>
          <option value="S3">S3</option>
          <option value="RDS">RDS</option>
          <option value="Lambda">Lambda</option>
        </select>

        <select
          className="filter-select"
          value={filters.status}
          onChange={e => setFilters(f => ({ ...f, status: e.target.value }))}
        >
          <option value="">All Statuses</option>
          <option value="running">Running</option>
          <option value="stopped">Stopped</option>
          <option value="available">Available</option>
          <option value="active">Active</option>
        </select>

        <label style={{ display: 'flex', alignItems: 'center', gap: 6, cursor: 'pointer', fontSize: 13, color: 'var(--text-secondary)' }}>
          <input
            type="checkbox"
            checked={filters.idle_only}
            onChange={e => setFilters(f => ({ ...f, idle_only: e.target.checked }))}
            style={{ accentColor: 'var(--accent-1)' }}
          />
          Idle only
        </label>
      </div>

      {/* Table */}
      <div className="card" style={{ padding: 0 }}>
        <div className="data-table-wrap">
          {loading ? (
            <div className="spinner-wrap"><div className="spinner" /><span>Loading resources…</span></div>
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
                  <th style={{ textAlign: 'right' }}>Monthly Cost</th>
                  <th>Idle?</th>
                </tr>
              </thead>
              <tbody>
                {resources.length === 0 ? (
                  <tr><td colSpan={9} style={{ textAlign: 'center', padding: 40, color: 'var(--text-muted)' }}>
                    No resources found.
                  </td></tr>
                ) : resources.map(r => (
                  <tr key={r.resource_id}>
                    <td className="resource-name" title={r.resource_id}>
                      {r.resource_name || r.resource_id}
                      <div style={{ fontSize: 10, color: 'var(--text-muted)', fontWeight: 400, marginTop: 2 }}>
                        {r.resource_id}
                      </div>
                    </td>
                    <td style={{ color: SERVICE_COLORS[r.service_type], fontWeight: 600 }}>
                      {r.service_type}
                    </td>
                    <td style={{ color: 'var(--text-muted)', fontSize: 12 }}>{r.resource_type || '—'}</td>
                    <td style={{ color: 'var(--text-muted)', fontSize: 12 }}>{r.region}</td>
                    <td><span className={`badge badge-${r.status}`}>{r.status}</span></td>
                    <td style={{ color: 'var(--text-secondary)', fontSize: 12 }}>
                      {r.cpu_utilization_avg != null ? `${r.cpu_utilization_avg.toFixed(1)}%` : '—'}
                    </td>
                    <td style={{ color: 'var(--text-secondary)', fontSize: 12 }}>
                      {r.storage_size_gb != null ? r.storage_size_gb.toFixed(2) : '—'}
                    </td>
                    <td style={{ textAlign: 'right', fontWeight: 700, color: 'var(--text-primary)' }}>
                      ${(r.estimated_monthly_cost || 0).toFixed(2)}
                    </td>
                    <td>
                      {r.is_idle
                        ? <span className="badge badge-idle">Idle</span>
                        : <span style={{ color: 'var(--text-muted)', fontSize: 12 }}>—</span>
                      }
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
