/** @type {import('next').NextConfig} */
const nextConfig = {
  async rewrites() {
    const isProd = process.env.NODE_ENV === 'production'
    const fallback = isProd
      ? 'https://backend-production-30d6.up.railway.app'
      : 'http://localhost:8000'
    const backendUrl = (process.env.BACKEND_URL || fallback).replace(/\/$/, '')
    console.log(`[next.config] proxying /api/* -> ${backendUrl}`)
    return [
      { source: '/api/:path*', destination: `${backendUrl}/api/:path*` },
    ]
  },
}

export default nextConfig
