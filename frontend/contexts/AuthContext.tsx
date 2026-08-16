'use client'

import { createContext, useContext, useState, useEffect } from 'react'
import type { User } from '@/lib/types'
import { api, setTokenGetter, setUnauthorizedHandler } from '@/lib/api'

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
    // Сервер уже отверг токен — гасить его повторно незачем, а вызов api.logout()
    // получил бы очередной 401 и снова позвал этот же обработчик.
    setUnauthorizedHandler(clearLocalSession)
  }, [token])

  const login = (u: User, t: string) => {
    setUser(u)
    setToken(t)
    localStorage.setItem('mediahub_user', JSON.stringify(u))
    localStorage.setItem('mediahub_token', t)
  }

  const clearLocalSession = () => {
    setUser(null)
    setToken(null)
    localStorage.removeItem('mediahub_user')
    localStorage.removeItem('mediahub_token')
  }

  const logout = () => {
    // Сначала гасим токен на сервере — иначе он остаётся действительным ещё
    // до 72 часов, и «выход» защищает только от того, кто сидит за этим же
    // браузером. Ответа не ждём: локально выходим в любом случае.
    api.logout().catch(() => {})
    clearLocalSession()
  }

  const getToken = () => token

  return <AuthContext.Provider value={{ user, token, loading, login, logout, getToken }}>{children}</AuthContext.Provider>
}

export const useAuth = () => useContext(AuthContext)
