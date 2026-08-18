/** @type {import('next').NextConfig} */

/**
 * Адрес бэкенда, на который проксируются /api/* и /uploads/*.
 *
 * Умолчание на railway-домен оставлено только внутри самого Railway. Раньше оно
 * действовало в любой production-сборке, и это худший вид умолчания: развёрнутый
 * на своём сервере фронтенд без BACKEND_URL не падал, а молча работал с чужим
 * бэкендом — с чужими группами, постами и статистикой. Заметить такое можно
 * далеко не сразу.
 */
function resolveBackendUrl() {
  const configured = (process.env.BACKEND_URL || '').replace(/\/$/, '')
  if (configured) return configured

  if (process.env.NODE_ENV !== 'production') return 'http://localhost:8000'

  if (process.env.RAILWAY_ENVIRONMENT) {
    return 'https://backend-production-30d6.up.railway.app'
  }

  throw new Error(
    'BACKEND_URL не задан. Укажите адрес бэкенда — например ' +
    'BACKEND_URL=https://mediahub.example.ru — в окружении фронтенда. ' +
    'Без него сборка не знает, куда проксировать /api/* и /uploads/*.'
  )
}

const nextConfig = {
  async rewrites() {
    const backendUrl = resolveBackendUrl()
    console.log(`[next.config] proxying /api/* -> ${backendUrl}`)
    return [
      { source: '/api/:path*',     destination: `${backendUrl}/api/:path*` },
      { source: '/uploads/:path*', destination: `${backendUrl}/uploads/:path*` },
    ]
  },
}

export default nextConfig
