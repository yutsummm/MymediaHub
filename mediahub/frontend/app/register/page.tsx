'use client'
import { useState, useEffect } from 'react'
import { useRouter } from 'next/navigation'
import Link from 'next/link'
import { useAuth } from '@/contexts/AuthContext'
import { api } from '@/lib/api'

const COMMON_PASSWORDS = [
  '123456','123123','12345678','111111','000000','password','qwerty','abc123',
  'iloveyou','admin','letmein','welcome','monkey','dragon','master','sunshine',
  'princess','passw0rd','shadow','superman','michael','football','baseball',
  'qwertyuiop','1234567890','987654321','password1','qazwsx','zxcvbnm',
  'asdfgh','1q2w3e','1q2w3e4r','qwerty123','test1234','hello123',
]

function getPasswordStrength(pwd: string): { score: number; label: string; color: string } {
  if (pwd.length === 0) return { score: 0, label: '', color: '' }
  if (COMMON_PASSWORDS.includes(pwd.toLowerCase()))
    return { score: 1, label: 'Очень слабый', color: '#ef4444' }

  let score = 0
  if (pwd.length >= 8) score++
  if (pwd.length >= 12) score++
  if (/[A-Z]/.test(pwd)) score++
  if (/[a-z]/.test(pwd)) score++
  if (/[0-9]/.test(pwd)) score++
  if (/[^A-Za-z0-9]/.test(pwd)) score++

  if (score <= 2) return { score: 1, label: 'Слабый', color: '#ef4444' }
  if (score <= 3) return { score: 2, label: 'Средний', color: '#f59e0b' }
  if (score <= 4) return { score: 3, label: 'Хороший', color: '#3b82f6' }
  return { score: 4, label: 'Сильный', color: '#10b981' }
}

function validatePassword(pwd: string): string | null {
  if (pwd.length < 8) return 'Пароль должен содержать минимум 8 символов'
  if (COMMON_PASSWORDS.includes(pwd.toLowerCase())) return 'Пароль слишком простой — придумайте другой'
  if (!/[A-Za-z]/.test(pwd)) return 'Пароль должен содержать хотя бы одну букву'
  if (!/[0-9]/.test(pwd)) return 'Пароль должен содержать хотя бы одну цифру'
  return null
}

export default function RegisterPage() {
  const { user, loading } = useAuth()
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

  const strength = getPasswordStrength(password)

  async function submit(e: React.FormEvent) {
    e.preventDefault()
    setErr('')
    if (!name.trim()) { setErr('Введите имя'); return }
    const pwdErr = validatePassword(password)
    if (pwdErr) { setErr(pwdErr); return }
    if (password !== confirm) { setErr('Пароли не совпадают'); return }
    setIsSubmitting(true)
    try {
      const { email: verifyEmail } = await api.register(name.trim(), email.trim(), password)
      router.push(`/verify?email=${encodeURIComponent(verifyEmail)}`)
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
                placeholder="Минимум 8 символов"
                autoComplete="new-password"
              />
              {password.length > 0 && (
                <div style={{ marginTop: 8 }}>
                  <div style={{ display: 'flex', gap: 4, marginBottom: 4 }}>
                    {[1,2,3,4].map(i => (
                      <div key={i} style={{
                        flex: 1, height: 3, borderRadius: 2,
                        background: i <= strength.score ? strength.color : 'rgba(255,255,255,0.1)',
                        transition: 'background 0.2s',
                      }} />
                    ))}
                  </div>
                  <div style={{ fontSize: 11, color: strength.color }}>{strength.label}</div>
                </div>
              )}
              {password.length > 0 && (
                <div style={{ marginTop: 6, fontSize: 11, color: 'var(--text-3)', lineHeight: 1.7 }}>
                  <span style={{ color: password.length >= 8 ? '#10b981' : 'var(--text-3)' }}>
                    {password.length >= 8 ? '✓' : '·'} Минимум 8 символов
                  </span>{' · '}
                  <span style={{ color: /[A-Za-z]/.test(password) ? '#10b981' : 'var(--text-3)' }}>
                    {/[A-Za-z]/.test(password) ? '✓' : '·'} Буква
                  </span>{' · '}
                  <span style={{ color: /[0-9]/.test(password) ? '#10b981' : 'var(--text-3)' }}>
                    {/[0-9]/.test(password) ? '✓' : '·'} Цифра
                  </span>
                </div>
              )}
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
