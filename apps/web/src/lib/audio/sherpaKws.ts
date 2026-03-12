/**
 * Sherpa-onnx WASM Wake Word Detection.
 *
 * Provides wake word detection in the browser using Whisper STT.
 * Uses local WASM module with ASR model bundled in .data file.
 *
 * Architecture:
 * - VAD (Voice Activity Detection) detects speech segments
 * - Whisper STT transcribes each segment
 * - Wake word is detected by checking transcription for configured keywords
 *
 * Two-model architecture:
 * - Wake word: Whisper model bundled in WASM .data file (browser)
 * - Main STT: whisper-small (Python backend, multilingual, ~375 MB)
 *
 * NOTE: Model is bundled at WASM compile time in the .data file.
 * To change the wake word model (e.g., to whisper-tiny.en), the WASM must be rebuilt.
 * See: https://k2-fsa.github.io/sherpa/onnx/wasm/index.html
 *
 * Features:
 * - 100% offline after initial load
 * - Configurable wake words via keywords.txt
 *
 * Default wake words: "OK Guy", "OK Guys", "okay guy", "okay guys"
 *
 * Reference: plan zippy-drifting-valley.md (section 2.5.1)
 * Created: 2026-02-01
 */

import { logger } from '@/lib/logger';
import {
  VOICE_INPUT_SAMPLE_RATE,
  VOICE_MODE_MIN_SPEECH_MS,
} from '@/lib/constants';

// ============================================================================
// Types
// ============================================================================

/**
 * Sherpa-onnx Whisper configuration.
 */
export interface SherpaWhisperConfig {
  /** Feature extraction config */
  featConfig: {
    sampleRate: number;
    featureDim: number;
  };
  /** Model configuration */
  modelConfig: {
    whisper: {
      encoder: string;
      decoder: string;
      language: string;
      task: string;
      tailPaddings: number;
    };
    tokens: string;
    numThreads: number;
    debug: number;
  };
  /** Decoding method */
  decodingMethod: string;
}

/**
 * Audio stream for feeding samples to recognizer.
 */
export interface SherpaStream {
  /** Feed audio samples to the stream */
  acceptWaveform: (sampleRate: number, samples: Float32Array) => void;
  /** Free the stream resources */
  free?: () => void;
}

/**
 * Result from speech recognition.
 */
export interface SherpaResult {
  /** Transcribed text */
  text: string;
}

/**
 * Sherpa-onnx Offline Recognizer instance.
 */
export interface SherpaRecognizer {
  /** Create a new audio stream */
  createStream: () => SherpaStream;
  /** Decode audio in stream */
  decode: (stream: SherpaStream) => void;
  /** Get recognition result */
  getResult: (stream: SherpaStream) => SherpaResult;
  /** Free resources */
  free?: () => void;
}

/**
 * VAD (Voice Activity Detection) instance.
 */
export interface SherpaVad {
  /** Configuration */
  config: {
    sileroVad: {
      windowSize: number;
    };
  };
  /** Feed audio samples */
  acceptWaveform: (samples: Float32Array) => void;
  /** Check if speech is detected */
  isDetected: () => boolean;
  /** Check if segment queue is empty */
  isEmpty: () => boolean;
  /** Get front segment */
  front: () => { samples: Float32Array };
  /** Pop front segment */
  pop: () => void;
  /** Reset VAD state */
  reset: () => void;
}

/**
 * Circular buffer for audio samples.
 */
export interface SherpaCircularBuffer {
  /** Push samples to buffer */
  push: (samples: Float32Array) => void;
  /** Get current buffer size */
  size: () => number;
  /** Get buffer head position */
  head: () => number;
  /** Get samples from position */
  get: (position: number, length: number) => Float32Array;
  /** Pop samples from buffer */
  pop: (length: number) => void;
  /** Reset buffer */
  reset: () => void;
}

/**
 * Sherpa-onnx WASM Module interface.
 */
