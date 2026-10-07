import { useEffect } from 'react'
import { motion, useMotionValue, useSpring } from 'framer-motion'
import Navbar from '../components/home/Navbar'
import Hero from '../components/home/Hero'
import CloudProviders from '../components/home/CloudProviders'
import FeaturesGrid from '../components/home/FeaturesGrid'
import Workflow from '../components/home/Workflow'
import DashboardShowcase from '../components/home/DashboardShowcase'
import Benefits from '../components/home/Benefits'
import CTA from '../components/home/CTA'

function CursorGlow() {
  const mouseX = useMotionValue(-1000)
  const mouseY = useMotionValue(-1000)
  
  const springConfig = { damping: 25, stiffness: 150 }
  const x = useSpring(mouseX, springConfig)
  const y = useSpring(mouseY, springConfig)

  useEffect(() => {
    const updateMousePosition = (e: MouseEvent) => {
      mouseX.set(e.clientX - 300)
      mouseY.set(e.clientY - 300)
    }
    window.addEventListener('mousemove', updateMousePosition)
    return () => window.removeEventListener('mousemove', updateMousePosition)
  }, [mouseX, mouseY])

  return (
    <motion.div
      className="pointer-events-none fixed top-0 left-0 w-[600px] h-[600px] bg-blue-600/30 dark:bg-cyan-500/15 rounded-full blur-[120px] z-0 mix-blend-normal dark:mix-blend-screen"
      style={{ x, y }}
    />
  )
}

export default function HomePage() {
  return (
    <div className="min-h-screen bg-slate-50 dark:bg-[#030712] text-slate-900 dark:text-slate-100 font-sans transition-colors duration-300 relative overflow-hidden">
      <CursorGlow />
      <Navbar />
      <Hero />
      <div className="relative z-10">
        <CloudProviders />
        <FeaturesGrid />
        <Workflow />
        <DashboardShowcase />
        <Benefits />
        <CTA />
      </div>
    </div>
  )
}
