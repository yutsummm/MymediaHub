'use client'
import { useState, useEffect, Suspense } from 'react'
import { useRouter, useSearchParams } from 'next/navigation'
import Link from 'next/link'
import { useAuth } from '@/contexts/AuthContext'
import { api } from '@/lib/api'

const S = { width: 13, height: 13, viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', strokeWidth: 2, strokeLinecap: 'round' as const, strokeLinejoin: 'round' as const }

function PwStrength({ pw }: { pw: string }) {
  if (!pw) return null
  const has8  = pw.length >= 8
  const hasLt = /[a-zA-Zа-яА-Я]/.test(pw)
  const hasSp = /[!@#$%^&*()_+\-=\[\]{};':"\\|,.<>\/?]/.test(pw)
  const score = [has8, hasLt, hasSp].filter(Boolean).length
  const colors = ['var(--red)', 'var(--yellow)', 'var(--green)']
  const labels = ['Слабый', 'Нормальный', 'Сильный']
  return (
    <div style={{ marginTop: 8 }}>
      <div style={{ display: 'flex', gap: 4, marginBottom: 6 }}>
        {[0, 1, 2].map(i => (
          <div key={i} style={{
            flex: 1, height: 3, borderRadius: 2,
            background: i < score ? colors[score - 1] : 'var(--border-2)',
            transition: 'background var(--dur-base)',
          }} />
        ))}
      </div>
      <div style={{ fontSize: 11, color: colors[score - 1] ?? 'var(--text-3)', fontWeight: 600 }}>
        {score > 0 ? labels[score - 1] : ''}
      </div>
    </div>
  )
}

// useSearchParams требует Suspense-границы, иначе страница не соберётся статически
export default function RegisterPage() {
  return (
    <Suspense fallback={null}>
      <RegisterForm />
    </Suspense>
  )
}

function RegisterForm() {
  const { user, loading, login } = useAuth()
  const router = useRouter()
  const searchParams = useSearchParams()
  // Пришли по ссылке-приглашению — токен несём в регистрацию, иначе человек
  // зарегистрируется «в пустоту» и приглашение потеряется.
  const inviteToken = searchParams.get('invite')

  useEffect(() => {
    if (!loading && user) router.replace('/dashboard')
  }, [user, loading, router])

  const [name, setName]           = useState('')
  const [email, setEmail]         = useState('')
  const [password, setPassword]   = useState('')
  const [confirm, setConfirm]     = useState('')
  const [showPw, setShowPw]       = useState(false)
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [err, setErr]             = useState('')
  // Регистрация двухшаговая: 'form' — анкета, 'code' — ввод кода из письма.
  // Аккаунт создаётся только на втором шаге, поэтому здесь ещё нет ни токена,
  // ни пользователя.
  const [step, setStep]           = useState<'form' | 'code'>('form')
  const [code, setCode]           = useState('')
  const [resent, setResent]       = useState('')

  async function submit(e: React.FormEvent) {
    e.preventDefault()
    setErr('')
    if (!name.trim())                   { setErr('Введите имя'); return }
    if (password.length < 8)            { setErr('Пароль должен содержать минимум 8 символов'); return }
    if (!/[a-zA-Zа-яА-Я]/.test(password))  { setErr('Пароль должен содержать хотя бы одну букву'); return }
    if (!/[!@#$%^&*()_+\-=\[\]{};':"\\|,.<>\/?]/.test(password)) { setErr('Пароль должен содержать хотя бы один спецсимвол'); return }
    if (password !== confirm)           { setErr('Пароли не совпадают'); return }
    setIsSubmitting(true)
    try {
      await api.register(name.trim(), email.trim(), password, inviteToken)
      setStep('code')
    } catch (ex: unknown) {
      setErr((ex as Error).message)
    } finally {
      setIsSubmitting(false)
    }
  }

  async function submitCode(e: React.FormEvent) {
    e.preventDefault()
    setErr(''); setResent('')
    if (code.trim().length !== 6) { setErr('Код состоит из 6 цифр'); return }
    setIsSubmitting(true)
    try {
      const { user, token, invite_error } = await api.verifyEmail(email.trim(), code.trim())
      login(user, token)
      // Приглашение могло исчерпаться, пока человек искал письмо — молчать об
      // этом нельзя, иначе он не поймёт, почему групп нет.
      if (invite_error) alert(`Аккаунт создан, но в группу войти не удалось: ${invite_error}`)
      router.push('/dashboard')
    } catch (ex: unknown) {
      setErr((ex as Error).message)
    } finally {
      setIsSubmitting(false)
    }
  }

  async function resend() {
    setErr(''); setResent('')
    try {
      await api.resendCode(email.trim())
      setResent('Новый код отправлен')
    } catch (ex: unknown) {
      setErr((ex as Error).message)
    }
  }

  const EyeBtn = ({ onClick }: { onClick: () => void }) => (
    <button type="button" onClick={onClick} style={{
      position: 'absolute', right: 12, top: '50%', transform: 'translateY(-50%)',
      background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text-3)',
      display: 'flex', alignItems: 'center', padding: 0, transition: 'color var(--dur-fast)',
    }}
      onMouseEnter={e => (e.currentTarget.style.color = 'var(--text-2)')}
      onMouseLeave={e => (e.currentTarget.style.color = 'var(--text-3)')}
    >
      {showPw
        ? <svg {...S}><path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94"/><path d="M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19"/><line x1="1" y1="1" x2="23" y2="23"/></svg>
        : <svg {...S}><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg>
      }
    </button>
  )

  return (
    <div className="login-bg">
      <div className="login-orb login-orb-1" />
      <div className="login-orb login-orb-2" />

      <div className="login-shell">
        <div className="login-card anim-in">
          {/* Logo */}
          <div style={{ textAlign: 'center', marginBottom: 24 }}>
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
            <div style={{ fontSize: 12, color: 'var(--text-3)', fontWeight: 500, marginTop: 12 }}>
              {step === 'form' ? 'Создайте аккаунт' : 'Подтвердите почту'}
            </div>
          </div>

          {step === 'code' ? (
            <form onSubmit={submitCode}>
              <div style={{
                padding: '12px 14px', borderRadius: 'var(--r-lg)',
                background: 'var(--accent-light)', border: '1px solid var(--border)',
                fontSize: 12.5, color: 'var(--text-3)', lineHeight: 1.6, marginBottom: 16,
              }}>
                Мы отправили код на <strong style={{ color: 'var(--text-2)' }}>{email}</strong>.
                Введите его, чтобы завершить регистрацию. Код действует 15 минут.
              </div>

              <div className="fg">
                <label>Код из письма</label>
                <input
                  type="text" inputMode="numeric" autoComplete="one-time-code" autoFocus
                  value={code} maxLength={6} placeholder="000000"
                  onChange={e => setCode(e.target.value.replace(/\D/g, ''))}
                  style={{ textAlign: 'center', fontSize: 22, fontWeight: 700, letterSpacing: '8px' }}
                />
              </div>

              {err && (
                <div style={{
                  padding: '10px 14px', borderRadius: 'var(--r-md)',
                  background: 'var(--red-bg)', border: '1px solid rgba(239,68,68,0.25)',
                  color: 'var(--red)', fontSize: 12.5, fontWeight: 500,
                  marginBottom: 14, display: 'flex', alignItems: 'center', gap: 8,
                }}>
                  <svg {...S} style={{ flexShrink: 0 }}><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>
                  {err}
                </div>
              )}
              {resent && (
                <div style={{ fontSize: 12, color: 'var(--green)', fontWeight: 600, marginBottom: 12 }}>
                  {resent}
                </div>
              )}

              <button type="submit" className="btn btn-primary" disabled={isSubmitting}
                style={{ width: '100%', justifyContent: 'center', height: 40, fontSize: 13.5, fontWeight: 600 }}>
                {isSubmitting ? (
                  <>
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" style={{ animation: 'spin 0.7s linear infinite' }}><path d="M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83M2 12h4M18 12h4M4.93 19.07l2.83-2.83M16.24 7.76l2.83-2.83"/></svg>
                    Проверяем...
                  </>
                ) : (
                  <>
                    Подтвердить и войти
                    <svg {...S}><line x1="5" y1="12" x2="19" y2="12"/><polyline points="12 5 19 12 12 19"/></svg>
                  </>
                )}
              </button>

              <div style={{
                display: 'flex', justifyContent: 'space-between', gap: 12,
                marginTop: 14, fontSize: 12, color: 'var(--text-3)',
              }}>
                <button type="button" onClick={() => { setStep('form'); setCode(''); setErr(''); setResent('') }}
                  style={{ background: 'none', border: 'none', padding: 0, cursor: 'pointer', color: 'var(--text-3)', fontSize: 12 }}>
                  Изменить адрес
                </button>
                <button type="button" onClick={resend}
                  style={{ background: 'none', border: 'none', padding: 0, cursor: 'pointer', color: 'var(--accent)', fontWeight: 600, fontSize: 12 }}>
                  Отправить код заново
                </button>
              </div>
            </form>
          ) : (
          <>
          <form onSubmit={submit}>
            <div className="fg">
              <label>Имя и фамилия</label>
              <input type="text" value={name} onChange={e => setName(e.target.value)}
                required placeholder="Алексей Иванов" autoComplete="name" autoFocus />
            </div>
            <div className="fg">
              <label>Email</label>
              <input type="email" value={email} onChange={e => setEmail(e.target.value)}
                required placeholder="your@email.com" autoComplete="email" />
            </div>
            <div className="fg">
              <label>Пароль</label>
              <div style={{ position: 'relative' }}>
                <input type={showPw ? 'text' : 'password'} value={password}
                  onChange={e => setPassword(e.target.value)}
                  required placeholder="Минимум 8 символов"
                  autoComplete="new-password" style={{ paddingRight: 42 }} />
                <EyeBtn onClick={() => setShowPw(v => !v)} />
              </div>
              <PwStrength pw={password} />
            </div>
            <div className="fg">
              <label>Подтвердите пароль</label>
              <div style={{ position: 'relative' }}>
                <input type={showPw ? 'text' : 'password'} value={confirm}
                  onChange={e => setConfirm(e.target.value)}
                  required placeholder="Повторите пароль"
                  autoComplete="new-password" style={{ paddingRight: 42 }} />
                {confirm && password && (
                  <div style={{
                    position: 'absolute', right: 12, top: '50%', transform: 'translateY(-50%)',
                    color: confirm === password ? 'var(--green)' : 'var(--red)',
                    display: 'flex', alignItems: 'center',
                  }}>
                    {confirm === password
                      ? <svg {...S}><polyline points="20 6 9 17 4 12"/></svg>
                      : <svg {...S}><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
                    }
                  </div>
                )}
              </div>
            </div>

            {err && (
              <div style={{
                padding: '10px 14px', borderRadius: 'var(--r-md)',
                background: 'var(--red-bg)', border: '1px solid rgba(239,68,68,0.25)',
                color: 'var(--red)', fontSize: 12.5, fontWeight: 500,
                marginBottom: 14, display: 'flex', alignItems: 'center', gap: 8,
              }}>
                <svg {...S} style={{ flexShrink: 0 }}><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>
                {err}
              </div>
            )}

            <button type="submit" className="btn btn-primary" disabled={isSubmitting}
              style={{ width: '100%', justifyContent: 'center', height: 40, fontSize: 13.5, fontWeight: 600, marginTop: 4 }}>
              {isSubmitting ? (
                <>
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" style={{ animation: 'spin 0.7s linear infinite' }}><path d="M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83M2 12h4M18 12h4M4.93 19.07l2.83-2.83M16.24 7.76l2.83-2.83"/></svg>
                  Регистрируем...
                </>
              ) : (
                <>
                  Создать аккаунт
                  <svg {...S}><line x1="5" y1="12" x2="19" y2="12"/><polyline points="12 5 19 12 12 19"/></svg>
                </>
              )}
            </button>
          </form>

          <div style={{ textAlign: 'center', marginTop: 16, fontSize: 12, color: 'var(--text-3)' }}>
            Уже есть аккаунт?{' '}
            <Link href="/login" style={{ color: 'var(--accent)', textDecoration: 'none', fontWeight: 600 }}>
              Войти
            </Link>
          </div>

          <div style={{
            marginTop: 14, padding: '10px 14px', borderRadius: 'var(--r-lg)',
            background: 'var(--accent-light)', border: '1px solid var(--border)',
            fontSize: 11, color: 'var(--text-3)', lineHeight: 1.6,
          }}>
            На указанный адрес придёт код подтверждения — без него аккаунт не создаётся.
            Доступ к группе даёт только приглашение от администратора.
          </div>
          </>
          )}
        </div>
      </div>
    </div>
  )
}