interface SherpaWasmModule {
  /** Create VAD instance */
  createVad?: (module: SherpaWasmModule) => SherpaVad;
  /** Create circular buffer */
  CircularBuffer?: new (size: number, module: SherpaWasmModule) => SherpaCircularBuffer;
  /** Create offline recognizer */
  OfflineRecognizer?: new (config: SherpaWhisperConfig, module: SherpaWasmModule) => SherpaRecognizer;
  // Emscripten module functions
  _malloc: (size: number) => number;
  _free: (ptr: number) => void;
  HEAPF32: Float32Array;
  // ... other Emscripten functions
}

/**
 * Wake word detection result.
 */
export interface WakeWordResult {
  /** Detected wake word (null if none) */
  keyword: string | null;
  /** Full transcription from wake word model */
  text: string;
  /**
   * Text remaining after wake word segment.
   * Always null because the entire transcribed segment is considered the wake word.
   * The actual request should be in a separate audio segment (after a pause).
   */
  remainingText: null;
  /** Audio duration in seconds */
  durationSeconds: number;
}

/**
 * Wake word detector instance interface.
 */
export interface SherpaKwsInstance {
  /** Process audio samples and check for wake word */
  processAudio: (samples: Float32Array) => WakeWordResult | null;
  /** Reset detector state */
  reset: () => void;
  /** Get supported wake words */
  getWakeWords: () => string[];
  /** Free resources */
  free?: () => void;
}

// ============================================================================
// Constants
// ============================================================================

/**
 * Base path for WASM files in public folder.
 */
const WASM_BASE_PATH = '/models/sherpa-wasm';

/**
 * Default wake words (case-insensitive matching).
 * English-only since we use whisper-tiny.en model.
 * Primary: "OK Guy" / "OK Guys" (user-facing wake words)
 * Fallback: single words for robust detection
 */
const DEFAULT_WAKE_WORDS = ['ok guy', 'okay guy', 'ok guys', 'okay guys', 'ok', 'okay', 'guy', 'guys'];

/**
 * Minimum transcription length to check for wake word.
 */
const MIN_TRANSCRIPTION_LENGTH = 2;

// ============================================================================
// Module State
// ============================================================================

/** Cached WASM module */
let cachedModule: SherpaWasmModule | null = null;

/** Pending module initialization promise (to handle concurrent calls) */
let pendingModuleInit: Promise<SherpaWasmModule> | null = null;

/** Cached VAD instance */
let cachedVad: SherpaVad | null = null;

/** Cached recognizer instance */
let cachedRecognizer: SherpaRecognizer | null = null;

/** Cached circular buffer */
let cachedBuffer: SherpaCircularBuffer | null = null;

/** Configured wake words */
let configuredWakeWords: string[] = [...DEFAULT_WAKE_WORDS];

// ============================================================================
// Module Loading
// ============================================================================

/**
 * Load wake words from keywords.txt file.
 */
async function loadWakeWords(): Promise<string[]> {
  try {
    const response = await fetch('/models/keywords.txt');
    if (!response.ok) {
      logger.warn('wake_words_file_not_found', {
        component: 'sherpaKws',
        status: response.status,
      });
      return DEFAULT_WAKE_WORDS;
    }

    const text = await response.text();
    const words = text
      .split('\n')
      .map(line => line.trim().toLowerCase())
      .filter(line => line.length > 0 && !line.startsWith('#'));

    if (words.length === 0) {
      return DEFAULT_WAKE_WORDS;
    }

    logger.info('wake_words_loaded', {
      component: 'sherpaKws',
      count: words.length,
      words,
    });

    return words;
  } catch (error) {
    logger.warn('wake_words_load_failed', {
      component: 'sherpaKws',
      error: String(error),
    });
    return DEFAULT_WAKE_WORDS;
  }
}

/** Track loaded scripts to prevent duplicate loading (causes "already declared" errors) */
const loadedScripts = new Set<string>();

/**
 * Check if a script is already in the DOM.
 */
function isScriptInDOM(src: string): boolean {
  return document.querySelector(`script[src="${src}"]`) !== null;
}

