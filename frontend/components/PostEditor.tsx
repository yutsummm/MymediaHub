'use client'
import { useEffect, useRef, useState, type ReactNode } from 'react'
import { useRouter } from 'next/navigation'
import Image from 'next/image'
import dynamic from 'next/dynamic'
import EmojiPicker, { EmojiClickData, Theme } from 'emoji-picker-react'
import { api, publishOutcome, waitForPublish } from '@/lib/api'
import { useToast } from '@/contexts/ToastContext'
import { useGroup } from '@/contexts/GroupContext'
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

// short — всегда видно на карточке, info — полный текст в нативной подсказке при наведении
const AI_MODES_CONFIG: { id: AiMode; icon: ReactNode; title: string; short: string; info: string }[] = [
  { id: 'creative',     icon: <svg {...S14}><path d="m21.64 3.64-1.28-1.28a1.21 1.21 0 0 0-1.72 0L2.36 18.64a1.21 1.21 0 0 0 0 1.72l1.28 1.28a1.2 1.2 0 0 0 1.72 0L21.64 5.36a1.2 1.2 0 0 0 0-1.72z"/><path d="m14 7 3 3"/></svg>,    title: 'Улучшить текст', short: 'Живее, с эмодзи', info: 'Переписывает текст для молодёжной аудитории: добавляет энергичность и эмодзи, сохраняя все факты, даты и имена' },
  { id: 'formal',       icon: <svg {...S14}><line x1="3" x2="21" y1="22" y2="22"/><line x1="6" x2="6" y1="18" y2="11"/><line x1="10" x2="10" y1="18" y2="11"/><line x1="14" x2="14" y1="18" y2="11"/><line x1="18" x2="18" y1="18" y2="11"/><polygon points="12 2 20 7 4 7"/></svg>, title: 'Официальный тон', short: 'Нейтрально-деловой тон', info: 'Переводит в нейтрально-деловой стиль — подходит для объявлений, вакансий и грантовых постов' },
  { id: 'calltoaction', icon: <svg {...S14}><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/></svg>,                                                                                                                                                                                   title: 'Призыв к действию', short: 'Допишет призыв в конце', info: 'Дописывает сильный CTA — «зарегистрируйся», «приходи», «поделись» — по теме поста' },
]

const AI_MODIFIERS_CONFIG: { id: AiModifier; icon: ReactNode; title: string; short: string; info: string }[] = [
  { id: 'shortify', icon: <svg {...S14}><circle cx="6" cy="6" r="3"/><circle cx="6" cy="18" r="3"/><line x1="20" y1="4" x2="8.12" y2="15.88"/><line x1="14.47" y1="14.48" x2="20" y2="20"/><line x1="8.12" y1="8.12" x2="12" y2="12"/></svg>, title: 'Сократить', short: 'Вдвое короче', info: 'Сокращает пост вдвое: убирает лишние слова и повторы, сохраняя ключевые факты и смысл' },
  { id: 'hashtags', icon: <svg {...S14}><line x1="4" y1="9" x2="20" y2="9"/><line x1="4" y1="15" x2="20" y2="15"/><line x1="10" y1="3" x2="8" y2="21"/><line x1="16" y1="3" x2="14" y2="21"/></svg>,                                          title: 'Хештеги', short: '7–10 хештегов в конец', info: 'Анализирует тему поста и добавляет 7–10 актуальных хештегов для ВКонтакте и Telegram в конец' },
  { id: 'russify',  icon: <svg {...S14}><polyline points="4 7 4 4 20 4 20 7"/><line x1="9" y1="20" x2="15" y2="20"/><line x1="12" y1="4" x2="12" y2="20"/></svg>,                                                                               title: 'Русификация', short: 'Русские слова вместо англицизмов', info: 'Заменяет иностранные слова на естественные русские: фидбек→отклик, дедлайн→срок, контент→публикации' },
]

/**
 * Что автор выбирает в поле «Статус». Совпадает со статусами поста, но
 * `on_review` здесь означает намерение — «сохранить и отправить на
 * согласование», — а сам переход делает отдельная ручка: у него есть побочные
 * действия (уведомить администраторов, записать в журнал), и вешать их на
 * обычное сохранение нельзя.
 */
