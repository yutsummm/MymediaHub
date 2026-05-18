'use client'
import { useState } from 'react'
import { useRouter } from 'next/navigation'
import { api } from '@/lib/api'
import { useToast } from '@/contexts/ToastContext'
import { useGroup } from '@/contexts/GroupContext'

export default function QuickPostModal({ onClose, scheduledDate, onSaved }: {
  onClose: () => void
  scheduledDate?: string
  onSaved?: () => void
}) {
  const [title, setTitle]     = useState('')
  const [content, setContent] = useState('')
  const [saving, setSaving]   = useState(false)
  const { showToast }         = useToast()
  const { currentGroup }      = useGroup()
  const router                = useRouter()

  async function save() {
    if (!title.trim() || saving) return
    setSaving(true)
    try {
      const post = await api.createPost({
        title:        title.trim(),
        content:      content.trim(),
        status:       scheduledDate ? 'scheduled' : 'draft',
        scheduled_at: scheduledDate ? `${scheduledDate}T09:00` : undefined,
        platforms:    [],
        tags:         [],
        group_id:     currentGroup?.id,
      }) as { id: number }
      showToast('Черновик создан', 'success', `«${title.trim()}» — откроется в редакторе`)
      onSaved?.()
      onClose()
      router.push(`/posts/${post.id}/edit`)
    } catch (e: unknown) {
      showToast((e as Error).message, 'error')
    } finally {
      setSaving(false)
    }
  }

  function onRootKey(e: React.KeyboardEvent) {
    if (e.key === 'Escape') onClose()
  }

  function onBodyKey(e: React.KeyboardEvent) {
    if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') { e.preventDefault(); save() }
  }

  return (
    <div className="overlay" onClick={onClose} onKeyDown={onRootKey}>
      <div className="quick-post-modal" onClick={e => e.stopPropagation()} onKeyDown={onBodyKey}>

        <div className="qpm-header">
          <span className="qpm-header-title">Новый черновик</span>
          <button
            className="btn btn-ghost btn-sm"
            style={{ fontSize: 20, padding: '1px 8px', lineHeight: 1 }}
            onClick={onClose}
            aria-label="Закрыть"
          >×</button>
        </div>

        <div className="qpm-body">
          <input
            className="qpm-title-input"
            placeholder="Заголовок поста..."
            value={title}
            onChange={e => setTitle(e.target.value)}
            autoFocus
          />
          <div className="qpm-divider" />
          <textarea
            className="qpm-content-input"
            placeholder="Начните писать текст..."
            value={content}
            onChange={e => setContent(e.target.value)}
            rows={5}
          />
        </div>

        <div className="qpm-footer">
          <span className="qpm-hint">⌘↵ — сохранить</span>
          <button className="btn btn-ghost btn-sm" onClick={onClose}>Отмена</button>
          <button
            className="btn btn-primary btn-sm"
            onClick={save}
            disabled={!title.trim() || saving}
          >
            {saving ? 'Создание...' : 'Сохранить черновик →'}
          </button>
        </div>

      </div>
    </div>
  )
}
