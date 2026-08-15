'use client'
import { useEffect, useRef, useState, type ReactNode } from 'react'
import { useRouter } from 'next/navigation'
import Image from 'next/image'
import dynamic from 'next/dynamic'
import EmojiPicker, { EmojiClickData, Theme } from 'emoji-picker-react'
import { api } from '@/lib/api'
import { useToast } from '@/contexts/ToastContext'
import { useGroup } from '@/contexts/GroupContext'
import { useAuth } from '@/contexts/AuthContext'
import { applyEmojiSuggestion, getEmojiSuggestions } from '@/lib/postUtils'
import type { MediaItem, Post, Template } from '@/lib/types'

/* ── SVG props ── */
const S14 = { width: 14, height: 14, viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', strokeWidth: 1.75, strokeLinecap: 'round' as const, strokeLinejoin: 'round' as const }
const S16 = { width: 16, height: 16, viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', strokeWidth: 1.75, strokeLinecap: 'round' as const, strokeLinejoin: 'round' as const }

/* ── Template card icons ── */
const SI = { width: 22, height: 22, viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', strokeWidth: 1.6, strokeLinecap: 'round' as const, strokeLinejoin: 'round' as const }
const TSVG: Record<string, ReactNode> = {
  announcement: <svg {...SI}>
    <path d="M22 2 11 13"/><path d="M22 2 15 22l-4-9-9-4 20-7z"/>
  </svg>,
  results: <svg {...SI}>
    <path d="M7 4h10v6a5 5 0 0 1-10 0V4z"/>
    <path d="M5 4H4a1 1 0 0 0 0 6h3M19 4h1a1 1 0 0 1 0 6h-3"/>
    <path d="M12 15v6M9 21h6"/>
    <path d="M9.5 8.5l1.5 1.5 3-3"/>
  </svg>,
  vacancy: <svg {...SI}>
    <rect x="2" y="7" width="20" height="14" rx="2"/>
    <path d="M16 7V5a2 2 0 0 0-4 0v2M8 7V5a2 2 0 0 1 4 0"/>
    <path d="M12 12v4M10 14h4"/>
  </svg>,
  grant: <svg {...SI}>
    <circle cx="12" cy="8" r="5"/>
    <path d="M8.5 13.5 7 21l5-2.5L17 21l-1.5-7.5"/>
    <path d="M10 7l1.5 2L14 7"/>
  </svg>,
}
const TSVG_BLANK = <svg {...SI}>
  <path d="M12 20h9"/><path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4L16.5 3.5z"/>
</svg>

/* ── Shared icons ── */
const IcoCheck = <svg {...S16}><polyline points="20 6 9 17 4 12"/></svg>
const IcoSend  = <svg {...S16}><line x1="22" y1="2" x2="11" y2="13"/><polygon points="22 2 15 22 11 13 2 9 22 2"/></svg>
const IcoAI    = <svg {...S16}><path d="m12 3-1.912 5.813a2 2 0 0 1-1.275 1.275L3 12l5.813 1.912a2 2 0 0 1 1.275 1.275L12 21l1.912-5.813a2 2 0 0 1 1.275-1.275L21 12l-5.813-1.912a2 2 0 0 1-1.275-1.275L12 3z"/></svg>
const IcoSmile = <svg {...S14}><circle cx="12" cy="12" r="10"/><path d="M8 13s1.5 2 4 2 4-2 4-2"/><line x1="9" y1="9" x2="9.01" y2="9"/><line x1="15" y1="9" x2="15.01" y2="9"/></svg>

const STEPS = [{ n: 1, l: 'Шаблон' }, { n: 2, l: 'Данные' }, { n: 3, l: 'Редактор' }, { n: 4, l: 'Публикация' }]

type AiMode = 'creative' | 'formal' | 'calltoaction'
type AiModifier = 'shortify' | 'hashtags' | 'russify'

const AI_MODES_CONFIG: { id: AiMode; icon: ReactNode; title: string; info: string }[] = [
  { id: 'creative',     icon: <svg {...S14}><path d="m21.64 3.64-1.28-1.28a1.21 1.21 0 0 0-1.72 0L2.36 18.64a1.21 1.21 0 0 0 0 1.72l1.28 1.28a1.2 1.2 0 0 0 1.72 0L21.64 5.36a1.2 1.2 0 0 0 0-1.72z"/><path d="m14 7 3 3"/></svg>,    title: 'Улучшить текст',    info: 'Переписывает текст для молодёжной аудитории: добавляет энергичность и эмодзи, сохраняя все факты, даты и имена' },
  { id: 'formal',       icon: <svg {...S14}><line x1="3" x2="21" y1="22" y2="22"/><line x1="6" x2="6" y1="18" y2="11"/><line x1="10" x2="10" y1="18" y2="11"/><line x1="14" x2="14" y1="18" y2="11"/><line x1="18" x2="18" y1="18" y2="11"/><polygon points="12 2 20 7 4 7"/></svg>, title: 'Официальный тон',   info: 'Переводит в нейтрально-деловой стиль — подходит для объявлений, вакансий и грантовых постов' },
  { id: 'calltoaction', icon: <svg {...S14}><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/></svg>,                                                                                                                                                                                   title: 'Призыв к действию', info: 'Дописывает сильный CTA — «зарегистрируйся», «приходи», «поделись» — по теме поста' },
]

const AI_MODIFIERS_CONFIG: { id: AiModifier; icon: ReactNode; title: string; info: string }[] = [
  { id: 'shortify', icon: <svg {...S14}><circle cx="6" cy="6" r="3"/><circle cx="6" cy="18" r="3"/><line x1="20" y1="4" x2="8.12" y2="15.88"/><line x1="14.47" y1="14.48" x2="20" y2="20"/><line x1="8.12" y1="8.12" x2="12" y2="12"/></svg>, title: 'Сократить',   info: 'Сокращает пост вдвое: убирает лишние слова и повторы, сохраняя ключевые факты и смысл' },
  { id: 'hashtags', icon: <svg {...S14}><line x1="4" y1="9" x2="20" y2="9"/><line x1="4" y1="15" x2="20" y2="15"/><line x1="10" y1="3" x2="8" y2="21"/><line x1="16" y1="3" x2="14" y2="21"/></svg>,                                          title: 'Хештеги',     info: 'Анализирует тему поста и добавляет 7–10 актуальных хештегов для ВКонтакте и Telegram в конец' },
  { id: 'russify',  icon: <svg {...S14}><polyline points="4 7 4 4 20 4 20 7"/><line x1="9" y1="20" x2="15" y2="20"/><line x1="12" y1="4" x2="12" y2="20"/></svg>,                                                                               title: 'Русификация', info: 'Заменяет иностранные слова на естественные русские: фидбек→отклик, дедлайн→срок, контент→публикации' },
]

type PostEditorProps = {
  editPost?: Post
  initialStatus?: 'draft' | 'scheduled' | 'published'
  initialScheduledAt?: string
  initialLocationAddress?: string
  initialLocationLat?: number | null
  initialLocationLng?: number | null
}

type LocationPickerPayload = {
  address: string
  lat: number | null
  lng: number | null
}

type LocationPickerProps = {
  open: boolean
  initialAddress?: string
  initialLat?: number | null
  initialLng?: number | null
  onClose: () => void
  onSelect: (payload: LocationPickerPayload) => void
}

const EventLocationPickerModal = dynamic<LocationPickerProps>(
  () => import('@/components/EventLocationPickerModal'),
  { ssr: false }
)

export default function PostEditor({
  editPost,
  initialStatus,
  initialScheduledAt,
  initialLocationAddress,
  initialLocationLat,
  initialLocationLng,
}: PostEditorProps) {
  const router = useRouter()
  const { showToast } = useToast()
  const { currentGroup } = useGroup()
  const { user } = useAuth()
  const isEdit = !!editPost
  const textareaRef = useRef<HTMLTextAreaElement | null>(null)
  const emojiCloseTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  const [step, setStep] = useState(isEdit ? 3 : 1)
  const [tmplType, setTmplType] = useState(editPost?.template_type ?? '')
  const [tmpls, setTmpls] = useState<Template[]>([])
  const [fields, setFields] = useState<Record<string, string>>({})
  const [title, setTitle] = useState(editPost?.title ?? '')
  const [content, setContent] = useState(editPost?.content ?? '')
  const [platforms, setPlatforms] = useState<string[]>(editPost?.platforms ?? ['vk'])
  const [tags, setTags] = useState<string[]>(editPost?.tags ?? [])
  const [status, setStatus] = useState<'draft' | 'scheduled' | 'published'>(editPost?.status ?? initialStatus ?? 'draft')
  const [schedAt, setSchedAt] = useState(editPost?.scheduled_at ? editPost.scheduled_at.slice(0, 16) : initialScheduledAt ?? '')
  const [locationAddress, setLocationAddress] = useState(editPost?.location_address ?? initialLocationAddress ?? '')
  const [locationLat, setLocationLat] = useState<number | null>(editPost?.location_lat ?? initialLocationLat ?? null)
  const [locationLng, setLocationLng] = useState<number | null>(editPost?.location_lng ?? initialLocationLng ?? null)
  const [media, setMedia] = useState<MediaItem[]>(editPost?.media ?? [])
  const [uploading, setUploading] = useState(false)
  const fileInputRef = useRef<HTMLInputElement | null>(null)
  const [gen, setGen] = useState(false)
  const [saving, setSaving] = useState(false)
  const [tagIn, setTagIn] = useState('')
  const [emojiPickerOpen, setEmojiPickerOpen] = useState(false)
  const [aiSplitOpen, setAiSplitOpen] = useState(false)
  const [aiMode, setAiMode] = useState<AiMode | null>(null)
  const [withShortify, setWithShortify] = useState(false)
  const [withHashtags, setWithHashtags] = useState(false)
  const [withRussify, setWithRussify] = useState(false)
  const [splitLeft, setSplitLeft] = useState('')
  const [splitRight, setSplitRight] = useState('')
  const [splitLoading, setSplitLoading] = useState(false)
  const [hoveredModeInfo, setHoveredModeInfo] = useState<string | null>(null)
  const [locationPickerOpen, setLocationPickerOpen] = useState(false)
  const [prevContent, setPrevContent] = useState<string | null>(null)
  const splitCallIdRef = useRef(0)
  const splitDebounceRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const [volModalOpen, setVolModalOpen] = useState(false)
  const [volItems, setVolItems] = useState<import('@/lib/types').VolunteerMedia[] | null>(null)

  useEffect(() => { api.getTemplates().then(setTmpls).catch(console.error) }, [])
  useEffect(() => {
    return () => {
      if (emojiCloseTimerRef.current) clearTimeout(emojiCloseTimerRef.current)
      if (splitDebounceRef.current) clearTimeout(splitDebounceRef.current)
    }
  }, [])

  function openEmojiPicker() {
    if (emojiCloseTimerRef.current) clearTimeout(emojiCloseTimerRef.current)
    setEmojiPickerOpen(true)
  }

  function closeEmojiPickerLater() {
    if (emojiCloseTimerRef.current) clearTimeout(emojiCloseTimerRef.current)
    emojiCloseTimerRef.current = setTimeout(() => setEmojiPickerOpen(false), 1400)
  }

  async function generateText() {
    const empty = tmplFields.filter(f => !fields[f.key]?.trim()).map(f => f.label)
    if (empty.length) { showToast(`Заполните: ${empty.join(', ')}`, 'error'); return }
    setGen(true)
    try {
      const d = await api.generateText(tmplType, fields)
      setContent(d.text); setTitle(d.title); setStep(3)
    } catch (e: unknown) { showToast((e as Error).message, 'error') }
    finally { setGen(false) }
  }

  async function save() {
    if (!title.trim()) { showToast('Введите заголовок', 'error'); return }
    if (!content.trim()) { showToast('Введите текст', 'error'); return }
    setSaving(true)
    try {
      const body = {
        title, content, status, platforms, tags, media,
        scheduled_at: status === 'scheduled' ? (schedAt || null) : null,
        location_address: locationAddress.trim() || null,
        location_lat: locationLat,
        location_lng: locationLng,
        template_type: tmplType || null,
      }
      if (isEdit) {
        if (currentGroup) await api.updateGroupPost(currentGroup.id, editPost!.id, body)
        else await api.updatePost(editPost!.id, body)
        showToast('Пост обновлён!', 'success')
      } else {
        let newPost: import('@/lib/types').Post
        if (currentGroup) newPost = await api.createGroupPost(currentGroup.id, body)
        else newPost = await api.createPost(body)
        if (status === 'published' && currentGroup) {
          try {
            const r = await api.publishGroupPost(currentGroup.id, newPost.id)
            const errs: string[] = []
            const okParts: string[] = []
            if (r.vk_error) errs.push(`VK: ${r.vk_error}`)
            else if (r.vk_post_id) okParts.push(`VK`)
            if (r.tg_error) errs.push(`Telegram: ${r.tg_error}`)
            else if (r.tg_message_ids?.length) okParts.push(`Telegram`)
            if (errs.length) showToast(okParts.length ? 'Опубликован частично' : 'Ошибка публикации', 'error', errs.join('\n'))
            else showToast('Пост опубликован!', 'success', okParts.length ? okParts.join(' + ') : undefined)
          } catch {
            showToast('Пост создан, но ошибка публикации', 'error')
          }
        } else {
          showToast('Пост создан!', 'success')
        }
      }
      router.push('/posts')
    } catch (e: unknown) { showToast((e as Error).message, 'error') }
    finally { setSaving(false) }
  }

  async function handleFiles(files: FileList | null) {
    if (!files || files.length === 0) return
    setUploading(true)
    try {
      for (const file of Array.from(files)) {
        const item = await api.uploadFile(file)
        setMedia(prev => [...prev, item])
      }
    } catch (e: unknown) { showToast((e as Error).message, 'error') }
    finally { setUploading(false) }
  }

  function removeMedia(url: string) {
    setMedia(prev => prev.filter(m => m.url !== url))
  }

  function openVolModal() {
    setVolModalOpen(true)
    if (!volItems && currentGroup) {
      api.getVolunteerMedia(currentGroup.id, { status: 'approved' })
        .then(data => setVolItems(data.items))
        .catch(() => {})
    }
  }

  function addVolMedia(m: import('@/lib/types').MediaItem) {
    if (!media.find(x => x.url === m.url)) {
      setMedia(prev => [...prev, m])
    }
  }

  function togglePl(pl: string) {
    setPlatforms(p => p.includes(pl) ? p.filter(x => x !== pl) : [...p, pl])
  }

  function addTag(e: React.KeyboardEvent<HTMLInputElement>) {
    if ((e.key === 'Enter' || e.key === ',') && tagIn.trim()) {
      e.preventDefault()
      if (!tags.includes(tagIn.trim())) setTags(t => [...t, tagIn.trim()])
      setTagIn('')
    }
  }

  const tmplFields = tmpls.find(t => t.type === tmplType)?.fields ?? []
  const emojiSuggestions = getEmojiSuggestions(`${title}\n${content}`)

  function applySuggestion(id: string) {
    setTitle(prev => applyEmojiSuggestion(prev, id))
    setContent(prev => applyEmojiSuggestion(prev, id))
  }

  async function runSplitAI(
    text: string,
    mode: AiMode | null,
    doShortify: boolean,
    doHashtags: boolean,
    doRussify: boolean,
  ) {
    if (!text.trim() || (!mode && !doShortify && !doHashtags && !doRussify)) {
      setSplitRight(''); return
    }
    const callId = ++splitCallIdRef.current
    setSplitLoading(true)
    try {
      let result = text
      for (const step of ([mode, doShortify && 'shortify', doHashtags && 'hashtags', doRussify && 'russify'] as (string | false | null)[])) {
        if (!step) continue
        const d = await api.enhanceText(result, step)
        if (callId !== splitCallIdRef.current) return
        result = d.text
      }
      setSplitRight(result)
    } catch (e: unknown) {
      if (callId !== splitCallIdRef.current) return
      showToast((e as Error).message, 'error')
    } finally {
      if (callId === splitCallIdRef.current) setSplitLoading(false)
    }
  }

  function triggerSplit(overrides?: Partial<{ mode: AiMode | null; shortify: boolean; hashtags: boolean; russify: boolean }>) {
    const mode     = overrides?.mode     !== undefined ? overrides.mode     : aiMode
    const shortify = overrides?.shortify !== undefined ? overrides.shortify : withShortify
    const hashtags = overrides?.hashtags !== undefined ? overrides.hashtags : withHashtags
    const russify  = overrides?.russify  !== undefined ? overrides.russify  : withRussify
    if (splitLeft.trim()) runSplitAI(splitLeft, mode, shortify, hashtags, russify)
  }

  function handleSplitLeftChange(val: string) {
    setSplitLeft(val)
    if (!aiMode && !withShortify && !withHashtags && !withRussify) return
    if (splitDebounceRef.current) clearTimeout(splitDebounceRef.current)
    splitDebounceRef.current = setTimeout(
      () => runSplitAI(val, aiMode, withShortify, withHashtags, withRussify), 900
    )
  }

  function handleModeChange(mode: AiMode) {
    if (splitDebounceRef.current) clearTimeout(splitDebounceRef.current)
    setAiMode(mode)
    triggerSplit({ mode })
  }

  function handleModifierToggle(mod: 'shortify' | 'hashtags' | 'russify', checked: boolean) {
    if (splitDebounceRef.current) clearTimeout(splitDebounceRef.current)
    if (mod === 'shortify') { setWithShortify(checked); triggerSplit({ shortify: checked }) }
    if (mod === 'hashtags') { setWithHashtags(checked); triggerSplit({ hashtags: checked }) }
    if (mod === 'russify')  { setWithRussify(checked);  triggerSplit({ russify:  checked }) }
  }

  function openAiSplit() {
    setSplitLeft(content)
    setSplitRight('')
    setAiMode(null)
    setAiSplitOpen(true)
  }

  function applyAiResult() {
    if (!splitRight) return
    setPrevContent(content)
    setContent(splitRight)
    setAiSplitOpen(false)
    showToast('ИИ-текст применён!', 'success')
  }

  function applyAllSuggestions() {
    let nextTitle = title
    let nextContent = content
    for (const suggestion of emojiSuggestions) {
      nextTitle = applyEmojiSuggestion(nextTitle, suggestion.id)
      nextContent = applyEmojiSuggestion(nextContent, suggestion.id)
    }
    setTitle(nextTitle)
    setContent(nextContent)
    showToast('Эмодзи-подсказки добавлены в текст', 'success')
  }

  function insertEmoji(emoji: string) {
    let nextCursorPosition = emoji.length
    setContent(prev => {
      const trimmed = prev.trimEnd()
      const nextValue = trimmed ? `${trimmed} ${emoji}` : emoji
      nextCursorPosition = nextValue.length
      return nextValue
    })
    requestAnimationFrame(() => {
      const textarea = textareaRef.current
      if (!textarea) return
      textarea.focus()
      textarea.setSelectionRange(nextCursorPosition, nextCursorPosition)
    })
  }

  function handleEmojiPick(emojiData: EmojiClickData) {
    insertEmoji(emojiData.emoji)
  }

  function clearLocation() {
    setLocationAddress('')
    setLocationLat(null)
    setLocationLng(null)
  }

  return (
    <div className="content">
      <div style={{ maxWidth: 720, margin: '0 auto' }}>

        {/* Step indicator */}
        {!isEdit && (
          <div className="step-row">
            {STEPS.map((s, i) => (
              <div key={s.n} style={{ display: 'flex', alignItems: 'center' }}>
                <div className={`step${step === s.n ? ' active' : step > s.n ? ' done' : ''}`}>
                  <div className="step-num" onClick={() => step > s.n && setStep(s.n)}>
                    {step > s.n ? IcoCheck : s.n}
                  </div>
                  <span className="step-lbl">{s.l}</span>
                </div>
                {i < STEPS.length - 1 && <div className="step-sep" />}
              </div>
            ))}
          </div>
        )}

        {/* Step 1: шаблон */}
        {step === 1 && (
          <div className="card card-p">
            <h2 style={{ fontSize: 16, fontWeight: 700, marginBottom: 6, color: 'var(--text)', letterSpacing: '-0.02em' }}>Выберите шаблон</h2>
            <p className="ts tg" style={{ marginBottom: 20 }}>Шаблон заполнит структуру поста автоматически</p>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2,1fr)', gap: 12, marginBottom: 20 }}>
              {tmpls.map(t => (
                <div key={t.type} className={`tmpl-card${tmplType === t.type ? ' sel' : ''}`} onClick={() => setTmplType(t.type)}>
                  <div className="tmpl-icon">{TSVG[t.type] ?? TSVG_BLANK}</div>
                  <div>
                    <div className="tmpl-name">{t.name}</div>
                    <div className="tmpl-desc">{t.description}</div>
                  </div>
                </div>
              ))}
              <div className={`tmpl-card${tmplType === '' ? ' sel' : ''}`} onClick={() => setTmplType('')}>
                <div className="tmpl-icon">{TSVG_BLANK}</div>
                <div>
                  <div className="tmpl-name">С нуля</div>
                  <div className="tmpl-desc">Написать пост самостоятельно</div>
                </div>
              </div>
            </div>
            <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
              <button className="btn btn-primary" onClick={() => setStep(tmplType ? 2 : 3)}>
                Далее
                <span className="btn-icon">→</span>
              </button>
            </div>
          </div>
        )}

        {/* Step 2: поля шаблона */}
        {step === 2 && tmplType && (
          <div className="card card-p">
            <h2 style={{ fontSize: 16, fontWeight: 700, marginBottom: 6, color: 'var(--text)', letterSpacing: '-0.02em' }}>Заполните данные</h2>
            <p className="ts tg" style={{ marginBottom: 20 }}>Текст будет сгенерирован по шаблону</p>
            {tmplFields.map(f => {
              const isNumeric = f.key === 'participants'
              return (
                <div key={f.key} className="fg">
                  <label>{f.label}</label>
                  <input
                    type="text"
                    inputMode={isNumeric ? 'numeric' : 'text'}
                    placeholder={f.placeholder}
                    value={fields[f.key] ?? ''}
                    onChange={e => {
                      const val = isNumeric ? e.target.value.replace(/\D/g, '') : e.target.value
                      setFields(p => ({ ...p, [f.key]: val }))
                    }}
                  />
                </div>
              )
            })}
            <div style={{ display: 'flex', justifyContent: 'space-between', gap: 10 }}>
              <button className="btn btn-secondary" onClick={() => setStep(1)}>← Назад</button>
              <button className="btn btn-primary" onClick={generateText} disabled={gen}>
                {gen ? 'Генерирую...' : 'Сгенерировать текст'}
                {!gen && <span className="btn-icon">{IcoAI}</span>}
              </button>
            </div>
          </div>
        )}

        {/* Step 3: редактор */}
        {step === 3 && (
          <div className="card card-p post-editor-card">
            <h2 style={{ fontSize: 16, fontWeight: 700, marginBottom: 20, color: 'var(--text)', letterSpacing: '-0.02em' }}>
              {isEdit ? 'Редактировать пост' : 'Редактор текста'}
            </h2>
            <div className="fg">
              <label>Заголовок поста</label>
              <input type="text" value={title} onChange={e => setTitle(e.target.value)} placeholder="Введите заголовок..." />
            </div>
            <div className="fg">
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 }}>
                <label style={{ marginBottom: 0 }}>Текст поста</label>
                <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
                  {prevContent !== null && (
                    <button
                      type="button"
                      className="btn btn-ghost btn-sm"
                      onClick={() => { setContent(prevContent); setPrevContent(null) }}
                      title="Отменить изменения ИИ"
                    >
                      ↩ Отменить ИИ
                    </button>
                  )}
                  <button
                    type="button"
                    className="btn btn-secondary btn-sm ai-assist-btn"
                    onClick={openAiSplit}
                  >
                    <span className="ai-assist-icon">{IcoAI}</span> ИИ-помощник
                  </button>
                </div>
              </div>
              <div className="emoji-textarea-wrap">
                <textarea
                  ref={textareaRef}
                  value={content}
                  onChange={e => setContent(e.target.value)}
                  rows={10}
                  placeholder="Введите текст поста..."
                  className="emoji-textarea"
                />
                <div
                  className={`emoji-popover-shell${emojiPickerOpen ? ' open' : ''}`}
                  onMouseEnter={openEmojiPicker}
                  onMouseLeave={closeEmojiPickerLater}
                  onFocus={openEmojiPicker}
                  onBlur={closeEmojiPickerLater}
                >
                  <button
                    type="button"
                    className="emoji-fab"
                    title="Открыть меню эмодзи"
                  >
                    {IcoSmile} Эмодзи
                  </button>
                  <div className="emoji-popover" role="dialog" aria-label="Выбор эмодзи">
                    <EmojiPicker
                      onEmojiClick={handleEmojiPick}
                      autoFocusSearch={false}
                      skinTonesDisabled
                      previewConfig={{ showPreview: false }}
                      lazyLoadEmojis
                      theme={Theme.DARK}
                      width="100%"
                      height={360}
                    />
                  </div>
                </div>
              </div>
            </div>
            <div className="emoji-hints">
                <div className="emoji-hints-head">
                  <div>
                    <div className="emoji-hints-title">Подсказки для эмодзи</div>
                    <div className="emoji-hints-copy">
                      Когда в тексте встречаются знакомые слова, редактор предлагает, какие эмодзи можно добавить.
                    </div>
                  </div>
                  {emojiSuggestions.length > 0 && (
                    <button type="button" className="btn btn-secondary btn-sm" onClick={applyAllSuggestions}>
                      Добавить всё
                    </button>
                  )}
                </div>
                {emojiSuggestions.length > 0 ? (
                  <div className="emoji-hint-list">
                    {emojiSuggestions.map(suggestion => (
                      <div key={suggestion.id} className="emoji-hint-item">
                        <div className="emoji-hint-mark">!</div>
                        <div className="emoji-hint-body">
                          <div className="emoji-hint-label">
                            Можно добавить: {suggestion.label} {suggestion.emoji}
                          </div>
                          <div className="emoji-hint-meta">
                            Найдено совпадений: {suggestion.count}
                          </div>
                        </div>
                        <button
                          type="button"
                          className="btn btn-secondary btn-sm"
                          onClick={() => applySuggestion(suggestion.id)}
                        >
                          Добавить
                        </button>
                      </div>
                    ))}
                  </div>
                ) : (
                  <div className="emoji-hints-empty">
                    Пока подсказок нет. Если напишешь слова вроде «Роза», «Сердце» или «Огонь», здесь появятся рекомендации.
                  </div>
                )}
              </div>
            {/* Media upload */}
            <div className="fg">
              <label>Фото, видео и документы</label>
              <input
                ref={fileInputRef}
                type="file"
                multiple
                accept="image/jpeg,image/png,image/gif,image/webp,video/mp4,video/quicktime,video/webm,application/pdf,application/msword,application/vnd.openxmlformats-officedocument.wordprocessingml.document,application/vnd.ms-excel,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,application/vnd.ms-powerpoint,application/vnd.openxmlformats-officedocument.presentationml.presentation,text/plain,text/csv"
                style={{ display: 'none' }}
                onChange={e => handleFiles(e.target.files)}
              />
              {media.length > 0 && (
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: 10, marginBottom: 10 }}>
                  {media.map(item => {
                    const ext = (item.filename.split('.').pop() || '').toLowerCase()
                    const docIcon = ext === 'pdf' ? '📕'
                      : ['doc', 'docx'].includes(ext) ? '📘'
                      : ['xls', 'xlsx', 'csv'].includes(ext) ? '📊'
                      : ['ppt', 'pptx'].includes(ext) ? '📙'
                      : '📄'
                    return (
                    <div key={item.url} style={{ position: 'relative', borderRadius: 'var(--r-md)', overflow: 'hidden', border: '1px solid var(--border)' }}>
                      {item.type === 'image' ? (
                        <Image src={item.url} alt={item.filename} width={96} height={96} style={{ objectFit: 'cover' }} />
                      ) : item.type === 'video' ? (
                        <div style={{ width: 96, height: 96, background: 'var(--surface-2)', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 4 }}>
                          <span style={{ fontSize: 28 }}>▶</span>
                          <span style={{ fontSize: 9, color: 'var(--text-3)', textAlign: 'center', padding: '0 4px', wordBreak: 'break-all' }}>{item.filename}</span>
                        </div>
                      ) : (
                        <div style={{ width: 96, height: 96, background: 'var(--surface-2)', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 4 }}>
                          <span style={{ fontSize: 28 }}>{docIcon}</span>
                          <span style={{ fontSize: 9, color: 'var(--text-3)', textAlign: 'center', padding: '0 4px', wordBreak: 'break-all' }}>{item.filename}</span>
                        </div>
                      )}
                      <button
                        type="button"
                        onClick={() => removeMedia(item.url)}
                        style={{ position: 'absolute', top: 3, right: 3, width: 20, height: 20, borderRadius: '50%', background: 'rgba(0,0,0,0.65)', border: 'none', color: '#fff', cursor: 'pointer', fontSize: 12, lineHeight: 1, display: 'flex', alignItems: 'center', justifyContent: 'center' }}
                      >×</button>
                    </div>
                    )
                  })}
                </div>
              )}
              <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                <button
                  type="button"
                  className="btn btn-secondary"
                  onClick={() => fileInputRef.current?.click()}
                  disabled={uploading}
                  style={{ alignSelf: 'flex-start' }}
                >
                  {uploading ? 'Загружаем...' : '+ Добавить фото / видео / документ'}
                </button>
                {(user?.role === 'editor' || user?.role === 'admin') && (
                  <button
                    type="button"
                    className="btn btn-secondary"
                    onClick={openVolModal}
                    style={{ alignSelf: 'flex-start' }}
                  >
                    📸 Из медиа волонтёров
                  </button>
                )}
              </div>
            </div>

            <div style={{ display: 'flex', justifyContent: 'space-between', gap: 10 }}>
              {!isEdit && <button className="btn btn-secondary" onClick={() => setStep(tmplType ? 2 : 1)}>← Назад</button>}
              {isEdit && <button className="btn btn-secondary" onClick={() => router.push('/posts')}>Отмена</button>}
              <button className="btn btn-primary" onClick={() => isEdit ? save() : setStep(4)} disabled={saving}>
                {isEdit ? (saving ? 'Сохраняем...' : 'Сохранить') : 'Далее'}
                {!saving && <span className="btn-icon">{isEdit ? IcoCheck : '→'}</span>}
              </button>
            </div>
          </div>
        )}

        {/* Step 4: публикация */}
        {step === 4 && (
          <div className="card card-p">
            <h2 style={{ fontSize: 16, fontWeight: 700, marginBottom: 20, color: 'var(--text)', letterSpacing: '-0.02em' }}>Настройки публикации</h2>

            <div className="fg">
              <label>Платформы</label>
              <div style={{ display: 'flex', gap: 10 }}>
                {[{ id: 'vk', l: 'ВКонтакте' }, { id: 'telegram', l: 'Telegram' }].map(pl => (
                  <div key={pl.id} className={`pltoggle${platforms.includes(pl.id) ? ' on' : ''}`} onClick={() => togglePl(pl.id)}>
                    {platforms.includes(pl.id) && <span style={{ marginRight: 5, display: 'inline-flex', verticalAlign: 'middle' }}>{IcoCheck}</span>}{pl.l}
                  </div>
                ))}
              </div>
            </div>

            <div className="fg">
              <label>Теги / рубрики</label>
              <div className="tag-wrap">
                {tags.map(t => (
                  <span key={t} className="tag-chip">
                    {t}<span className="tag-x" onClick={() => setTags(p => p.filter(x => x !== t))}>×</span>
                  </span>
                ))}
                <input type="text" value={tagIn} onChange={e => setTagIn(e.target.value)} onKeyDown={addTag}
                  placeholder={tags.length === 0 ? 'Введите тег, нажмите Enter...' : ''}
                  style={{ border: 'none', outline: 'none', background: 'transparent', color: 'var(--text)', fontSize: 12, padding: '2px 4px', flex: 1, minWidth: 80, width: 'auto' }} />
              </div>
              <div style={{ display: 'flex', gap: 6, marginTop: 8, flexWrap: 'wrap' }}>
                {['мероприятия', 'вакансии', 'гранты', 'новости'].map(t => (
                  <span key={t} className="tag" style={{ cursor: 'pointer' }} onClick={() => !tags.includes(t) && setTags(p => [...p, t])}>
                    + {t}
                  </span>
                ))}
              </div>
            </div>

            <div className="fg">
              <label>Статус</label>
              <select value={status} onChange={e => setStatus(e.target.value as 'draft' | 'scheduled' | 'published')}>
                <option value="draft">Черновик</option>
                <option value="scheduled">Запланировать</option>
                <option value="published">Опубликовать сейчас</option>
              </select>
            </div>

            {status === 'scheduled' && (
              <div className="fg">
                <label>Дата и время публикации</label>
                <input type="datetime-local" value={schedAt} onChange={e => setSchedAt(e.target.value)} />
              </div>
            )}

            <div className="fg">
              <label>Адрес / место проведения</label>
              <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
                <input
                  type="text"
                  value={locationAddress}
                  onChange={e => setLocationAddress(e.target.value)}
                  placeholder="Введите адрес вручную или выберите на карте"
                  style={{ flex: 1, minWidth: 240 }}
                />
                <button type="button" className="btn btn-secondary" onClick={() => setLocationPickerOpen(true)}>
                  Отметить на карте
                </button>
                {locationAddress && (
                  <button type="button" className="btn btn-ghost" onClick={clearLocation}>
                    Очистить
                  </button>
                )}
              </div>
              {(locationLat !== null && locationLng !== null) && (
                <div className="ts tg" style={{ marginTop: 8 }}>
                  Место события: {locationAddress || 'точка выбрана на карте'}
                </div>
              )}
            </div>

            <div style={{ marginBottom: 16 }}>
              <div style={{ fontSize: 10, fontWeight: 700, color: 'var(--text-3)', marginBottom: 8, textTransform: 'uppercase', letterSpacing: '0.1em' }}>Предпросмотр</div>
              <div className="preview">{content}</div>
            </div>

            <div style={{ display: 'flex', justifyContent: 'space-between', gap: 10 }}>
              <button className="btn btn-secondary" onClick={() => setStep(3)}>← Назад</button>
              <button className="btn btn-primary" onClick={save} disabled={saving}>
                {saving ? 'Сохраняем...' : status === 'published' ? 'Опубликовать' : status === 'scheduled' ? 'Запланировать' : 'Сохранить'}
                {!saving && <span className="btn-icon">{status === 'published' ? IcoSend : IcoCheck}</span>}
              </button>
            </div>
          </div>
        )}
      </div>
      {volModalOpen && (
        <div className="overlay" onClick={() => setVolModalOpen(false)}>
          <div className="modal" style={{ maxWidth: 640, maxHeight: '80vh', display: 'flex', flexDirection: 'column' }} onClick={e => e.stopPropagation()}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '18px 22px', borderBottom: '1px solid var(--border)' }}>
              <div className="card-title">Медиа волонтёров</div>
              <button type="button" className="btn btn-ghost btn-sm" style={{ fontSize: 16, lineHeight: 1, padding: '4px 8px' }} onClick={() => setVolModalOpen(false)}>✕</button>
            </div>
            <div style={{ flex: 1, overflow: 'auto', padding: 16 }}>
              {volItems === null ? (
                <div style={{ textAlign: 'center', padding: 40, color: 'var(--text-3)' }}>Загрузка...</div>
              ) : volItems.length === 0 ? (
                <div style={{ textAlign: 'center', padding: 40, color: 'var(--text-3)' }}>
                  Одобренных медиа от волонтёров пока нет
                </div>
              ) : (
                <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
                  {volItems.map(item => (
                    <div key={item.id}>
                      <div style={{ fontWeight: 600, fontSize: 13, marginBottom: 8, color: 'var(--text-2)' }}>{item.event_name}</div>
                      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
                        {item.media.filter(m => m.type === 'image').map((m, i) => {
                          const url = m.url || ''
                          const selected = !!media.find(x => x.url === url)
                          return (
                            <div
                              key={i}
                              onClick={() => addVolMedia(m)}
                              style={{
                                width: 100, height: 100, borderRadius: 'var(--r-md)',
                                overflow: 'hidden', cursor: 'pointer',
                                border: selected ? '2px solid var(--accent)' : '2px solid transparent',
                                opacity: selected ? 0.6 : 1,
                                position: 'relative',
                              }}
                            >
                              <Image src={url} alt="" width={100} height={100} style={{ objectFit: 'cover' }} />
                              {selected && (
                                <div style={{ position: 'absolute', top: 4, right: 4, width: 18, height: 18, borderRadius: '50%', background: 'var(--accent)', color: '#fff', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 11, fontWeight: 700 }}>
                                  ✓
                                </div>
                              )}
                            </div>
                          )
                        })}
                        {item.media.filter(m => m.type === 'video').map((m, i) => {
                          const url = m.url || ''
                          const selected = !!media.find(x => x.url === url)
                          return (
                            <div
                              key={`v${i}`}
                              onClick={() => addVolMedia(m)}
                              style={{
                                width: 100, height: 100, borderRadius: 'var(--r-md)',
                                background: 'var(--surface-2)', cursor: 'pointer',
                                display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 4,
                                border: selected ? '2px solid var(--accent)' : '2px solid transparent',
                                opacity: selected ? 0.6 : 1,
                              }}
                            >
                              <span style={{ fontSize: 24 }}>🎬</span>
                              <span style={{ fontSize: 9, color: 'var(--text-3)', textAlign: 'center', padding: '0 4px', wordBreak: 'break-all' }}>{m.filename}</span>
                              {selected && (
                                <div style={{ position: 'absolute', top: 4, right: 4, width: 18, height: 18, borderRadius: '50%', background: 'var(--accent)', color: '#fff', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 11, fontWeight: 700 }}>
                                  ✓
                                </div>
                              )}
                            </div>
                          )
                        })}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
            <div className="modal-ft">
              <button type="button" className="btn btn-primary btn-sm" onClick={() => setVolModalOpen(false)}>
                Готово
              </button>
            </div>
          </div>
        </div>
      )}
      {aiSplitOpen && (
        <div className="overlay" onClick={() => { if (!splitLoading) setAiSplitOpen(false) }}>
          <div className="modal ai-split-modal" onClick={e => e.stopPropagation()}>

            {/* Header */}
            <div className="ai-split-hd">
              <div className="ai-split-hd-top">
                <div className="card-title" style={{ fontSize: 13, display: 'flex', alignItems: 'center', gap: 6 }}>{IcoAI} ИИ-помощник</div>
                <button type="button" className="btn btn-ghost btn-sm" style={{ fontSize: 16, lineHeight: 1, padding: '4px 8px' }} onClick={() => setAiSplitOpen(false)}>✕</button>
              </div>

              {/* Main mode tabs */}
              <div className="ai-split-tabs">
                {AI_MODES_CONFIG.map(m => (
                  <button
                    key={m.id}
                    className={`ai-split-tab${aiMode === m.id ? ' active' : ''}`}
                    onClick={() => handleModeChange(m.id)}
                  >
                    <span>{m.icon}</span>
                    <span>{m.title}</span>
                    <span
                      className="ai-info-badge"
                      onMouseEnter={() => setHoveredModeInfo(m.info)}
                      onMouseLeave={() => setHoveredModeInfo(null)}
                    >!</span>
                  </button>
                ))}
              </div>

              {/* Modifier toggles + description */}
              <div className="ai-split-sub-row">
                {AI_MODIFIERS_CONFIG.map(mod => {
                  const checked = mod.id === 'shortify' ? withShortify : mod.id === 'hashtags' ? withHashtags : withRussify
                  return (
                    <label key={mod.id} className="ai-russify-toggle">
                      <input
                        type="checkbox"
                        checked={checked}
                        onChange={e => handleModifierToggle(mod.id, e.target.checked)}
                      />
                      <span>{mod.icon}</span> {mod.title}
                      <span
                        className="ai-info-badge"
                        style={{ marginLeft: 3 }}
                        onMouseEnter={() => setHoveredModeInfo(mod.info)}
                        onMouseLeave={() => setHoveredModeInfo(null)}
                      >!</span>
                    </label>
                  )
                })}
                <div className="ai-tab-desc">
                  {hoveredModeInfo ?? (aiMode ? AI_MODES_CONFIG.find(m => m.id === aiMode)?.info : 'Выберите режим или отметьте галочки')}
                </div>
              </div>
            </div>

            {/* Split body */}
            <div className="ai-split-bd">
              <div className="ai-split-pane">
                <div className="ai-split-pane-hd">Оригинал</div>
                <textarea
                  className="ai-split-textarea"
                  value={splitLeft}
                  onChange={e => handleSplitLeftChange(e.target.value)}
                  placeholder="Введите или отредактируйте текст..."
                />
              </div>
              <div className="ai-split-pane">
                <div className="ai-split-pane-hd">
                  Результат ИИ
                  {splitLoading && <span className="ai-spinner" style={{ width: 14, height: 14, borderWidth: 2 }} />}
                </div>
                <div className="ai-split-result">
                  {splitRight
                    ? splitRight
                    : <span className="ai-split-result-empty">{splitLoading ? 'Генерирую...' : (!aiMode && !withShortify && !withHashtags && !withRussify ? 'Выберите режим или отметьте галочку' : 'Результат появится здесь')}</span>
                  }
                </div>
              </div>
            </div>

            {/* Footer */}
            <div className="modal-ft">
              <button type="button" className="btn btn-secondary btn-sm" onClick={() => setAiSplitOpen(false)}>
                Отмена
              </button>
              <button
                type="button"
                className="btn btn-primary btn-sm"
                disabled={!splitRight || splitLoading}
                onClick={applyAiResult}
              >
                Применить результат <span style={{ display: 'inline-flex', verticalAlign: 'middle', marginLeft: 4 }}>{IcoCheck}</span>
              </button>
            </div>
          </div>
        </div>
      )}
      <EventLocationPickerModal
        open={locationPickerOpen}
        initialAddress={locationAddress}
        initialLat={locationLat}
        initialLng={locationLng}
        onClose={() => setLocationPickerOpen(false)}
        onSelect={({ address, lat, lng }) => {
          setLocationAddress(address)
          setLocationLat(lat)
          setLocationLng(lng)
          setLocationPickerOpen(false)
          showToast('Адрес добавлен к посту', 'success')
        }}
      />
    </div>
  )
}
