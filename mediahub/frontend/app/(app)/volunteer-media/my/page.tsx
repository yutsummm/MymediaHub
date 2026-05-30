'use client'
import { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import { api } from '@/lib/api'
import { useAuth } from '@/contexts/AuthContext'
import { useGroup } from '@/contexts/GroupContext'
import { useToast } from '@/contexts/ToastContext'
import type { VolunteerMedia, MediaItem } from '@/lib/types'

const S = { width: 14, height: 14, viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', strokeWidth: 1.75, strokeLinecap: 'round' as const, strokeLinejoin: 'round' as const }
const IcoTrash = <svg {...S}><polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/><path d="M10 11v6"/><path d="M14 11v6"/><path d="M9 6V4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2"/></svg>
const IcoBack = <svg {...S}><line x1="19" y1="12" x2="5" y2="12"/><polyline points="12 19 5 12 12 5"/></svg>
const IcoUp = <svg {...S}><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/></svg>

const S31 = { width: 31, height: 31, viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', strokeWidth: 1.2, strokeLinecap: 'round' as const, strokeLinejoin: 'round' as const }
const IcoEmpty = <svg {...S31}><rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="8.5" cy="8.5" r="1.5"/><polyline points="21 15 16 10 5 21"/></svg>

const STATUS_LABEL: Record<string, string> = { pending: 'На рассмотрении', approved: 'Одобрено', rejected: 'Отклонено' }
const STATUS_CLASS: Record<string, string> = { pending: 's-draft', approved: 's-published', rejected: 's-scheduled' }

export default function MyUploadsPage() {
  const router = useRouter()
  const { user } = useAuth()
  const { currentGroup } = useGroup()
  const { showToast } = useToast()
  const [items, setItems] = useState<VolunteerMedia[] | null>(null)
  const [loading, setLoading] = useState(true)
  const [deleting, setDeleting] = useState<number | null>(null)

  function load() {
    if (!currentGroup) return
    setLoading(true)
    api.getVolunteerMedia(currentGroup.id, { user_id: String(user?.id) })
      .then(setItems)
      .catch(console.error)
      .finally(() => setLoading(false))
  }

  useEffect(load, [currentGroup])

  async function handleDelete(item: VolunteerMedia) {
    if (!confirm(`Удалить медиа с мероприятия «${item.event_name}»?`)) return
    if (!currentGroup) return
    setDeleting(item.id)
    try {
      await api.deleteVolunteerMedia(currentGroup.id, item.id)
      showToast('Удалено', 'success')
      load()
    } catch (e: unknown) {
      showToast((e as Error).message, 'error')
    } finally {
      setDeleting(null)
    }
  }

  function getPreview(m: MediaItem) {
    const isImg = m.type === 'image'
    return { isImg, url: m.url || '' }
  }

  return (
    <div className="content">
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 20 }}>
        <button className="btn btn-ghost btn-sm" onClick={() => router.back()}>{IcoBack} Назад</button>
        <h2 style={{ fontSize: 18, fontWeight: 700, margin: 0 }}>Мои загрузки</h2>
        <button className="btn btn-primary btn-sm" onClick={() => router.push('/volunteer-media/upload')} style={{ marginLeft: 'auto' }}>
          {IcoUp} Загрузить
        </button>
      </div>

      {loading ? (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))', gap: 12 }}>
          {[0,1,2].map(i => (
            <div key={i} className="card" style={{ height: 140 }}>
              <div className="skeleton skeleton-text" style={{ width: '60%', marginBottom: 12 }} />
              <div className="skeleton skeleton-text" style={{ width: '40%' }} />
            </div>
          ))}
        </div>
      ) : !items || items.length === 0 ? (
        <div className="card" style={{ padding: '60px 24px', textAlign: 'center' }}>
          <div style={{ color: 'var(--text-3)', marginBottom: 16, display: 'inline-block' }}>{IcoEmpty}</div>
          <div style={{ fontSize: 15, fontWeight: 600, marginBottom: 6 }}>Вы ещё ничего не загружали</div>
          <div style={{ fontSize: 12.5, color: 'var(--text-3)', marginBottom: 20, lineHeight: 1.6 }}>
            Фото и видео с мероприятий можно загрузить<br/>через форму добавления медиа
          </div>
          <button className="btn btn-primary" onClick={() => router.push('/volunteer-media/upload')}>
            Загрузить фото/видео
          </button>
        </div>
      ) : (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(320px, 1fr))', gap: 12 }}>
          {items.map(item => (
            <div key={item.id} className="card">
              <div style={{ padding: '14px 16px', borderBottom: '1px solid var(--border)' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                  <div>
                    <div style={{ fontWeight: 700, fontSize: 14, marginBottom: 4 }}>{item.event_name}</div>
                    <div style={{ fontSize: 11, color: 'var(--text-3)' }}>
                      {new Date(item.created_at).toLocaleDateString('ru-RU', { day: '2-digit', month: 'long', year: 'numeric' })}
                      {' · '}{item.media.length} файл(ов)
                    </div>
                  </div>
                  <span className={`sbadge ${STATUS_CLASS[item.status]}`}>{STATUS_LABEL[item.status]}</span>
                </div>
              </div>

              {item.media.length > 0 && (
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 2, padding: 2 }}>
                  {item.media.slice(0, 6).map((m, i) => {
                    const { isImg, url } = getPreview(m)
                    return (
                      <a key={i} href={url} target="_blank" rel="noopener noreferrer"
                        style={{
                          aspectRatio: '1', borderRadius: 'var(--r-sm)',
                          background: 'var(--surface-2)', overflow: 'hidden',
                          display: 'flex', alignItems: 'center', justifyContent: 'center',
                          fontSize: 22, cursor: 'pointer',
                        }}
                      >
                        {isImg ? (
                          <img src={url} alt="" style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
                        ) : (
                          <span>🎬</span>
                        )}
                      </a>
                    )
                  })}
                  {item.media.length > 6 && (
                    <div style={{
                      aspectRatio: '1', borderRadius: 'var(--r-sm)',
                      background: 'var(--surface-2)',
                      display: 'flex', alignItems: 'center', justifyContent: 'center',
                      fontSize: 13, fontWeight: 700, color: 'var(--text-3)',
                    }}>
                      +{item.media.length - 6}
                    </div>
                  )}
                </div>
              )}

              <div style={{ padding: '10px 16px', display: 'flex', justifyContent: 'flex-end', gap: 8 }}>
                <button
                  className="btn btn-ghost btn-sm"
                  onClick={() => handleDelete(item)}
                  disabled={deleting === item.id}
                  style={{ color: 'var(--red)' }}
                >
                  {deleting === item.id ? '...' : <>{IcoTrash} Удалить</>}
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
