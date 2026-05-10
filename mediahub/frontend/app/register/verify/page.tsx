'use client'
import { useEffect, Suspense } from 'react'
import { useRouter } from 'next/navigation'

function VerifyRedirect() {
  const router = useRouter()
  useEffect(() => { router.replace('/register') }, [router])
  return null
}

export default function VerifyRegisterPage() {
  return <Suspense><VerifyRedirect /></Suspense>
}
