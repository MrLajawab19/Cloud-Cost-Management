// src/pages/SavingsOptimiser.jsx — Savings Plan Optimiser Page
import { useState, useEffect } from 'react'
import { Info, AlertCircle, CheckCircle, Lightbulb, Banknote, ShieldAlert } from 'lucide-react'
import { savingsOptimiserAPI } from '../api/client'
import { useAuth } from '../contexts/AuthContext'

export default function SavingsOptimiser() {
  const { dataVersion } = useAuth()
  const [data,    setData]    = useState(null)
  const [loading, setLoading] = useState(true)
  const [error,   setError]   = useState(null)

  const loadPlans = async () => {
    setLoading(true)
    setError(null)
    try {
      const res = await savingsOptimiserAPI.getPlans()
      setData(res.data)
    } catch (err) {
      console.error('Failed to load savings plans:', err)
      setError(err?.response?.data?.detail || 'Failed to load savings plan options')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadPlans()
  }, [dataVersion])

  const services = data?.services || []

  return (
    <div className="page-content animate-up">
      {/* Page Title */}
      <div style={{ marginBottom: 'var(--s-4)' }}>
        <h1 className="page-title" style={{ fontSize: '24px', fontWeight: 700, margin: 0 }}>
          Savings Plan Optimiser
        </h1>
        <p className="page-subtitle" style={{ color: 'var(--text-3)', fontSize: '13px', marginTop: 'var(--s-1)' }}>
          Compare 1-year commitment options against your 30-day baseline forecasts to maximize cost reduction.
        </p>
      </div>

      {/* Illustrative Banner */}
      <div
        className="card"
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 'var(--s-3)',
          background: 'rgba(59, 130, 246, 0.08)',
          borderColor: 'rgba(59, 130, 246, 0.25)',
          padding: '12px 18px',
          marginBottom: 'var(--s-4)'
        }}
      >
        <Info size={18} color="var(--color-info, #3b82f6)" />
        <span style={{ fontSize: '13px', color: 'var(--text-2)' }}>
          <strong>Illustrative pricing, not live AWS/Azure rates</strong> — Commitments shown use standard reference discounts (20% No Upfront, 25-30% Partial Upfront, 35% All Upfront) to evaluate cash flow trade-offs.
        </span>
      </div>

      {loading ? (
        <div className="card" style={{ padding: '60px 20px', textAlign: 'center' }}>
          <div className="spinner" style={{ margin: '0 auto var(--s-3)' }} />
          <div style={{ color: 'var(--text-3)', fontSize: '14px' }}>Evaluating commitment models…</div>
        </div>
      ) : error ? (
        <div className="card" style={{ padding: '40px 20px', textAlign: 'center' }}>
          <AlertCircle size={32} color="var(--color-danger, #ef4444)" style={{ margin: '0 auto var(--s-2)' }} />
          <div style={{ fontSize: '15px', fontWeight: 600, color: 'var(--text-1)' }}>{error}</div>
        </div>
      ) : services.length === 0 ? (
        /* Empty State */
        <div className="card" style={{ padding: '60px 20px', textAlign: 'center' }}>
          <ShieldAlert size={36} color="var(--text-3)" style={{ margin: '0 auto var(--s-2)' }} />
          <div style={{ fontSize: '16px', fontWeight: 600, color: 'var(--text-1)', marginBottom: 'var(--s-1)' }}>
            Not enough history yet - stay pay-as-you-go
          </div>
          <div style={{ fontSize: '13px', color: 'var(--text-3)', maxWidth: '440px', margin: '0 auto' }}>
            No eligible services (EC2, RDS, AzureVM, AzureSQL) currently meet the historical data and spend thresholds required for commitment plan analysis.
          </div>
        </div>
      ) : (
        /* One card per service */
        <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--s-4)' }}>
          {services.map(svc => {
            const options = svc.options_list || []
            const isNoCommitment = svc.recommended === 'No commitment option for this service' || svc.has_commitment_option === false
            const isPaygRecommended = svc.recommended === 'pay_as_you_go'

            return (
              <div key={svc.service} className="card" style={{ padding: 'var(--s-4)' }}>
                {/* Card Header */}
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: 'var(--s-2)', marginBottom: 'var(--s-3)' }}>
                  <div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--s-2)' }}>
                      <span className={`chip chip-${svc.service.toLowerCase()}`} style={{ fontSize: '12px', padding: '4px 10px' }}>
                        {svc.service}
                      </span>
                      {svc.is_new && (
                        <span className="badge badge-info" style={{ fontSize: '11px', padding: '2px 8px' }}>
                          New
                        </span>
                      )}
                      <h2 style={{ fontSize: '18px', fontWeight: 700, margin: 0, color: 'var(--text-1)' }}>
                        {svc.service === 'AzureVM' ? 'Azure Virtual Machines'
                          : svc.service === 'AzureSQL' ? 'Azure SQL Database'
                          : svc.service === 'AzureBlob' ? 'Azure Blob Storage'
                          : svc.service === 'AzureFunctions' ? 'Azure Functions'
                          : `${svc.service} Compute`}
                      </h2>
                    </div>
                    <div style={{ fontSize: '13px', color: 'var(--text-3)', marginTop: '4px' }}>
                      30-Day Baseline Spend:{' '}
                      <strong style={{ color: 'var(--text-1)' }}>
                        {svc.baseline_monthly != null && !isNaN(svc.baseline_monthly)
                          ? `$${svc.baseline_monthly.toFixed(2)}/mo`
                          : 'Cost unavailable'}
                      </strong>
                    </div>
                  </div>

                  <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--s-2)', flexWrap: 'wrap' }}>
                    {svc.cv != null && (
                      <span
                        style={{
                          fontSize: '11px',
                          fontWeight: 600,
                          padding: '3px 8px',
                          borderRadius: '12px',
                          background: svc.cv <= 0.10 ? 'rgba(16, 185, 129, 0.15)' : svc.cv <= 0.25 ? 'rgba(245, 158, 11, 0.15)' : 'rgba(239, 68, 68, 0.15)',
                          color: svc.cv <= 0.10 ? '#10b981' : svc.cv <= 0.25 ? '#f59e0b' : '#ef4444',
                          border: `1px solid ${svc.cv <= 0.10 ? 'rgba(16, 185, 129, 0.3)' : svc.cv <= 0.25 ? 'rgba(245, 158, 11, 0.3)' : 'rgba(239, 68, 68, 0.3)'}`
                        }}
                      >
                        {svc.cv <= 0.10 ? `Steady (CV ${(svc.cv * 100).toFixed(1)}%)`
                          : svc.cv <= 0.25 ? `Moderate (CV ${(svc.cv * 100).toFixed(1)}%)`
                          : `Volatile (CV ${(svc.cv * 100).toFixed(1)}%)`}
                      </span>
                    )}
                    {svc.trend_pct != null && (
                      <span
                        style={{
                          fontSize: '11px',
                          fontWeight: 600,
                          padding: '3px 8px',
                          borderRadius: '12px',
                          background: svc.trend_pct <= -10.0 ? 'rgba(239, 68, 68, 0.15)' : 'rgba(99, 102, 241, 0.12)',
                          color: svc.trend_pct <= -10.0 ? '#ef4444' : 'var(--text-2, #a1a1aa)',
                          border: `1px solid ${svc.trend_pct <= -10.0 ? 'rgba(239, 68, 68, 0.3)' : 'rgba(99, 102, 241, 0.25)'}`
                        }}
                      >
                        Trend: {svc.trend_pct >= 0 ? '+' : ''}{svc.trend_pct.toFixed(1)}%/mo
                      </span>
                    )}
                    <span className={`badge ${isNoCommitment ? 'badge-neutral' : svc.preview_if_resolved ? 'badge-warning' : isPaygRecommended ? 'badge-warning' : 'badge-success'}`} style={{ padding: '4px 10px', fontSize: '12px' }}>
                      Recommended: {svc.preview_if_resolved ? 'Held: pay-as-you-go' : (svc.options?.[svc.recommended]?.name || svc.recommended)}
                    </span>
                  </div>
                </div>

                {/* Coverage Bar for Eligible Services */}
                {!isNoCommitment && svc.coverage_pct != null && svc.coverage_pct > 0 && (
                  <div style={{ marginBottom: 'var(--s-3)', background: 'rgba(255, 255, 255, 0.02)', padding: '10px 14px', borderRadius: 'var(--radius-sm, 6px)', border: '1px solid var(--border-subtle, rgba(255, 255, 255, 0.05))' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '12px', marginBottom: '6px', color: 'var(--text-2)' }}>
                      <span>
                        <strong style={{ color: '#10b981' }}>Committed: {svc.coverage_pct}%</strong>
                        {svc.committed_monthly != null && ` ($${svc.committed_monthly.toFixed(2)}/mo floor)`}
                      </span>
                      <span>
                        <strong style={{ color: 'var(--text-3)' }}>PAYG Peak: {100 - svc.coverage_pct}%</strong>
                        {svc.uncommitted_monthly != null && ` ($${svc.uncommitted_monthly.toFixed(2)}/mo)`}
                      </span>
                    </div>
                    <div style={{ width: '100%', height: '8px', background: 'rgba(255, 255, 255, 0.08)', borderRadius: '4px', overflow: 'hidden', display: 'flex' }}>
                      <div style={{ width: `${svc.coverage_pct}%`, height: '100%', background: 'linear-gradient(90deg, #10b981, #059669)', transition: 'width 0.3s' }} />
                      <div style={{ width: `${100 - svc.coverage_pct}%`, height: '100%', background: 'rgba(255, 255, 255, 0.15)', transition: 'width 0.3s' }} />
                    </div>
                  </div>
                )}

                {/* Right-size first note */}
                {svc.right_size_first_note && (
                  <div
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: 'var(--s-2)',
                      background: 'rgba(245, 158, 11, 0.1)',
                      border: '1px solid rgba(245, 158, 11, 0.3)',
                      borderRadius: 'var(--radius-sm, 6px)',
                      padding: '8px 12px',
                      fontSize: '12px',
                      color: 'var(--color-warning, #f59e0b)',
                      marginBottom: 'var(--s-3)'
                    }}
                  >
                    <AlertCircle size={15} />
                    <span>{svc.right_size_first_note}</span>
                  </div>
                )}

                {/* Reason & Cash Note Box */}
                <div
                  style={{
                    background: 'var(--glass-bg, rgba(255, 255, 255, 0.03))',
                    border: '1px solid var(--glass-border, rgba(255, 255, 255, 0.06))',
                    borderRadius: 'var(--radius-sm, 6px)',
                    padding: '12px 16px',
                    marginBottom: 'var(--s-3)',
                    display: 'flex',
                    flexDirection: 'column',
                    gap: '6px'
                  }}
                >
                  <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--s-2)', fontSize: '13px', color: 'var(--text-2)' }}>
                    <Lightbulb size={16} color="var(--color-primary, #6366f1)" />
                    <span><strong>Recommendation rationale:</strong> {svc.reason || 'Analysis complete.'}</span>
                  </div>
                  {svc.preview_if_resolved && (
                    <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--s-2)', fontSize: '12px', color: '#10b981', marginLeft: '24px' }}>
                      <CheckCircle size={14} />
                      <span>
                        <strong>Preview:</strong> After resolving the anomaly, the recommended plan is {svc.preview_if_resolved.recommended} ({svc.preview_if_resolved.coverage}% coverage).
                      </span>
                    </div>
                  )}
                  {svc.cash_note && (
                    <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--s-2)', fontSize: '12px', color: 'var(--text-3)', marginLeft: '24px' }}>
                      <Banknote size={14} />
                      <span>Cash outlay: {svc.cash_note}</span>
                    </div>
                  )}
                </div>

                {/* Options Table */}
                {options.length === 0 ? (
                  <div
                    style={{
                      padding: '24px 20px',
                      textAlign: 'center',
                      color: 'var(--text-3)',
                      fontSize: '13px',
                      background: 'rgba(255, 255, 255, 0.02)',
                      borderRadius: 'var(--radius-sm, 6px)',
                      border: '1px solid var(--border-subtle, rgba(255, 255, 255, 0.05))'
                    }}
                  >
                    No commitment option for this service
                  </div>
                ) : (
                <div className="table-wrap">
                  <table className="data-table" style={{ fontSize: '13px' }}>
                    <thead>
                      <tr>
                        <th>Option</th>
                        <th style={{ textAlign: 'right' }}>Upfront Cash</th>
                        <th style={{ textAlign: 'right' }}>Monthly Payment</th>
                        <th style={{ textAlign: 'right' }}>12-Mo Total</th>
                        <th style={{ textAlign: 'right' }}>12-Mo Net Savings</th>
                        <th style={{ textAlign: 'right' }}>Payback</th>
                        <th style={{ textAlign: 'center', width: '120px' }}>Status</th>
                      </tr>
                    </thead>
                    <tbody>
                      {options.map(opt => {
                        const isRec = opt.id === svc.recommended
                        return (
                          <tr
                            key={opt.id}
                            style={{
                              background: isRec ? 'rgba(16, 185, 129, 0.05)' : 'transparent',
                              fontWeight: isRec ? 600 : 400
                            }}
                          >
                            <td className="td-primary">
                              <div style={{ display: 'flex', flexDirection: 'column' }}>
                                <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--s-2)' }}>
                                  <span>{opt.name}</span>
                                  {opt.discount_pct > 0 && (
                                    <span style={{ fontSize: '10px', color: 'var(--color-success, #10b981)', background: 'rgba(16, 185, 129, 0.1)', padding: '1px 6px', borderRadius: 4 }}>
                                      {opt.discount_pct}% off
                                    </span>
                                  )}
                                </div>
                                {opt.is_illustrative && (
                                  <span style={{ fontSize: '10px', color: 'var(--text-3)' }}>Illustrative tier</span>
                                )}
                              </div>
                            </td>

                            <td style={{ textAlign: 'right' }}>
                              {opt.upfront_cash != null && !isNaN(opt.upfront_cash) ? (
                                opt.upfront_cash === 0 ? '$0.00' : `$${opt.upfront_cash.toFixed(2)}`
                              ) : (
                                'Cost unavailable'
                              )}
                            </td>

                            <td style={{ textAlign: 'right' }}>
                              {opt.monthly_payment != null && !isNaN(opt.monthly_payment) ? (
                                `$${opt.monthly_payment.toFixed(2)}`
                              ) : (
                                'Cost unavailable'
                              )}
                            </td>

                            <td style={{ textAlign: 'right' }}>
                              {opt.total_12m != null && !isNaN(opt.total_12m) ? (
                                `$${opt.total_12m.toFixed(2)}`
                              ) : (
                                'Cost unavailable'
                              )}
                            </td>

                            <td style={{ textAlign: 'right', fontWeight: 700, color: opt.saving_vs_payg_12m > 0 ? 'var(--color-success, #10b981)' : 'var(--text-3)' }}>
                              {opt.saving_vs_payg_12m != null && !isNaN(opt.saving_vs_payg_12m) ? (
                                opt.saving_vs_payg_12m > 0 ? `+$${opt.saving_vs_payg_12m.toFixed(2)}` : '$0.00'
                              ) : (
                                'Cost unavailable'
                              )}
                            </td>

                            <td style={{ textAlign: 'right', color: 'var(--text-2)' }}>
                              {opt.break_even_months != null && !isNaN(opt.break_even_months) ? (
                                opt.upfront_cash === 0 ? 'Immediate' : `${opt.break_even_months.toFixed(1)} mos`
                              ) : (
                                '—'
                              )}
                            </td>

                            <td style={{ textAlign: 'center' }}>
                              {isRec ? (
                                <span className="badge badge-success" style={{ padding: '3px 8px', fontSize: '10px' }}>
                                  <CheckCircle size={10} style={{ marginRight: 3 }} /> Recommended
                                </span>
                              ) : (
                                <span style={{ color: 'var(--text-3)', fontSize: '11px' }}>Alternative</span>
                              )}
                            </td>
                          </tr>
                        )
                      })}
                    </tbody>
                  </table>
                </div>
                )}
              </div>
            )
          })}
        </div>
      )}

      {/* Disclaimers */}
      <div style={{ marginTop: 'var(--s-4)', padding: '12px 16px', background: 'rgba(255, 255, 255, 0.02)', borderRadius: 'var(--radius-sm, 6px)', border: '1px solid var(--border-subtle, rgba(255, 255, 255, 0.05))', fontSize: '12px', color: 'var(--text-3)', textAlign: 'center' }}>
        Heuristic recommendation based on usage behaviour; illustrative pricing.
      </div>
    </div>
  )
}
