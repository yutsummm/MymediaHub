'use client'

import { createContext, useContext, useState, useEffect } from 'react'
import type { User } from '@/lib/types'
import { setTokenGetter } from '@/lib/api'

interface AuthCtx {
  user: User | null
  token: string | null
  loading: boolean
  login: (user: User, token: string) => void
  logout: () => void
  getToken: () => string | null
}

const AuthContext = createContext<AuthCtx>({ user: null, token: null, loading: true, login: () => {}, logout: () => {}, getToken: () => null })

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [token, setToken] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    try {
      const stored = localStorage.getItem('mediahub_user')
      const storedToken = localStorage.getItem('mediahub_token')
      if (stored) setUser(JSON.parse(stored))
      if (storedToken) setToken(storedToken)
    } catch {}
    setLoading(false)
  }, [])

  useEffect(() => {
    setTokenGetter(() => token)
  }, [token])

  const login = (u: User, t: string) => {
    setUser(u)
    setToken(t)
    localStorage.setItem('mediahub_user', JSON.stringify(u))
    localStorage.setItem('mediahub_token', t)
  }

  const logout = () => {
    setUser(null)
    setToken(null)
    localStorage.removeItem('mediahub_user')
    localStorage.removeItem('mediahub_token')
  }

  const getToken = () => token

  return <AuthContext.Provider value={{ user, token, loading, login, logout, getToken }}>{children}</AuthContext.Provider>
}

export const useAuth = () => useContext(AuthContext)
