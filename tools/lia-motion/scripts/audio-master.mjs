import { spawnSync } from 'node:child_process';

export function runFfmpeg(args) {
  const result = spawnSync('ffmpeg', ['-hide_banner', '-nostdin', '-y', ...args], {
    encoding: 'utf8',
    maxBuffer: 8 * 1024 * 1024,
  });
  if (result.status !== 0) throw new Error(`FFmpeg failed: ${result.stderr}`);
  return result.stderr;
}

export function measuredLoudnessFilter(inputArgs, prefix = '', target = -23) {
  const measurement = runFfmpeg([
    ...inputArgs,
    '-vn',
    '-af',
    `${prefix}loudnorm=I=${target}:LRA=7:TP=-1:print_format=json`,
    '-f',
    'null',
    '-',
  ]);
  const data = JSON.parse(
    measurement.slice(measurement.lastIndexOf('{'), measurement.lastIndexOf('}') + 1)
  );
  return {
    measurement: data,
    filter: `${prefix}loudnorm=I=${target}:LRA=7:TP=-1:measured_I=${data.input_i}:measured_TP=${data.input_tp}:measured_LRA=${data.input_lra}:measured_thresh=${data.input_thresh}:offset=${data.target_offset}:linear=true`,
  };
}
