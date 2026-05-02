'use client'
import { useState, useEffect, useRef } from 'react'
import { useRouter, useSearchParams } from 'next/navigation'
import { useAuth } from '@/contexts/AuthContext'
import { api } from '@/lib/api'

export default function VerifyPage() {
  const { login } = useAuth()
  const router = useRouter()
  const searchParams = useSearchParams()
  const email = searchParams.get('email') ?? ''

  const [digits, setDigits] = useState(['', '', '', '', '', ''])
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [isResending, setIsResending] = useState(false)
  const [err, setErr] = useState('')
  const [resendMsg, setResendMsg] = useState('')
  const [countdown, setCountdown] = useState(0)
  const inputRefs = useRef<(HTMLInputElement | null)[]>([])

  useEffect(() => {
    if (!email) router.replace('/register')
  }, [email, router])

  useEffect(() => {
    inputRefs.current[0]?.focus()
  }, [])

  useEffect(() => {
    if (countdown <= 0) return
    const t = setTimeout(() => setCountdown(c => c - 1), 1000)
    return () => clearTimeout(t)
  }, [countdown])

  function handleDigit(i: number, val: string) {
    const char = val.replace(/\D/g, '').slice(-1)
    const next = [...digits]
    next[i] = char
    setDigits(next)
    setErr('')
    if (char && i < 5) {
      inputRefs.current[i + 1]?.focus()
    }
    if (char && i === 5) {
      const code = [...next.slice(0, 5), char].join('')
      if (code.length === 6) submitCode(code)
    }
  }

  function handleKeyDown(i: number, e: React.KeyboardEvent<HTMLInputElement>) {
    if (e.key === 'Backspace' && !digits[i] && i > 0) {
      inputRefs.current[i - 1]?.focus()
    }
    if (e.key === 'ArrowLeft' && i > 0) inputRefs.current[i - 1]?.focus()
    if (e.key === 'ArrowRight' && i < 5) inputRefs.current[i + 1]?.focus()
  }

  function handlePaste(e: React.ClipboardEvent) {
    const pasted = e.clipboardData.getData('text').replace(/\D/g, '').slice(0, 6)
    if (pasted.length === 6) {
      e.preventDefault()
      const next = pasted.split('')
      setDigits(next)
      inputRefs.current[5]?.focus()
      submitCode(pasted)
    }
  }

  async function submitCode(code: string) {
    if (isSubmitting) return
    setIsSubmitting(true)
    setErr('')
    try {
      const { user, token } = await api.verifyEmail(email, code)
      login(user, token)
      router.push('/dashboard')
    } catch (ex: unknown) {
      setErr((ex as Error).message)
      setDigits(['', '', '', '', '', ''])
      inputRefs.current[0]?.focus()
    } finally {
      setIsSubmitting(false)
    }
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    const code = digits.join('')
    if (code.length < 6) { setErr('Введите все 6 цифр'); return }
    submitCode(code)
  }

  async function handleResend() {
    setIsResending(true)
    setResendMsg('')
    setErr('')
    try {
      await api.resendCode(email)
      setResendMsg('Новый код отправлен')
      setCountdown(60)
      setDigits(['', '', '', '', '', ''])
      inputRefs.current[0]?.focus()
    } catch (ex: unknown) {
      setErr((ex as Error).message)
    } finally {
      setIsResending(false)
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

          <div style={{ textAlign: 'center', marginBottom: 24 }}>
            <div style={{ fontSize: 18, fontWeight: 700, color: 'var(--text)', marginBottom: 8 }}>
              Подтвердите email
            </div>
            <div style={{ fontSize: 13, color: 'var(--text-3)', lineHeight: 1.6 }}>
              Код отправлен на{' '}
              <span style={{ color: 'var(--text-2)', fontWeight: 600 }}>{email}</span>
            </div>
          </div>

          <form onSubmit={handleSubmit} className="login-form">
            <div style={{ display: 'flex', gap: 8, justifyContent: 'center', marginBottom: 8 }} onPaste={handlePaste}>
              {digits.map((d, i) => (
                <input
                  key={i}
                  ref={el => { inputRefs.current[i] = el }}
                  type="text"
                  inputMode="numeric"
                  maxLength={1}
                  value={d}
                  onChange={e => handleDigit(i, e.target.value)}
                  onKeyDown={e => handleKeyDown(i, e)}
                  disabled={isSubmitting}
                  style={{
                    width: 44,
                    height: 52,
                    textAlign: 'center',
                    fontSize: 22,
                    fontWeight: 700,
                    borderRadius: 'var(--r-lg)',
                    border: `2px solid ${err ? '#ef4444' : d ? 'var(--accent)' : 'var(--border)'}`,
                    background: 'var(--surface)',
                    color: 'var(--text)',
                    outline: 'none',
                    transition: 'border-color 0.15s',
                    caretColor: 'transparent',
                  }}
                />
              ))}
            </div>

            {err && <div className="login-err">{err}</div>}
            {resendMsg && (
              <div style={{ textAlign: 'center', fontSize: 12, color: '#10b981', marginTop: 4 }}>
                {resendMsg}
              </div>
            )}

            <button
              type="submit"
              className="btn btn-primary login-submit"
              disabled={isSubmitting || digits.join('').length < 6}
            >
              {isSubmitting ? 'Проверяем...' : 'Подтвердить'}
              {!isSubmitting && <span className="btn-icon">→</span>}
            </button>
          </form>

          <div style={{ textAlign: 'center', marginTop: 16, fontSize: 13, color: 'var(--text-3)' }}>
            {countdown > 0 ? (
              <span>Отправить повторно через {countdown} с</span>
            ) : (
              <button
                type="button"
                onClick={handleResend}
                disabled={isResending}
                style={{
                  background: 'none', border: 'none', cursor: 'pointer',
                  color: 'var(--accent)', fontWeight: 600, fontSize: 13,
                }}
              >
                {isResending ? 'Отправляем...' : 'Отправить код повторно'}
              </button>
            )}
          </div>

          <div style={{ textAlign: 'center', marginTop: 12, fontSize: 12, color: 'var(--text-3)' }}>
            <button
              type="button"
              onClick={() => router.push('/register')}
              style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text-3)', fontSize: 12 }}
            >
              ← Вернуться к регистрации
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
