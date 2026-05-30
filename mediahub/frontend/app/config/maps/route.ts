import { NextResponse } from 'next/server'

export const dynamic = 'force-dynamic'
export const revalidate = 0

function getYandexMapsKey() {
  return (
    process.env.NEXT_PUBLIC_YANDEX_MAPS_KEY ||
    process.env.NEXT_PUBLIC_YANDEX_MAPS_API_KEY ||
    process.env.YANDEX_MAPS_KEY ||
    process.env.YANDEX_MAPS_API_KEY ||
    ''
  ).trim()
}

export function GET() {
  return NextResponse.json(
    { yandexMapsKey: getYandexMapsKey() },
    {
      headers: {
        'Cache-Control': 'no-store, no-cache, must-revalidate',
      },
    }
  )
}
