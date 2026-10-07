import { motion } from 'framer-motion'
import { Cloud, Eye, TrendingDown, Layout } from 'lucide-react'

const benefits = [
  { icon: Cloud, title: 'AWS + Azure', desc: 'Unified visibility across both major cloud providers.' },
  { icon: Eye, title: '24/7 Visibility', desc: 'Real-time insights into idle and orphaned resources.' },
  { icon: TrendingDown, title: 'Forecast Driven', desc: 'Make commitment purchases based on ML predictions.' },
  { icon: Layout, title: 'Single Dashboard', desc: 'Stop jumping between different vendor consoles.' },
]

export default function Benefits() {
  return (
    <section className="py-24 relative">
      <div className="container mx-auto px-6 md:px-12">
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-6">
          {benefits.map((b, i) => (
            <motion.div
              key={i}
              initial={{ opacity: 0, y: 20 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true }}
              transition={{ duration: 0.5, delay: i * 0.1 }}
              className="p-8 rounded-2xl bg-white dark:bg-white/[0.02] border border-slate-200 dark:border-white/5 hover:border-slate-300 dark:hover:border-white/10 transition-colors text-center flex flex-col items-center"
            >
              <b.icon className="w-8 h-8 text-blue-600 dark:text-blue-400 mb-6" />
              <h3 className="text-lg font-bold text-slate-900 dark:text-white mb-3">{b.title}</h3>
              <p className="text-sm text-slate-600 dark:text-slate-400 leading-relaxed">
                {b.desc}
              </p>
            </motion.div>
          ))}
        </div>
      </div>
    </section>
  )
}
