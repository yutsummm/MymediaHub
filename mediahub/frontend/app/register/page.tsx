'use client'
import { useState, useEffect } from 'react'
import { useRouter } from 'next/navigation'
import Link from 'next/link'
import { useAuth } from '@/contexts/AuthContext'
import { api } from '@/lib/api'

export default function RegisterPage() {
  const { login, user, loading } = useAuth()
  const router = useRouter()

  useEffect(() => {
    if (!loading && user) router.replace('/dashboard')
  }, [user, loading, router])
  const [name, setName] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [err, setErr] = useState('')

  async function submit(e: React.FormEvent) {
    e.preventDefault()
    setErr('')
    if (!name.trim()) { setErr('Введите имя'); return }
    if (password.length < 6) { setErr('Пароль должен содержать минимум 6 символов'); return }
    if (password !== confirm) { setErr('Пароли не совпадают'); return }
    setIsSubmitting(true)
    try {
      const { user, token } = await api.register(name.trim(), email.trim(), password)
      login(user, token)
      router.push('/dashboard')
    } catch (ex: unknown) {
      setErr((ex as Error).message)
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <div className="login-bg">
      <div className="login-orb login-orb-1" />
      <div className="login-orb login-orb-2" />

      <div className="login-shell">
        <div className="login-card">
          <div className="login-eyebrow">Медиаплатформа</div>
          <img src="/logo.png" alt="Медиа-Хаб" className="login-logo-mark" />

          <form onSubmit={submit} className="login-form">
            <div className="fg">
              <label>Имя и фамилия</label>
              <input
                type="text"
                value={name}
                onChange={e => setName(e.target.value)}
                required
                placeholder="Алексей Иванов"
                autoComplete="name"
              />
            </div>
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
                required
                placeholder="Минимум 6 символов"
                autoComplete="new-password"
              />
            </div>
            <div className="fg">
              <label>Подтвердите пароль</label>
              <input
                type="password"
                value={confirm}
                onChange={e => setConfirm(e.target.value)}
                required
                placeholder="Повторите пароль"
                autoComplete="new-password"
              />
            </div>

            {err && <div className="login-err">{err}</div>}

            <button
              type="submit"
              className="btn btn-primary login-submit"
              disabled={isSubmitting}
            >
              {isSubmitting ? 'Регистрируем...' : 'Создать аккаунт'}
              {!isSubmitting && <span className="btn-icon">→</span>}
            </button>
          </form>

          <div style={{ textAlign: 'center', marginTop: 12, fontSize: 12, color: 'var(--text-3)' }}>
            Уже есть аккаунт?{' '}
            <Link href="/login" style={{ color: 'var(--accent)', textDecoration: 'none', fontWeight: 600 }}>
              Войти
            </Link>
          </div>

          <div style={{
            marginTop: 16, padding: '10px 14px', borderRadius: 'var(--r-lg)',
            background: 'rgba(139,92,246,0.08)', border: '1px solid rgba(139,92,246,0.2)',
            fontSize: 11, color: 'var(--text-3)', lineHeight: 1.6,
          }}>
            После регистрации аккаунт получает роль <strong style={{ color: 'var(--text-2)' }}>Редактор</strong>.
            Администратор может изменить роль в настройках.
          </div>
        </div>
      </div>
    </div>
  )
}
