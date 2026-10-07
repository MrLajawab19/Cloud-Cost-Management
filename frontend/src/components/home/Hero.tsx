import { useNavigate } from 'react-router-dom'
import { motion } from 'framer-motion'
import { AreaChart, Area, ResponsiveContainer } from 'recharts'
import { Play } from 'lucide-react'

const mockData = [
  { name: '1', cost: 300, forecast: 320 },
  { name: '2', cost: 340, forecast: 330 },
  { name: '3', cost: 280, forecast: 290 },
  { name: '4', cost: 490, forecast: 310, anomaly: true },
  { name: '5', cost: 350, forecast: 340 },
  { name: '6', cost: 320, forecast: 330 },
  { name: '7', cost: 380, forecast: 360 },
]

const AnomalyDot = (props: any) => {
  const { cx, cy, payload } = props;
  if (payload?.anomaly) {
    return <circle cx={cx} cy={cy} r={6} fill="#ef4444" stroke="#fff" strokeWidth={2} />;
  }
  return null;
}

const BackgroundTopology = () => (
  <div className="absolute inset-0 overflow-hidden pointer-events-none flex items-center justify-center">
    <motion.div 
      animate={{ 
        scale: [1, 1.2, 1],
        x: [0, 50, 0],
        y: [0, -30, 0]
      }}
      transition={{ duration: 15, repeat: Infinity, ease: "easeInOut" }}
      className="absolute top-1/4 left-1/4 w-[30rem] h-[30rem] rounded-full bg-blue-500/20 dark:bg-blue-500/30 blur-[120px]" 
    />
    <motion.div 
      animate={{ 
        scale: [1, 1.3, 1],
        x: [0, -50, 0],
        y: [0, 40, 0]
      }}
      transition={{ duration: 20, repeat: Infinity, ease: "easeInOut" }}
      className="absolute bottom-1/4 right-1/4 w-[30rem] h-[30rem] rounded-full bg-cyan-500/20 dark:bg-cyan-500/30 blur-[120px]" 
    />
    <motion.div 
      animate={{ 
        scale: [1, 1.1, 1],
        opacity: [0.5, 0.8, 0.5]
      }}
      transition={{ duration: 12, repeat: Infinity, ease: "easeInOut" }}
      className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[40rem] h-[40rem] rounded-full bg-indigo-500/10 dark:bg-indigo-500/20 blur-[150px]" 
    />
    <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_center,rgba(37,99,235,0.08)_1px,transparent_1px)] bg-[size:32px_32px] dark:bg-[radial-gradient(ellipse_at_center,rgba(255,255,255,0.03)_1px,transparent_1px)]" />
  </div>
)

