'use client'
import { useState } from 'react'
import { useRouter } from 'next/navigation'
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
  const [loading, setLoading] = useState(false)
  const [err, setErr] = useState('')

  async function submit(e: React.FormEvent) {
    e.preventDefault()
    setLoading(true); setErr('')
    try {
      const { user } = await api.login(email)
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
      {/* Radial gradient orbs — GPU-safe, fixed position */}
      <div className="login-orb login-orb-1" />
      <div className="login-orb login-orb-2" />

      {/* Outer shell (double-bezel architecture) */}
      <div className="login-shell">
        {/* Inner core */}
        <div className="login-card">

          {/* Eyebrow tag */}
          <div className="login-eyebrow">Медиаплатформа</div>

          {/* Logo mark — содержит название и слоган внутри */}
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
                defaultValue="password"
                readOnly
                placeholder="••••••••"
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

          {/* Demo accounts */}
          <div className="login-demos">
            <p className="login-demos-label">Демо-аккаунты</p>
            <div className="login-demos-list">
              {DEMOS.map(d => (
                <button
                  key={d.email}
                  type="button"
                  onClick={() => setEmail(d.email)}
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
