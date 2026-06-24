import { createContext, useState, useEffect, useContext } from 'react'
import { authAPI, accountsAPI } from '../api/client'

const AuthContext = createContext()

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null)
  const [loading, setLoading] = useState(true)
  const [accounts, setAccounts] = useState([])
  const [activeAccount, setActiveAccount] = useState(null)

  useEffect(() => {
    const initAuth = async () => {
      const token = localStorage.getItem('access_token')
      if (token) {
        try {
          const res = await authAPI.me()
          setUser(res.data)
          await loadAccounts()
        } catch (err) {
          console.error("Auth failed:", err)
          localStorage.removeItem('access_token')
        }
      }
      setLoading(false)
    }
    initAuth()
  }, [])

  const loadAccounts = async () => {
    try {
      const res = await accountsAPI.list()
      setAccounts(res.data)
      const storedAccountId = localStorage.getItem('active_account_id')
      if (res.data.length > 0) {
        const found = res.data.find(a => a.id === storedAccountId)
        if (found) {
          setActiveAccount(found)
        } else {
          setActiveAccount(res.data[0])
          localStorage.setItem('active_account_id', res.data[0].id)
        }
      } else {
        setActiveAccount(null)
        localStorage.removeItem('active_account_id')
      }
    } catch (err) {
      console.error("Failed to load accounts", err)
    }
  }

  const login = async (email, password) => {
    const formData = new URLSearchParams()
    formData.append('username', email)
    formData.append('password', password)
    
    const res = await authAPI.login(formData)
    localStorage.setItem('access_token', res.data.access_token)
    
    const meRes = await authAPI.me()
    setUser(meRes.data)
    await loadAccounts()
  }

  const register = async (email, password) => {
    await authAPI.register({ email, password })
    await login(email, password)
  }

  const logout = () => {
    localStorage.removeItem('access_token')
    localStorage.removeItem('active_account_id')
    setUser(null)
    setAccounts([])
    setActiveAccount(null)
  }

  const switchAccount = (accountId) => {
    const acc = accounts.find(a => a.id === accountId)
    if (acc) {
      setActiveAccount(acc)
      localStorage.setItem('active_account_id', accountId)
      window.location.reload() // Reload to fetch data for new account
    }
  }

  const deleteAccount = async (accountId) => {
    try {
      await accountsAPI.delete(accountId)
      await loadAccounts()
      window.location.reload()
    } catch (err) {
      console.error("Failed to delete account", err)
      alert("Failed to delete account. Please try again.")
    }
  }

  return (
    <AuthContext.Provider value={{
      user, loading, login, register, logout,
      accounts, activeAccount, loadAccounts, switchAccount, deleteAccount
    }}>
      {children}
    </AuthContext.Provider>
  )
}

export const useAuth = () => useContext(AuthContext)