type EditorStatus = 'draft' | 'on_review' | 'scheduled' | 'queued' | 'published'

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
  const isEdit = !!editPost
  // Виза нужна, когда группа этого требует, а человек не её администратор:
  // заставлять администратора утверждать самого себя — обряд без содержания.
  const needsApproval = !!currentGroup?.require_approval && currentGroup.role !== 'admin'
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
  const [status, setStatus] = useState<EditorStatus>(
    (editPost?.status === 'on_review' ? 'on_review' : editPost?.status) ?? initialStatus ?? 'draft')
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
  const [locationPickerOpen, setLocationPickerOpen] = useState(false)
  const [prevContent, setPrevContent] = useState<string | null>(null)
  const splitCallIdRef = useRef(0)
  const splitDebounceRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  // Медиатека: всё уже загруженное в группе — одобренные материалы волонтёров
  // и файлы из прошлых постов. Раньше выбор шёл только по волонтёрским
  // загрузкам, то есть переиспользовать снятое на прошлом мероприятии было
  // нельзя, хотя лежало оно в той же базе.
  const [libOpen, setLibOpen] = useState(false)
  const [libItems, setLibItems] = useState<import('@/lib/types').MediaLibraryItem[] | null>(null)
  const [libQuery, setLibQuery] = useState('')
  const [libSource, setLibSource] = useState<'' | 'volunteer' | 'post'>('')
  // Очередь по расписанию: время считает сервер, мы только показываем, какое
  // окно достанется. Держать копию правил расписания на клиенте значило бы
  // однажды с ними разойтись.
  const [nextSlot, setNextSlot] = useState<string | null>(null)
  const [slotsAvailable, setSlotsAvailable] = useState(false)
  const [autoDeleteAt, setAutoDeleteAt] = useState(
    editPost?.auto_delete_at ? editPost.auto_delete_at.slice(0, 16) : '')

  useEffect(() => { api.getTemplates().then(setTmpls).catch(console.error) }, [])

  // Расписание группы: если окон нет, вариант «в очередь» не предлагаем вовсе —
  // пустой пункт меню, который отвечает ошибкой, хуже отсутствующего.
  useEffect(() => {
    if (!currentGroup) { setSlotsAvailable(false); return }
    api.getSlots(currentGroup.id)
      .then(d => setSlotsAvailable(d.slots.length > 0))
      .catch(() => setSlotsAvailable(false))
  }, [currentGroup])

  useEffect(() => {
    if (status !== 'queued' || !currentGroup) return
    setNextSlot(null)
    api.getNextSlot(currentGroup.id)
      .then(d => setNextSlot(d.at))
      .catch(() => setNextSlot(null))
  }, [status, currentGroup])

  // Пост мог прийти из календаря сразу «на публикацию», а группа требует визы —
  // тогда в списке не окажется выбранного варианта, и поле молча покажет не то,
  // что в состоянии. Приводим намерение к тому, что человеку доступно.
  useEffect(() => {
    if (needsApproval && (status === 'scheduled' || status === 'published')) {
      setStatus('on_review')
    }
  }, [needsApproval, status])
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

  const hashtagSets = currentGroup?.hashtag_sets ?? []
  const variableKeys = Object.keys(currentGroup?.variables ?? {})
  // Что реально подставится в этом тексте — показываем только использованные
  // ключи: перечислять весь словарь значило бы утопить полезное в шуме.
  const usedVariables = Object.entries(currentGroup?.variables ?? {})
    .filter(([key]) => content.includes(`{{${key}}}`))

  function appendText(chunk: string) {
    setContent(prev => (prev.trimEnd() + '\n\n' + chunk).trimStart())
  }

  function insertAtCursor(chunk: string) {
    const el = textareaRef.current
    if (!el) { appendText(chunk); return }
    const start = el.selectionStart ?? content.length
    const end = el.selectionEnd ?? content.length
    setContent(content.slice(0, start) + chunk + content.slice(end))
    requestAnimationFrame(() => {
      el.focus()
      el.setSelectionRange(start + chunk.length, start + chunk.length)
    })
  }

  /**
   * Что сказать после постановки в очередь. Там, где нужна виза, окно занято,
   * но пост сам не выйдет — умолчать об этом значило бы обмануть автора.
   */
  function queuedToast(post: import('@/lib/types').Post & { queued: boolean }):
    [string, 'success' | 'info', string] {
    const when = post.scheduled_at ? post.scheduled_at.replace('T', ', ') : 'ближайшее окно'
    return post.queued
      ? ['Пост в очереди', 'success', `Выйдет ${when}`]
      : ['Окно занято, ждём согласования', 'info',
         `После одобрения пост выйдет ${when}`]
  }

  async function save() {
    if (!title.trim()) { showToast('Введите заголовок', 'error'); return }
    if (!content.trim()) { showToast('Введите текст', 'error'); return }
    setSaving(true)
    try {
      // on_review в тело не кладём: пост сохраняется черновиком, а на
      // согласование его отправляет отдельная ручка — она же уведомляет
      // администраторов и пишет в журнал.
      // Ни on_review, ни queued в тело не кладём: оба перехода делают
      // отдельные ручки — у них есть побочные действия (уведомить
      // администраторов; занять окно расписания), и вешать их на обычное
      // сохранение значило бы, что любой PUT их запускает.
      const body = {
        title, content,
        status: (status === 'on_review' || status === 'queued') ? 'draft' : status,
        platforms, tags, media,
        auto_delete_at: autoDeleteAt || null,
        // Желаемое время нужно и при согласовании: одобряющий по нему решает,
        // ставить пост в расписание или выпускать сразу.
        scheduled_at: (status === 'scheduled' || status === 'on_review') ? (schedAt || null) : null,
        location_address: locationAddress.trim() || null,
        location_lat: locationLat,
        location_lng: locationLng,
        template_type: tmplType || null,
      }
      if (isEdit) {
        if (currentGroup) await api.updateGroupPost(currentGroup.id, editPost!.id, body)
        else await api.updatePost(editPost!.id, body)
        if (status === 'on_review' && currentGroup) {
          await api.submitGroupPost(currentGroup.id, editPost!.id)
          showToast('Отправлено на согласование', 'success',
                    'Администратор группы получит уведомление')
        } else if (status === 'queued' && currentGroup) {
          const queued = await api.queueGroupPost(currentGroup.id, editPost!.id, autoDeleteAt || null)
          showToast(...queuedToast(queued))
        } else {
          showToast('Пост обновлён!', 'success')
        }
      } else {
        let newPost: import('@/lib/types').Post
        if (currentGroup) newPost = await api.createGroupPost(currentGroup.id, body)
        else newPost = await api.createPost(body)
        if (status === 'on_review' && currentGroup) {
          await api.submitGroupPost(currentGroup.id, newPost.id)
          showToast('Отправлено на согласование', 'success',
                    'Администратор группы получит уведомление')
        } else if (status === 'queued' && currentGroup) {
          const queued = await api.queueGroupPost(currentGroup.id, newPost.id, autoDeleteAt || null)
          showToast(...queuedToast(queued))
        } else if (status === 'published' && currentGroup) {
          try {
            // Ставим в очередь и ждём воркера: сама отправка идёт вне запроса
            const job = await api.publishGroupPost(currentGroup.id, newPost.id)
            const finished = await waitForPublish(job.id)
            if (finished.state === 'failed') {
              showToast('Пост создан, но опубликовать не удалось', 'error',
                        finished.error ?? undefined)
              router.push('/posts')
              return
            }
            const r = publishOutcome(finished)
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

  function loadLibrary() {
    if (!currentGroup) return
    const params: Record<string, string> = { limit: '60' }
    if (libQuery.trim()) params.q = libQuery.trim()
    if (libSource) params.source = libSource
    api.getMediaLibrary(currentGroup.id, params)
      .then(data => setLibItems(data.items))
      .catch(() => setLibItems([]))
  }

  // Поиск и фильтр по источнику считает сервер: фильтровать на клиенте поверх
  // загруженной страницы значило бы «ничего не найдено» вместо «нет на этой
  // странице». Ищем после паузы — иначе запрос на каждую букву.
  useEffect(() => {
    if (!libOpen) return
    const t = setTimeout(loadLibrary, libQuery ? 350 : 0)
    return () => clearTimeout(t)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [libOpen, libQuery, libSource, currentGroup])

  function toggleLibItem(m: import('@/lib/types').MediaItem) {
    const item = { url: m.url, type: m.type, filename: m.filename }
    setMedia(prev => prev.find(x => x.url === m.url)
      ? prev.filter(x => x.url !== m.url)
      : [...prev, item])
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
    // повторный клик по выбранному режиму снимает выбор
    const next = aiMode === mode ? null : mode
    setAiMode(next)
    triggerSplit({ mode: next })
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
            {/* Наборы хештегов и подстановки группы. Одно и то же набирается
                заново в каждом втором посте; здесь это одно нажатие. */}
            {(hashtagSets.length > 0 || variableKeys.length > 0) && (
              <div className="fg">
                <label>Готовые вставки</label>
                <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                  {hashtagSets.map(set => (
                    <button key={set.name} type="button" className="tag"
                      style={{ cursor: 'pointer' }}
                      title={set.tags}
                      onClick={() => appendText(set.tags)}>
                      # {set.name}
                    </button>
                  ))}
                  {variableKeys.map(key => (
                    <button key={key} type="button" className="tag"
                      style={{ cursor: 'pointer' }}
                      title={`Подставится при публикации: ${currentGroup?.variables?.[key] ?? ''}`}
                      onClick={() => insertAtCursor(`{{${key}}}`)}>
                      {'{{'}{key}{'}}'}
                    </button>
                  ))}
                </div>
                {usedVariables.length > 0 && (
                  <div className="ts tg" style={{ marginTop: 8 }}>
                    При публикации подставится: {usedVariables.map(
                      ([k, v]) => `${k} → ${v}`).join(', ')}
                  </div>
                )}
              </div>
            )}

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
                {/* Право на медиатеку даёт роль в ГРУППЕ. Раньше здесь стояла
                    глобальная роль 'editor', которой после разделения систем
                    ролей не существует, — кнопку видели одни глобальные
                    администраторы, а редакторы групп загружали файлы заново. */}
                {currentGroup && currentGroup.role !== 'volunteer' && (
                  <button
                    type="button"
                    className="btn btn-secondary"
                    onClick={() => setLibOpen(true)}
                    style={{ alignSelf: 'flex-start' }}
                  >
                    🗂 Медиатека
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
              <select value={status} onChange={e => setStatus(e.target.value as EditorStatus)}>
                <option value="draft">Черновик</option>
                {/* «В очередь» показываем, только когда расписание задано:
                    пункт меню, который отвечает ошибкой, хуже отсутствующего. */}
                {slotsAvailable && <option value="queued">В очередь по расписанию</option>}
                {needsApproval ? (
                  <option value="on_review">Отправить на согласование</option>
                ) : (
                  <>
                    <option value="scheduled">Запланировать</option>
                    <option value="published">Опубликовать сейчас</option>
                  </>
                )}
              </select>
              {needsApproval && (
                <div className="ts tg" style={{ marginTop: 8 }}>
                  В этой группе посты выходят после согласования: выпустит его администратор группы.
                </div>
              )}
            </div>

            {status === 'queued' && (
              <div className="fg">
                <label>Ближайшее свободное окно</label>
                <div className="ts tg">
                  {nextSlot
                    ? `Пост выйдет ${nextSlot.replace('T', ' в ')}` +
                      (needsApproval ? ' — после согласования' : '')
                    : 'Считаем свободное окно...'}
                </div>
                <div className="ts tg" style={{ marginTop: 6 }}>
                  Время берётся из расписания группы. Занятые окна пропускаются, чтобы два
                  поста не вышли в одну минуту и не перебили друг друга в ленте.
                </div>
              </div>
            )}

            {(status === 'scheduled' || status === 'on_review') && (
              <div className="fg">
                <label>
                  {status === 'on_review'
                    ? 'Желаемая дата публикации (необязательно)'
                    : 'Дата и время публикации'}
                </label>
                <input type="datetime-local" value={schedAt} onChange={e => setSchedAt(e.target.value)} />
                {status === 'on_review' && (
                  <div className="ts tg" style={{ marginTop: 6 }}>
                    Если дату не указать, согласованный пост уйдёт сразу после одобрения.
                  </div>
                )}
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

            <div className="fg">
              <label>Снять с публикации (необязательно)</label>
              <input type="datetime-local" value={autoDeleteAt}
                onChange={e => setAutoDeleteAt(e.target.value)} />
              <div className="ts tg" style={{ marginTop: 6 }}>
                Запись исчезнет из соцсетей в указанное время — удобно для анонсов:
                прошедшее мероприятие не будет висеть в ленте и путать людей.
                У нас пост останется и продолжит учитываться в отчётах.
              </div>
              {autoDeleteAt && (
                <button type="button" className="btn btn-ghost btn-sm" style={{ marginTop: 8 }}
                  onClick={() => setAutoDeleteAt('')}>Не снимать</button>
              )}
            </div>

            <div style={{ marginBottom: 16 }}>
              <div style={{ fontSize: 10, fontWeight: 700, color: 'var(--text-3)', marginBottom: 8, textTransform: 'uppercase', letterSpacing: '0.1em' }}>Предпросмотр</div>
              <div className="preview">{content}</div>
            </div>

            <div style={{ display: 'flex', justifyContent: 'space-between', gap: 10 }}>
              <button className="btn btn-secondary" onClick={() => setStep(3)}>← Назад</button>
              <button className="btn btn-primary" onClick={save} disabled={saving}>
                {saving ? 'Сохраняем...'
                  : status === 'published' ? 'Опубликовать'
                  : status === 'scheduled' ? 'Запланировать'
                  : status === 'on_review' ? 'На согласование'
                  : status === 'queued' ? 'В очередь'
                  : 'Сохранить'}
                {!saving && <span className="btn-icon">{status === 'published' ? IcoSend : IcoCheck}</span>}
              </button>
            </div>
          </div>
        )}
      </div>
      {libOpen && (
        <div className="overlay" onClick={() => setLibOpen(false)}>
          <div className="modal media-lib" onClick={e => e.stopPropagation()}>
            <div className="media-lib-hd">
              <div>
                <div className="card-title">Медиатека</div>
                <div className="media-lib-sub">
                  Файлы, уже загруженные в группе: материалы волонтёров и вложения прошлых постов
                </div>
              </div>
              <button type="button" className="btn btn-ghost btn-sm" style={{ fontSize: 16, lineHeight: 1, padding: '4px 8px' }} onClick={() => setLibOpen(false)}>✕</button>
            </div>

            <div className="media-lib-bar">
              <input
                className="srch"
                placeholder="Поиск по названию файла или мероприятия..."
                value={libQuery}
                onChange={e => setLibQuery(e.target.value)}
                style={{ flex: 1, minWidth: 200 }}
              />
              <div className="period-seg">
                {([
                  { v: '', l: 'Всё' },
                  { v: 'volunteer', l: 'От волонтёров' },
                  { v: 'post', l: 'Из постов' },
                ] as const).map(o => (
                  <button
                    key={o.v}
                    type="button"
                    className={`period-seg-btn${libSource === o.v ? ' active' : ''}`}
                    onClick={() => setLibSource(o.v)}
                  >{o.l}</button>
                ))}
              </div>
            </div>

            <div className="media-lib-body">
              {libItems === null ? (
                <div className="media-lib-empty">Загрузка...</div>
              ) : libItems.length === 0 ? (
                <div className="media-lib-empty">
                  {libQuery || libSource
                    ? 'Ничего не нашлось — попробуйте изменить запрос'
                    : 'Медиатека пуста. Файлы попадут сюда из постов и одобренных загрузок волонтёров'}
                </div>
              ) : (
                <div className="media-lib-grid">
                  {libItems.map(m => {
                    const selected = !!media.find(x => x.url === m.url)
                    return (
                      <button
                        key={m.url}
                        type="button"
                        className={`media-lib-card${selected ? ' selected' : ''}`}
                        onClick={() => toggleLibItem(m)}
                        title={`${m.label}${m.author ? ` · ${m.author}` : ''}`}
                      >
                        <div className="media-lib-thumb">
                          {m.type === 'image' ? (
                            <Image src={m.url} alt={m.filename} width={132} height={100} style={{ objectFit: 'cover', width: '100%', height: '100%' }} />
                          ) : (
                            <span className="media-lib-ico">{m.type === 'video' ? '🎬' : '📄'}</span>
                          )}
                          {selected && <span className="media-lib-check">✓</span>}
                        </div>
                        <div className="media-lib-meta">
                          <span className="media-lib-label">{m.label}</span>
                          <span className="media-lib-src">
                            {m.source === 'volunteer' ? 'от волонтёра' : 'из поста'}
                            {m.at ? ` · ${m.at.slice(8, 10)}.${m.at.slice(5, 7)}.${m.at.slice(0, 4)}` : ''}
                          </span>
                        </div>
                      </button>
                    )
                  })}
                </div>
              )}
            </div>

            <div className="modal-ft" style={{ justifyContent: 'space-between' }}>
              <span style={{ fontSize: 12, color: 'var(--text-3)' }}>
                Выбрано файлов: {media.length}
              </span>
              <button type="button" className="btn btn-primary btn-sm" onClick={() => setLibOpen(false)}>
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

              {/* Шаг 1 — как переписать (одно из трёх, необязательно) */}
              <div className="ai-opt-group">
                <div className="ai-opt-label">
                  Шаг 1 — как переписать
                  <span className="ai-opt-hint">выберите одно</span>
                </div>
                <div className="ai-opt-grid">
                  {AI_MODES_CONFIG.map(m => (
                    <button
                      key={m.id}
                      type="button"
                      title={m.info}
                      aria-pressed={aiMode === m.id}
                      className={`ai-opt${aiMode === m.id ? ' active' : ''}`}
                      onClick={() => handleModeChange(m.id)}
                    >
                      <span className="ai-opt-ico">{m.icon}</span>
                      <span className="ai-opt-txt">
                        <span className="ai-opt-ttl">{m.title}</span>
                        <span className="ai-opt-sub">{m.short}</span>
                      </span>
                    </button>
                  ))}
                </div>
              </div>

              {/* Шаг 2 — добавки поверх, можно несколько */}
              <div className="ai-opt-group">
                <div className="ai-opt-label">
                  Шаг 2 — что добавить
                  <span className="ai-opt-hint">необязательно, можно несколько</span>
                </div>
                <div className="ai-opt-grid">
                  {AI_MODIFIERS_CONFIG.map(mod => {
                    const checked = mod.id === 'shortify' ? withShortify : mod.id === 'hashtags' ? withHashtags : withRussify
                    return (
                      <button
                        key={mod.id}
                        type="button"
                        title={mod.info}
                        aria-pressed={checked}
                        className={`ai-opt${checked ? ' active' : ''}`}
                        onClick={() => handleModifierToggle(mod.id, !checked)}
                      >
                        <span className="ai-opt-ico">{mod.icon}</span>
                        <span className="ai-opt-txt">
                          <span className="ai-opt-ttl">{mod.title}</span>
                          <span className="ai-opt-sub">{mod.short}</span>
                        </span>
                        <span className="ai-opt-mark" aria-hidden="true">{checked ? IcoCheck : null}</span>
                      </button>
                    )
                  })}
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
                    : <span className="ai-split-result-empty">{
                        splitLoading
                          ? 'Генерирую…'
                          : !splitLeft.trim()
                            ? 'Слева пусто — введите текст поста'
                            : (!aiMode && !withShortify && !withHashtags && !withRussify)
                              ? 'Выберите вариант выше — здесь появится переписанный текст'
                              : 'Результат появится здесь'
                      }</span>
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
