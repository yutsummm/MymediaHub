'use client'

import { useState, useEffect } from 'react'
import { useRouter, useParams } from 'next/navigation'
import { useAuth } from '@/contexts/AuthContext'
import { useGroup } from '@/contexts/GroupContext'
import { api } from '@/lib/api'
import type { InvitePreview } from '@/lib/types'

export default function InvitePage() {
  const router = useRouter()
  const params = useParams()
  const token = params.token as string
  const { user } = useAuth()
  const { refreshGroups } = useGroup()
  const [invite, setInvite] = useState<InvitePreview | null>(null)
  const [loading, setLoading] = useState(true)
  const [accepting, setAccepting] = useState(false)
  const [err, setErr] = useState('')

  useEffect(() => {
    const load = async () => {
      try {
        const data = await api.getInvitePreview(token)
        setInvite(data)
      } catch (ex: unknown) {
        setErr((ex as Error).message)
      } finally {
        setLoading(false)
      }
    }
    load()
  }, [token])

  async function acceptInvite() {
    if (!user) {
      router.push(`/login?redirect=/invite/${token}`)
      return
    }
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

  if (loading) {
    return <div style={{ padding: 40, textAlign: 'center' }}>Загружаем приглашение...</div>
  }

  if (!invite) {
    return (
      <div style={{
        minHeight: '100vh',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        padding: '20px',
      }}>
        <div style={{ textAlign: 'center' }}>
          <h1 style={{ fontSize: 24, marginBottom: 12 }}>Ссылка не найдена</h1>
          <p style={{ color: 'var(--text-3)' }}>
            {err || 'Это приглашение больше не действительно'}
          </p>
        </div>
      </div>
    )
  }

  const roleLabels: Record<string, string> = {
    admin: 'Администратор',
    editor: 'Редактор',
    observer: 'Наблюдатель',
  }

  return (
    <div style={{
      minHeight: '100vh',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      padding: '20px',
      background: 'var(--bg)',
    }}>
      <div style={{
        width: '100%',
        maxWidth: '500px',
        padding: '40px 30px',
        borderRadius: 'var(--r-lg)',
        border: '1px solid var(--border)',
        background: 'var(--bg-secondary)',
      }}>
        <h1 style={{ fontSize: 24, marginBottom: 8 }}>
          {invite.group_name}
        </h1>
        {invite.group_description && (
          <p style={{ fontSize: 14, color: 'var(--text-3)', marginBottom: 24 }}>
            {invite.group_description}
          </p>
        )}

        <div style={{
          padding: '16px',
          borderRadius: 'var(--r-md)',
          background: 'rgba(99,102,241,0.08)',
          border: '1px solid rgba(99,102,241,0.2)',
          marginBottom: 24,
        }}>
          <div style={{ fontSize: 12, color: 'var(--text-3)', marginBottom: 4 }}>
            Ваша роль:
          </div>
          <div style={{ fontSize: 16, fontWeight: 600, color: 'var(--accent)' }}>
            {roleLabels[invite.role] || invite.role}
          </div>
        </div>

        <div style={{
          fontSize: 12,
          color: 'var(--text-3)',
          marginBottom: 24,
          padding: '12px',
          borderRadius: 'var(--r-md)',
          background: 'rgba(107,114,128,0.1)',
        }}>
          ⏰ Действует до: {new Date(invite.expires_at).toLocaleString('ru-RU')}
        </div>

        {err && <div style={{
          padding: '10px 12px',
          borderRadius: 'var(--r-md)',
          background: 'rgba(239,68,68,0.1)',
          border: '1px solid rgba(239,68,68,0.3)',
          color: '#ef4444',
          fontSize: 14,
          marginBottom: 20,
        }}>
          {err}
        </div>}

        <button
          onClick={acceptInvite}
          disabled={accepting}
          className="btn btn-primary"
          style={{ width: '100%' }}
        >
          {accepting ? 'Присоединяемся...' : user ? 'Присоединиться' : 'Войти чтобы присоединиться'}
          {!accepting && <span className="btn-icon">→</span>}
        </button>
      </div>
    </div>
  )
}