/**
 * Load a script file and return a promise.
 * Skips if script was already loaded (prevents duplicate global declarations).
 * Also checks DOM to handle React Strict Mode re-mounts.
 */
function loadScript(src: string): Promise<void> {
  // Check if already loaded in our tracking Set
  if (loadedScripts.has(src)) {
    logger.debug('sherpa_script_already_loaded', { component: 'sherpaKws', src });
    return Promise.resolve();
  }

  // Also check DOM (handles React Strict Mode re-mounts where module state persists)
  if (isScriptInDOM(src)) {
    loadedScripts.add(src);
    logger.debug('sherpa_script_found_in_dom', { component: 'sherpaKws', src });
    return Promise.resolve();
  }

  return new Promise((resolve, reject) => {
    const script = document.createElement('script');
    script.src = src;
    script.async = true;
    script.onload = () => {
      loadedScripts.add(src);
      logger.debug('sherpa_script_loaded', { component: 'sherpaKws', src });
      resolve();
    };
    script.onerror = (error) => {
      logger.error('sherpa_script_load_failed', new Error(String(error)), {
        component: 'sherpaKws',
        src,
      });
      reject(new Error(`Failed to load script: ${src}`));
    };
    document.head.appendChild(script);
  });
}

/**
 * Load Sherpa-onnx WASM module from local files.
 *
 * Loading order is critical:
 * 1. Set up global Module config first
 * 2. sherpa-onnx-vad.js - Defines createVad, CircularBuffer
 * 3. sherpa-onnx-asr.js - Defines OfflineRecognizer
 * 4. sherpa-onnx-wasm-main-vad-asr.js - Main WASM module
 */
async function loadSherpaModule(): Promise<SherpaWasmModule> {
  // Return cached module if already initialized
  if (cachedModule) {
    return cachedModule;
  }

  // If initialization is in progress, wait for it (handles React Strict Mode)
  if (pendingModuleInit) {
    logger.debug('sherpa_wasm_waiting_for_pending_init', { component: 'sherpaKws' });
    return pendingModuleInit;
  }

  logger.info('sherpa_wasm_loading', {
    component: 'sherpaKws',
    path: WASM_BASE_PATH,
  });

  pendingModuleInit = new Promise((resolve, reject) => {
    // Step 1: Create module configuration FIRST
    const moduleConfig: Partial<SherpaWasmModule> & {
      locateFile?: (path: string, prefix: string) => string;
      onRuntimeInitialized?: () => void;
      setStatus?: (status: string) => void;
    } = {
      locateFile: (path: string, prefix: string) => {
        // Redirect to local files
        if (path.endsWith('.wasm') || path.endsWith('.data')) {
          return `${WASM_BASE_PATH}/${path}`;
        }
        return prefix + path;
      },
      onRuntimeInitialized: () => {
        logger.info('sherpa_wasm_initialized', { component: 'sherpaKws' });
        cachedModule = moduleConfig as SherpaWasmModule;
        pendingModuleInit = null; // Clear pending so future calls use cachedModule
        resolve(cachedModule);
      },
      setStatus: (status: string) => {
        if (status) {
          logger.debug('sherpa_wasm_status', { component: 'sherpaKws', status });
        }
      },
    };

    // Step 2: Assign to global Module BEFORE loading any scripts
    (window as unknown as { Module: typeof moduleConfig }).Module = moduleConfig;

    // Step 3: Load helper scripts and main WASM module in sequence
    const loadAllScripts = async () => {
      try {
        // Load helper scripts first (they define global functions)
        await loadScript(`${WASM_BASE_PATH}/sherpa-onnx-vad.js`);
        await loadScript(`${WASM_BASE_PATH}/sherpa-onnx-asr.js`);

        // Verify helper functions are available
        const win = window as unknown as {
          createVad?: unknown;
          CircularBuffer?: unknown;
          OfflineRecognizer?: unknown;
        };

        logger.debug('sherpa_helpers_loaded', {
          component: 'sherpaKws',
          hasCreateVad: typeof win.createVad === 'function',
          hasCircularBuffer: typeof win.CircularBuffer === 'function',
          hasOfflineRecognizer: typeof win.OfflineRecognizer === 'function',
        });

        // Load the main WASM JavaScript file (also check for duplicates)
        const mainScriptSrc = `${WASM_BASE_PATH}/sherpa-onnx-wasm-main-vad-asr.js`;

        // Check if already loaded (React Strict Mode may re-mount)
        if (loadedScripts.has(mainScriptSrc) || isScriptInDOM(mainScriptSrc)) {
          loadedScripts.add(mainScriptSrc);
          logger.debug('sherpa_main_script_already_loaded', { component: 'sherpaKws' });
          // Module is already initialized, resolve immediately if cached
          if (cachedModule) {
            resolve(cachedModule);
          }
          // Otherwise, onRuntimeInitialized will be called when ready
          return;
        }

        const script = document.createElement('script');
        script.src = mainScriptSrc;
        script.async = true;
        script.onload = () => {
          loadedScripts.add(mainScriptSrc);
        };
        script.onerror = (error) => {
          logger.error('sherpa_wasm_script_load_failed', new Error(String(error)), {
            component: 'sherpaKws',
            src: script.src,
          });
          reject(new Error(`Failed to load WASM script: ${script.src}`));
        };

        document.head.appendChild(script);
      } catch (error) {
        reject(error);
      }
    };

    // Start loading
    loadAllScripts();

    // Timeout after 60 seconds (increased for larger model)
    setTimeout(() => {
      if (!cachedModule) {
        pendingModuleInit = null;
        reject(new Error('WASM module load timeout'));
      }
    }, 60000);
  });

  return pendingModuleInit;
}

