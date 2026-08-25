'use client'
import { useEffect, useState } from 'react'
import Link from 'next/link'
import { api } from '@/lib/api'
import { useGroup } from '@/contexts/GroupContext'
import type { OnboardingProgress } from '@/lib/types'

const HIDDEN_KEY = 'mediahub_onboarding_hidden'

/**
 * Карточка «Начало работы»: что в группе ещё не настроено.
 *
 * У системы больше тридцати функций и ни одной подсказки о том, что они есть.
 * Человек, зашедший впервые, видел пустой дашборд и не знал ни про
 * согласование, ни про медиатеку, ни про расписание, ни про отчёты — половина
 * уже написанной работы просто не находилась.
 *
 * Карточка исчезает сама, когда обязательные шаги пройдены: подсказка, которая
 * больше не подсказывает, превращается в шум. Скрыть её можно и раньше — тогда
 * решение запоминается в браузере, а не на сервере: это предпочтение одного
 * человека за одним компьютером, и хранить его в общей базе незачем.
 */
export default function Onboarding() {
  const { currentGroup } = useGroup()
  const [state, setState] = useState<OnboardingProgress | null>(null)
  const [hidden, setHidden] = useState(true)

  useEffect(() => {
    try { setHidden(localStorage.getItem(HIDDEN_KEY) === '1') } catch { setHidden(false) }
  }, [])

  useEffect(() => {
    if (!currentGroup) { setState(null); return }
    api.getOnboarding(currentGroup.id).then(setState).catch(() => setState(null))
  }, [currentGroup])

  function hide() {
    setHidden(true)
    try { localStorage.setItem(HIDDEN_KEY, '1') } catch {}
  }

  if (!state || hidden || state.complete) return null

  const percent = state.total ? Math.round((state.done / state.total) * 100) : 0

  return (
    <div className="card anim-in" style={{ marginBottom: 20 }}>
      <div className="card-header" style={{ gap: 12, flexWrap: 'wrap' }}>
        <span className="card-title">Начало работы</span>
        <div className="onb-head" style={{ flex: 1 }}>
          <div className="onb-bar"><i style={{ width: `${percent}%` }} /></div>
          <span className="onb-count">{state.done} из {state.total}</span>
        </div>
        <button className="btn btn-ghost btn-sm" onClick={hide}>Скрыть</button>
      </div>

      <div style={{ padding: '4px 20px 16px' }}>
        <div className="onb-list">
          {state.steps.map(step => (
            <Link key={step.key} href={step.href}
              className={`onb-step${step.done ? ' done' : ''}`}>
              <span className="onb-mark">{step.done ? '✓' : ''}</span>
              <span style={{ minWidth: 0 }}>
                <span className="onb-ttl">
                  {step.title}
                  {step.optional && <span className="onb-opt">необязательно</span>}
                </span>
                <span className="onb-hint">{step.hint}</span>
              </span>
            </Link>
          ))}
        </div>
      </div>
    </div>
  )
}
