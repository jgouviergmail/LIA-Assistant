/** One optional static skin buffer, owned and disposed with its mesh material. */
import type { ChannelValues } from '../rig/channels';
import type { VolumeGraphics } from './mesh-gpu';
import type { VolumeSkin } from './volume-geometry';
import { updateLimbUniforms } from './limb-skin';

export function createLimbGpu(gl: VolumeGraphics, program: WebGLProgram, skin?: VolumeSkin) {
  if (!skin) return { draw(_values?: Readonly<ChannelValues>) {}, dispose() {} };
  const buffer = gl.createBuffer();
  if (!buffer) return null;
  gl.bindBuffer(gl.ARRAY_BUFFER, buffer);
  gl.bufferData(gl.ARRAY_BUFFER, skin.vertices, gl.STATIC_DRAW);
  const locations = ['a_skin', 'a_gradient'].map(name => gl.getAttribLocation(program, name));
  const uniform = gl.getUniformLocation(program, 'u_joints[0]');
  return {
    draw(values?: Readonly<ChannelValues>) {
      gl.bindBuffer(gl.ARRAY_BUFFER, buffer);
      locations.forEach((location, index) => {
        if (location < 0) return;
        gl.enableVertexAttribArray(location);
        gl.vertexAttribPointer(location, 4, gl.FLOAT, false, 32, index * 16);
      });
      updateLimbUniforms(skin, values);
      gl.uniform4fv(uniform, skin.joints);
    },
    dispose() {
      gl.deleteBuffer(buffer);
    },
  };
}