/**
 * Check if a file exists in the Emscripten virtual file system.
 * Uses the same pattern as Sherpa-onnx's fileExists function.
 */
function fileExists(filename: string, module: SherpaWasmModule): boolean {
  const moduleAny = module as unknown as {
    lengthBytesUTF8: (s: string) => number;
    _malloc: (size: number) => number;
    stringToUTF8: (str: string, outPtr: number, maxBytesToWrite: number) => void;
    _SherpaOnnxFileExists: (ptr: number) => number;
    _free: (ptr: number) => void;
  };

  try {
    const filenameLen = moduleAny.lengthBytesUTF8(filename) + 1;
    const buffer = moduleAny._malloc(filenameLen);
    moduleAny.stringToUTF8(filename, buffer, filenameLen);

    const exists = moduleAny._SherpaOnnxFileExists(buffer);

    moduleAny._free(buffer);

    return exists === 1;
  } catch (error) {
    logger.debug('file_exists_check_failed', {
      component: 'sherpaKws',
      filename,
      error: String(error),
    });
    return false;
  }
}

/**
 * Detect which ASR model is available in the bundled .data file.
 * The .data file packages models when the WASM is built.
 * Returns config compatible with OfflineRecognizer.
 *
 * IMPORTANT: Config structure must match app-vad-asr.js EXACTLY.
 * The official example uses minimal config - do not add extra fields.
 */
