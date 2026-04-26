'use client'
import { useEffect, useRef, useState } from 'react'
import { useRouter } from 'next/navigation'
import EmojiPicker, { EmojiClickData, Theme } from 'emoji-picker-react'
import { api } from '@/lib/api'
import { useToast } from '@/contexts/ToastContext'
import { applyEmojiSuggestion, getEmojiSuggestions } from '@/lib/postUtils'
import type { MediaItem, Post, Template } from '@/lib/types'

const TICO: Record<string, string> = { announcement: '◈', results: '✓', vacancy: '↗', grant: '◎' }
const STEPS = [{ n: 1, l: 'Шаблон' }, { n: 2, l: 'Данные' }, { n: 3, l: 'Редактор' }, { n: 4, l: 'Публикация' }]

export default function PostEditor({ editPost }: { editPost?: Post }) {
  const router = useRouter()
  const { showToast } = useToast()
  const isEdit = !!editPost
  const textareaRef = useRef<HTMLTextAreaElement | null>(null)

  const [step, setStep] = useState(isEdit ? 3 : 1)
  const [tmplType, setTmplType] = useState(editPost?.template_type ?? '')
  const [tmpls, setTmpls] = useState<Template[]>([])
  const [fields, setFields] = useState<Record<string, string>>({})
  const [title, setTitle] = useState(editPost?.title ?? '')
  const [content, setContent] = useState(editPost?.content ?? '')
  const [platforms, setPlatforms] = useState<string[]>(editPost?.platforms ?? ['vk'])
  const [tags, setTags] = useState<string[]>(editPost?.tags ?? [])
  const [status, setStatus] = useState<'draft' | 'scheduled' | 'published'>(editPost?.status ?? 'draft')
  const [schedAt, setSchedAt] = useState(editPost?.scheduled_at ? editPost.scheduled_at.slice(0, 16) : '')
  const [media, setMedia] = useState<MediaItem[]>(editPost?.media ?? [])
  const [uploading, setUploading] = useState(false)
  const fileInputRef = useRef<HTMLInputElement | null>(null)
  const [gen, setGen] = useState(false)
  const [saving, setSaving] = useState(false)
  const [tagIn, setTagIn] = useState('')
  const [emojiPickerOpen, setEmojiPickerOpen] = useState(false)
  const [aiModalOpen, setAiModalOpen] = useState(false)
  const [aiLoading, setAiLoading] = useState<'creative' | 'russify' | null>(null)
  const [prevContent, setPrevContent] = useState<string | null>(null)

  useEffect(() => { api.getTemplates().then(setTmpls).catch(console.error) }, [])

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
        template_type: tmplType || null,
      }
      if (isEdit) await api.updatePost(editPost!.id, body)
      else await api.createPost(body)
      showToast(isEdit ? 'Пост обновлён!' : 'Пост создан!', 'success')
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

  async function enhanceWithAI(mode: 'creative' | 'russify') {
    if (!content.trim()) { showToast('Сначала введите текст поста', 'error'); return }
    setAiLoading(mode)
    try {
      const d = await api.enhanceText(content, mode)
      setPrevContent(content)
      setContent(d.text)
      setAiModalOpen(false)
      showToast(mode === 'creative' ? '✨ Текст улучшен!' : '🔤 Русификация применена!', 'success')
    } catch (e: unknown) { showToast((e as Error).message, 'error') }
    finally { setAiLoading(null) }
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
    const textarea = textareaRef.current
    if (!textarea) {
      setContent(prev => `${prev}${emoji}`)
      return
    }
    const start = textarea.selectionStart ?? content.length
    const end = textarea.selectionEnd ?? content.length
    const nextValue = `${content.slice(0, start)}${emoji}${content.slice(end)}`
    setContent(nextValue)
    requestAnimationFrame(() => {
      textarea.focus()
      const nextPos = start + emoji.length
      textarea.setSelectionRange(nextPos, nextPos)
    })
  }

  function handleEmojiPick(emojiData: EmojiClickData) {
    insertEmoji(emojiData.emoji)
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
                    {step > s.n ? '✓' : s.n}
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
                  <div className="tmpl-icon" style={{ fontSize: 20 }}>{TICO[t.type] ?? '≡'}</div>
                  <div className="tmpl-name">{t.name}</div>
                  <div className="tmpl-desc">{t.description}</div>
                </div>
              ))}
              <div className={`tmpl-card${tmplType === '' ? ' sel' : ''}`} onClick={() => setTmplType('')}>
                <div className="tmpl-icon" style={{ fontSize: 20 }}>✍</div>
                <div className="tmpl-name">С нуля</div>
                <div className="tmpl-desc">Написать пост самостоятельно</div>
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
                {!gen && <span className="btn-icon">✦</span>}
              </button>
            </div>
          </div>
        )}

        {/* Step 3: редактор */}
        {step === 3 && (
          <div className="card card-p">
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
                    onClick={() => setAiModalOpen(true)}
                  >
                    <span className="ai-assist-icon">✦</span> ИИ-помощник
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
                <button
                  type="button"
                  className="emoji-fab"
                  onClick={() => setEmojiPickerOpen(true)}
                  title="Открыть меню эмодзи"
                >
                  ✨ Эмодзи
                </button>
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
                        <img src={item.url} alt={item.filename} style={{ width: 96, height: 96, objectFit: 'cover', display: 'block' }} />
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
              <button
                type="button"
                className="btn btn-secondary"
                onClick={() => fileInputRef.current?.click()}
                disabled={uploading}
                style={{ alignSelf: 'flex-start' }}
              >
                {uploading ? 'Загружаем...' : '+ Добавить фото / видео / документ'}
              </button>
            </div>

            <div style={{ display: 'flex', justifyContent: 'space-between', gap: 10 }}>
              {!isEdit && <button className="btn btn-secondary" onClick={() => setStep(tmplType ? 2 : 1)}>← Назад</button>}
              {isEdit && <button className="btn btn-secondary" onClick={() => router.push('/posts')}>Отмена</button>}
              <button className="btn btn-primary" onClick={() => isEdit ? save() : setStep(4)} disabled={saving}>
                {isEdit ? (saving ? 'Сохраняем...' : 'Сохранить') : 'Далее'}
                {!saving && <span className="btn-icon">{isEdit ? '✓' : '→'}</span>}
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
                    {platforms.includes(pl.id) ? '✓ ' : ''}{pl.l}
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
                <option value="draft">○ Черновик</option>
                <option value="scheduled">◑ Запланировать</option>
                <option value="published">● Опубликовать сейчас</option>
              </select>
            </div>

            {status === 'scheduled' && (
              <div className="fg">
                <label>Дата и время публикации</label>
                <input type="datetime-local" value={schedAt} onChange={e => setSchedAt(e.target.value)} />
              </div>
            )}

            <div style={{ marginBottom: 16 }}>
              <div style={{ fontSize: 10, fontWeight: 700, color: 'var(--text-3)', marginBottom: 8, textTransform: 'uppercase', letterSpacing: '0.1em' }}>Предпросмотр</div>
              <div className="preview">{content}</div>
            </div>

            <div style={{ display: 'flex', justifyContent: 'space-between', gap: 10 }}>
              <button className="btn btn-secondary" onClick={() => setStep(3)}>← Назад</button>
              <button className="btn btn-primary" onClick={save} disabled={saving}>
                {saving ? 'Сохраняем...' : status === 'published' ? 'Опубликовать' : status === 'scheduled' ? 'Запланировать' : 'Сохранить'}
                {!saving && <span className="btn-icon">{status === 'published' ? '↗' : '✓'}</span>}
              </button>
            </div>
          </div>
        )}
      </div>
      {emojiPickerOpen && (
        <div className="overlay" onClick={() => setEmojiPickerOpen(false)}>
          <div className="modal emoji-modal" onClick={e => e.stopPropagation()}>
            <div className="modal-hd">
              <div>
                <div className="card-title">Выбор эмодзи</div>
                <div className="ts tg" style={{ marginTop: 4 }}>Выбери эмодзи, и он вставится в текст в позицию курсора.</div>
              </div>
              <button type="button" className="btn btn-secondary btn-sm" onClick={() => setEmojiPickerOpen(false)}>
                Закрыть
              </button>
            </div>
            <div className="modal-bd emoji-modal-bd">
              <EmojiPicker
                onEmojiClick={handleEmojiPick}
                autoFocusSearch={false}
                skinTonesDisabled
                previewConfig={{ showPreview: false }}
                lazyLoadEmojis
                theme={Theme.DARK}
                width="100%"
                height={420}
              />
            </div>
            <div className="modal-ft">
              {emojiSuggestions.length > 0 && (
                <button type="button" className="btn btn-secondary" onClick={applyAllSuggestions}>
                  Добавить подсказанные эмодзи
                </button>
              )}
              <button type="button" className="btn btn-primary" onClick={() => setEmojiPickerOpen(false)}>
                Готово
              </button>
            </div>
          </div>
        </div>
      )}
      {aiModalOpen && (
        <div className="overlay" onClick={() => { if (!aiLoading) setAiModalOpen(false) }}>
          <div className="modal ai-modal" onClick={e => e.stopPropagation()}>
            <div className="modal-hd">
              <div>
                <div className="card-title">✦ ИИ-помощник</div>
                <div className="ts tg" style={{ marginTop: 4 }}>Выберите, что сделать с текстом поста</div>
              </div>
              <button type="button" className="btn btn-secondary btn-sm" onClick={() => { if (!aiLoading) setAiModalOpen(false) }}>
                Закрыть
              </button>
            </div>
            <div className="ai-modal-bd">
              <button
                className="ai-mode-card"
                onClick={() => enhanceWithAI('creative')}
                disabled={!!aiLoading}
              >
                <span className="ai-mode-icon">✨</span>
                <div className="ai-mode-body">
                  <div className="ai-mode-title">Улучшить текст</div>
                  <div className="ai-mode-desc">Сделает пост ярким и цепляющим для молодёжной аудитории, сохранив все факты</div>
                </div>
                {aiLoading === 'creative' && <span className="ai-spinner" />}
              </button>
              <button
                className="ai-mode-card"
                onClick={() => enhanceWithAI('russify')}
                disabled={!!aiLoading}
              >
                <span className="ai-mode-icon">🔤</span>
                <div className="ai-mode-body">
                  <div className="ai-mode-title">Русифицировать</div>
                  <div className="ai-mode-desc">Заменит англицизмы и заимствования на естественные русские слова</div>
                </div>
                {aiLoading === 'russify' && <span className="ai-spinner" />}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
