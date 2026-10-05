import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import {
  RemotePcmCapture,
  buildRemoteCaptureWorklet,
  REMOTE_CAPTURE_PROCESSOR,
} from '../remote-capture';

interface Processor {
  port: { postMessage: (message: { pcm: ArrayBuffer; epoch: number }) => void };
  process(inputs: Float32Array[][]): boolean;
}
beforeEach(() => {
  vi.spyOn(HTMLMediaElement.prototype, 'play').mockResolvedValue();
  vi.spyOn(HTMLMediaElement.prototype, 'pause').mockImplementation(() => {});
});
it('captures the exact sample clock before the vendor filter, including weak speech and interior zeros', () => {
  const packets: ArrayBuffer[] = [];
  const processors = new Map<string, new () => Processor>();
  class Worklet {
    port = {
      postMessage: (packet: { pcm: ArrayBuffer; epoch: number }) => packets.push(packet.pcm),
    };
  }
  new Function('AudioWorkletProcessor', 'registerProcessor', buildRemoteCaptureWorklet())(
    Worklet,
    (name: string, ctor: new () => Processor) => processors.set(name, ctor)
  );
  const Constructor = processors.get(REMOTE_CAPTURE_PROCESSOR);
  if (!Constructor) throw new Error('processor missing');
  const processor = new Constructor();
  processor.process([]);
  const signal = new Float32Array(3072);
  signal.fill(0.005, 0, 1024);
  signal.fill(0.001, 2048);
  for (let start = 0; start < signal.length; start += 137) {
    const channel = signal.subarray(start, start + 137);
    processor.process([[channel, channel]]);
  }
  expect(packets.reduce((size, packet) => size + packet.byteLength, 0)).toBe(6144);
  expect(new DataView(packets[0]).getInt16(0, true)).toBe(164);
  expect(new DataView(packets[1]).getInt16(400, true)).toBe(0);
  expect(new DataView(packets[2]).getInt16(0, true)).toBe(33);
});
class Node {
  connect = vi.fn();
  disconnect = vi.fn();
  gain = { value: 1 };
}
class Context {
  static instances: Context[] = [];
  state = 'running';
  sampleRate = 48000;
  destination = new Node();
  source = new Node();
  gain = new Node();
  audioWorklet = { addModule: vi.fn(async () => {}) };
  resume = vi.fn(async () => {});
  close = vi.fn(async () => {});
  constructor() {
    Context.instances.push(this);
  }
  createMediaStreamSource() {
    return this.source;
  }
  createGain() {
    return this.gain;
  }
}
class CaptureNode extends Node {
  static instances: CaptureNode[] = [];
  port: {
    onmessage: ((event: { data: unknown }) => void) | null;
    postMessage: (message: unknown) => void;
  } = {
    onmessage: null,
    postMessage: vi.fn(),
  };
  constructor() {
    super();
    CaptureNode.instances.push(this);
  }
}
afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});
it('warms on the gesture, uses the actual context rate, and releases its graph without stopping borrowed tracks', async () => {
  Context.instances = [];
  CaptureNode.instances = [];
  vi.stubGlobal('AudioContext', Context);
  vi.stubGlobal('AudioWorkletNode', CaptureNode);
  vi.stubGlobal('MediaStream', class {});
  vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:fixture');
  const consume = vi.fn();
  const capture = new RemotePcmCapture(consume);
  await capture.warmup();
  const release = capture.attach(new MediaStream());
  for (let i = 0; i < 20; i++) await Promise.resolve();
  const node = CaptureNode.instances[0];
  const late = node.port.onmessage;
  node.port.onmessage?.({ data: { pcm: new ArrayBuffer(2048), epoch: 0 } });
  expect(consume).toHaveBeenCalledWith(expect.any(ArrayBuffer), 48000);
  expect(Context.instances[0].gain.gain.value).toBe(0);
  release();
  late?.({ data: { pcm: new ArrayBuffer(2048), epoch: 0 } });
  expect(consume).toHaveBeenCalledTimes(1);
  expect(Context.instances[0].source.disconnect).toHaveBeenCalled();
  capture.dispose();
  expect(Context.instances[0].close).toHaveBeenCalledTimes(1);
});
it('preserves native local playback if the worklet fails before capture', async () => {
  Context.instances = [];
  vi.stubGlobal('AudioContext', Context);
  vi.stubGlobal('MediaStream', class {});
  const failed = vi.fn();
  const capture = new RemotePcmCapture(vi.fn(), failed);
  await capture.warmup();
  Context.instances[0].audioWorklet.addModule.mockRejectedValue(new Error('untrusted detail'));
  capture.attach(new MediaStream());
  for (let i = 0; i < 20; i++) await Promise.resolve();
  expect(failed).toHaveBeenCalledTimes(1);
  expect(Context.instances[0].gain.gain.value).toBe(1);
  expect(Context.instances[0].source.connect).toHaveBeenCalledWith(Context.instances[0].gain);
  capture.dispose();
});