function detectBundledModel(module: SherpaWasmModule): {
  type: 'whisper' | 'sense-voice' | 'transducer' | 'paraformer' | 'moonshine' | 'none';
  config: Record<string, unknown>;
} {
  // Check tokens file first - required for all models
  const hasTokens = fileExists('./tokens.txt', module);
  logger.info('bundled_model_check_tokens', {
    component: 'sherpaKws',
    hasTokens,
  });

  // Check for various model types (EXACT pattern from app-vad-asr.js)
  // Note: fileExists returns 1 for true, not boolean
  if (fileExists('./sense-voice.onnx', module)) {
    logger.info('bundled_model_detected', { component: 'sherpaKws', type: 'sense-voice' });
    return {
      type: 'sense-voice',
      config: {
        modelConfig: {
          debug: 1,
          tokens: './tokens.txt',
          senseVoice: {
            model: './sense-voice.onnx',
            useInverseTextNormalization: 1,
          },
        },
      },
    };
  }

  if (fileExists('./whisper-encoder.onnx', module)) {
    logger.info('bundled_model_detected', { component: 'sherpaKws', type: 'whisper' });
    return {
      type: 'whisper',
      config: {
        modelConfig: {
          debug: 1,
          tokens: './tokens.txt',
          whisper: {
            encoder: './whisper-encoder.onnx',
            decoder: './whisper-decoder.onnx',
            // Force English for wake word detection only
            // Main STT uses backend Whisper (multilingual)
            language: 'en',
            task: 'transcribe',
          },
        },
      },
    };
  }

  if (fileExists('./transducer-encoder.onnx', module)) {
    logger.info('bundled_model_detected', { component: 'sherpaKws', type: 'transducer' });
    return {
      type: 'transducer',
      config: {
        modelConfig: {
          debug: 1,
          tokens: './tokens.txt',
          transducer: {
            encoder: './transducer-encoder.onnx',
            decoder: './transducer-decoder.onnx',
            joiner: './transducer-joiner.onnx',
          },
          modelType: 'transducer',
        },
      },
    };
  }

  if (fileExists('./paraformer.onnx', module)) {
    logger.info('bundled_model_detected', { component: 'sherpaKws', type: 'paraformer' });
    return {
      type: 'paraformer',
      config: {
        modelConfig: {
          debug: 1,
          tokens: './tokens.txt',
          paraformer: {
            model: './paraformer.onnx',
          },
        },
      },
    };
  }

  if (fileExists('./moonshine-preprocessor.onnx', module)) {
    logger.info('bundled_model_detected', { component: 'sherpaKws', type: 'moonshine' });
    return {
      type: 'moonshine',
      config: {
        modelConfig: {
          debug: 1,
          tokens: './tokens.txt',
          moonshine: {
            preprocessor: './moonshine-preprocessor.onnx',
            encoder: './moonshine-encoder.onnx',
            uncachedDecoder: './moonshine-uncached-decoder.onnx',
            cachedDecoder: './moonshine-cached-decoder.onnx',
          },
        },
      },
    };
  }

  // No model found - list what we checked
  logger.warn('no_bundled_model_found', {
    component: 'sherpaKws',
    checkedFiles: [
      'sense-voice.onnx',
      'whisper-encoder.onnx',
      'transducer-encoder.onnx',
      'paraformer.onnx',
      'moonshine-preprocessor.onnx',
    ],
  });
  return { type: 'none', config: {} };
}

/**
 * Initialize VAD and recognizer components.
 */
