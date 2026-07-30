'use client'

import { createContext, useContext, useState, useCallback } from 'react'

interface Toast {
  id: number
  message: string
  detail?: string
  type: 'info' | 'success' | 'error' | 'warning'
  onUndo?: () => void
}

interface ToastCtx {
  showToast: (msg: string, type?: Toast['type'], detail?: string, onUndo?: () => void) => void
}

const ToastContext = createContext<ToastCtx>({ showToast: () => {} })

const S = {
  width: 15, height: 15, viewBox: '0 0 24 24', fill: 'none',
  stroke: 'currentColor', strokeWidth: 2.5,
  strokeLinecap: 'round' as const, strokeLinejoin: 'round' as const,
}

const ICONS = {
  success: <svg {...S}><polyline points="20 6 9 17 4 12"/></svg>,
  error:   <svg {...S}><circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/></svg>,
  warning: <svg {...S}><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>,
  info:    <svg {...S}><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>,
}

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([])

  const showToast = useCallback((message: string, type: Toast['type'] = 'info', detail?: string, onUndo?: () => void) => {
    const id = Date.now()
    setToasts(p => [...p, { id, message, type, detail, onUndo }])
    const dur = onUndo ? 12000 : detail ? 5000 : 3200
    setTimeout(() => setToasts(p => p.filter(t => t.id !== id)), dur)
  }, [])

  function dismiss(id: number) {
    setToasts(p => p.filter(t => t.id !== id))
  }

  return (
    <ToastContext.Provider value={{ showToast }}>
      {children}
      <div style={{
        position: 'fixed', bottom: 24, right: 24, zIndex: 1000,
        display: 'flex', flexDirection: 'column', gap: 8, alignItems: 'flex-end',
      }}>
        {toasts.map(t => (
          <div key={t.id} className={`toast toast-${t.type}`}>
            <span className={`toast-icon toast-icon-${t.type}`}>{ICONS[t.type]}</span>
            <div className="toast-body">
              <div className="toast-msg">{t.message}</div>
              {t.detail && <div className="toast-detail">{t.detail}</div>}
            </div>
            {t.onUndo ? (
              <button className="toast-undo" onClick={() => { t.onUndo!(); dismiss(t.id) }}>Отменить</button>
            ) : (
              <button className="toast-close" onClick={() => dismiss(t.id)}>×</button>
            )}
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  )
}

export const useToast = () => useContext(ToastContext)
