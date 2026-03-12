'use client';

import { useState, useEffect, useCallback, useRef } from 'react';

interface UseDeviceParallaxOptions {
  /** Maximum offset in pixels (default: 20) */
  maxOffset?: number;
  /** Smoothing factor 0-1, higher = smoother but slower (default: 0.15) */
  smoothing?: number;
  /** Whether parallax is enabled (default: true) */
  enabled?: boolean;
}

interface UseDeviceParallaxResult {
  /** Current parallax offset in pixels */
  offset: { x: number; y: number };
  /** Whether device orientation is supported */
  isSupported: boolean;
  /** Whether permission was granted (iOS 13+) */
  hasPermission: boolean;
  /** Request permission (required for iOS 13+) */
  requestPermission: () => Promise<boolean>;
  /** Whether currently active */
  isActive: boolean;
}

/**
 * Hook for parallax effect based on device tilt (gyroscope/accelerometer)
 * Works on iOS and Android mobile browsers
 */
export function useDeviceParallax(
  options: UseDeviceParallaxOptions = {}
): UseDeviceParallaxResult {
  const { maxOffset = 20, smoothing = 0.15, enabled = true } = options;

  const [offset, setOffset] = useState({ x: 0, y: 0 });
  const [isSupported, setIsSupported] = useState(false);
  const [hasPermission, setHasPermission] = useState(false);
  const [isActive, setIsActive] = useState(false);

  // Use refs for smooth animation
  const targetOffset = useRef({ x: 0, y: 0 });
  const currentOffset = useRef({ x: 0, y: 0 });
  const animationFrameId = useRef<number | null>(null);

  // Check support on mount
  useEffect(() => {
    if (typeof window === 'undefined') return;

    const supported = 'DeviceOrientationEvent' in window;
    setIsSupported(supported);

    // On non-iOS devices, permission is implicitly granted
    // iOS 13+ requires explicit permission request
    const isIOS =
      /iPad|iPhone|iPod/.test(navigator.userAgent) ||
      (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1);

    if (supported && !isIOS) {
      setHasPermission(true);
    }
  }, []);

  // Request permission (iOS 13+)
  const requestPermission = useCallback(async (): Promise<boolean> => {
    if (typeof window === 'undefined') return false;

    // Check if DeviceOrientationEvent.requestPermission exists (iOS 13+)
    const DeviceOrientationEventWithPermission = DeviceOrientationEvent as typeof DeviceOrientationEvent & {
      requestPermission?: () => Promise<'granted' | 'denied' | 'default'>;
    };

    if (typeof DeviceOrientationEventWithPermission.requestPermission === 'function') {
      try {
        const permission = await DeviceOrientationEventWithPermission.requestPermission();
        const granted = permission === 'granted';
        setHasPermission(granted);
        return granted;
      } catch {
        setHasPermission(false);
        return false;
      }
    }

    // Non-iOS or older iOS - permission is implicit
    setHasPermission(true);
    return true;
  }, []);

  // Smooth animation loop
  useEffect(() => {
    if (!enabled || !hasPermission) return;

    const animate = () => {
      // Lerp (linear interpolation) for smooth movement
      currentOffset.current.x +=
        (targetOffset.current.x - currentOffset.current.x) * smoothing;
      currentOffset.current.y +=
        (targetOffset.current.y - currentOffset.current.y) * smoothing;

      // Only update state if there's meaningful change (avoid unnecessary re-renders)
      const dx = Math.abs(currentOffset.current.x - offset.x);
      const dy = Math.abs(currentOffset.current.y - offset.y);

      if (dx > 0.1 || dy > 0.1) {
        setOffset({
          x: Math.round(currentOffset.current.x * 10) / 10,
          y: Math.round(currentOffset.current.y * 10) / 10,
        });
      }

      animationFrameId.current = requestAnimationFrame(animate);
    };

    animationFrameId.current = requestAnimationFrame(animate);

    return () => {
      if (animationFrameId.current) {
        cancelAnimationFrame(animationFrameId.current);
      }
    };
  }, [enabled, hasPermission, smoothing, offset.x, offset.y]);

  // Device orientation handler
  useEffect(() => {
    if (!enabled || !isSupported || !hasPermission) return;

    const handleOrientation = (event: DeviceOrientationEvent) => {
      // beta: front-back tilt (-180 to 180, 0 = flat)
      // gamma: left-right tilt (-90 to 90, 0 = flat)
      const { beta, gamma } = event;

      if (beta === null || gamma === null) return;

      setIsActive(true);

      // Normalize to -1 to 1 range
      // beta: typical phone usage is around 45-90 degrees, normalize around 60
      // gamma: -45 to 45 is comfortable range
      const normalizedY = Math.max(-1, Math.min(1, (beta - 60) / 30));
      const normalizedX = Math.max(-1, Math.min(1, gamma / 30));

      // Apply max offset
      targetOffset.current = {
        x: normalizedX * maxOffset,
        y: normalizedY * maxOffset,
      };
    };

    window.addEventListener('deviceorientation', handleOrientation, true);

    return () => {
      window.removeEventListener('deviceorientation', handleOrientation, true);
      setIsActive(false);
    };
  }, [enabled, isSupported, hasPermission, maxOffset]);

  return {
    offset,
    isSupported,
    hasPermission,
    requestPermission,
    isActive,
  };
}

export default useDeviceParallax;
