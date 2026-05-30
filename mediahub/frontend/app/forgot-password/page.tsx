'use client'
import { useState } from 'react'
import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { api } from '@/lib/api'

const S = { width: 15, height: 15, viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', strokeWidth: 1.75, strokeLinecap: 'round' as const, strokeLinejoin: 'round' as const }

type Step = 'email' | 'code' | 'done'

export default function ForgotPasswordPage() {
  const router = useRouter()
  const [step, setStep]           = useState<Step>('email')
  const [email, setEmail]         = useState('')
  const [code, setCode]           = useState('')
  const [password, setPassword]   = useState('')
  const [confirm, setConfirm]     = useState('')
  const [showPw, setShowPw]       = useState(false)
  const [loading, setLoading]     = useState(false)
  const [err, setErr]             = useState('')

  async function submitEmail(e: React.FormEvent) {
    e.preventDefault()
    setLoading(true); setErr('')
    try {
      await api.forgotPassword(email.trim())
      setStep('code')
    } catch (ex: unknown) {
      setErr((ex as Error).message)
    } finally {
      setLoading(false)
    }
  }

  async function submitReset(e: React.FormEvent) {
    e.preventDefault()
    setErr('')
    if (password.length < 8)                                   { setErr('Пароль должен содержать минимум 8 символов'); return }
    if (!/[a-zA-Zа-яА-Я]/.test(password))                     { setErr('Пароль должен содержать хотя бы одну букву'); return }
    if (!/[!@#$%^&*()_+\-=\[\]{};':"\\|,.<>\/?]/.test(password)) { setErr('Пароль должен содержать хотя бы один спецсимвол'); return }
    if (password !== confirm)                                   { setErr('Пароли не совпадают'); return }
    setLoading(true)
    try {
      await api.resetPassword(email.trim(), code.trim(), password)
      setStep('done')
    } catch (ex: unknown) {
      setErr((ex as Error).message)
    } finally {
      setLoading(false)
    }
  }

  function ErrBlock() {
    if (!err) return null
    return (
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
    )
  }

  return (
    <div className="login-bg">
      <div className="login-orb login-orb-1" />
      <div className="login-orb login-orb-2" />

      <div className="login-shell">
        <div className="login-card anim-in">
          {/* Logo */}
          <div style={{ textAlign: 'center', marginBottom: 28 }}>
            <svg viewBox="0 0 212 46" xmlns="http://www.w3.org/2000/svg"
              style={{ width: 196, height: 'auto', display: 'block', margin: '0 auto 6px' }}>
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
          </div>

          {step === 'email' && (
            <>
              <div style={{ marginBottom: 24 }}>
                <div style={{ fontSize: 17, fontWeight: 700, color: 'var(--text)', letterSpacing: '-0.03em', marginBottom: 4 }}>
                  Забыли пароль?
                </div>
                <div style={{ fontSize: 12, color: 'var(--text-3)', lineHeight: 1.5 }}>
                  Введите email — пришлём код для сброса пароля
                </div>
              </div>

              <form onSubmit={submitEmail}>
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

                <ErrBlock />

                <button
                  type="submit"
                  className="btn btn-primary"
                  disabled={loading}
                  style={{ width: '100%', justifyContent: 'center', height: 40, fontSize: 13.5, fontWeight: 600, marginTop: 4 }}
                >
                  {loading ? (
                    <>
                      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" style={{ animation: 'spin 0.7s linear infinite' }}><path d="M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83M2 12h4M18 12h4M4.93 19.07l2.83-2.83M16.24 7.76l2.83-2.83"/></svg>
                      Отправляем...
                    </>
                  ) : (
                    <>
                      Отправить код
                      <svg {...S}><line x1="5" y1="12" x2="19" y2="12"/><polyline points="12 5 19 12 12 19"/></svg>
                    </>
                  )}
                </button>
              </form>
            </>
          )}

          {step === 'code' && (
            <>
              <div style={{ marginBottom: 24 }}>
                <div style={{ fontSize: 17, fontWeight: 700, color: 'var(--text)', letterSpacing: '-0.03em', marginBottom: 4 }}>
                  Новый пароль
                </div>
                <div style={{ fontSize: 12, color: 'var(--text-3)', lineHeight: 1.5 }}>
                  Код отправлен на{' '}
                  <span style={{ color: 'var(--text-2)', fontWeight: 600 }}>{email}</span>
                </div>
              </div>

              <form onSubmit={submitReset}>
                <div className="fg">
                  <label>Код из письма</label>
                  <input
                    type="text"
                    inputMode="numeric"
                    value={code}
                    onChange={e => setCode(e.target.value.replace(/\D/g, '').slice(0, 6))}
                    required
                    placeholder="000000"
                    autoFocus
                    style={{ letterSpacing: '0.18em', fontWeight: 700, fontSize: 16 }}
                  />
                </div>

                <div className="fg" style={{ position: 'relative' }}>
                  <label>Новый пароль</label>
                  <div style={{ position: 'relative' }}>
                    <input
                      type={showPw ? 'text' : 'password'}
                      value={password}
                      onChange={e => setPassword(e.target.value)}
                      placeholder="мин. 8 символов"
                      autoComplete="new-password"
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

                <div className="fg">
                  <label>Повторите пароль</label>
                  <input
                    type={showPw ? 'text' : 'password'}
                    value={confirm}
                    onChange={e => setConfirm(e.target.value)}
                    placeholder="••••••••"
                    autoComplete="new-password"
                  />
                </div>

                <ErrBlock />

                <button
                  type="submit"
                  className="btn btn-primary"
                  disabled={loading || code.length < 6}
                  style={{ width: '100%', justifyContent: 'center', height: 40, fontSize: 13.5, fontWeight: 600, marginTop: 4 }}
                >
                  {loading ? (
                    <>
                      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" style={{ animation: 'spin 0.7s linear infinite' }}><path d="M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83M2 12h4M18 12h4M4.93 19.07l2.83-2.83M16.24 7.76l2.83-2.83"/></svg>
                      Сохраняем...
                    </>
                  ) : (
                    <>
                      Сохранить пароль
                      <svg {...S}><polyline points="20 6 9 17 4 12"/></svg>
                    </>
                  )}
                </button>

                <button
                  type="button"
                  onClick={() => { setStep('email'); setErr(''); setCode(''); setPassword(''); setConfirm('') }}
                  style={{
                    width: '100%', marginTop: 10, background: 'none', border: 'none', cursor: 'pointer',
                    color: 'var(--text-3)', fontSize: 12, fontWeight: 500, padding: '6px 0',
                    transition: 'color var(--dur-fast)',
                  }}
                  onMouseEnter={e => (e.currentTarget.style.color = 'var(--text-2)')}
                  onMouseLeave={e => (e.currentTarget.style.color = 'var(--text-3)')}
                >
                  Отправить код повторно
                </button>
              </form>
            </>
          )}

          {step === 'done' && (
            <div style={{ textAlign: 'center', padding: '8px 0' }}>
              <div style={{
                width: 52, height: 52, borderRadius: '50%',
                background: 'var(--green-bg, rgba(16,185,129,0.1))',
                border: '1px solid rgba(16,185,129,0.25)',
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                margin: '0 auto 20px',
              }}>
                <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="var(--green)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <polyline points="20 6 9 17 4 12"/>
                </svg>
              </div>
              <div style={{ fontSize: 17, fontWeight: 700, color: 'var(--text)', letterSpacing: '-0.03em', marginBottom: 8 }}>
                Пароль изменён
              </div>
              <div style={{ fontSize: 12.5, color: 'var(--text-3)', marginBottom: 28, lineHeight: 1.5 }}>
                Теперь вы можете войти с новым паролем
              </div>
              <button
                onClick={() => router.push('/login')}
                className="btn btn-primary"
                style={{ width: '100%', justifyContent: 'center', height: 40, fontSize: 13.5, fontWeight: 600 }}
              >
                Войти
                <svg {...S}><line x1="5" y1="12" x2="19" y2="12"/><polyline points="12 5 19 12 12 19"/></svg>
              </button>
            </div>
          )}

          <div style={{ textAlign: 'center', marginTop: 20, fontSize: 12, color: 'var(--text-3)' }}>
            <Link href="/login" style={{ color: 'var(--accent)', textDecoration: 'none', fontWeight: 600 }}>
              ← Вернуться ко входу
            </Link>
          </div>
        </div>
      </div>
    </div>
  )
}
