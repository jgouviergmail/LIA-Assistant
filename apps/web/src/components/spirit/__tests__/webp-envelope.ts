function canvasHeader(bytes: Buffer, chunk: string, start: number, length: number) {
  if (chunk === 'VP8X') {
    if (length < 10) throw new Error('WebP canvas header is truncated');
    return {
      width: bytes.readUIntLE(start + 4, 3) + 1,
      height: bytes.readUIntLE(start + 7, 3) + 1,
      alpha: Boolean(bytes[start] & 0x10),
      animation: Boolean(bytes[start] & 0x02),
    };
  }
  if (chunk === 'VP8L') {
    if (length < 5 || bytes[start] !== 0x2f) throw new Error('Invalid lossless WebP signature');
    const packed = bytes.readUInt32LE(start + 1);
    return {
      width: (packed & 0x3fff) + 1,
      height: ((packed >>> 14) & 0x3fff) + 1,
      alpha: Boolean((packed >>> 28) & 1),
      animation: false,
    };
  }
  if (chunk === 'VP8 ') {
    if (length < 10 || bytes.toString('hex', start + 3, start + 6) !== '9d012a') {
      throw new Error('Invalid lossy WebP signature');
    }
    return {
      width: bytes.readUInt16LE(start + 6) & 0x3fff,
      height: bytes.readUInt16LE(start + 8) & 0x3fff,
      alpha: false,
      animation: false,
    };
  }
  return null;
}

/** Read the container's own canvas and alpha declarations without decoding pixels. */
export function webpEnvelope(bytes: Buffer) {
  if (bytes.toString('ascii', 0, 4) !== 'RIFF' || bytes.toString('ascii', 8, 12) !== 'WEBP') {
    throw new Error('The avatar is not a WebP container');
  }
  if (bytes.readUInt32LE(4) + 8 !== bytes.length) throw new Error('WebP length is inconsistent');
  let canvas = { width: 0, height: 0, alpha: false, animation: false };
  let frames = 0;
  let durationMs = 0;
  for (let offset = 12; offset + 8 <= bytes.length; ) {
    const chunk = bytes.toString('ascii', offset, offset + 4);
    const length = bytes.readUInt32LE(offset + 4);
    const start = offset + 8;
    if (start + length > bytes.length) throw new Error('WebP chunk is truncated');
    const header =
      chunk === 'VP8X' || canvas.width === 0 ? canvasHeader(bytes, chunk, start, length) : null;
    if (header) canvas = header;
    if (chunk === 'ANMF') {
      if (length < 16) throw new Error('WebP frame header is truncated');
      frames++;
      durationMs += bytes.readUIntLE(start + 12, 3);
    }
    offset = start + length + (length % 2);
  }
  return { ...canvas, frames, durationMs };
}
