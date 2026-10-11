import { vi } from 'vitest';
import type { SphereGraphics } from '../smiley/sphere-gpu';

/** Typed driver double; behavioral tests own their real canvas/event lifecycle. */
export function sphereGraphics() {
  return {
    VERTEX_SHADER: 35633,
    FRAGMENT_SHADER: 35632,
    LINK_STATUS: 35714,
    ARRAY_BUFFER: 34962,
    STATIC_DRAW: 35044,
    FLOAT: 5126,
    TRIANGLES: 4,
    createShader: vi.fn<() => WebGLShader | null>(() => ({})),
    shaderSource: vi.fn(),
    compileShader: vi.fn(),
    deleteShader: vi.fn(),
    createProgram: vi.fn<() => WebGLProgram | null>(() => ({})),
    attachShader: vi.fn(),
    linkProgram: vi.fn(),
    getProgramParameter: vi.fn(() => true),
    deleteProgram: vi.fn(),
    createBuffer: vi.fn<() => WebGLBuffer | null>(() => ({})),
    deleteBuffer: vi.fn(),
    bindBuffer: vi.fn(),
    bufferData: vi.fn(),
    useProgram: vi.fn(),
    getAttribLocation: vi.fn(() => 0),
    enableVertexAttribArray: vi.fn(),
    vertexAttribPointer: vi.fn(),
    getUniformLocation: vi.fn<(program: WebGLProgram, name: string) => WebGLUniformLocation | null>(
      () => ({})
    ),
    uniform4fv: vi.fn(),
    uniform1f: vi.fn(),
    viewport: vi.fn(),
    drawArrays: vi.fn(),
    flush: vi.fn(),
  } satisfies SphereGraphics;
}
