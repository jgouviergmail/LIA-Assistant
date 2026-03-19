/**
 * AudioQueue - Queue-based audio playback for voice comments.
 *
 * Manages sequential playback of base64-encoded audio chunks using Web Audio API.
 * Features:
 * - Queue-based playback (FIFO)
 * - Automatic sequential playback
 * - Interruption support (stop all playback)
 * - iOS Safari compatibility (AudioContext suspension handling)
 * - Silent warmup for iOS audio unlock
 * - Keep-alive mechanism to prevent iOS context suspension
 * - Graceful cleanup
 *
 * iOS Safari Considerations:
 * - AudioContext can be suspended at any time (tab switch, lock screen, inactivity)
 * - User gesture is required to resume suspended context
 * - Context state must be checked before EACH playback attempt
 * - Playing a silent buffer during user gesture "unlocks" the audio system
 * - Keep-alive pings prevent iOS from suspending context during inactivity
 *
 * Updated: 2026-01-16 - Added warmup() and keep-alive for robust iOS support
 */

// ============================================================================
// Configuration Constants
// ============================================================================

/** Maximum attempts to auto-resume AudioContext before requiring user interaction */
const AUDIO_MAX_RESUME_ATTEMPTS = 3;

/** Time window (ms) within which a user interaction is considered "recent" for iOS resume */
const AUDIO_USER_INTERACTION_WINDOW_MS = 1000;

/** Enable debug logging for audio playback (development only) */
const AUDIO_DEBUG_LOGGING = process.env.NODE_ENV === 'development';

/** Duration of silent buffer for iOS warmup (in seconds) */
const AUDIO_WARMUP_DURATION_SECONDS = 0.1;

/** Interval for iOS keep-alive ping (ms) - prevents context suspension during inactivity */
const AUDIO_KEEPALIVE_INTERVAL_MS = 25000; // 25 seconds (iOS suspends after ~30s inactivity)

// ============================================================================
// Utilities
// ============================================================================

/**
 * Conditional logger - only logs in development mode.
 * Prevents console noise in production while preserving debug info during development.
 */
const audioLogger = {
  log: (message: string, ...args: unknown[]) => {
    if (AUDIO_DEBUG_LOGGING) console.log(`[AudioQueue] ${message}`, ...args);
  },
  warn: (message: string, ...args: unknown[]) => {
    // Warnings always logged (useful for debugging production issues)
    console.warn(`[AudioQueue] ${message}`, ...args);
  },
  error: (message: string, ...args: unknown[]) => {
    console.error(`[AudioQueue] ${message}`, ...args);
  },
};

/**
 * Detect iOS Safari for platform-specific handling.
 * iOS Safari has unique AudioContext suspension behavior.
 */
const isIOSSafari = (): boolean => {
  if (typeof window === 'undefined') return false;
  const ua = window.navigator.userAgent;
  const isIOS =
    /iPad|iPhone|iPod/.test(ua) && !(window as Window & { MSStream?: unknown }).MSStream;
  const isSafari = /Safari/.test(ua) && !/Chrome/.test(ua) && !/CriOS/.test(ua);
  return isIOS || (isSafari && /Macintosh/.test(ua) && 'ontouchend' in document);
};

/**
 * Converts a base64 string to an ArrayBuffer.
 */
function base64ToArrayBuffer(base64: string): ArrayBuffer {
  const binaryString = atob(base64);
  const bytes = new Uint8Array(binaryString.length);
  for (let i = 0; i < binaryString.length; i++) {
    bytes[i] = binaryString.charCodeAt(i);
  }
  return bytes.buffer;
}

export type AudioQueueState = 'idle' | 'playing' | 'suspended' | 'error';

export class AudioQueue {
  private context: AudioContext | null = null;
  private queue: ArrayBuffer[] = [];
  private isPlaying = false;
  private currentSource: AudioBufferSourceNode | null = null;
  private onPlaybackComplete: (() => void) | null = null;
  private onError: ((error: Error) => void) | null = null;
  private onStateChange: ((state: AudioQueueState) => void) | null = null;
  private stateChangeHandler: (() => void) | null = null;
  private visibilityChangeHandler: (() => void) | null = null;
  private resumeAttempts = 0;
  private lastUserInteractionTime = 0;
  private keepAliveInterval: ReturnType<typeof setInterval> | null = null;
  private isWarmedUp = false;

