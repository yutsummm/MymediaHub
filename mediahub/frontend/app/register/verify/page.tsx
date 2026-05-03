'use client'
import { useState, useEffect, Suspense } from 'react'
import { useRouter, useSearchParams } from 'next/navigation'
import { useAuth } from '@/contexts/AuthContext'
import { api } from '@/lib/api'

function VerifyForm() {
  const { login } = useAuth()
  const router = useRouter()
  const params = useSearchParams()
  const email = params.get('email') ?? ''

  const [code, setCode] = useState('')
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [err, setErr] = useState('')
  const [resent, setResent] = useState(false)

  useEffect(() => {
    if (!email) router.replace('/register')
  }, [email, router])

  async function submit(e: React.FormEvent) {
    e.preventDefault()
    if (code.length !== 6) { setErr('Введите 6-значный код'); return }
    setErr('')
    setIsSubmitting(true)
    try {
      const { user, token } = await api.verifyRegister(email, code)
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
          <div className="login-eyebrow">Подтверждение почты</div>
          <img src="/logo.png" alt="Медиа-Хаб" className="login-logo-mark" />

          <p style={{ textAlign: 'center', color: 'var(--text-2)', fontSize: 14, margin: '0 0 20px' }}>
            Мы отправили 6-значный код на<br />
            <strong style={{ color: 'var(--text-1)' }}>{email}</strong>
          </p>

          <form onSubmit={submit} className="login-form">
            <div className="fg">
              <label>Код из письма</label>
              <input
                type="text"
                inputMode="numeric"
                maxLength={6}
                value={code}
                onChange={e => setCode(e.target.value.replace(/\D/g, ''))}
                placeholder="000000"
                autoComplete="one-time-code"
                style={{ textAlign: 'center', fontSize: 24, letterSpacing: 8 }}
                autoFocus
              />
            </div>

            {err && <div className="login-err">{err}</div>}
            {resent && <div style={{ color: 'var(--success, #22c55e)', fontSize: 13, textAlign: 'center' }}>Код отправлен повторно</div>}

            <button
              type="submit"
              className="btn btn-primary login-submit"
              disabled={isSubmitting}
            >
              {isSubmitting ? 'Проверяем...' : 'Подтвердить'}
              {!isSubmitting && <span className="btn-icon">→</span>}
            </button>
          </form>

          <div style={{ textAlign: 'center', marginTop: 16, fontSize: 13, color: 'var(--text-3)' }}>
            Не получили письмо?{' '}
            <button
              onClick={() => router.push('/register')}
              style={{ background: 'none', border: 'none', color: 'var(--accent)', cursor: 'pointer', fontWeight: 600, fontSize: 13 }}
            >
              Зарегистрироваться снова
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}

export default function VerifyRegisterPage() {
  return (
    <Suspense>
      <VerifyForm />
    </Suspense>
  )
}
