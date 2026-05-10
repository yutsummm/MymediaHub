'use client'
import { useState, useEffect, Suspense } from 'react'
import { useRouter, useSearchParams } from 'next/navigation'
import { useAuth } from '@/contexts/AuthContext'
import { api } from '@/lib/api'

function VerifyForm() {
  const { login } = useAuth()
  const router    = useRouter()
  const params    = useSearchParams()
  const email     = params.get('email') ?? ''

  const [code, setCode]             = useState('')
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [err, setErr]               = useState('')

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
        <div className="login-card anim-in">
          {/* Logo + header */}
          <div style={{ textAlign: 'center', marginBottom: 24 }}>
            <svg viewBox="0 0 212 46" xmlns="http://www.w3.org/2000/svg"
              style={{ width: 196, height: 'auto', display: 'block', margin: '0 auto 18px' }}>
              <rect x="0"  y="3"  width="7" height="36" rx="1.5" style={{ fill: 'var(--text)' }}/>
              <rect x="10" y="11" width="7" height="28" rx="1.5" style={{ fill: 'var(--text)', opacity: 0.48 }}/>
              <rect x="20" y="19" width="7" height="20" rx="1.5" style={{ fill: 'var(--text)', opacity: 0.26 }}/>
              <rect x="30" y="11" width="7" height="28" rx="1.5" style={{ fill: 'var(--text)', opacity: 0.48 }}/>
              <rect x="40" y="3"  width="7" height="36" rx="1.5" style={{ fill: 'var(--text)' }}/>
              <rect x="0"  y="41" width="47" height="3" rx="1.5" style={{ fill: 'var(--accent)', opacity: 0.55 }}/>
              <line x1="57" y1="5" x2="57" y2="40" style={{ stroke: 'var(--border-2)' }} strokeWidth="1"/>
              <text x="66" y="20" fontFamily="'Plus Jakarta Sans','Inter','Arial',sans-serif" fontSize="10" fontWeight="700" style={{ fill: 'var(--text)' }}>МЕДИАПРОСТРАНСТВО</text>
              <text x="66" y="34" fontFamily="'Plus Jakarta Sans','Inter','Arial',sans-serif" fontSize="8.5" fontWeight="400" style={{ fill: 'var(--text-3)' }}>молодёжных центров</text>
            </svg>
            <div style={{ fontSize: 17, fontWeight: 800, color: 'var(--text)', letterSpacing: '-0.04em', marginBottom: 6 }}>
              Подтверждение почты
            </div>
            <div style={{ fontSize: 12.5, color: 'var(--text-3)', lineHeight: 1.6 }}>
              Мы отправили 6-значный код на<br />
              <strong style={{ color: 'var(--text-2)', fontWeight: 600 }}>{email}</strong>
            </div>
          </div>

          <form onSubmit={submit}>
            <div className="fg">
              <label style={{ textAlign: 'center', display: 'block' }}>Код из письма</label>
              <input
                type="text"
                inputMode="numeric"
                maxLength={6}
                value={code}
                onChange={e => setCode(e.target.value.replace(/\D/g, ''))}
                placeholder="000000"
                autoComplete="one-time-code"
                autoFocus
                style={{
                  textAlign: 'center', fontSize: 26, letterSpacing: 10,
                  fontWeight: 700, fontVariantNumeric: 'tabular-nums',
                }}
              />
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

            <button type="submit" className="btn btn-primary" disabled={isSubmitting || code.length !== 6}
              style={{ width: '100%', justifyContent: 'center', height: 40, fontSize: 13.5, fontWeight: 600 }}>
              {isSubmitting ? (
                <>
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" style={{ animation: 'spin 0.7s linear infinite' }}><path d="M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83M2 12h4M18 12h4M4.93 19.07l2.83-2.83M16.24 7.76l2.83-2.83"/></svg>
                  Проверяем...
                </>
              ) : (
                <>
                  Подтвердить
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><polyline points="20 6 9 17 4 12"/></svg>
                </>
              )}
            </button>
          </form>

          <div style={{ textAlign: 'center', marginTop: 20, fontSize: 12, color: 'var(--text-3)' }}>
            Не получили письмо?{' '}
            <button
              onClick={() => router.push('/register')}
              style={{ background: 'none', border: 'none', color: 'var(--accent)', cursor: 'pointer', fontWeight: 600, fontSize: 12, padding: 0 }}
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
