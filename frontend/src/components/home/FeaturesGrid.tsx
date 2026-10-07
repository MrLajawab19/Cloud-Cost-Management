import { motion } from 'framer-motion'
import { BarChart3, ShieldAlert, FlaskConical, Settings, Lightbulb, Zap } from 'lucide-react'

const features = [
  {
    icon: BarChart3,
    title: 'Forecast Spending',
    description: 'Accurately predict future cloud costs based on historical usage patterns and seasonality.',
    color: 'text-blue-500',
    bg: 'bg-blue-500/10'
  },
  {
    icon: ShieldAlert,
    title: 'Detect Anomalies',
    description: 'Instantly identify unexpected cost spikes with statistically sound Z-score models.',
    color: 'text-red-500',
    bg: 'bg-red-500/10'
  },
  {
    icon: FlaskConical,
    title: 'Simulate Changes',
    description: 'Run what-if scenarios to see how architecture changes affect your bottom line before deploying.',
    color: 'text-purple-500',
    bg: 'bg-purple-500/10'
  },
  {
    icon: Settings,
    title: 'Rightsizing Recommendations',
    description: 'Discover underutilized resources and get actionable resizing recommendations.',
    color: 'text-emerald-500',
    bg: 'bg-emerald-500/10'
  },
  {
    icon: Lightbulb,
    title: 'Optimize Savings Plans',
    description: 'Automatically calculate the exact break-even horizon for commitment purchases.',
    color: 'text-amber-500',
    bg: 'bg-amber-500/10'
  },
  {
    icon: Zap,
    title: 'Automated Remediation',
    description: 'Automatically stop idle instances or apply changes directly from the dashboard.',
    color: 'text-orange-500',
    bg: 'bg-orange-500/10'
  }
]

export default function FeaturesGrid() {
  return (
    <section id="features" className="py-24 relative">
      <div className="container mx-auto px-6 md:px-12">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          transition={{ duration: 0.6 }}
          className="text-center mb-16"
        >
          <h2 className="text-3xl md:text-4xl font-bold text-slate-900 dark:text-white mb-4">
            Key Capabilities
          </h2>
          <p className="text-slate-600 dark:text-slate-400 max-w-2xl mx-auto">
            Everything you need to monitor and optimize cloud costs.
          </p>
        </motion.div>

        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {features.map((f, i) => (
            <motion.div
              key={i}
              initial={{ opacity: 0, y: 20 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true }}
              transition={{ duration: 0.5, delay: i * 0.1 }}
              whileHover={{ y: -8 }}
              className="h-[220px] rounded-2xl bg-white dark:bg-white/[0.02] border border-slate-200 dark:border-white/5 p-8 flex flex-col justify-center transition-all hover:border-blue-500/30 hover:shadow-[0_0_30px_rgba(37,99,235,0.1)] dark:hover:shadow-[0_0_30px_rgba(37,99,235,0.05)] cursor-default"
            >
              <div className={`w-12 h-12 rounded-xl flex items-center justify-center mb-6 ${f.bg}`}>
                <f.icon className={`w-6 h-6 ${f.color}`} />
              </div>
              <h3 className="text-lg font-bold text-slate-900 dark:text-white mb-2">{f.title}</h3>
              <p className="text-sm text-slate-600 dark:text-slate-400 leading-relaxed line-clamp-2">
                {f.description}
              </p>
            </motion.div>
          ))}
        </div>
      </div>
    </section>
  )
}
