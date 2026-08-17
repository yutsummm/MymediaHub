'use client'
import { useEffect, useRef, useState, memo } from 'react'

type Variant = 'danger' | 'warning' | 'info'

const ICONS: Record<Variant, React.ReactNode> = {
  danger: (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/>
      <line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/>
    </svg>
  ),
  warning: (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/>
    </svg>
  ),
  info: (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/>
    </svg>
  ),
}

const ConfirmDialog = memo(function ConfirmDialog({
  open,
  title,
  description,
  variant = 'danger',
  confirmLabel = 'Подтвердить',
  cancelLabel = 'Отмена',
  loading = false,
  confirmWith,
  confirmHint,
  details,
  onConfirm,
  onCancel,
}: {
  open: boolean
  title: string
  description?: string
  variant?: Variant
  confirmLabel?: string
  cancelLabel?: string
  loading?: boolean
  /**
   * Точная фраза, которую нужно набрать: название группы или почта.
   * Нажать «Да» можно не глядя, набрать название своей группы — нет.
   * Без совпадения кнопка не работает, и то же самое проверяет сервер.
   */
  confirmWith?: string
  confirmHint?: React.ReactNode
  /** Смета: что именно исчезнет. Считает сервер, мы только показываем. */
  details?: { label: string; value: number | string }[]
  onConfirm: () => void
  onCancel: () => void
}) {
  const confirmRef = useRef<HTMLButtonElement>(null)
  const inputRef = useRef<HTMLInputElement>(null)
  const [typed, setTyped] = useState('')

  // Открыли заново — поле обязано быть пустым: подтверждение прошлого
  // удаления не должно засчитываться следующему.
  useEffect(() => { if (open) setTyped('') }, [open, confirmWith])

  const matches = !confirmWith || typed.trim() === confirmWith.trim()

  useEffect(() => {
    if (open) {
      if (confirmWith) inputRef.current?.focus()
      else confirmRef.current?.focus()
      const handleEsc = (e: KeyboardEvent) => { if (e.key === 'Escape') onCancel() }
      document.addEventListener('keydown', handleEsc)
      return () => document.removeEventListener('keydown', handleEsc)
    }
  }, [open, onCancel, confirmWith])

  if (!open) return null

  return (
    <div className="confirm-overlay" onClick={onCancel}>
      <div className="confirm-box" onClick={e => e.stopPropagation()} role="dialog" aria-modal="true">
        <div className="confirm-hd">
          <div className={`confirm-icon confirm-icon-${variant}`}>
            {ICONS[variant]}
          </div>
          <div style={{ flex: 1, minWidth: 0 }}>
            <div className="confirm-title">{title}</div>
            {description && <div className="confirm-desc">{description}</div>}
          </div>
        </div>
        {details && details.length > 0 && (
          <div className="confirm-details">
            {details.map(d => (
              <div key={d.label} className="confirm-details-row">
                <span>{d.label}</span>
                <b>{d.value}</b>
              </div>
            ))}
          </div>
        )}
        {confirmWith && (
          <div className="confirm-typebox">
            <label className="confirm-typebox-label">
              {confirmHint || <>Для подтверждения введите <b>{confirmWith}</b></>}
            </label>
            <input
              ref={inputRef}
              className="input"
              value={typed}
              onChange={e => setTyped(e.target.value)}
              onKeyDown={e => { if (e.key === 'Enter' && matches && !loading) onConfirm() }}
              placeholder={confirmWith}
              autoComplete="off"
              spellCheck={false}
            />
          </div>
        )}
        <div className="confirm-ft">
          <button
            className="btn btn-ghost btn-sm"
            onClick={onCancel}
            disabled={loading}
          >
            {cancelLabel}
          </button>
          <button
            ref={confirmRef}
            className={`btn btn-sm ${variant === 'danger' ? 'btn-danger' : variant === 'warning' ? 'btn-primary' : 'btn-primary'}`}
            onClick={onConfirm}
            disabled={loading || !matches}
            title={matches ? undefined : 'Введите точное название, чтобы подтвердить'}
          >
            {loading ? '...' : confirmLabel}
          </button>
        </div>
      </div>
    </div>
  )
})

export default ConfirmDialog
