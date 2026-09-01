'use client'
import { useCallback, useEffect, useState } from 'react'
import Pagination from '@/components/Pagination'
import HelpTip from '@/components/HelpTip'
import { api } from '@/lib/api'
import { useToast } from '@/contexts/ToastContext'
import { useGroup } from '@/contexts/GroupContext'
import type { PostComment } from '@/lib/types'

const PAGE_SIZE = 25

const S = { width: 14, height: 14, viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', strokeWidth: 1.75, strokeLinecap: 'round' as const, strokeLinejoin: 'round' as const }
const IcoSearch = <svg {...S}><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>

const FILTERS = [
  { v: 'pending',  l: 'Ждут ответа' },
  { v: 'answered', l: 'Отвечены' },
  { v: 'all',      l: 'Все' },
]

/**
 * Сколько осталось до срока — словами. Числом в минутах это читается плохо:
 * «осталось 372» не говорит человеку ничего, «6 часов» говорит сразу.
 */
function timeLeft(minutes: number): string {
  const abs = Math.abs(minutes)
  const days = Math.floor(abs / 1440)
  const hours = Math.floor((abs % 1440) / 60)
  const mins = abs % 60

  let text: string
  if (days > 0) {
    // За сутками минуты уже не важны: «просрочено на 2 дня 9 ч» читается,
    // «просрочено на 57 ч 3 мин» — нет.
    const word = days === 1 ? 'день' : days < 5 ? 'дня' : 'дней'
    text = `${days} ${word}${hours ? ` ${hours} ч` : ''}`
  } else if (hours > 0) {
    text = `${hours} ч${mins ? ` ${mins} мин` : ''}`
  } else {
    text = `${mins} мин`
  }
  return minutes < 0 ? `просрочено на ${text}` : `осталось ${text}`
}

/** Чем меньше времени, тем тревожнее. Просроченное — красным. */
function urgency(c: PostComment): string {
  if (c.answered_at) return 'done'
  if (c.overdue) return 'over'
  if ((c.minutes_left ?? 0) < 120) return 'soon'
  return ''
}

const fmt = (s: string | null) => {
  if (!s) return ''
  const d = new Date(s)
  return d.toLocaleDateString('ru-RU', { day: '2-digit', month: 'short' })
    + ', ' + d.toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' })
}

export default function CommentsPage() {
  const { showToast } = useToast()
  const { currentGroup } = useGroup()
  const [items, setItems] = useState<PostComment[] | null>(null)
  const [meta, setMeta] = useState({ total: 0, limit: PAGE_SIZE, offset: 0 })
  const [sla, setSla] = useState(8)
  const [filter, setFilter] = useState('pending')
  const [search, setSearch] = useState('')
  const [offset, setOffset] = useState(0)
  const [replyTo, setReplyTo] = useState<number | null>(null)
  const [replyText, setReplyText] = useState('')
  const [sending, setSending] = useState(false)

  const load = useCallback(() => {
    if (!currentGroup) return
    const params: Record<string, string> = {
      status: filter, limit: String(PAGE_SIZE), offset: String(offset),
    }
    if (search.trim()) params.q = search.trim()
    setItems(null)
    api.getComments(currentGroup.id, params)
      .then(d => {
        setItems(d.items)
        setSla(d.sla_hours)
        setMeta({ total: d.total, limit: d.limit, offset: d.offset })
      })
      .catch(e => { setItems([]); showToast((e as Error).message, 'error') })
  }, [currentGroup, filter, offset, search, showToast])

  // Поиск набирают по букве — ждём паузы, иначе запрос на каждое нажатие
  useEffect(() => {
    const t = setTimeout(load, search ? 350 : 0)
    return () => clearTimeout(t)
  }, [load, search])

  useEffect(() => { setOffset(0) }, [filter, search, currentGroup])

  async function sendReply(comment: PostComment) {
    if (!currentGroup || !replyText.trim()) return
    setSending(true)
    try {
      await api.replyToComment(currentGroup.id, comment.id, replyText.trim())
      showToast('Ответ отправлен', 'success', 'Он появится под записью во ВКонтакте')
      setReplyTo(null); setReplyText('')
      load()
    }
    catch (e: unknown) { showToast((e as Error).message, 'error') }
    finally { setSending(false) }
  }

  if (!currentGroup) {
    return (
      <div className="content">
        <div className="card card-p empty-state">
          <div className="empty-state-title">Выберите группу</div>
          <div className="empty-state-sub">Обращения приходят под публикации конкретной группы</div>
        </div>
      </div>
    )
  }

  return (
    <div className="content">
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 16, flexWrap: 'wrap' }}>
        <div className="period-seg">
          {FILTERS.map(f => (
            <button key={f.v} className={`period-seg-btn${filter === f.v ? ' active' : ''}`}
              onClick={() => setFilter(f.v)}>{f.l}</button>
          ))}
        </div>

        <div style={{ position: 'relative', flex: 1, minWidth: 180, maxWidth: 300 }}>
          <span style={{ position: 'absolute', left: 12, top: '50%', transform: 'translateY(-50%)', color: 'var(--text-3)', pointerEvents: 'none', display: 'flex' }}>
            {IcoSearch}
          </span>
          <input className="srch" placeholder="Поиск по тексту или автору..." value={search}
            onChange={e => setSearch(e.target.value)} style={{ paddingLeft: 34, width: '100%' }} />
        </div>

        <span style={{ fontSize: 12, color: 'var(--text-3)', marginLeft: 'auto', fontWeight: 500 }}>
          Срок ответа: {sla} ч
        </span>
        <HelpTip topic="comments.answered" />
      </div>

      {items === null ? (
        <div className="card card-p" style={{ color: 'var(--text-3)' }}>Загрузка...</div>
      ) : items.length === 0 ? (
        <div className="card card-p">
          <div className="empty-state" style={{ padding: '40px 24px' }}>
            <div className="empty-state-title">
              {filter === 'pending' ? 'Все обращения отвечены' : 'Обращений нет'}
            </div>
            <div className="empty-state-sub" style={{ maxWidth: '58ch' }}>
              {search
                ? 'Попробуйте изменить запрос'
                : 'Сюда попадают комментарии жителей под вашими публикациями во ВКонтакте. ' +
                  'Учреждение обязано отвечать на них, поэтому у каждого обращения есть срок, ' +
                  'а перед его истечением приходит напоминание.'}
            </div>
          </div>
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          {items.map(c => (
            <div key={c.id} className={`card comment-card ${urgency(c)}`}>
              <div className="comment-hd">
                <span className="comment-author">{c.author_name || 'Житель'}</span>
                <span className="comment-when">{fmt(c.created_at)}</span>
                {c.post_title && <span className="comment-post">под постом «{c.post_title}»</span>}
                {c.answered_at ? (
                  <span className="comment-flag done">Отвечено {fmt(c.answered_at)}</span>
                ) : (
                  <span className={`comment-flag ${urgency(c)}`}>
                    {timeLeft(c.minutes_left ?? 0)}
                  </span>
                )}
              </div>

              <div className="comment-text">{c.text || <i>без текста</i>}</div>

              {!c.answered_at && (
                replyTo === c.id ? (
                  <div className="comment-reply">
                    <textarea
                      value={replyText}
                      onChange={e => setReplyText(e.target.value)}
                      rows={3}
                      placeholder="Ответ от лица сообщества..."
                      autoFocus
                      style={{ width: '100%', resize: 'vertical' }}
                    />
                    <div style={{ display: 'flex', gap: 8, marginTop: 8 }}>
                      <button className="btn btn-primary btn-sm" disabled={sending || !replyText.trim()}
                        onClick={() => sendReply(c)}>
                        {sending ? 'Отправляем...' : 'Ответить'}
                      </button>
                      <button className="btn btn-secondary btn-sm"
                        onClick={() => { setReplyTo(null); setReplyText('') }}>Отмена</button>
                    </div>
                  </div>
                ) : (
                  <button className="btn btn-secondary btn-sm" style={{ marginTop: 10 }}
                    onClick={() => { setReplyTo(c.id); setReplyText('') }}>
                    Ответить
                  </button>
                )
              )}
            </div>
          ))}
        </div>
      )}

      <Pagination total={meta.total} limit={meta.limit} offset={meta.offset} onChange={setOffset} unit="обращений" />
    </div>
  )
}