async function initializeComponents(module: SherpaWasmModule): Promise<{
  vad: SherpaVad;
  recognizer: SherpaRecognizer;
  buffer: SherpaCircularBuffer;
}> {
  // Use global functions set up by the WASM module
  const globalModule = window as unknown as {
    createVad: (m: SherpaWasmModule) => SherpaVad;
    CircularBuffer: new (size: number, m: SherpaWasmModule) => SherpaCircularBuffer;
    OfflineRecognizer: new (config: SherpaWhisperConfig, m: SherpaWasmModule) => SherpaRecognizer;
  };

  logger.info('sherpa_init_components_start', {
    component: 'sherpaKws',
    hasCreateVad: typeof globalModule.createVad === 'function',
    hasCircularBuffer: typeof globalModule.CircularBuffer === 'function',
    hasOfflineRecognizer: typeof globalModule.OfflineRecognizer === 'function',
  });

  // Create VAD first (uses bundled model)
  if (!cachedVad) {
    if (typeof globalModule.createVad !== 'function') {
      throw new Error('createVad function not found in WASM module');
    }
    try {
      cachedVad = globalModule.createVad(module);
      logger.info('sherpa_vad_created', { component: 'sherpaKws' });
    } catch (vadError) {
      logger.error('sherpa_vad_creation_failed', vadError instanceof Error ? vadError : new Error(String(vadError)), {
        component: 'sherpaKws',
      });
      throw vadError;
    }
  }

  // Create circular buffer (30 seconds at 16kHz)
  if (!cachedBuffer) {
    if (typeof globalModule.CircularBuffer !== 'function') {
      throw new Error('CircularBuffer not found in WASM module');
    }
    try {
      cachedBuffer = new globalModule.CircularBuffer(30 * VOICE_INPUT_SAMPLE_RATE, module);
      logger.info('sherpa_buffer_created', { component: 'sherpaKws' });
    } catch (bufferError) {
      logger.error('sherpa_buffer_creation_failed', bufferError instanceof Error ? bufferError : new Error(String(bufferError)), {
        component: 'sherpaKws',
      });
      throw bufferError;
    }
  }

  // Detect which ASR model is available in the bundled .data file
  // NOTE: Model is bundled at WASM compile time, not loaded dynamically
  logger.info('sherpa_detecting_bundled_model', { component: 'sherpaKws' });
  const bundledModel = detectBundledModel(module);
  logger.info('sherpa_bundled_model_result', {
    component: 'sherpaKws',
    type: bundledModel.type,
    config: JSON.stringify(bundledModel.config),
  });

  if (bundledModel.type === 'none') {
    throw new Error(
      'No ASR model found in bundled WASM. ' +
      'The .data file should contain whisper, sense-voice, transducer, paraformer, or moonshine model.'
    );
  }

  // Create recognizer with detected bundled model (use config exactly as from detectBundledModel)
  if (!cachedRecognizer) {
    if (typeof globalModule.OfflineRecognizer !== 'function') {
      throw new Error('OfflineRecognizer not found in WASM module');
    }

    logger.info('sherpa_recognizer_creating', {
      component: 'sherpaKws',
      modelType: bundledModel.type,
      config: bundledModel.config,
    });

    try {
      // Use config EXACTLY as returned by detectBundledModel (matches app-vad-asr.js pattern)
      cachedRecognizer = new globalModule.OfflineRecognizer(
        bundledModel.config as unknown as SherpaWhisperConfig,
        module
      );
    } catch (recognizerError) {
      logger.error('sherpa_recognizer_constructor_failed', recognizerError instanceof Error ? recognizerError : new Error(String(recognizerError)), {
        component: 'sherpaKws',
        modelType: bundledModel.type,
      });
      throw recognizerError;
    }

    // Check if recognizer was created successfully
    const recognizerAny = cachedRecognizer as unknown as { handle: number };
    if (!recognizerAny.handle || recognizerAny.handle === 0) {
      throw new Error('Failed to create OfflineRecognizer - model files may be missing or corrupted');
    }

    logger.info('sherpa_recognizer_created', {
      component: 'sherpaKws',
      handle: recognizerAny.handle,
    });
  }

  return {
    vad: cachedVad,
    recognizer: cachedRecognizer,
    buffer: cachedBuffer,
  };
}

// ============================================================================
// Wake Word Detector Class
// ============================================================================

/**
 * Wake word detector using VAD + Whisper STT.
 */
class WakeWordDetector implements SherpaKwsInstance {
  private vad: SherpaVad;
  private recognizer: SherpaRecognizer;
  private buffer: SherpaCircularBuffer;
  private wakeWords: string[];
  private speechDetected = false;

  constructor(
    vad: SherpaVad,
    recognizer: SherpaRecognizer,
    buffer: SherpaCircularBuffer,
    wakeWords: string[]
  ) {
    this.vad = vad;
    this.recognizer = recognizer;
    this.buffer = buffer;
    this.wakeWords = wakeWords;
  }

