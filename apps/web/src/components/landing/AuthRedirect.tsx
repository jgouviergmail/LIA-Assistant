'use client';

import { useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { useAuth } from '@/hooks/useAuth';

interface AuthRedirectProps {
  lng: string;
}

export function AuthRedirect({ lng }: AuthRedirectProps) {
  const router = useRouter();
  const { user, isLoading } = useAuth();

  useEffect(() => {
    if (!isLoading && user) {
      router.push(`/${lng}/dashboard`);
    }
  }, [user, isLoading, router, lng]);

  return null;
}
