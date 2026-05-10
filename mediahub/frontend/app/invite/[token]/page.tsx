'use client'
import { useState, useEffect } from 'react'
import { useRouter, useParams } from 'next/navigation'
import { useAuth } from '@/contexts/AuthContext'
import { useGroup } from '@/contexts/GroupContext'
import { api } from '@/lib/api'
import type { InvitePreview } from '@/lib/types'

const RC: Record<string, string> = { admin: 'r-admin', editor: 'r-editor', observer: 'r-observer' }
const RL: Record<string, string> = { admin: 'Администратор', editor: 'Редактор', observer: 'Наблюдатель' }

export default function InvitePage() {
  const router  = useRouter()
  const params  = useParams()
  const token   = params.token as string
  const { user } = useAuth()
  const { refreshGroups } = useGroup()

  const [invite, setInvite]     = useState<InvitePreview | null>(null)
  const [loading, setLoading]   = useState(true)
  const [accepting, setAccepting] = useState(false)
  const [err, setErr]           = useState('')

  useEffect(() => {
    api.getInvitePreview(token)
      .then(setInvite)
      .catch(ex => setErr((ex as Error).message))
      .finally(() => setLoading(false))
  }, [token])

  async function acceptInvite() {
    if (!user) { router.push(`/login?redirect=/invite/${token}`); return }
    setAccepting(true)
    try {
      await api.acceptInvite(token)
      await refreshGroups()
      router.push('/dashboard')
    } catch (ex: unknown) {
      setErr((ex as Error).message)
    } finally {
      setAccepting(false)
    }
  }

  return (
    <div className="login-bg">
      <div className="login-orb login-orb-1" />
      <div className="login-orb login-orb-2" />

      <div className="login-shell" style={{ maxWidth: 440 }}>
        <div className="login-card anim-in">

          {loading ? (
            <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 14, padding: '20px 0' }}>
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" style={{ animation: 'spin 0.7s linear infinite', color: 'var(--text-3)' }}><path d="M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83M2 12h4M18 12h4M4.93 19.07l2.83-2.83M16.24 7.76l2.83-2.83"/></svg>
              <div style={{ fontSize: 12.5, color: 'var(--text-3)' }}>Загружаем приглашение...</div>
            </div>
          ) : !invite ? (
            <div style={{ textAlign: 'center', padding: '12px 0' }}>
              <div style={{
                display: 'inline-flex', width: 48, height: 48, borderRadius: 14,
                background: 'var(--red-bg)', border: '1px solid rgba(239,68,68,0.2)',
                alignItems: 'center', justifyContent: 'center', marginBottom: 16,
              }}>
                <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="var(--red)" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                  <circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/>
                </svg>
              </div>
              <div style={{ fontSize: 16, fontWeight: 700, color: 'var(--text)', marginBottom: 8, letterSpacing: '-0.03em' }}>
                Ссылка недействительна
              </div>
              <div style={{ fontSize: 13, color: 'var(--text-3)', marginBottom: 24 }}>
                {err || 'Это приглашение больше не действительно'}
              </div>
              <button className="btn btn-secondary btn-sm" onClick={() => router.push('/login')}>
                Перейти на главную
              </button>
            </div>
          ) : (
            <>
              {/* Header */}
              <div style={{ marginBottom: 22 }}>
                <div style={{
                  display: 'inline-flex', width: 48, height: 48, borderRadius: 14,
                  background: 'var(--surface-2)', border: '1px solid var(--border)',
                  alignItems: 'center', justifyContent: 'center', marginBottom: 16,
                }}>
                  <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/>
                    <circle cx="9" cy="7" r="4"/>
                    <path d="M23 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/>
                  </svg>
                </div>
                <div style={{ fontSize: 11, fontWeight: 700, color: 'var(--text-3)', textTransform: 'uppercase', letterSpacing: '0.1em', marginBottom: 6 }}>
                  Приглашение в группу
                </div>
                <div style={{ fontSize: 20, fontWeight: 800, color: 'var(--text)', letterSpacing: '-0.04em', marginBottom: 4 }}>
                  {invite.group_name}
                </div>
                {invite.group_description && (
                  <div style={{ fontSize: 12.5, color: 'var(--text-3)', lineHeight: 1.6 }}>
                    {invite.group_description}
                  </div>
                )}
              </div>

              {/* Role */}
              <div style={{
                display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                padding: '12px 16px', borderRadius: 'var(--r-lg)',
                background: 'var(--surface-2)', border: '1px solid var(--border)',
                marginBottom: 12,
              }}>
                <span style={{ fontSize: 12, color: 'var(--text-3)', fontWeight: 500 }}>Ваша роль</span>
                <span className={`user-role-lbl ${RC[invite.role] ?? ''}`} style={{ fontSize: 10 }}>
                  {RL[invite.role] ?? invite.role}
                </span>
              </div>

              {/* Expiry */}
              <div style={{
                display: 'flex', alignItems: 'center', gap: 8,
                padding: '10px 16px', borderRadius: 'var(--r-md)',
                background: 'var(--surface-2)', border: '1px solid var(--border)',
                marginBottom: 20, fontSize: 12, color: 'var(--text-3)',
              }}>
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/>
                </svg>
                Действует до: <strong style={{ color: 'var(--text-2)' }}>{new Date(invite.expires_at).toLocaleString('ru-RU', { day: 'numeric', month: 'long', hour: '2-digit', minute: '2-digit' })}</strong>
              </div>

              {err && (
                <div style={{
                  padding: '10px 14px', borderRadius: 'var(--r-md)',
                  background: 'var(--red-bg)', border: '1px solid rgba(239,68,68,0.25)',
                  color: 'var(--red)', fontSize: 12.5, marginBottom: 16, display: 'flex', gap: 8, alignItems: 'center',
                }}>
                  <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" style={{ flexShrink: 0 }}>
                    <circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/>
                  </svg>
                  {err}
                </div>
              )}

              <button onClick={acceptInvite} disabled={accepting} className="btn btn-primary"
                style={{ width: '100%', justifyContent: 'center', height: 40, fontSize: 13.5, fontWeight: 600 }}>
                {accepting ? (
                  <>
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" style={{ animation: 'spin 0.7s linear infinite' }}><path d="M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83M2 12h4M18 12h4M4.93 19.07l2.83-2.83M16.24 7.76l2.83-2.83"/></svg>
                    Присоединяемся...
                  </>
                ) : user ? (
                  <>
                    Присоединиться к группе
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><line x1="5" y1="12" x2="19" y2="12"/><polyline points="12 5 19 12 12 19"/></svg>
                  </>
                ) : (
                  <>
                    Войти чтобы присоединиться
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><line x1="5" y1="12" x2="19" y2="12"/><polyline points="12 5 19 12 12 19"/></svg>
                  </>
                )}
              </button>
            </>
          )}
        </div>
      </div>
    </div>
  )
}
