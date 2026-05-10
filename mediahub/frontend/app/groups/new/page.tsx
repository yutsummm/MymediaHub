'use client'
import { useState } from 'react'
import { useRouter } from 'next/navigation'
import { useAuth } from '@/contexts/AuthContext'
import { useGroup } from '@/contexts/GroupContext'
import { api } from '@/lib/api'

export default function CreateGroupPage() {
  const router = useRouter()
  const { user } = useAuth()
  const { refreshGroups } = useGroup()
  const [name, setName]           = useState('')
  const [description, setDescription] = useState('')
  const [loading, setLoading]     = useState(false)
  const [err, setErr]             = useState('')

  if (!user) {
    return <div style={{ padding: 20, textAlign: 'center', color: 'var(--text-3)' }}>Требуется вход...</div>
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault()
    setErr('')
    if (!name.trim()) { setErr('Введите название группы'); return }
    setLoading(true)
    try {
      await api.createGroup(name.trim(), description.trim())
      await refreshGroups()
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

      <div className="login-shell" style={{ maxWidth: 480 }}>
        <div className="login-card anim-in">
          {/* Header */}
          <div style={{ marginBottom: 26 }}>
            <div style={{
              display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
              width: 44, height: 44, borderRadius: 12,
              background: 'var(--surface-2)', border: '1px solid var(--border)',
              marginBottom: 16, boxShadow: 'var(--shadow-sm)',
            }}>
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/>
                <circle cx="9" cy="7" r="4"/>
                <path d="M23 21v-2a4 4 0 0 0-3-3.87"/>
                <path d="M16 3.13a4 4 0 0 1 0 7.75"/>
              </svg>
            </div>
            <div style={{ fontSize: 17, fontWeight: 800, color: 'var(--text)', letterSpacing: '-0.04em', marginBottom: 6 }}>
              Создайте вашу первую группу
            </div>
            <div style={{ fontSize: 12.5, color: 'var(--text-3)', lineHeight: 1.6 }}>
              Группа — изолированное рабочее пространство для управления контентом.
              Вы сможете пригласить участников и управлять их ролями.
            </div>
          </div>

          <form onSubmit={submit}>
            <div className="fg">
              <label>Название группы</label>
              <input
                type="text"
                value={name}
                onChange={e => setName(e.target.value)}
                placeholder="например: МЦ «Зеркало»"
                autoFocus
              />
            </div>

            <div className="fg">
              <label>Описание <span style={{ color: 'var(--text-3)', fontWeight: 400 }}>(опционально)</span></label>
              <textarea
                value={description}
                onChange={e => setDescription(e.target.value)}
                placeholder="Например: Медиа-центр Красноярска"
                rows={3}
                style={{ fontFamily: 'inherit', resize: 'vertical' }}
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

            <div style={{ display: 'flex', gap: 10, marginTop: 4 }}>
              <button type="button" className="btn btn-secondary" onClick={() => router.back()} style={{ flex: 1, justifyContent: 'center' }}>
                Отмена
              </button>
              <button type="submit" className="btn btn-primary" disabled={loading} style={{ flex: 2, justifyContent: 'center', height: 40, fontWeight: 600 }}>
                {loading ? (
                  <>
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" style={{ animation: 'spin 0.7s linear infinite' }}><path d="M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83M2 12h4M18 12h4M4.93 19.07l2.83-2.83M16.24 7.76l2.83-2.83"/></svg>
                    Создаём...
                  </>
                ) : (
                  <>
                    Создать группу
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><line x1="5" y1="12" x2="19" y2="12"/><polyline points="12 5 19 12 12 19"/></svg>
                  </>
                )}
              </button>
            </div>
          </form>
        </div>
      </div>
    </div>
  )
}