  /**
   * Process audio samples and check for wake word.
   *
   * @param samples Audio samples (Float32, 16kHz, normalized [-1, 1])
   * @returns Wake word result if detected, null otherwise
   */
  processAudio(samples: Float32Array): WakeWordResult | null {
    // Push samples to buffer
    this.buffer.push(samples);

    // Process buffer through VAD
    while (this.buffer.size() > this.vad.config.sileroVad.windowSize) {
      const vadSamples = this.buffer.get(
        this.buffer.head(),
        this.vad.config.sileroVad.windowSize
      );
      this.vad.acceptWaveform(vadSamples);
      this.buffer.pop(this.vad.config.sileroVad.windowSize);

      // Track speech detection
      if (this.vad.isDetected() && !this.speechDetected) {
        this.speechDetected = true;
        logger.debug('speech_detected', { component: 'sherpaKws' });
      }

      if (!this.vad.isDetected()) {
        this.speechDetected = false;
      }

      // Process completed speech segments
      while (!this.vad.isEmpty()) {
        const segment = this.vad.front();
        const duration = segment.samples.length / VOICE_INPUT_SAMPLE_RATE;
        this.vad.pop();

        // Skip very short segments
        if (duration < VOICE_MODE_MIN_SPEECH_MS / 1000) {
          continue;
        }

        // Transcribe segment
        // NOTE: decode() is synchronous and can take 200-400ms, causing browser violations
        // TODO: Consider moving STT to Web Worker for better performance
        const stream = this.recognizer.createStream();
        stream.acceptWaveform(VOICE_INPUT_SAMPLE_RATE, segment.samples);
        const decodeStart = performance.now();
        this.recognizer.decode(stream);
        const decodeTime = performance.now() - decodeStart;
        const result = this.recognizer.getResult(stream);
        stream.free?.();

        if (decodeTime > 100) {
          logger.debug('kws_decode_slow', {
            component: 'sherpaKws',
            decodeMs: Math.round(decodeTime),
            segmentDurationSec: Math.round(duration * 100) / 100,
          });
        }

        const text = result.text.trim().toLowerCase();

        // Log ALL transcriptions for debugging wake word detection
        logger.info('kws_transcription', {
          component: 'sherpaKws',
          text: text || '(empty)',
          duration: Math.round(duration * 100) / 100,
          wakeWords: this.wakeWords,
          matched: text.length >= MIN_TRANSCRIPTION_LENGTH ? this.findWakeWord(text) : null,
        });

        // Check for wake word
        if (text.length >= MIN_TRANSCRIPTION_LENGTH) {
          const detectedWakeWord = this.findWakeWord(text);
          if (detectedWakeWord) {
            logger.info('wake_word_detected', {
              component: 'sherpaKws',
              wakeWord: detectedWakeWord,
              transcription: text,
              duration,
            });

            return {
              keyword: detectedWakeWord,
              text,
              remainingText: null, // Entire segment is considered wake word
              durationSeconds: duration,
            };
          }
        }
      }
    }

    return null;
  }

  /**
   * Find wake word in transcription.
   */
  private findWakeWord(text: string): string | null {
    const normalizedText = text.toLowerCase();

    for (const wakeWord of this.wakeWords) {
      // Check if wake word appears at the beginning or as a standalone word
      if (
        normalizedText === wakeWord ||
        normalizedText.startsWith(wakeWord + ' ') ||
        normalizedText.startsWith(wakeWord + ',') ||
        normalizedText.startsWith(wakeWord + '.')
      ) {
        return wakeWord;
      }
    }

    return null;
  }

  /**
   * Reset detector state.
   */
  reset(): void {
    this.vad.reset();
    this.buffer.reset();
    this.speechDetected = false;
    logger.debug('detector_reset', { component: 'sherpaKws' });
  }

  /**
   * Get configured wake words.
   */
  getWakeWords(): string[] {
    return [...this.wakeWords];
  }

  /**
   * Free resources.
   */
  free(): void {
    // Note: We don't free cached components as they may be reused
    logger.debug('detector_freed', { component: 'sherpaKws' });
  }
}

// ============================================================================
// Public API
// ============================================================================