it('rejects malformed and stale frames, flushes during module loading, and isolates a failed consumer', async () => {
  Context.instances = [];
  CaptureNode.instances = [];
  vi.stubGlobal('AudioContext', Context);
  vi.stubGlobal('AudioWorkletNode', CaptureNode);
  vi.stubGlobal('MediaStream', class {});
  let complete = () => {};
  const consume = vi.fn();
  const failed = vi.fn();
  const capture = new RemotePcmCapture(consume, failed);
  await capture.warmup();
  Context.instances[0].audioWorklet.addModule.mockImplementation(
    () =>
      new Promise<void>(resolve => {
        complete = resolve;
      })
  );
  const release = capture.attach(new MediaStream());
  capture.flush();
  complete();
  for (let n = 0; n < 20; n++) await Promise.resolve();
  const node = CaptureNode.instances[0];
  expect(node.port.postMessage).toHaveBeenCalledWith({ type: 'flush', epoch: 1 });
  for (const data of [
    null,
    'invalid',
    {},
    { pcm: new ArrayBuffer(2048) },
    { epoch: 1 },
    { pcm: new ArrayBuffer(2048), epoch: 0 },
    { pcm: 'invalid', epoch: 1 },
  ])
    node.port.onmessage?.({ data });
  expect(consume).not.toHaveBeenCalled();
  consume.mockImplementation(() => {
    throw new Error('private detail');
  });
  node.port.onmessage?.({ data: { pcm: new ArrayBuffer(2048), epoch: 1 } });
  expect(failed).toHaveBeenCalledOnce();
  expect(Context.instances[0].gain.gain.value).toBe(1);
  release();
  expect(Context.instances[0].source.disconnect).toHaveBeenCalledTimes(2);
  Context.instances[0].close.mockRejectedValue(new Error('already closed'));
  capture.dispose();
});

it('late module resolution and an old release cannot resurrect or detach a newer graph', async () => {
  Context.instances = [];
  CaptureNode.instances = [];
  vi.stubGlobal('AudioContext', Context);
  vi.stubGlobal('AudioWorkletNode', CaptureNode);
  vi.stubGlobal('MediaStream', class {});
  const consume = vi.fn();
  const capture = new RemotePcmCapture(consume);
  await capture.warmup();
  let complete = () => {};
  Context.instances[0].audioWorklet.addModule.mockImplementationOnce(
    () =>
      new Promise<void>(resolve => {
        complete = resolve;
      })
  );
  const old = capture.attach(new MediaStream());
  const release = capture.attach(new MediaStream());
  for (let n = 0; n < 20; n++) await Promise.resolve();
  old();
  complete();
  for (let n = 0; n < 20; n++) await Promise.resolve();
  expect(CaptureNode.instances).toHaveLength(1);
  CaptureNode.instances[0].port.onmessage?.({ data: { pcm: new ArrayBuffer(2048), epoch: 0 } });
  expect(consume).toHaveBeenCalledOnce();
  release();
  capture.dispose();
});

it('a locked or absent context fails safely without constructing an audible graph', async () => {
  Context.instances = [];
  vi.stubGlobal('AudioContext', Context);
  vi.stubGlobal('MediaStream', class {});
  const capture = new RemotePcmCapture(vi.fn());
  capture.attach(new MediaStream());
  for (let n = 0; n < 20; n++) await Promise.resolve();
  expect(Context.instances).toHaveLength(0);
  await capture.warmup();
  await capture.warmup();
  Context.instances[0].state = 'suspended';
  capture.attach(new MediaStream());
  for (let n = 0; n < 20; n++) await Promise.resolve();
  expect(Context.instances[0].source.connect).not.toHaveBeenCalled();
  capture.dispose();
  capture.dispose();
});
