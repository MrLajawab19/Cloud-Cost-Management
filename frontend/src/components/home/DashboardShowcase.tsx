import { motion } from 'framer-motion'
import { LayoutDashboard, TrendingUp, AlertTriangle, Lightbulb, Zap, FlaskConical } from 'lucide-react'
import { AreaChart, Area, PieChart, Pie, Cell, ResponsiveContainer, Tooltip } from 'recharts'

const features = [
  { icon: TrendingUp, title: 'Forecasting', desc: 'ML-powered cost prediction baseline' },
  { icon: AlertTriangle, title: 'Anomaly Detection', desc: 'Real-time spike alerts' },
  { icon: Lightbulb, title: 'Optimization', desc: 'Intelligent rightsizing' },
  { icon: FlaskConical, title: 'Simulation Engine', desc: 'What-if financial modeling' },
  { icon: Zap, title: 'Automation', desc: 'One-click resource remediation' },
]

const mockTrendData = [
  { name: '1', cost: 120, forecast: 110 },
  { name: '2', cost: 130, forecast: 115 },
  { name: '3', cost: 125, forecast: 120 },
  { name: '4', cost: 160, forecast: 125, anomaly: true },
  { name: '5', cost: 140, forecast: 130 },
  { name: '6', cost: 135, forecast: 135 },
  { name: '7', cost: 150, forecast: 140 },
]

const mockProviderData = [
  { name: 'AWS', value: 66, color: '#FF9900' },
  { name: 'Azure', value: 34, color: '#0078D4' }
]

const AnomalyDot = (props: any) => {
  const { cx, cy, payload } = props;
  if (payload?.anomaly) {
    return <circle cx={cx} cy={cy} r={4} fill="#ef4444" stroke="#fff" strokeWidth={1.5} />;
  }
  return null;
}

