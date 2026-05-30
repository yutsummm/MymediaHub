'use client'
import { useState, useRef } from 'react'
import Image from 'next/image'
import { useRouter } from 'next/navigation'
import { api } from '@/lib/api'
import { useAuth } from '@/contexts/AuthContext'
import { useGroup } from '@/contexts/GroupContext'
import { useToast } from '@/contexts/ToastContext'
import type { MediaItem } from '@/lib/types'

const S16 = { width: 16, height: 16, viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', strokeWidth: 1.75, strokeLinecap: 'round' as const, strokeLinejoin: 'round' as const }

const IcoUpload = <svg {...S16}><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/></svg>
const IcoCheck = <svg {...S16}><polyline points="20 6 9 17 4 12"/></svg>
const IcoTrash = <svg {...S16}><polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/><path d="M10 11v6"/><path d="M14 11v6"/><path d="M9 6V4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2"/></svg>
const IcoSpin = <svg {...S16} style={{ animation: 'spin 0.7s linear infinite' }}><line x1="12" y1="2" x2="12" y2="6"/><line x1="12" y1="18" x2="12" y2="22"/><line x1="4.93" y1="4.93" x2="7.76" y2="7.76"/><line x1="16.24" y1="16.24" x2="19.07" y2="19.07"/><line x1="2" y1="12" x2="6" y2="12"/><line x1="18" y1="12" x2="22" y2="12"/><line x1="4.93" y1="19.07" x2="7.76" y2="16.24"/><line x1="16.24" y1="7.76" x2="19.07" y2="4.93"/></svg>

export default function VolunteerMediaUploadPage() {
  const router = useRouter()
  const { user } = useAuth()
  const { currentGroup } = useGroup()
  const { showToast } = useToast()
  const fileInputRef = useRef<HTMLInputElement | null>(null)
  const [eventName, setEventName] = useState('')
  const [files, setFiles] = useState<{ file: File; uploading?: boolean; uploaded?: MediaItem; error?: string }[]>([])
  const [submitting, setSubmitting] = useState(false)
  const [done, setDone] = useState(false)

  function handleFilePick(e: React.ChangeEvent<HTMLInputElement>) {
    const picked = Array.from(e.target.files || [])
    setFiles(prev => [...prev, ...picked.map(f => ({ file: f }))])
    if (e.target) e.target.value = ''
  }

  function removeFile(index: number) {
    setFiles(prev => prev.filter((_, i) => i !== index))
  }

  async function uploadAll(): Promise<MediaItem[]> {
    const uploaded: MediaItem[] = []
    for (let i = 0; i < files.length; i++) {
      const item = files[i]
      if (item.uploaded) { uploaded.push(item.uploaded); continue }
      setFiles(prev => prev.map((f, j) => j === i ? { ...f, uploading: true, error: undefined } : f))
      try {
        const result = await api.uploadFile(item.file)
        setFiles(prev => prev.map((f, j) => j === i ? { ...f, uploading: false, uploaded: result } : f))
        uploaded.push(result)
      } catch (e: unknown) {
        const msg = (e as Error).message
        setFiles(prev => prev.map((f, j) => j === i ? { ...f, uploading: false, error: msg } : f))
      }
    }
    return uploaded
  }

  async function handleSubmit() {
    if (!eventName.trim()) { showToast('Укажите название мероприятия', 'error'); return }
    if (files.length === 0) { showToast('Добавьте хотя бы один файл', 'error'); return }
    if (!currentGroup) { showToast('Выберите группу', 'error'); return }
    setSubmitting(true)
    try {
      const media = await uploadAll()
      if (media.length === 0) { showToast('Не удалось загрузить файлы', 'error'); setSubmitting(false); return }
      await api.createVolunteerMedia(currentGroup.id, { event_name: eventName.trim(), media })
      setDone(true)
      showToast('Медиа отправлены! SMM-щик их увидит', 'success')
    } catch (e: unknown) {
      showToast((e as Error).message, 'error')
    } finally {
      setSubmitting(false)
    }
  }

  if (done) {
    return (
      <div className="content">
        <div className="card card-p" style={{ maxWidth: 480, margin: '40px auto', textAlign: 'center' }}>
          <div style={{
            display: 'inline-flex', width: 64, height: 64, borderRadius: 20,
            background: 'var(--green-dim)', border: '1px solid rgba(16,185,129,0.2)',
            alignItems: 'center', justifyContent: 'center', marginBottom: 20, color: 'var(--green)',
          }}>{IcoCheck}</div>
          <h2 style={{ fontSize: 18, fontWeight: 700, marginBottom: 8 }}>Медиа загружены!</h2>
          <p style={{ fontSize: 13, color: 'var(--text-3)', marginBottom: 24, lineHeight: 1.6 }}>
            Фото и видео с «{eventName}» отправлены SMM-щику.
            Следить за статусом можно в разделе «Мои загрузки».
          </p>
          <div style={{ display: 'flex', gap: 10, justifyContent: 'center' }}>
            <button className="btn btn-primary" onClick={() => { setDone(false); setEventName(''); setFiles([]) }}>
              Загрузить ещё
            </button>
            <button className="btn btn-secondary" onClick={() => router.push('/volunteer-media/my')}>
              Мои загрузки
            </button>
          </div>
        </div>
      </div>
    )
  }

  const hasUploading = files.some(f => f.uploading)

  return (
    <div className="content">
      <div style={{ maxWidth: 560, margin: '0 auto' }}>
        <div className="card card-p">
          <h2 style={{ fontSize: 16, fontWeight: 700, marginBottom: 6, letterSpacing: '-0.02em' }}>
            Загрузить фото/видео с мероприятия
          </h2>
          <p className="ts tg" style={{ marginBottom: 22 }}>
            Снимки попадут к SMM-щику, который отберёт лучшие для публикации
          </p>

          <div className="fg">
            <label>Название мероприятия</label>
            <input
              type="text"
              value={eventName}
              onChange={e => setEventName(e.target.value)}
              placeholder="Например: Хакатон IT-Кубок"
              disabled={submitting}
            />
          </div>

          <div className="fg">
            <label>Фото и видео</label>
            <input
              ref={fileInputRef}
              type="file"
              multiple
              accept="image/jpeg,image/png,image/gif,image/webp,video/mp4,video/quicktime,video/webm"
              style={{ display: 'none' }}
              onChange={handleFilePick}
              disabled={submitting}
            />

            {files.length > 0 && (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 8, marginBottom: 12 }}>
                {files.map((item, i) => {
                  const ext = item.file.name.split('.').pop()?.toLowerCase() || ''
                  const isImage = ['jpg', 'jpeg', 'png', 'gif', 'webp'].includes(ext)
                  const url = item.uploaded?.url ? URL.createObjectURL(item.file) : ''
                  return (
                    <div key={i} style={{
                      display: 'flex', alignItems: 'center', gap: 12,
                      padding: '10px 12px', borderRadius: 'var(--r-md)',
                      background: 'var(--surface-2)', border: '1px solid var(--border)',
                    }}>
                      <div style={{
                        width: 40, height: 40, borderRadius: 'var(--r-sm)',
                        background: 'var(--surface)', flexShrink: 0,
                        display: 'flex', alignItems: 'center', justifyContent: 'center',
                        overflow: 'hidden', fontSize: 20,
                      }}>
                        {item.uploaded && isImage && item.uploaded.url
                          ? <Image src={item.uploaded.url} alt="" width={40} height={40} style={{ objectFit: 'cover' }} />
                          : isImage ? '📷' : '🎬'}
                      </div>
                      <div style={{ flex: 1, minWidth: 0 }}>
                        <div className="trunc" style={{ fontSize: 12.5, fontWeight: 600 }}>{item.file.name}</div>
                        <div style={{ fontSize: 11, color: item.error ? 'var(--red)' : 'var(--text-3)' }}>
                          {item.error ? `Ошибка: ${item.error}` : item.uploaded ? 'Загружено ✓' : `${(item.file.size / 1024 / 1024).toFixed(1)} МБ`}
                        </div>
                      </div>
                      {item.uploading ? (
                        <span style={{ color: 'var(--text-3)' }}>{IcoSpin}</span>
                      ) : !item.uploaded ? (
                        <button onClick={() => removeFile(i)} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text-3)', padding: 4 }} title="Удалить">
                          {IcoTrash}
                        </button>
                      ) : (
                        <span style={{ color: 'var(--green)' }}>{IcoCheck}</span>
                      )}
                    </div>
                  )
                })}
              </div>
            )}

            <button
              type="button"
              className="btn btn-secondary"
              onClick={() => fileInputRef.current?.click()}
              disabled={submitting}
              style={{ alignSelf: 'flex-start' }}
            >
              + Выбрать файлы
            </button>
            {files.length > 0 && (
              <div className="ts tg" style={{ marginTop: 6 }}>{files.length} файл(ов) выбрано</div>
            )}
          </div>

          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 10 }}>
            <button className="btn btn-secondary" onClick={() => router.back()} disabled={submitting}>
              Отмена
            </button>
            <button className="btn btn-primary" onClick={handleSubmit} disabled={submitting || !eventName.trim() || files.length === 0}>
              {submitting ? (
                <>{IcoSpin} Загружаем...</>
              ) : (
                <>{IcoUpload} Отправить SMM-щику</>
              )}
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
