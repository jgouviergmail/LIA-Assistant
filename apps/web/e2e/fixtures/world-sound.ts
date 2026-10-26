import type { Page } from '@playwright/test';
import { readFileSync } from 'node:fs';
import { dirname, relative, resolve, sep } from 'node:path';
import ts from 'typescript';
import type { Soundscape } from '../../src/features/world/audio/soundscape';
import type { BrowserWorldAudio } from '../../src/features/world/audio/browser-audio';
import type { SOUND_FILES, soundUrl } from '../../src/features/world/audio/catalogue';
declare global {
  interface Window {
    worldSoundOracle: {
      Soundscape: typeof Soundscape;
      BrowserWorldAudio: typeof BrowserWorldAudio;
      SOUND_FILES: typeof SOUND_FILES;
      soundUrl: typeof soundUrl;
      player: Soundscape | null;
    };
    worldSoundProbe: {
      context: AudioContext | null;
      starts: { duration: number; loop: boolean }[];
      active: number;
      maximum: number;
      rms(): number;
      outputLevels(): number[];
    };
  }
}
export async function installSoundOracle(page: Page): Promise<void> {
  const root = resolve(__dirname, '../../src/features/world/audio'),
    modules = new Map<string, string>();
  function compile(name: string): void {
    if (modules.has(name)) return;
    const path = resolve(root, name);
    if (!path.startsWith(root + sep)) throw new Error('Audio oracle outside trusted sources');
    modules.set(name, '');
    let code = ts.transpileModule(readFileSync(path, 'utf8'), {
      compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
    }).outputText;
    code = code.replace(/require\(["']([^"']+)["']\)/g, (_full, reference: string) => {
      if (reference === '@/lib/api-client') {
        const path = resolve(__dirname, '../../src/lib/api-client.ts');
        const native = ts.createSourceFile(
          path,
          readFileSync(path, 'utf8'),
          ts.ScriptTarget.ES2022,
          true
        );
        const declarations = native.statements.filter(
          node =>
            (ts.isFunctionDeclaration(node) && node.name?.text === 'readPublicAssetResponse') ||
            (ts.isClassDeclaration(node) && node.name?.text === 'ApiError')
        );
        if (declarations.length !== 2) throw new Error('Missing native public asset transport');
        modules.set(
          '__public_asset_transport',
          ts.transpileModule(declarations.map(node => node.getText(native)).join('\n'), {
            compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
          }).outputText
        );
        return 'require("__public_asset_transport")';
      }
      if (!reference.startsWith('.')) throw new Error('Unexpected audio runtime import');
      const dependency = relative(root, resolve(dirname(path), reference + '.ts')).replaceAll(
        '\\',
        '/'
      );
      compile(dependency);
      return 'require(' + JSON.stringify(dependency) + ')';
    });
    modules.set(name, code);
  }
  for (const entry of ['catalogue.ts', 'soundscape.ts', 'browser-audio.ts']) compile(entry);
  const factories = [...modules]
    .map(([name, code]) => JSON.stringify(name) + ':(module,exports,require)=>{' + code + '\n}')
    .join(',');
  const script =
    '(()=>{const factories={' +
    factories +
    '},cache=Object.create(null);function require(name){if(cache[name])return cache[name].exports;const m={exports:{}};cache[name]=m;factories[name](m,m.exports,require);return m.exports;}window.worldSoundOracle={...require("catalogue.ts"),...require("soundscape.ts"),...require("browser-audio.ts"),player:null};document.querySelector("button").onclick=()=>{const a=window.worldSoundOracle;a.player=new a.Soundscape(new a.BrowserWorldAudio());void a.player.select("studio");void a.player.enable();};})();';
  await page.route('**/world-sound-oracle', route =>
    route.fulfill({
      contentType: 'text/html',
      headers: {
        'Content-Security-Policy':
          "default-src 'none'; connect-src 'self'; script-src 'nonce-sound-test'; style-src 'none'",
      },
      body:
        '<!doctype html><html lang="en"><title>Trusted sound oracle</title><body><button>Enable original ambience</button><script nonce="sound-test">' +
        script.replace(/<\/script/gi, '<\\/script') +
        '</script></body></html>',
    })
  );
  await page.goto('/world-sound-oracle');
}
export async function installAudioProbe(page: Page): Promise<void> {
  await page.addInitScript(() => {
    const Native = window.AudioContext;
    const probe: Window['worldSoundProbe'] = {
      context: null,
      starts: [],
      active: 0,
      maximum: 0,
      rms: () => 0,
      outputLevels: () => [],
    };
    window.worldSoundProbe = probe;
    if (typeof Native !== 'function') return;
    window.AudioContext = class extends Native {
      private meter: AnalyserNode;
      private outputs = new Set<GainNode>();
      constructor(options?: AudioContextOptions) {
        super(options);
        this.meter = super.createAnalyser();
        this.meter.fftSize = 1024;
        const silent = super.createGain();
        silent.gain.value = 0;
        this.meter.connect(silent);
        silent.connect(this.destination);
        probe.context = this;
        probe.outputLevels = () => [...this.outputs].map(node => node.gain.value);
        probe.rms = () => {
          const values = new Float32Array(1024);
          this.meter.getFloatTimeDomainData(values);
          return Math.sqrt(values.reduce((sum, v) => sum + v * v, 0) / values.length);
        };
      }
      override createGain(): GainNode {
        const gain = super.createGain();
        const connect = gain.connect.bind(gain);
        // Measure only the terminal output, after the owned world master gain.
        Object.defineProperty(gain, 'connect', {
          value: (destination: AudioNode | AudioParam, output = 0, input = 0) => {
            if (destination === this.destination) {
              this.outputs.add(gain);
              connect(this.meter);
            }
            if (destination instanceof AudioNode) return connect(destination, output, input);
            connect(destination, output);
          },
        });
        return gain;
      }
      override createBufferSource(): AudioBufferSourceNode {
        const source = super.createBufferSource(),
          start = source.start.bind(source);
        source.start = (when = 0, offset = 0, duration?: number) => {
          probe.starts.push({ duration: source.buffer?.duration ?? 0, loop: source.loop });
          probe.active++;
          probe.maximum = Math.max(probe.maximum, probe.active);
          source.addEventListener(
            'ended',
            () => {
              probe.active--;
            },
            { once: true }
          );
          start(when, offset, duration);
        };
        return source;
      }
    };
  });
}
