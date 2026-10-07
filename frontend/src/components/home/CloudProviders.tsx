import { motion } from 'framer-motion'

export default function CloudProviders() {
  return (
    <section className="py-24 relative">
      <div className="container mx-auto px-6 md:px-12 text-center">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          transition={{ duration: 0.6 }}
        >
          <h2 className="text-3xl md:text-4xl font-bold text-slate-900 dark:text-white mb-4">
            One Platform. Two Clouds.
          </h2>
          <p className="text-slate-600 dark:text-slate-400 mb-16 max-w-2xl mx-auto">
            Consolidate and normalize cost data from multiple cloud providers.
          </p>
        </motion.div>

        <div className="flex flex-col md:flex-row items-center justify-center gap-8 md:gap-16">
          <motion.div
            initial={{ opacity: 0, x: -30 }}
            whileInView={{ opacity: 1, x: 0 }}
            viewport={{ once: true }}
            whileHover={{ y: -8, scale: 1.02 }}
            className="w-full max-w-[320px] h-[180px] rounded-2xl bg-white/80 dark:bg-white/[0.03] backdrop-blur-xl border border-slate-200 dark:border-white/10 shadow-lg hover:shadow-[0_0_30px_rgba(247,156,22,0.2)] dark:hover:shadow-[0_0_30px_rgba(247,156,22,0.15)] flex flex-col items-center justify-center transition-all cursor-pointer relative overflow-hidden group"
          >
            <div className="absolute inset-0 bg-gradient-to-br from-orange-500/5 to-transparent opacity-0 group-hover:opacity-100 transition-opacity duration-500" />
            <div className="text-4xl font-black text-[#FF9900] mb-3">aws</div>
            <div className="text-sm font-medium text-slate-500 dark:text-slate-400">EC2 • S3 • RDS • Lambda</div>
          </motion.div>

          <div className="hidden md:flex items-center justify-center relative w-24">
            <div className="absolute w-full h-[2px] bg-gradient-to-r from-[#FF9900] via-blue-500 to-[#0078D4] opacity-50" />
            <motion.div 
              animate={{ rotate: 360 }}
              transition={{ duration: 4, repeat: Infinity, ease: "linear" }}
              className="w-8 h-8 rounded-full border-2 border-dashed border-blue-500 bg-slate-50 dark:bg-[#030712] z-10 flex items-center justify-center"
            >
              <div className="w-2 h-2 rounded-full bg-blue-500" />
            </motion.div>
          </div>

          <motion.div
            initial={{ opacity: 0, x: 30 }}
            whileInView={{ opacity: 1, x: 0 }}
            viewport={{ once: true }}
            whileHover={{ y: -8, scale: 1.02 }}
            className="w-full max-w-[320px] h-[180px] rounded-2xl bg-white/80 dark:bg-white/[0.03] backdrop-blur-xl border border-slate-200 dark:border-white/10 shadow-lg hover:shadow-[0_0_30px_rgba(0,120,212,0.2)] dark:hover:shadow-[0_0_30px_rgba(0,120,212,0.15)] flex flex-col items-center justify-center transition-all cursor-pointer relative overflow-hidden group"
          >
            <div className="absolute inset-0 bg-gradient-to-br from-blue-500/5 to-transparent opacity-0 group-hover:opacity-100 transition-opacity duration-500" />
            <div className="text-5xl font-black text-[#0078D4] mb-3 leading-none">A</div>
            <div className="text-sm font-medium text-slate-500 dark:text-slate-400">VMs • Blob • SQL • Functions</div>
          </motion.div>
        </div>
      </div>
    </section>
  )
}
