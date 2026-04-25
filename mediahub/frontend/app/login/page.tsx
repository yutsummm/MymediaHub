'use client'
import { useState } from 'react'
import { useRouter } from 'next/navigation'
import { useAuth } from '@/contexts/AuthContext'
import { api } from '@/lib/api'

const DEMOS = [
  { email: 'admin@mediahub.ru',    label: '🔑 Администратор' },
  { email: 'editor@mediahub.ru',   label: '✏️ Редактор' },
  { email: 'observer@mediahub.ru', label: '👁 Наблюдатель' },
]

export default function LoginPage() {
  const { login } = useAuth()
  const router = useRouter()
  const [email, setEmail] = useState('admin@mediahub.ru')
  const [loading, setLoading] = useState(false)
  const [err, setErr] = useState('')

  async function submit(e: React.FormEvent) {
    e.preventDefault()
    setLoading(true); setErr('')
    try {
      const { user } = await api.login(email)
      login(user)
      router.push('/dashboard')
    } catch (ex: unknown) {
      setErr((ex as Error).message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div style={{ minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center', background: 'var(--gray-900)' }}>
      <div style={{ background: '#fff', borderRadius: 16, padding: 40, width: 400, boxShadow: '0 25px 50px rgba(0,0,0,.3)' }}>
        <div style={{ textAlign: 'center', marginBottom: 32 }}>
          <div style={{ fontSize: 52, marginBottom: 10 }}>📡</div>
          <h1 style={{ fontSize: 24, fontWeight: 800, marginBottom: 4 }}>MediaHub</h1>
          <p style={{ color: 'var(--gray-500)', fontSize: 14 }}>Медиахаб для молодёжных центров</p>
        </div>

        <form onSubmit={submit}>
          <div className="fg">
            <label>Email</label>
            <input type="email" value={email} onChange={e => setEmail(e.target.value)} required />
          </div>
          <div className="fg">
            <label>Пароль</label>
            <input type="password" defaultValue="••••••••" readOnly />
          </div>
          {err && <div style={{ color: 'var(--red)', fontSize: 13, marginBottom: 12 }}>{err}</div>}
          <button type="submit" className="btn btn-primary" style={{ width: '100%', justifyContent: 'center', padding: 12 }} disabled={loading}>
            {loading ? '⏳ Входим...' : '🚀 Войти'}
          </button>
        </form>

        <div style={{ marginTop: 20, borderTop: '1px solid var(--gray-200)', paddingTop: 16 }}>
          <p style={{ fontSize: 12, color: 'var(--gray-400)', marginBottom: 10 }}>Демо-аккаунты:</p>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            {DEMOS.map(d => (
              <button key={d.email} type="button" onClick={() => setEmail(d.email)} className="btn btn-secondary btn-sm" style={{ justifyContent: 'flex-start', fontSize: 12 }}>
                {d.label} <span style={{ color: 'var(--gray-400)', marginLeft: 4 }}>{d.email}</span>
              </button>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}
