import { useNavigate } from 'react-router-dom'
import { Cloud, Moon, Sun } from 'lucide-react'
import { useState, useEffect } from 'react'
import { motion } from 'framer-motion'

export default function Navbar() {
  const navigate = useNavigate()
  const [scrolled, setScrolled] = useState(false)
  const [isDarkMode, setIsDarkMode] = useState(() => {
    return localStorage.getItem('theme') === 'dark'
  })

  useEffect(() => {
    if (isDarkMode) {
      document.documentElement.setAttribute('data-theme', 'dark')
      localStorage.setItem('theme', 'dark')
    } else {
      document.documentElement.removeAttribute('data-theme')
      localStorage.setItem('theme', 'light')
    }
  }, [isDarkMode])

  useEffect(() => {
    const handleScroll = () => setScrolled(window.scrollY > 20)
    window.addEventListener('scroll', handleScroll)
    return () => window.removeEventListener('scroll', handleScroll)
  }, [])

  return (
    <motion.nav 
      initial={{ y: -100 }}
      animate={{ y: 0 }}
      transition={{ duration: 0.6 }}
      className={`fixed top-0 left-0 right-0 z-[100] h-20 transition-all duration-300 flex items-center justify-between px-6 md:px-12 ${
        scrolled ? 'bg-white/80 dark:bg-[#030712]/60 backdrop-blur-xl border-b border-slate-200/50 dark:border-white/5' : 'bg-transparent'
      }`}
    >
      <div className="flex items-center gap-2 text-xl font-bold tracking-tight text-blue-600 dark:text-blue-400">
        <Cloud className="w-6 h-6" />
        <span className="text-slate-900 dark:text-white">CCMS</span>
      </div>

      <div className="hidden md:flex items-center gap-8 text-sm font-medium text-slate-600 dark:text-slate-300">
        <a href="#features" className="text-inherit hover:text-blue-600 dark:hover:text-blue-400 transition-colors no-underline">Features</a>
        <a href="#workflow" className="text-inherit hover:text-blue-600 dark:hover:text-blue-400 transition-colors no-underline">Workflow</a>
        <a href="#dashboard" className="text-inherit hover:text-blue-600 dark:hover:text-blue-400 transition-colors no-underline">Dashboard</a>
      </div>

      <div className="flex items-center gap-4">
        <button
          onClick={() => setIsDarkMode(!isDarkMode)}
          className="bg-transparent p-2 rounded-full hover:bg-slate-200 dark:hover:bg-white/10 transition-colors text-slate-600 dark:text-slate-300 flex items-center justify-center cursor-pointer border-none outline-none"
        >
          {isDarkMode ? <Sun className="w-5 h-5" /> : <Moon className="w-5 h-5" />}
        </button>
        <button 
          onClick={() => navigate('/login')}
          className="relative overflow-hidden group px-6 py-2 rounded-full font-medium text-sm text-white bg-blue-600 hover:bg-blue-700 transition-all shadow-[0_0_15px_rgba(37,99,235,0.4)] hover:shadow-[0_0_25px_rgba(37,99,235,0.6)] cursor-pointer"
        >
          <span className="relative z-10 flex items-center gap-2">
            Sign In
            <span className="group-hover:translate-x-1 transition-transform">→</span>
          </span>
          <div className="absolute inset-0 -translate-x-full bg-gradient-to-r from-cyan-400/0 via-cyan-400/30 to-cyan-400/0 group-hover:translate-x-full transition-transform duration-700 ease-out" />
        </button>
      </div>
    </motion.nav>
  )
}
