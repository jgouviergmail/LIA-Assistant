'use client';
import { useEffect, useState } from 'react';
import { nativePhotoAvailable } from '@/lib/native/photo';
export function useNativePhotoSharing() {
  const [available, setAvailable] = useState(false);
  useEffect(() => {
    let alive = true;
    void nativePhotoAvailable().then(value => {
      if (alive) setAvailable(value);
    });
    return () => {
      alive = false;
    };
  }, []);
  return available;
}
