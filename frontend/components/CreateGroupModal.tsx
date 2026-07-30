'use client'
import { useState } from 'react'
import { useGroup } from '@/contexts/GroupContext'
import { api } from '@/lib/api'

export default function CreateGroupModal({ onClose }: { onClose?: () => void }) {
  const { refreshGroups } = useGroup()
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [err, setErr] = useState('')

  async function submit(e: React.FormEvent) {
    e.preventDefault()
    setErr('')
    if (!name.trim()) {
      setErr('Введите название группы')
      return
    }
    setSubmitting(true)
    try {
      await api.createGroup(name.trim(), description.trim())
      await refreshGroups()
    } catch (ex: unknown) {
      setErr((ex as Error).message)
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div style={{
      position: 'fixed',
      inset: 0,
      background: 'rgba(0,0,0,0.7)',
      backdropFilter: 'blur(8px)',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      padding: '20px',
      zIndex: 1000,
    }}>
      <div style={{
        width: '100%',
        maxWidth: '500px',
        padding: '40px 30px',
        borderRadius: 'var(--r-xl)',
        border: '1px solid var(--border-2)',
        background: 'var(--bg-2)',
        boxShadow: 'var(--shadow-card)',
        position: 'relative',
      }}>
        {onClose && (
          <button
            type="button"
            onClick={onClose}
            style={{
              position: 'absolute',
              top: 16,
              right: 16,
              background: 'none',
              border: 'none',
              cursor: 'pointer',
              color: 'var(--text-3)',
              fontSize: 20,
              lineHeight: 1,
              padding: 4,
            }}
            aria-label="Закрыть"
          >
            ✕
          </button>
        )}
        <div style={{
          width: 44, height: 44,
          borderRadius: 'var(--r-md)',
          background: 'linear-gradient(135deg, var(--accent), var(--accent-2))',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          fontSize: 20, marginBottom: 20,
          boxShadow: '0 0 18px var(--accent-glow)',
        }}>
          👥
        </div>
        <h1 style={{ fontSize: 24, marginBottom: 8, color: 'var(--text)', fontWeight: 800, letterSpacing: '-0.03em' }}>
          Создайте вашу первую группу
        </h1>
        <p style={{ fontSize: 14, color: 'var(--text-3)', marginBottom: 24 }}>
          Группа — это изолированное рабочее пространство для управления контентом
          вашего медиа-центра. Вы сможете пригласить других участников и управлять их ролями.
        </p>

        <form onSubmit={submit}>
          <div className="fg" style={{ marginBottom: 16 }}>
            <label>Название группы</label>
            <input
              type="text"
              value={name}
              onChange={e => setName(e.target.value)}
              placeholder="например: МЦ «Зеркало»"
              autoFocus
            />
          </div>

          <div className="fg" style={{ marginBottom: 20 }}>
            <label>Описание (опционально)</label>
            <textarea
              value={description}
              onChange={e => setDescription(e.target.value)}
              placeholder="Например: Медиа-центр Красноярска"
              rows={3}
              style={{ fontFamily: 'inherit' }}
            />
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
            type="submit"
            className="btn btn-primary"
            disabled={submitting}
            style={{ width: '100%' }}
          >
            {submitting ? 'Создаём...' : 'Создать группу'}
            {!submitting && <span className="btn-icon">→</span>}
          </button>
        </form>
      </div>
    </div>
  )
}
