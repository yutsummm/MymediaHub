'use client'

import { useEffect, useState } from 'react'

const BUILD_TIME_YANDEX_MAPS_KEY = (
  process.env.NEXT_PUBLIC_YANDEX_MAPS_KEY ||
  process.env.NEXT_PUBLIC_YANDEX_MAPS_API_KEY ||
  ''
).trim()

type MapsConfigResponse = {
  yandexMapsKey?: string
}

export function useYandexMapsKey() {
  const [key, setKey] = useState(BUILD_TIME_YANDEX_MAPS_KEY)
  const [loading, setLoading] = useState(!BUILD_TIME_YANDEX_MAPS_KEY)
  const [error, setError] = useState('')

  useEffect(() => {
    if (BUILD_TIME_YANDEX_MAPS_KEY) return

    const controller = new AbortController()

    async function loadRuntimeKey() {
      try {
        setLoading(true)
        setError('')
        const response = await fetch('/config/maps', {
          cache: 'no-store',
          signal: controller.signal,
        })

        if (!response.ok) {
          throw new Error('Не удалось получить настройки карты.')
        }

        const data = await response.json() as MapsConfigResponse
        setKey((data.yandexMapsKey || '').trim())
      } catch (err) {
        if (controller.signal.aborted) return
        setError(err instanceof Error ? err.message : 'Не удалось загрузить ключ Яндекс Карт.')
      } finally {
        if (!controller.signal.aborted) setLoading(false)
      }
    }

    void loadRuntimeKey()

    return () => controller.abort()
  }, [])

  return { key, loading, error }
}
