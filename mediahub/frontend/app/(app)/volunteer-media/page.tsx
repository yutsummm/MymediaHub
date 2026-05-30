'use client'
import { useEffect, useState, useCallback } from 'react'
import { api } from '@/lib/api'
import { useAuth } from '@/contexts/AuthContext'
import { useGroup } from '@/contexts/GroupContext'
import { useToast } from '@/contexts/ToastContext'
import type { VolunteerMedia, MediaItem } from '@/lib/types'

const S = { width: 14, height: 14, viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', strokeWidth: 1.75, strokeLinecap: 'round' as const, strokeLinejoin: 'round' as const }
const IcoCheck = <svg {...S}><polyline points="20 6 9 17 4 12"/></svg>
const IcoX = <svg {...S}><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
const IcoDownload = <svg {...S}><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>
const IcoSearch = <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>

const STATUS_LABEL: Record<string, string> = { pending: 'На рассмотрении', approved: 'Одобрено', rejected: 'Отклонено' }
const STATUS_CLASS: Record<string, string> = { pending: 's-draft', approved: 's-published', rejected: 's-scheduled' }
const STATUSES = [
  { v: '',          l: 'Все' },
  { v: 'pending',   l: 'На рассмотрении' },
  { v: 'approved',  l: 'Одобренные' },
  { v: 'rejected',  l: 'Отклонённые' },
]

const MODAL_IMG = { position: 'fixed' as const, inset: 0, zIndex: 1000, background: 'rgba(0,0,0,0.85)', display: 'flex', alignItems: 'center', justifyContent: 'center', cursor: 'zoom-out', padding: 24 }

export default function VolunteerMediaGalleryPage() {
  const { user } = useAuth()
  const { currentGroup } = useGroup()
  const { showToast } = useToast()
  const [items, setItems] = useState<VolunteerMedia[] | null>(null)
  const [loading, setLoading] = useState(true)
  const [filter, setFilter] = useState('')
  const [searchEvent, setSearchEvent] = useState('')
  const [previewUrl, setPreviewUrl] = useState<string | null>(null)
  const [updating, setUpdating] = useState<number | null>(null)

  const load = useCallback(() => {
    if (!currentGroup) return
    setLoading(true)
    const params: Record<string, string> = {}
    if (filter) params.status = filter
    if (searchEvent.trim()) params.event = searchEvent.trim()
    api.getVolunteerMedia(currentGroup.id, params)
      .then(d => setItems(d.items))
      .catch(console.error)
      .finally(() => setLoading(false))
  }, [currentGroup, filter, searchEvent])

  useEffect(load, [load])

  async function handleStatus(item: VolunteerMedia, status: string) {
    if (!currentGroup) return
    setUpdating(item.id)
    try {
      await api.updateVolunteerMediaStatus(currentGroup.id, item.id, status)
      showToast(status === 'approved' ? 'Одобрено ✓' : 'Отклонено', 'success')
      load()
    } catch (e: unknown) {
      showToast((e as Error).message, 'error')
    } finally {
      setUpdating(null)
    }
  }

  function getPreview(m: MediaItem) {
    const isImg = m.type === 'image'
    return { isImg, url: m.url || '' }
  }

  async function downloadFile(m: MediaItem) {
    const url = m.url
    if (!url) return
    try {
      const response = await fetch(url)
      const blob = await response.blob()
      const a = document.createElement('a')
      a.href = URL.createObjectURL(blob)
      a.download = m.filename || 'file'
      a.click()
      URL.revokeObjectURL(a.href)
    } catch {
      window.open(url, '_blank')
    }
  }

  const isSmm = user?.role === 'editor' || user?.role === 'admin'

  return (
    <div className="content">
      {/* Preview modal */}
      {previewUrl && (
        <div style={MODAL_IMG} onClick={() => setPreviewUrl(null)}>
          <img src={previewUrl} alt="" style={{ maxWidth: '90vw', maxHeight: '90vh', borderRadius: 8, objectFit: 'contain' }} />
        </div>
      )}

      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 16, flexWrap: 'wrap' }}>
        <h2 style={{ fontSize: 18, fontWeight: 700, margin: 0 }}>Медиа от волонтёров</h2>

        <div className="period-seg" style={{ marginLeft: 12 }}>
          {STATUSES.map(s => (
            <button
              key={s.v}
              className={`period-seg-btn${filter === s.v ? ' active' : ''}`}
              onClick={() => setFilter(s.v)}
            >
              {s.l}
            </button>
          ))}
        </div>

        <div style={{ position: 'relative', flex: 1, minWidth: 160, maxWidth: 240 }}>
          <span style={{ position: 'absolute', left: 10, top: '50%', transform: 'translateY(-50%)', color: 'var(--text-3)', display: 'flex' }}>
            {IcoSearch}
          </span>
          <input
            className="srch"
            placeholder="Поиск по мероприятию..."
            value={searchEvent}
            onChange={e => setSearchEvent(e.target.value)}
            style={{ paddingLeft: 30, width: '100%', fontSize: 12.5 }}
          />
        </div>
      </div>

      {/* Content */}
      {loading ? (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(300px, 1fr))', gap: 12 }}>
          {[0,1,2,3].map(i => (
            <div key={i} className="card" style={{ height: 200 }}>
              <div className="skeleton skeleton-text" style={{ width: '50%', marginBottom: 12 }} />
              <div className="skeleton" style={{ width: '100%', height: 100, borderRadius: 'var(--r-sm)', marginBottom: 8 }} />
              <div className="skeleton skeleton-text" style={{ width: '70%' }} />
            </div>
          ))}
        </div>
      ) : !items || items.length === 0 ? (
        <div className="card" style={{ padding: '60px 24px', textAlign: 'center' }}>
          <div style={{ fontSize: 15, fontWeight: 600, marginBottom: 6 }}>Медиа от волонтёров пока нет</div>
          <div style={{ fontSize: 12.5, color: 'var(--text-3)' }}>
            {filter || searchEvent ? 'Попробуйте изменить фильтры' : 'После загрузки они появятся здесь'}
          </div>
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          {items.map(item => (
            <div key={item.id} className="card">
              {/* Header row */}
              <div style={{ padding: '14px 18px', borderBottom: '1px solid var(--border)', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                <div>
                  <div style={{ fontWeight: 700, fontSize: 15, marginBottom: 2 }}>{item.event_name}</div>
                  <div style={{ fontSize: 11.5, color: 'var(--text-3)' }}>
                    {item.user_name && `${item.user_name} · `}
                    {new Date(item.created_at).toLocaleDateString('ru-RU', { day: '2-digit', month: 'long', year: 'numeric' })}
                    {' · '}{item.media.length} файл(ов)
                  </div>
                </div>
                <span className={`sbadge ${STATUS_CLASS[item.status]}`} style={{ fontSize: 11.5, padding: '3px 12px' }}>
                  {STATUS_LABEL[item.status]}
                </span>
              </div>

              {/* Media grid */}
              <div style={{
                display: 'grid',
                gridTemplateColumns: 'repeat(auto-fill, minmax(140px, 1fr))',
                gap: 2, padding: 2,
              }}>
                {item.media.map((m, i) => {
                  const { isImg, url } = getPreview(m)
                  return (
                    <div key={i} style={{
                      position: 'relative',
                      aspectRatio: '1',
                      borderRadius: 'var(--r-sm)',
                      background: 'var(--surface-2)',
                      overflow: 'hidden',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      cursor: isImg ? 'zoom-in' : 'default',
                    }}>
                      {isImg ? (
                        <img
                          src={url}
                          alt={m.filename || ''}
                          style={{ width: '100%', height: '100%', objectFit: 'cover' }}
                          onClick={() => setPreviewUrl(url)}
                        />
                      ) : (
                        <video src={url} style={{ width: '100%', height: '100%', objectFit: 'cover' }} controls />
                      )}

                      {/* Overlay on hover */}
                      <div style={{
                        position: 'absolute', inset: 0,
                        background: 'rgba(0,0,0,0.5)',
                        opacity: 0,
                        transition: 'opacity var(--dur-fast)',
                        display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 6,
                      }}
                        className="media-overlay"
                        onMouseEnter={e => e.currentTarget.style.opacity = '1'}
                        onMouseLeave={e => e.currentTarget.style.opacity = '0'}
                      >
                        <button
                          onClick={() => downloadFile(m)}
                          style={{
                            width: 32, height: 32, borderRadius: 6, border: 'none',
                            background: 'rgba(255,255,255,0.2)', color: 'white',
                            cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center',
                          }}
                          title="Скачать"
                        >
                          {IcoDownload}
                        </button>
                      </div>
                    </div>
                  )
                })}
              </div>

              {/* Actions */}
              {isSmm && item.status === 'pending' && (
                <div style={{ padding: '10px 18px', borderTop: '1px solid var(--border)', display: 'flex', justifyContent: 'flex-end', gap: 8 }}>
                  <button
                    className="btn btn-ghost btn-sm"
                    onClick={() => handleStatus(item, 'rejected')}
                    disabled={updating === item.id}
                    style={{ color: 'var(--red)' }}
                  >
                    {IcoX} Отклонить
                  </button>
                  <button
                    className="btn btn-primary btn-sm"
                    onClick={() => handleStatus(item, 'approved')}
                    disabled={updating === item.id}
                    style={{ background: 'var(--green)', borderColor: 'var(--green)' }}
                  >
                    {IcoCheck} Одобрить
                  </button>
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