  /**
   * Initialize the AudioContext.
   * Must be called after user interaction (browser autoplay policy).
   */
  async initialize(): Promise<void> {
    if (this.context && this.context.state !== 'closed') {
      // Context exists, just ensure it's running
      await this.ensureContextRunning();
      return;
    }

    try {
      // Create AudioContext (with webkit prefix for older Safari)
      const AudioContextClass =
        window.AudioContext ||
        (window as typeof window & { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;

      if (!AudioContextClass) {
        throw new Error('Web Audio API not supported');
      }

      this.context = new AudioContextClass();

      // Set up state change listener for iOS suspension detection
      this.setupStateChangeListener();

      // Set up visibility change listener for iOS background handling
      this.setupVisibilityChangeListener();

      // Initial resume attempt
      await this.ensureContextRunning();

      audioLogger.log('Initialized, state:', this.context.state);
    } catch (error) {
      audioLogger.error('Failed to initialize AudioContext:', error);
      this.onStateChange?.('error');
      throw error;
    }
  }

  /**
   * Set up listener for AudioContext state changes.
   * iOS Safari can suspend context at any time.
   */
  private setupStateChangeListener(): void {
    if (!this.context) return;

    this.stateChangeHandler = () => {
      const state = this.context?.state;
      audioLogger.log('Context state changed:', state);

      if (state === 'suspended') {
        this.onStateChange?.('suspended');
        // Don't auto-resume here - iOS requires user gesture
        // We'll try to resume on next enqueue/playNext
      } else if (state === 'running') {
        this.onStateChange?.(this.isPlaying ? 'playing' : 'idle');
        this.resumeAttempts = 0; // Reset attempts on successful run
      } else if (state === 'closed') {
        this.onStateChange?.('error');
      }
    };

    this.context.addEventListener('statechange', this.stateChangeHandler);
  }

  /**
   * Set up listener for page visibility changes.
   * iOS aggressively suspends audio when page is backgrounded.
   */
  private setupVisibilityChangeListener(): void {
    this.visibilityChangeHandler = () => {
      if (document.visibilityState === 'visible') {
        audioLogger.log('Page became visible, checking context...');
        // Try to resume when page becomes visible again
        this.ensureContextRunning().catch(err => {
          audioLogger.warn('Could not resume on visibility change:', err);
        });
      }
    };

    document.addEventListener('visibilitychange', this.visibilityChangeHandler);
  }

  /**
   * Ensure AudioContext is in 'running' state.
   * Critical for iOS where context can be suspended at any time.
   */
  private async ensureContextRunning(): Promise<boolean> {
    if (!this.context) return false;

    if (this.context.state === 'running') {
      return true;
    }

    if (this.context.state === 'closed') {
      audioLogger.warn('Context is closed, needs reinitialization');
      return false;
    }

    if (this.context.state === 'suspended') {
      // Check if we have a recent user interaction
      const timeSinceInteraction = Date.now() - this.lastUserInteractionTime;
      const hasRecentInteraction = timeSinceInteraction < AUDIO_USER_INTERACTION_WINDOW_MS;

      if (this.resumeAttempts >= AUDIO_MAX_RESUME_ATTEMPTS && !hasRecentInteraction) {
        audioLogger.warn('Max resume attempts reached, needs user interaction', {
          attempts: this.resumeAttempts,
          timeSinceInteraction,
        });
        return false;
      }

      try {
        this.resumeAttempts++;
        audioLogger.log('Attempting to resume context, attempt:', this.resumeAttempts);
        await this.context.resume();

        // Re-read state after async resume (state may have changed)
        // Cast needed because TS narrowing doesn't understand resume() changes state
        const newState = this.context.state as AudioContextState;
        if (newState === 'running') {
          audioLogger.log('Context resumed successfully');
          this.resumeAttempts = 0;
          return true;
        }
      } catch (error) {
        audioLogger.warn('Failed to resume context:', error);
      }
    }

    // Re-read state for final check (cast for same reason)
    return (this.context.state as AudioContextState) === 'running';
  }

  /**
   * Record user interaction timestamp.
   * Call this on any user gesture to enable audio resume on iOS.
   */
  recordUserInteraction(): void {
    this.lastUserInteractionTime = Date.now();
    // Proactively try to resume context on user interaction
    if (this.context?.state === 'suspended') {
      this.ensureContextRunning().catch(() => {
        // Ignore errors, we'll try again on next playback
      });
    }
  }

  /**
   * Warm up the AudioContext by playing a silent buffer.
   * CRITICAL for iOS: Must be called during a user gesture (click/tap).
   * iOS requires actual audio output (even silence) to "unlock" the audio system.
   *
   * Call this:
   * - When user enables voice
   * - On first user interaction after page load
   * - Before attempting any audio playback on iOS
   *
   * @returns true if warmup was successful
   */
  async warmup(): Promise<boolean> {
    if (!this.context) {
      await this.initialize();
    }

    if (!this.context) {
      audioLogger.warn('Cannot warmup: no context');
      return false;
    }

    // If already warmed up and running, skip
    if (this.isWarmedUp && this.context.state === 'running') {
      audioLogger.log('Already warmed up');
      return true;
    }

    try {
      // Ensure context is running
      await this.ensureContextRunning();

      if (this.context.state !== 'running') {
        audioLogger.warn('Context not running after resume attempt');
        return false;
      }

      // Create a silent buffer and play it
      // This "unlocks" iOS audio by producing actual output during user gesture
      const sampleRate = this.context.sampleRate;
      const bufferSize = Math.ceil(sampleRate * AUDIO_WARMUP_DURATION_SECONDS);
      const silentBuffer = this.context.createBuffer(1, bufferSize, sampleRate);

      // Buffer is already filled with zeros (silence) by default
      const source = this.context.createBufferSource();
      source.buffer = silentBuffer;
      source.connect(this.context.destination);
      source.start(0);

      // Mark as warmed up
      this.isWarmedUp = true;
      this.resumeAttempts = 0;

      // Start keep-alive for iOS
      this.startKeepAlive();

      audioLogger.log('Warmup successful');
      return true;
    } catch (error) {
      audioLogger.error('Warmup failed:', error);
      return false;
    }
  }

  /**
   * Start keep-alive interval for iOS.
   * Periodically touches the AudioContext to prevent iOS from suspending it.
   */
  private startKeepAlive(): void {
    // Only needed on iOS
    if (!isIOSSafari()) return;

    // Clear existing interval
    this.stopKeepAlive();

    this.keepAliveInterval = setInterval(() => {
      if (this.context && this.context.state === 'running') {
        // Create a tiny silent oscillator pulse to keep context alive
        try {
          const oscillator = this.context.createOscillator();
          const gainNode = this.context.createGain();
          gainNode.gain.value = 0; // Silent
          oscillator.connect(gainNode);
          gainNode.connect(this.context.destination);
          oscillator.start();
          oscillator.stop(this.context.currentTime + 0.001);
          audioLogger.log('Keep-alive ping');
        } catch {
          // Ignore errors - context may have been closed
        }
      } else if (this.context?.state === 'suspended') {
        // Context got suspended, try to resume on next user interaction
        audioLogger.log('Keep-alive: context suspended, waiting for user interaction');
        this.isWarmedUp = false;
      }
    }, AUDIO_KEEPALIVE_INTERVAL_MS);
  }

  /**
   * Stop keep-alive interval.
   */
  private stopKeepAlive(): void {
    if (this.keepAliveInterval) {
      clearInterval(this.keepAliveInterval);
      this.keepAliveInterval = null;
    }
  }

  /**
   * Check if audio is warmed up and ready for playback.
   */
  get warmedUp(): boolean {
    return this.isWarmedUp && this.context?.state === 'running';
  }

  /**
   * Enqueue an audio chunk for playback.
   * @param audioBase64 - Base64-encoded audio data (MP3)
   */
  async enqueue(audioBase64: string): Promise<void> {
    if (!this.context) {
      await this.initialize();
    }

    if (!this.context) {
      throw new Error('AudioContext not initialized');
    }

    // iOS: Warmup if not already done (plays silent buffer to unlock audio)
    if (isIOSSafari() && !this.isWarmedUp) {
      audioLogger.log('iOS: Auto-warmup before first enqueue');
      await this.warmup();
    }

    // iOS: Check and try to resume context before enqueueing
    const contextRunning = await this.ensureContextRunning();
    if (!contextRunning && isIOSSafari()) {
      audioLogger.warn('iOS: Context not running, audio may not play');
      this.onStateChange?.('suspended');
      // Still enqueue - we'll try to play when context resumes
    }

    try {
      // Convert base64 to ArrayBuffer
      const arrayBuffer = base64ToArrayBuffer(audioBase64);

      // Add to queue
      this.queue.push(arrayBuffer);

      // Start playback if not already playing
      if (!this.isPlaying) {
        this.playNext();
      }
    } catch (error) {
      audioLogger.error('Failed to enqueue audio:', error);
      this.onError?.(error as Error);
    }
  }

  /**
   * Play the next audio chunk in the queue.
   */
  private async playNext(): Promise<void> {
    if (!this.context || this.queue.length === 0) {
      this.isPlaying = false;
      this.onStateChange?.('idle');
      this.onPlaybackComplete?.();
      return;
    }

    // iOS: Check context state before each playback
    const contextRunning = await this.ensureContextRunning();
    if (!contextRunning) {
      audioLogger.warn('Context not running, pausing playback');
      this.isPlaying = false;
      this.onStateChange?.('suspended');
      // Don't clear the queue - we'll resume when context is running
      return;
    }

    this.isPlaying = true;
    this.onStateChange?.('playing');
    const arrayBuffer = this.queue.shift()!;

    try {
      // Decode the audio data
      // Note: slice(0) creates a copy because decodeAudioData detaches the buffer
      const audioBuffer = await this.context.decodeAudioData(arrayBuffer.slice(0));

      // Create source node
      this.currentSource = this.context.createBufferSource();
      this.currentSource.buffer = audioBuffer;
      this.currentSource.connect(this.context.destination);

      // Handle playback completion
      this.currentSource.onended = () => {
        this.currentSource = null;
        this.playNext();
      };

      // Start playback
      this.currentSource.start(0);
    } catch (error) {
      audioLogger.error('Failed to play audio chunk:', error);
      this.onError?.(error as Error);
      // Continue to next chunk even on error
      this.currentSource = null;
      this.playNext();
    }
  }

  /**
   * Resume playback if suspended (for iOS recovery).
   * Should be called after user interaction when in suspended state.
   */
  async resumePlayback(): Promise<boolean> {
    this.recordUserInteraction();

    const running = await this.ensureContextRunning();
    if (running && this.queue.length > 0 && !this.isPlaying) {
      audioLogger.log('Resuming playback after user interaction');
      this.playNext();
      return true;
    }
    return running;
  }

  /**
   * Stop all playback and clear the queue.
   */
  stop(): void {
    // Clear queue
    this.queue = [];

    // Stop current playback
    if (this.currentSource) {
      try {
        this.currentSource.stop();
      } catch {
        // Ignore errors if already stopped
      }
      this.currentSource = null;
    }

    this.isPlaying = false;
    this.onStateChange?.('idle');
  }

  /**
   * Check if audio is currently playing.
   */
  get playing(): boolean {
    return this.isPlaying;
  }

  /**
   * Get the number of chunks waiting in the queue.
   */
  get queueLength(): number {
    return this.queue.length;
  }

  /**
   * Check if context is suspended (needs user interaction on iOS).
   */
  get isSuspended(): boolean {
    return this.context?.state === 'suspended';
  }

  /**
   * Set callback for when all playback is complete.
   */
  setOnPlaybackComplete(callback: () => void): void {
    this.onPlaybackComplete = callback;
  }

  /**
   * Set callback for playback errors.
   */
  setOnError(callback: (error: Error) => void): void {
    this.onError = callback;
  }

  /**
   * Set callback for state changes.
   * Useful for showing "tap to play" UI on iOS when suspended.
   */
  setOnStateChange(callback: (state: AudioQueueState) => void): void {
    this.onStateChange = callback;
  }

  /**
   * Dispose of the AudioQueue and release resources.
   */
  dispose(): void {
    this.stop();

    // Stop keep-alive interval
    this.stopKeepAlive();

    // Remove event listeners
    if (this.context && this.stateChangeHandler) {
      this.context.removeEventListener('statechange', this.stateChangeHandler);
    }
    if (this.visibilityChangeHandler) {
      document.removeEventListener('visibilitychange', this.visibilityChangeHandler);
    }

    if (this.context) {
      try {
        this.context.close();
      } catch {
        // Ignore errors on close
      }
      this.context = null;
    }

    this.stateChangeHandler = null;
    this.visibilityChangeHandler = null;
    this.onPlaybackComplete = null;
    this.onError = null;
    this.onStateChange = null;
    this.isWarmedUp = false;
  }
}
