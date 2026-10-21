// src/pages/SavingsOptimiser.jsx — Savings Plan Optimiser Page
import { useState, useEffect } from 'react'
import { Info, AlertCircle, CheckCircle, Lightbulb, Banknote, ShieldAlert } from 'lucide-react'
import { savingsOptimiserAPI } from '../api/client'

export default function SavingsOptimiser() {
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
  }, [])

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
            No eligible services (EC2, RDS, AzureVM) currently meet the historical data and spend thresholds required for commitment plan analysis.
          </div>
        </div>
      ) : (
        /* One card per service */
        <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--s-4)' }}>
          {services.map(svc => {
            const options = svc.options_list || []
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
                      <h2 style={{ fontSize: '18px', fontWeight: 700, margin: 0, color: 'var(--text-1)' }}>
                        {svc.service === 'AzureVM' ? 'Azure Virtual Machines' : `${svc.service} Compute`}
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

                  <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--s-2)' }}>
                    <span className={`badge ${isPaygRecommended ? 'badge-warning' : 'badge-success'}`} style={{ padding: '4px 10px', fontSize: '12px' }}>
                      Recommended: {svc.options?.[svc.recommended]?.name || svc.recommended}
                    </span>
                  </div>
                </div>

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
                  {svc.cash_note && (
                    <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--s-2)', fontSize: '12px', color: 'var(--text-3)', marginLeft: '24px' }}>
                      <Banknote size={14} />
                      <span>Cash outlay: {svc.cash_note}</span>
                    </div>
                  )}
                </div>

                {/* Options Table */}
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
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