export default function DashboardShowcase() {
  return (
    <section id="dashboard" className="py-24 relative bg-slate-100/50 dark:bg-white/[0.01]">
      <div className="container mx-auto px-6 md:px-12">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          transition={{ duration: 0.6 }}
          className="text-center mb-16"
        >
          <h2 className="text-3xl md:text-4xl font-bold text-slate-900 dark:text-white mb-4">
            Unified Dashboard Experience
          </h2>
          <p className="text-slate-600 dark:text-slate-400 max-w-2xl mx-auto">
            A single view of your multi-cloud costs with actionable insights.
          </p>
        </motion.div>

        <div className="flex flex-col lg:flex-row gap-12 items-center">
          
          {/* Dashboard Left (65%) */}
          <motion.div 
            initial={{ opacity: 0, x: -30 }}
            whileInView={{ opacity: 1, x: 0 }}
            viewport={{ once: true }}
            transition={{ duration: 0.8 }}
            className="w-full lg:w-[65%] h-[500px] rounded-2xl bg-white dark:bg-[#0B1220] border border-slate-200 dark:border-white/10 shadow-2xl overflow-hidden flex flex-col"
          >
            {/* Mock Header */}
            <div className="h-12 border-b border-slate-100 dark:border-white/5 flex items-center px-4 gap-4 justify-between">
              <div className="flex gap-1.5 items-center">
                <div className="w-3 h-3 rounded-full bg-red-400/80" />
                <div className="w-3 h-3 rounded-full bg-amber-400/80" />
                <div className="w-3 h-3 rounded-full bg-green-400/80" />
                <span className="ml-4 text-xs font-bold text-slate-700 dark:text-slate-300 flex items-center gap-2"><CloudIcon /> CCMS</span>
              </div>
              <div className="px-3 py-1 bg-slate-100 dark:bg-white/5 rounded text-[10px] font-medium text-slate-500 dark:text-slate-400">Last 30 days ⌄</div>
            </div>

            <div className="flex flex-1 min-h-0">
              {/* Mock Sidebar */}
              <div className="w-48 border-r border-slate-100 dark:border-white/5 p-4 flex flex-col gap-1">
                <div className="h-8 rounded bg-blue-50 dark:bg-blue-500/10 flex items-center px-3 cursor-default">
                  <LayoutDashboard className="w-4 h-4 text-blue-600 dark:text-blue-400 mr-2" />
                  <span className="text-xs font-semibold text-blue-700 dark:text-blue-300">Overview</span>
                </div>
                {[
                  { icon: TrendingUp, label: 'Costs' },
                  { icon: FlaskConical, label: 'Forecast' },
                  { icon: AlertTriangle, label: 'Anomalies' },
                  { icon: Lightbulb, label: 'Recommendations' }
                ].map((item, i) => (
                  <div key={i} className="h-8 rounded flex items-center px-3 cursor-default hover:bg-slate-50 dark:hover:bg-white/5">
                    <item.icon className="w-4 h-4 text-slate-400 dark:text-slate-500 mr-2" />
                    <span className="text-xs font-medium text-slate-600 dark:text-slate-400">{item.label}</span>
                  </div>
                ))}
              </div>

              {/* Mock Content */}
              <div className="flex-1 p-6 flex flex-col gap-6 bg-slate-50/50 dark:bg-transparent overflow-hidden">
                <div className="grid grid-cols-4 gap-4">
                  <div className="h-20 rounded-xl bg-white dark:bg-white/[0.03] border border-slate-200 dark:border-white/5 p-3 flex flex-col justify-between">
                    <span className="text-[10px] font-semibold text-slate-500">Total Spend</span>
                    <span className="text-lg font-bold text-slate-900 dark:text-white">$42,840</span>
                    <span className="text-[10px] font-medium text-red-500">↑ 12%</span>
                  </div>
                  <div className="h-20 rounded-xl bg-white dark:bg-white/[0.03] border border-slate-200 dark:border-white/5 p-3 flex flex-col justify-between">
                    <span className="text-[10px] font-semibold text-slate-500">Forecast</span>
                    <span className="text-lg font-bold text-slate-900 dark:text-white">$39,120</span>
                    <span className="text-[10px] font-medium text-emerald-500">↓ 8.7%</span>
                  </div>
                  <div className="h-20 rounded-xl bg-white dark:bg-white/[0.03] border border-slate-200 dark:border-white/5 p-3 flex flex-col justify-between">
                    <span className="text-[10px] font-semibold text-slate-500">Active Anomalies</span>
                    <span className="text-lg font-bold text-slate-900 dark:text-white flex items-center gap-1.5"><div className="w-1.5 h-1.5 rounded-full bg-red-500"/> 3</span>
                    <span className="text-[10px] font-medium text-slate-400 dark:text-slate-500">Requires attention</span>
                  </div>
                  <div className="h-20 rounded-xl bg-white dark:bg-white/[0.03] border border-slate-200 dark:border-white/5 p-3 flex flex-col justify-between">
                    <span className="text-[10px] font-semibold text-slate-500">Potential Savings</span>
                    <span className="text-lg font-bold text-slate-900 dark:text-white">$6,240</span>
                    <span className="text-[10px] font-medium text-emerald-500">↑ 18%</span>
                  </div>
                </div>
                
                <div className="flex-1 flex gap-4 min-h-0">
                  <div className="flex-[2] rounded-xl bg-white dark:bg-white/[0.03] border border-slate-200 dark:border-white/5 p-4 flex flex-col">
                    <div className="text-[11px] font-semibold text-slate-700 dark:text-slate-300 mb-4">Cost Overview</div>
                    <div className="flex-1 relative">
                      <ResponsiveContainer width="100%" height="100%">
                        <AreaChart data={mockTrendData} margin={{ top: 5, right: 5, left: -25, bottom: 0 }}>
                          <defs>
                            <linearGradient id="colorCostDash" x1="0" y1="0" x2="0" y2="1">
                              <stop offset="5%" stopColor="#8b5cf6" stopOpacity={0.3}/>
                              <stop offset="95%" stopColor="#8b5cf6" stopOpacity={0}/>
                            </linearGradient>
                          </defs>
                          <Area type="monotone" dataKey="forecast" stroke="#94a3b8" strokeDasharray="3 3" fill="none" strokeWidth={1.5} />
                          <Area type="monotone" dataKey="cost" stroke="#8b5cf6" fill="url(#colorCostDash)" strokeWidth={2} dot={<AnomalyDot />} />
                        </AreaChart>
                      </ResponsiveContainer>
                    </div>
                  </div>
                  
                  <div className="flex-[1] rounded-xl bg-white dark:bg-white/[0.03] border border-slate-200 dark:border-white/5 p-4 flex flex-col">
                     <div className="text-[11px] font-semibold text-slate-700 dark:text-slate-300 mb-2">Cost by Provider</div>
                     <div className="flex-1 flex flex-col items-center justify-center gap-4">
                       <div className="h-24 w-full">
                         <ResponsiveContainer width="100%" height="100%">
                           <PieChart>
                             <Pie data={mockProviderData} innerRadius={25} outerRadius={40} dataKey="value" stroke="none">
                               {mockProviderData.map((entry, index) => (
                                 <Cell key={`cell-${index}`} fill={entry.color} />
                               ))}
                             </Pie>
                           </PieChart>
                         </ResponsiveContainer>
                       </div>
                       <div className="flex flex-col gap-1 w-full px-2">
                         <div className="flex justify-between items-center text-[10px]">
                           <div className="flex items-center gap-1.5 text-slate-600 dark:text-slate-400"><div className="w-1.5 h-1.5 rounded-full bg-[#FF9900]" /> AWS</div>
                           <div className="font-bold text-slate-900 dark:text-white">66%</div>
                         </div>
                         <div className="flex justify-between items-center text-[10px]">
                           <div className="flex items-center gap-1.5 text-slate-600 dark:text-slate-400"><div className="w-1.5 h-1.5 rounded-full bg-[#0078D4]" /> Azure</div>
                           <div className="font-bold text-slate-900 dark:text-white">34%</div>
                         </div>
                       </div>
                     </div>
                  </div>
                </div>
              </div>
            </div>
          </motion.div>

          {/* Features Right (35%) */}
          <motion.div 
            initial={{ opacity: 0, x: 30 }}
            whileInView={{ opacity: 1, x: 0 }}
            viewport={{ once: true }}
            transition={{ duration: 0.8, delay: 0.2 }}
            className="w-full lg:w-[35%] flex flex-col gap-6"
          >
            {features.map((f, i) => (
              <div 
                key={i}
                className="group flex items-start gap-4 p-4 rounded-xl transition-all hover:bg-white dark:hover:bg-white/5 hover:shadow-lg dark:hover:shadow-none hover:scale-[1.02] cursor-default"
              >
                <div className="w-10 h-10 rounded-lg bg-slate-100 dark:bg-white/5 flex items-center justify-center shrink-0 group-hover:bg-blue-500/10 group-hover:text-blue-500 transition-colors">
                  <f.icon className="w-5 h-5 text-slate-500 dark:text-slate-400 group-hover:text-blue-500 transition-colors" />
                </div>
                <div>
                  <h4 className="text-sm font-bold text-slate-900 dark:text-white mb-1 group-hover:text-blue-600 dark:group-hover:text-blue-400 transition-colors">{f.title}</h4>
                  <p className="text-xs text-slate-600 dark:text-slate-400 leading-relaxed">{f.desc}</p>
                </div>
              </div>
            ))}
          </motion.div>

        </div>
      </div>
    </section>
  )
}

function CloudIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="text-blue-500">
      <path d="M17.5 19c2.485 0 4.5-2.015 4.5-4.5 0-2.485-2.015-4.5-4.5-4.5h-.335c-.144-2.222-1.996-4-4.265-4-1.91 0-3.53 1.258-4.082 3h-1.42A3.398 3.398 0 0 0 4.398 12.4 3.4 3.4 0 0 0 7.8 15.8h9.7Z" />
    </svg>
  )
}
