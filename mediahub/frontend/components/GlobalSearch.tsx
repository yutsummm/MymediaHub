'use client'
import { useState, useEffect, useRef } from 'react'
import { useRouter } from 'next/navigation'
import { api } from '@/lib/api'
import { useGroup } from '@/contexts/GroupContext'
import type { Post } from '@/lib/types'

const STATUS_COLOR: Record<string, string> = {
  draft:     'var(--text-3)',
  scheduled: 'var(--yellow)',
  published: 'var(--green)',
}

const STATUS_LABEL: Record<string, string> = {
  draft:     'Черновик',
  scheduled: 'Запланирован',
  published: 'Опубликован',
}

export default function GlobalSearch() {
  const router = useRouter()
  const { currentGroup } = useGroup()
  const [term, setTerm] = useState('')
  const [results, setResults] = useState<Post[]>([])
  const [open, setOpen] = useState(false)
  const [loading, setLoading] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)
  const wrapRef = useRef<HTMLDivElement>(null)
  const timerRef = useRef<ReturnType<typeof setTimeout>>()

  useEffect(() => {
    if (!term.trim()) { setResults([]); setOpen(false); return }
    setLoading(true)
    clearTimeout(timerRef.current)
    timerRef.current = setTimeout(async () => {
      try {
        const params: Record<string, string> = { q: term.trim(), limit: '10' }
        const data = currentGroup
          ? await api.getGroupPosts(currentGroup.id, params)
          : await api.getPosts(params)
        setResults(data.posts)
        setOpen(true)
      } catch { setResults([]) }
      finally { setLoading(false) }
    }, 300)
    return () => clearTimeout(timerRef.current)
  }, [term, currentGroup])

  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (wrapRef.current && !wrapRef.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', handleClick)
    return () => document.removeEventListener('mousedown', handleClick)
  }, [])

  useEffect(() => {
    function handleKey(e: KeyboardEvent) {
      if ((e.metaKey || e.ctrlKey) && e.key === 'k') { e.preventDefault(); inputRef.current?.focus() }
    }
    document.addEventListener('keydown', handleKey)
    return () => document.removeEventListener('keydown', handleKey)
  }, [])

  function selectPost(post: Post) {
    setOpen(false); setTerm('')
    router.push(`/posts/${post.id}/edit`)
  }

  return (
    <div ref={wrapRef} style={{ position: 'relative' }}>
      <div className="search-input-wrap">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" style={{ flexShrink: 0, color: 'var(--text-3)' }}>
          <circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/>
        </svg>
        <input
          ref={inputRef}
          type="text"
          className="search-input"
          placeholder="Поиск... (⌘K)"
          value={term}
          onChange={e => setTerm(e.target.value)}
          onFocus={() => { if (results.length > 0) setOpen(true) }}
        />
        {loading && (
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" style={{ animation: 'spin 0.7s linear infinite', flexShrink: 0, color: 'var(--text-3)' }}>
            <path d="M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83M2 12h4M18 12h4M4.93 19.07l2.83-2.83M16.24 7.76l2.83-2.83"/>
          </svg>
        )}
      </div>

      {open && results.length > 0 && (
        <div className="search-dropdown">
          {results.map(p => (
            <div
              key={p.id}
              className="search-result-item"
              onClick={() => selectPost(p)}
              role="button"
              tabIndex={0}
              onKeyDown={e => { if (e.key === 'Enter') selectPost(p) }}
            >
              <div className="search-result-main">
                <span className="search-result-title">{p.title || '(без заголовка)'}</span>
                <span className="search-result-content">{p.content?.slice(0, 80)}</span>
              </div>
              <div className="search-result-meta">
                <span className="search-result-badge" style={{ background: STATUS_COLOR[p.status] }}>
                  {STATUS_LABEL[p.status]}
                </span>
                <span className="search-result-date">
                  {new Date(p.scheduled_at ?? p.published_at ?? p.created_at).toLocaleDateString('ru-RU', { day: 'numeric', month: 'short' })}
                </span>
              </div>
            </div>
          ))}
        </div>
      )}

      {open && term && !loading && results.length === 0 && (
        <div className="search-dropdown">
          <div className="search-empty">Ничего не найдено</div>
        </div>
      )}
    </div>
  )
}
