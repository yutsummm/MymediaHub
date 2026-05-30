import Link from 'next/link'

export default function NotFound() {
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
        404
      </div>
      <h1 style={{ fontSize: 22, fontWeight: 700, color: 'var(--text)', margin: 0 }}>Страница не найдена</h1>
      <p style={{ color: 'var(--text-2)', fontSize: 14, maxWidth: 400, lineHeight: 1.6, margin: 0 }}>
        Возможно, она была удалена или вы перешли по неверной ссылке.
      </p>
      <Link
        href="/dashboard"
        style={{
          marginTop: 8,
          padding: '10px 24px',
          borderRadius: 8,
          background: 'var(--accent)',
          color: 'var(--btn-primary-fg)',
          fontSize: 14,
          fontWeight: 600,
          textDecoration: 'none',
        }}
      >
        На главную
      </Link>
    </div>
  )
}
