import { useNavigate } from 'react-router-dom'
import { motion } from 'framer-motion'

export default function CTA() {
  const navigate = useNavigate()

  return (
    <section className="relative h-[80vh] min-h-[600px] flex items-center justify-center overflow-hidden">
      {/* Background Gradients */}
      <div className="absolute inset-0 bg-slate-900 dark:bg-transparent">
        <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[80%] h-[80%] rounded-full bg-blue-600/30 blur-[150px] mix-blend-screen pointer-events-none" />
        <div className="absolute bottom-0 right-0 w-[50%] h-[50%] rounded-full bg-cyan-500/20 blur-[120px] mix-blend-screen pointer-events-none" />
        <div className="absolute top-0 left-0 w-[50%] h-[50%] rounded-full bg-purple-500/20 blur-[120px] mix-blend-screen pointer-events-none" />
      </div>

      <div className="container mx-auto px-6 relative z-10 text-center">
        <motion.div
          initial={{ opacity: 0, scale: 0.95 }}
          whileInView={{ opacity: 1, scale: 1 }}
          viewport={{ once: true }}
          transition={{ duration: 0.8 }}
          className="max-w-3xl mx-auto flex flex-col items-center"
        >
          <div className="inline-flex items-center gap-2 px-4 py-2 rounded-full bg-white/10 border border-white/20 mb-8 backdrop-blur-md">
            <span className="text-sm font-semibold text-white">Ready to save?</span>
          </div>
          
          <h2 className="text-5xl md:text-6xl font-black text-white mb-6 leading-tight">
            Start Optimizing<br />Cloud Costs Smarter.
          </h2>
          
          <p className="text-lg md:text-xl text-blue-100/80 mb-10 max-w-2xl">
            Gain visibility, predict future spending, and automate savings from one intelligent dashboard.
          </p>
          
          <button 
            onClick={() => navigate('/login')}
            className="group relative h-14 px-10 rounded-full bg-white text-blue-900 font-bold text-lg hover:scale-105 transition-all shadow-[0_0_40px_rgba(255,255,255,0.3)] hover:shadow-[0_0_60px_rgba(255,255,255,0.5)] overflow-hidden"
          >
            <span className="relative z-10 flex items-center gap-2">
              Sign In <span>→</span>
            </span>
            <div className="absolute inset-0 -translate-x-full bg-gradient-to-r from-blue-100/0 via-blue-100/50 to-blue-100/0 group-hover:translate-x-full transition-transform duration-700 ease-out" />
          </button>
        </motion.div>
      </div>

      {/* Floating clouds decorative */}
      <motion.div 
        animate={{ y: [0, -20, 0] }}
        transition={{ duration: 8, repeat: Infinity, ease: "easeInOut" }}
        className="absolute bottom-20 left-20 w-32 h-32 hidden lg:block"
      >
        <div className="w-full h-full opacity-20 dark:opacity-10">
           <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1" strokeLinecap="round" strokeLinejoin="round" className="text-white w-full h-full"><path d="M17.5 19c2.485 0 4.5-2.015 4.5-4.5 0-2.485-2.015-4.5-4.5-4.5h-.335c-.144-2.222-1.996-4-4.265-4-1.91 0-3.53 1.258-4.082 3h-1.42A3.398 3.398 0 0 0 4.398 12.4 3.4 3.4 0 0 0 7.8 15.8h9.7Z"/></svg>
        </div>
      </motion.div>

      <motion.div 
        animate={{ y: [0, 20, 0] }}
        transition={{ duration: 10, repeat: Infinity, ease: "easeInOut" }}
        className="absolute top-20 right-20 w-48 h-48 hidden lg:block"
      >
        <div className="w-full h-full opacity-20 dark:opacity-10">
           <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1" strokeLinecap="round" strokeLinejoin="round" className="text-white w-full h-full"><path d="M17.5 19c2.485 0 4.5-2.015 4.5-4.5 0-2.485-2.015-4.5-4.5-4.5h-.335c-.144-2.222-1.996-4-4.265-4-1.91 0-3.53 1.258-4.082 3h-1.42A3.398 3.398 0 0 0 4.398 12.4 3.4 3.4 0 0 0 7.8 15.8h9.7Z"/></svg>
        </div>
      </motion.div>
    </section>
  )
}
