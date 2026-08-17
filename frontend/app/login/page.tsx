'use client'
import { useState, useEffect } from 'react'
import { useRouter } from 'next/navigation'
import Link from 'next/link'
import { useAuth } from '@/contexts/AuthContext'
import { api } from '@/lib/api'
import Logo from '@/components/Logo'

const S = { width: 15, height: 15, viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', strokeWidth: 1.75, strokeLinecap: 'round' as const, strokeLinejoin: 'round' as const }

export default function LoginPage() {
  const { login, user, loading: authLoading } = useAuth()
  const router = useRouter()

  useEffect(() => {
    if (!authLoading && user) router.replace('/dashboard')
  }, [user, authLoading, router])

  const [email, setEmail]       = useState('')
  const [password, setPassword] = useState('')
  const [showPw, setShowPw]     = useState(false)
  const [loading, setLoading]   = useState(false)
  const [err, setErr]           = useState('')

  async function submit(e: React.FormEvent) {
    e.preventDefault()
    setLoading(true); setErr('')
    try {
      const { user, token } = await api.login(email, password)
      login(user, token)
      router.push('/dashboard')
    } catch (ex: unknown) {
      setErr((ex as Error).message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="login-bg">
      <div className="login-orb login-orb-1" />
      <div className="login-orb login-orb-2" />

      <div className="login-shell">
        <div className="login-card anim-in">
          {/* Logo */}
          <div style={{ textAlign: 'center', marginBottom: 28 }}>
            <Logo
              size={22}
              subtitle="молодёжных центров"
              style={{ display: 'flex', width: 'fit-content', alignItems: 'center', margin: '0 auto 6px' }}
            />
            <div style={{ fontSize: 12, color: 'var(--text-3)', fontWeight: 500, marginTop: 12 }}>
              Войдите в свой аккаунт
            </div>
          </div>

          <form onSubmit={submit}>
            <div className="fg">
              <label>Email</label>
              <input
                type="email"
                value={email}
                onChange={e => setEmail(e.target.value)}
                required
                placeholder="your@email.com"
                autoComplete="email"
                autoFocus
              />
            </div>

            <div className="fg" style={{ position: 'relative', marginBottom: 10 }}>
              <label>Пароль</label>
              <div style={{ position: 'relative' }}>
                <input
                  type={showPw ? 'text' : 'password'}
                  value={password}
                  onChange={e => setPassword(e.target.value)}
                  placeholder="••••••••"
                  autoComplete="current-password"
                  style={{ paddingRight: 42 }}
                />
                <button
                  type="button"
                  onClick={() => setShowPw(v => !v)}
                  style={{
                    position: 'absolute', right: 12, top: '50%', transform: 'translateY(-50%)',
                    background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text-3)',
                    display: 'flex', alignItems: 'center', padding: 0,
                    transition: 'color var(--dur-fast)',
                  }}
                  onMouseEnter={e => (e.currentTarget.style.color = 'var(--text-2)')}
                  onMouseLeave={e => (e.currentTarget.style.color = 'var(--text-3)')}
                >
                  {showPw
                    ? <svg {...S}><path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94"/><path d="M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19"/><line x1="1" y1="1" x2="23" y2="23"/></svg>
                    : <svg {...S}><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg>
                  }
                </button>
              </div>
            </div>

            <div style={{ marginBottom: 20 }}>
              <Link
                href="/forgot-password"
                style={{
                  fontSize: 12.5, color: 'var(--accent)', textDecoration: 'none',
                  fontWeight: 500, opacity: 0.8,
                  transition: 'opacity var(--dur-fast)',
                  display: 'inline-flex', alignItems: 'center', gap: 4,
                }}
                onMouseEnter={e => ((e.currentTarget as HTMLAnchorElement).style.opacity = '1')}
                onMouseLeave={e => ((e.currentTarget as HTMLAnchorElement).style.opacity = '0.8')}
              >
                Забыли пароль?
              </Link>
            </div>

            {err && (
              <div style={{
                padding: '10px 14px', borderRadius: 'var(--r-md)',
                background: 'var(--red-bg)', border: '1px solid rgba(239,68,68,0.25)',
                color: 'var(--red)', fontSize: 12.5, fontWeight: 500,
                marginBottom: 14, display: 'flex', alignItems: 'center', gap: 8,
              }}>
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" style={{ flexShrink: 0 }}>
                  <circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/>
                </svg>
                {err}
              </div>
            )}

            <button
              type="submit"
              className="btn btn-primary"
              disabled={loading}
              style={{ width: '100%', justifyContent: 'center', height: 40, fontSize: 13.5, fontWeight: 600, marginTop: 4 }}
            >
              {loading ? (
                <>
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" style={{ animation: 'spin 0.7s linear infinite' }}><path d="M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83M2 12h4M18 12h4M4.93 19.07l2.83-2.83M16.24 7.76l2.83-2.83"/></svg>
                  Входим...
                </>
              ) : (
                <>
                  Войти
                  <svg {...S}><line x1="5" y1="12" x2="19" y2="12"/><polyline points="12 5 19 12 12 19"/></svg>
                </>
              )}
            </button>
          </form>

          <div style={{ textAlign: 'center', marginTop: 20, fontSize: 12, color: 'var(--text-3)' }}>
            Нет аккаунта?{' '}
            <Link href="/register" style={{ color: 'var(--accent)', textDecoration: 'none', fontWeight: 600 }}>
              Зарегистрироваться
            </Link>
          </div>
        </div>
      </div>
    </div>
  )
}