/**
 * Initialize Sherpa-onnx wake word detector.
 *
 * Uses Whisper STT for multilingual wake word detection.
 *
 * Prerequisites:
 * - COOP/COEP headers enabled (for SharedArrayBuffer)
 * - WASM files in /public/models/sherpa-wasm/
 * - Whisper model in /public/models/whisper-small/
 *
 * @returns Promise resolving to wake word detector instance
 * @throws Error if WASM loading or initialization fails
 *
 * @example
 * ```ts
 * const detector = await initSherpaKws();
 *
 * // In audio processing callback:
 * const result = detector.processAudio(audioSamples);
 * if (result?.keyword) {
 *   console.log('Wake word detected:', result.keyword);
 *   startRecording();
 * }
 * ```
 */
export async function initSherpaKws(): Promise<SherpaKwsInstance> {
  // Check SharedArrayBuffer support
  if (typeof SharedArrayBuffer === 'undefined') {
    const error = new Error(
      'SharedArrayBuffer not available. Ensure COOP/COEP headers are set.'
    );
    logger.error('sherpa_kws_no_shared_array_buffer', error, {
      component: 'sherpaKws',
    });
    throw error;
  }

  logger.info('sherpa_kws_initializing', { component: 'sherpaKws' });

  try {
    // Load wake words
    configuredWakeWords = await loadWakeWords();

    // Load WASM module
    const wasmModule = await loadSherpaModule();

    // Initialize components
    const { vad, recognizer, buffer } = await initializeComponents(wasmModule);

    // Create detector
    const detector = new WakeWordDetector(vad, recognizer, buffer, configuredWakeWords);

    logger.info('sherpa_kws_initialized', {
      component: 'sherpaKws',
      wakeWords: configuredWakeWords,
    });

    return detector;
  } catch (error) {
    const err = error instanceof Error ? error : new Error(String(error));
    logger.error('sherpa_kws_init_failed', err, { component: 'sherpaKws' });
    throw err;
  }
}

/**
 * Check if Sherpa-onnx wake word detection is supported.
 *
 * Requirements:
 * - SharedArrayBuffer (COOP/COEP headers)
 * - WebAssembly
 * - AudioWorklet
 * - Cross-origin isolated context (for SharedArrayBuffer to work)
 *
 * @returns true if all requirements are met
 */
export function isSherpaKwsSupported(): boolean {
  const hasSharedArrayBuffer = typeof SharedArrayBuffer !== 'undefined';
  const hasWebAssembly = typeof WebAssembly !== 'undefined';
  const hasAudioWorklet =
    typeof AudioContext !== 'undefined' &&
    typeof AudioWorkletNode !== 'undefined';

  // Check if cross-origin isolated (required for SharedArrayBuffer on modern browsers)
  // This catches Safari iOS with COEP: credentialless (which doesn't enable isolation)
  const isCrossOriginIsolated =
    typeof crossOriginIsolated !== 'undefined' ? crossOriginIsolated : true;

  const supported =
    hasSharedArrayBuffer && hasWebAssembly && hasAudioWorklet && isCrossOriginIsolated;

  if (!supported) {
    logger.debug('sherpa_kws_not_supported', {
      component: 'sherpaKws',
      hasSharedArrayBuffer,
      hasWebAssembly,
      hasAudioWorklet,
      isCrossOriginIsolated,
    });
  }

  return supported;
}

/**
 * Clear cached WASM module and components.
 *
 * Useful for testing or when module needs to be reloaded.
 */
export function clearSherpaModuleCache(): void {
  cachedModule = null;
  pendingModuleInit = null;
  cachedVad = null;
  cachedRecognizer = null;
  cachedBuffer = null;
  // Note: loadedScripts is NOT cleared because scripts remain in DOM
  // Clearing it would cause "already declared" errors on re-init
  logger.debug('sherpa_kws_cache_cleared', { component: 'sherpaKws' });
}

/**
 * Get currently configured wake words.
 */
export function getConfiguredWakeWords(): string[] {
  return [...configuredWakeWords];
}

// Re-export types for backward compatibility
export type SherpaKwsConfig = SherpaWhisperConfig;
export type SherpaKwsStream = SherpaStream;
export type SherpaKwsResult = WakeWordResult;
