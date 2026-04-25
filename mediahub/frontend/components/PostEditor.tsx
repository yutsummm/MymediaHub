'use client'
import { useState, useEffect } from 'react'
import { useRouter } from 'next/navigation'
import { api } from '@/lib/api'
import { useToast } from '@/contexts/ToastContext'
import type { Post, Template } from '@/lib/types'

const TICO: Record<string, string> = { announcement: '◈', results: '✓', vacancy: '↗', grant: '◎' }
const STEPS = [{ n: 1, l: 'Шаблон' }, { n: 2, l: 'Данные' }, { n: 3, l: 'Редактор' }, { n: 4, l: 'Публикация' }]

export default function PostEditor({ editPost }: { editPost?: Post }) {
  const router = useRouter()
  const { showToast } = useToast()
  const isEdit = !!editPost

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
  const [gen, setGen] = useState(false)
  const [saving, setSaving] = useState(false)
  const [tagIn, setTagIn] = useState('')

  useEffect(() => { api.getTemplates().then(setTmpls).catch(console.error) }, [])

  async function generateText() {
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
      const body = { title, content, status, platforms, tags, scheduled_at: schedAt || null, template_type: tmplType || null }
      if (isEdit) await api.updatePost(editPost!.id, body)
      else await api.createPost(body)
      showToast(isEdit ? 'Пост обновлён!' : 'Пост создан!', 'success')
      router.push('/posts')
    } catch (e: unknown) { showToast((e as Error).message, 'error') }
    finally { setSaving(false) }
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
            {tmplFields.map(f => (
              <div key={f.key} className="fg">
                <label>{f.label}</label>
                <input type="text" placeholder={f.placeholder} value={fields[f.key] ?? ''}
                  onChange={e => setFields(p => ({ ...p, [f.key]: e.target.value }))} />
              </div>
            ))}
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
              <label>Текст поста</label>
              <textarea value={content} onChange={e => setContent(e.target.value)} rows={10} placeholder="Введите текст поста..." />
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
    </div>
  )
}
