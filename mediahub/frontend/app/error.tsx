'use client'

export default function ErrorPage({
  error,
  reset,
}: {
  error: Error & { digest?: string }
  reset: () => void
}) {
  return (
    <div style={{
      minHeight: '100dvh',
      display: 'flex',
      flexDirection: 'column',
      alignItems: 'center',
      justifyContent: 'center',
      gap: 16,
      padding: 24,
      background: 'var(--bg)',
      color: 'var(--text)',
      textAlign: 'center',
    }}>
      <div style={{ fontSize: 72, fontWeight: 800, letterSpacing: '-0.06em', color: 'var(--text-3)', lineHeight: 1 }}>
        500
      </div>
      <h1 style={{ fontSize: 22, fontWeight: 700, color: 'var(--text)', margin: 0 }}>Что-то пошло не так</h1>
      <p style={{ color: 'var(--text-2)', fontSize: 14, maxWidth: 400, lineHeight: 1.6, margin: 0 }}>
        Произошла внутренняя ошибка сервера. Попробуйте обновить страницу.
      </p>
      <div style={{ display: 'flex', gap: 10, marginTop: 8 }}>
        <button
          onClick={reset}
          style={{
            padding: '10px 24px',
            borderRadius: 8,
            background: 'var(--accent)',
            color: 'var(--btn-primary-fg)',
            fontSize: 14,
            fontWeight: 600,
            border: 'none',
            cursor: 'pointer',
          }}
        >
          Попробовать снова
        </button>
      </div>
    </div>
  )
}
