'use client'
import { useState } from 'react'
import { useRouter } from 'next/navigation'
import Link from 'next/link'
import { useAuth } from '@/contexts/AuthContext'
import { api } from '@/lib/api'

const DEMOS = [
  { email: 'admin@mediahub.ru',    label: 'Администратор' },
  { email: 'editor@mediahub.ru',   label: 'Редактор' },
  { email: 'observer@mediahub.ru', label: 'Наблюдатель' },
]

export default function LoginPage() {
  const { login } = useAuth()
  const router = useRouter()
  const [email, setEmail] = useState('admin@mediahub.ru')
  const [password, setPassword] = useState('')
  const [loading, setLoading] = useState(false)
  const [err, setErr] = useState('')

  async function submit(e: React.FormEvent) {
    e.preventDefault()
    setLoading(true); setErr('')
    try {
      const { user } = await api.login(email, password || 'demo')
      login(user)
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
        <div className="login-card">
          <div className="login-eyebrow">Медиаплатформа</div>
          <img src="/logo.png" alt="Медиа-Хаб — пространство идей и контента" className="login-logo-mark" />

          <form onSubmit={submit} className="login-form">
            <div className="fg">
              <label>Email</label>
              <input
                type="email"
                value={email}
                onChange={e => setEmail(e.target.value)}
                required
                placeholder="your@email.com"
                autoComplete="email"
              />
            </div>
            <div className="fg">
              <label>Пароль</label>
              <input
                type="password"
                value={password}
                onChange={e => setPassword(e.target.value)}
                placeholder="••••••••"
                autoComplete="current-password"
              />
            </div>

            {err && <div className="login-err">{err}</div>}

            <button
              type="submit"
              className="btn btn-primary login-submit"
              disabled={loading}
            >
              {loading ? 'Входим...' : 'Войти'}
              {!loading && <span className="btn-icon">→</span>}
            </button>
          </form>

          <div style={{ textAlign: 'center', marginTop: 12, fontSize: 12, color: 'var(--text-3)' }}>
            Нет аккаунта?{' '}
            <Link href="/register" style={{ color: 'var(--accent)', textDecoration: 'none', fontWeight: 600 }}>
              Зарегистрироваться
            </Link>
          </div>

          <div className="login-demos">
            <p className="login-demos-label">Демо-аккаунты</p>
            <div className="login-demos-list">
              {DEMOS.map(d => (
                <button
                  key={d.email}
                  type="button"
                  onClick={() => { setEmail(d.email); setPassword('') }}
                  className={`login-demo-btn${email === d.email ? ' active' : ''}`}
                >
                  <span className="login-demo-name">{d.label}</span>
                  <span className="login-demo-email">{d.email}</span>
                </button>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
