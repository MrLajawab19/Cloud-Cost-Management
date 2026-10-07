import { motion } from 'framer-motion'

const steps = [
  { num: '01', title: 'Collect', desc: 'AWS & Azure data' },
  { num: '02', title: 'Analyze', desc: 'Process usage' },
  { num: '03', title: 'Forecast', desc: 'Predict spend' },
  { num: '04', title: 'Detect', desc: 'Find anomalies' },
  { num: '05', title: 'Recommend', desc: 'Discover savings' },
  { num: '06', title: 'Simulate', desc: 'Evaluate impact' },
  { num: '07', title: 'Automate', desc: 'Execute actions' },
]

export default function Workflow() {
  return (
    <section id="workflow" className="py-24 relative overflow-hidden">
      <div className="container mx-auto px-6 md:px-12">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          transition={{ duration: 0.6 }}
          className="text-center mb-24"
        >
          <h2 className="text-3xl md:text-4xl font-bold text-slate-900 dark:text-white mb-4">
            How It Works
          </h2>
          <p className="text-slate-600 dark:text-slate-400 max-w-2xl mx-auto">
            From data collection to automated savings.
          </p>
        </motion.div>

        <div className="relative">
          {/* Desktop horizontal line */}
          <div className="hidden lg:block absolute top-6 left-[5%] right-[5%] h-[2px] bg-gradient-to-r from-blue-600 via-purple-500 to-cyan-400 opacity-20" />
          
          {/* Mobile vertical line */}
          <div className="block lg:hidden absolute top-[5%] bottom-[5%] left-[23px] w-[2px] bg-gradient-to-b from-blue-600 via-purple-500 to-cyan-400 opacity-20" />

          <div className="flex flex-col lg:flex-row justify-between gap-12 lg:gap-4 relative z-10">
            {steps.map((step, i) => (
              <motion.div
                key={i}
                initial={{ opacity: 0, y: 20 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true }}
                transition={{ duration: 0.5, delay: i * 0.1 }}
                className="flex flex-row lg:flex-col items-center lg:items-center gap-6 lg:gap-4 text-left lg:text-center group"
              >
                <div className="relative w-12 h-12 rounded-full bg-white dark:bg-[#0B1220] border-2 border-slate-200 dark:border-white/10 flex items-center justify-center shrink-0 transition-all duration-500 group-hover:border-blue-500 group-hover:shadow-[0_0_20px_rgba(37,99,235,0.4)]">
                  <span className="text-xs font-bold text-slate-500 dark:text-slate-400 group-hover:text-blue-600 dark:group-hover:text-blue-400 transition-colors">{step.num}</span>
                </div>
                <div>
                  <h4 className="text-sm font-bold text-slate-900 dark:text-white mb-1">{step.title}</h4>
                  <p className="text-xs text-slate-500 dark:text-slate-400 whitespace-nowrap">{step.desc}</p>
                </div>
              </motion.div>
            ))}
          </div>
        </div>
      </div>
    </section>
  )
}