export default function Hero() {
  const navigate = useNavigate()

  return (
    <div className="relative min-h-screen flex items-center pt-20">
      <BackgroundTopology />
      <div className="container mx-auto px-6 md:px-12 relative z-10">
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-16 items-center">
          
          <motion.div 
            initial={{ opacity: 0, x: -30 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ duration: 0.8, staggerChildren: 0.2 }}
            className="flex flex-col gap-8"
          >
            <motion.div className="inline-flex items-center gap-2 px-4 py-2 rounded-full bg-blue-50 dark:bg-white/5 border border-blue-100 dark:border-white/10 w-fit">
              <div className="w-2 h-2 rounded-full bg-blue-500 animate-pulse" />
              <span className="text-sm font-semibold text-blue-700 dark:text-blue-300">AWS + Azure</span>
            </motion.div>

            <motion.h1 className="text-5xl md:text-[72px] font-[800] leading-[0.95] tracking-tight text-slate-900 dark:text-white">
              Understand.<br />
              Predict.<br />
              Optimize.<br />
              <span className="text-transparent bg-clip-text bg-gradient-to-r from-blue-600 to-cyan-500 dark:from-blue-400 dark:to-cyan-300">
                Cloud Costs.
              </span>
            </motion.h1>

            <motion.p className="text-lg md:text-xl text-slate-600 dark:text-slate-400 max-w-[550px] leading-relaxed">
              Unified cloud cost intelligence across AWS and Azure with forecasting, anomaly detection, optimization recommendations, and automated savings.
            </motion.p>

            <motion.div className="flex flex-col sm:flex-row gap-4 pt-4">
              <button 
                onClick={() => navigate('/login')}
                className="h-[52px] px-8 rounded-[14px] bg-blue-600 hover:bg-blue-700 text-white font-semibold transition-all shadow-[0_0_20px_rgba(37,99,235,0.3)] hover:shadow-[0_0_30px_rgba(37,99,235,0.5)] flex items-center justify-center gap-2"
              >
                Get Started <span>→</span>
              </button>
              <button 
                onClick={() => navigate('/login')}
                className="h-[52px] px-8 rounded-[14px] bg-white dark:bg-white/5 hover:bg-slate-50 dark:hover:bg-white/10 text-slate-900 dark:text-white border border-slate-200 dark:border-white/10 font-semibold transition-all flex items-center justify-center gap-2"
              >
                <Play className="w-4 h-4" /> View Dashboard
              </button>
            </motion.div>
          </motion.div>

          <motion.div 
            initial={{ opacity: 0, y: 30 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.8, delay: 0.2 }}
            className="relative lg:h-[600px] flex items-center justify-center"
          >
            <motion.div 
              animate={{ y: [-10, 10, -10] }}
              transition={{ duration: 6, repeat: Infinity, ease: "easeInOut" }}
              className="w-full max-w-[600px] h-[420px] rounded-2xl bg-white/80 dark:bg-white/[0.04] backdrop-blur-[24px] border border-slate-200/50 dark:border-white/10 shadow-2xl overflow-hidden flex flex-col p-6"
            >
              <div className="flex justify-between items-center mb-8">
                <div>
                  <div className="text-sm font-semibold text-slate-500 dark:text-slate-400">Cloud Spend</div>
                  <div className="text-4xl font-bold text-slate-900 dark:text-white mt-1">$42,840</div>
                  <div className="text-sm font-medium text-emerald-500 mt-2 flex items-center gap-1">
                    <span className="text-emerald-500">↑</span> 12%
                  </div>
                </div>
                <div className="text-right">
                  <div className="inline-flex items-center gap-2 px-3 py-1.5 rounded-md bg-slate-100 dark:bg-white/5 text-xs font-medium text-slate-600 dark:text-slate-300">
                    Last 30 days <span>⌄</span>
                  </div>
                </div>
              </div>

              <div className="flex-1 min-h-0 relative">
                <ResponsiveContainer width="100%" height="100%">
                  <AreaChart data={mockData} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
                    <defs>
                      <linearGradient id="colorCost" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="5%" stopColor="#3b82f6" stopOpacity={0.3}/>
                        <stop offset="95%" stopColor="#3b82f6" stopOpacity={0}/>
                      </linearGradient>
                    </defs>
                    <Area type="monotone" dataKey="forecast" stroke="#94a3b8" strokeDasharray="4 4" fill="none" strokeWidth={2} />
                    <Area type="monotone" dataKey="cost" stroke="#3b82f6" fill="url(#colorCost)" strokeWidth={3} dot={<AnomalyDot />} />
                  </AreaChart>
                </ResponsiveContainer>
              </div>

              <div className="grid grid-cols-3 gap-4 mt-6 pt-6 border-t border-slate-200 dark:border-white/10">
                <div>
                  <div className="text-xs font-medium text-slate-500 dark:text-slate-400 mb-1">Forecast</div>
                  <div className="text-lg font-bold text-slate-900 dark:text-white">$39,120</div>
                  <div className="text-xs font-medium text-emerald-500 mt-1">↓ 8.7%</div>
                </div>
                <div>
                  <div className="text-xs font-medium text-slate-500 dark:text-slate-400 mb-1">Anomalies</div>
                  <div className="text-lg font-bold text-slate-900 dark:text-white flex items-center gap-2">
                    <div className="w-2 h-2 rounded-full bg-red-500" /> 3
                  </div>
                </div>
                <div>
                  <div className="text-xs font-medium text-slate-500 dark:text-slate-400 mb-1">Potential Savings</div>
                  <div className="text-lg font-bold text-slate-900 dark:text-white">$6,240</div>
                  <div className="text-xs font-medium text-emerald-500 mt-1">↑ 18%</div>
                </div>
              </div>
            </motion.div>
          </motion.div>
        </div>
      </div>
    </div>
  )
}
