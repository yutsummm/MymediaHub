'use client'

function DefaultLoading() {
  return (
    <div className="state-wrap-loading">
      <div className="state-wrap-spinner" />
      <span style={{ fontSize: 13, fontWeight: 600 }}>Загрузка...</span>
    </div>
  )
}

function DefaultEmpty({ text }: { text?: string }) {
  return (
    <div className="empty-state">
      <div className="empty-state-icon">
        <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="0.8" strokeLinecap="round" strokeLinejoin="round">
          <circle cx="12" cy="12" r="10"/><path d="M16 16s-1.5-2-4-2-4 2-4 2"/><line x1="9" y1="9" x2="9.01" y2="9"/><line x1="15" y1="9" x2="15.01" y2="9"/>
        </svg>
      </div>
      <div className="empty-state-title">{text || 'Нет данных'}</div>
    </div>
  )
}

function DefaultError({ error, onRetry }: { error?: string; onRetry?: () => void }) {
  return (
    <div className="empty-state">
      <div className="empty-state-icon" style={{ color: 'var(--red)' }}>
        <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="0.8" strokeLinecap="round" strokeLinejoin="round">
          <circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/>
        </svg>
      </div>
      <div className="empty-state-title">Ошибка</div>
      <div className="empty-state-sub" style={{ maxWidth: 300 }}>{error || 'Произошла неизвестная ошибка'}</div>
      {onRetry && (
        <button className="btn btn-secondary btn-sm" style={{ marginTop: 8 }} onClick={onRetry}>
          Повторить
        </button>
      )}
    </div>
  )
}

type WrapperProps = {
  loading?: boolean
  error?: string | null
  empty?: boolean
  emptyText?: string
  onRetry?: () => void
  loadingFallback?: React.ReactNode
  emptyFallback?: React.ReactNode
  errorFallback?: React.ReactNode
  skeleton?: React.ReactNode
  children: React.ReactNode
}

export default function StateWrapper({
  loading,
  error,
  empty,
  emptyText,
  onRetry,
  loadingFallback,
  emptyFallback,
  errorFallback,
  skeleton,
  children,
}: WrapperProps) {
  if (loading) {
    return loadingFallback ?? skeleton ?? <DefaultLoading />
  }

  if (error) {
    return errorFallback ?? <DefaultError error={error} onRetry={onRetry} />
  }

  if (empty) {
    return emptyFallback ?? <DefaultEmpty text={emptyText} />
  }

  return <>{children}</>
}
