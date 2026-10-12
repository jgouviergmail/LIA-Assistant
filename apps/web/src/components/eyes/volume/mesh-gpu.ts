/** One bounded native mesh/material port. It owns resources, never a frame clock. */
import type { VolumeMesh, VolumePose } from './volume-geometry';
export type VolumeGraphics = Pick<
  WebGLRenderingContext,
  | 'VERTEX_SHADER'
  | 'FRAGMENT_SHADER'
  | 'LINK_STATUS'
  | 'ARRAY_BUFFER'
  | 'ELEMENT_ARRAY_BUFFER'
  | 'STATIC_DRAW'
  | 'FLOAT'
  | 'UNSIGNED_SHORT'
  | 'TRIANGLES'
  | 'TEXTURE_2D'
  | 'TEXTURE0'
  | 'RGBA'
  | 'UNSIGNED_BYTE'
  | 'TEXTURE_MIN_FILTER'
  | 'TEXTURE_MAG_FILTER'
  | 'TEXTURE_WRAP_S'
  | 'TEXTURE_WRAP_T'
  | 'LINEAR'
  | 'REPEAT'
  | 'CLAMP_TO_EDGE'
  | 'BLEND'
  | 'ONE'
  | 'ONE_MINUS_SRC_ALPHA'
  | 'DEPTH_TEST'
  | 'LEQUAL'
  | 'ALWAYS'
  | 'COLOR_BUFFER_BIT'
  | 'DEPTH_BUFFER_BIT'
  | 'createShader'
  | 'shaderSource'
  | 'compileShader'
  | 'attachShader'
  | 'linkProgram'
  | 'getProgramParameter'
  | 'deleteShader'
  | 'deleteProgram'
  | 'deleteBuffer'
  | 'bindBuffer'
  | 'bufferData'
  | 'useProgram'
  | 'getAttribLocation'
  | 'enableVertexAttribArray'
  | 'vertexAttribPointer'
  | 'getUniformLocation'
  | 'uniform2fv'
  | 'uniform1f'
  | 'uniform1i'
  | 'deleteTexture'
  | 'bindTexture'
  | 'activeTexture'
  | 'texImage2D'
  | 'texParameteri'
  | 'enable'
  | 'blendFunc'
  | 'depthFunc'
  | 'depthMask'
  | 'clearColor'
  | 'clear'
  | 'viewport'
  | 'drawElements'
> & {
  /** Context loss can reject allocations even where newer DOM types say otherwise. */
  createProgram(): WebGLProgram | null;
  createBuffer(): WebGLBuffer | null;
  createTexture(): WebGLTexture | null;
};

const VERTEX = `
attribute vec3 a_position; attribute vec3 a_normal; attribute vec2 a_uv;
uniform vec2 u_pose; uniform float u_extent; varying vec2 v_uv; varying vec3 v_normal; varying vec3 v_original; varying vec3 v_material;
vec3 turn(vec3 p){float sy=sin(u_pose.x),cy=cos(u_pose.x),sp=sin(u_pose.y),cp=cos(u_pose.y);vec3 q=vec3(p.x*cy+p.z*sy,p.y,p.z*cy-p.x*sy);return vec3(q.x,q.y*cp-q.z*sp,q.y*sp+q.z*cp);}
void main(){vec3 p=turn(a_position);gl_Position=vec4(p.x/u_extent,-p.y/u_extent,-p.z/3.0,1.0);v_uv=a_uv;v_normal=turn(a_normal);v_original=a_normal;v_material=vec3(step(1.5,a_normal.z),1.-step(.0000001,abs(a_normal.z)),step(a_normal.z,0.));}`;
// A radial organic normal can have z=0. Only the monitor's casing owns
// opaque wall material; a smooth body's contour retains source alpha.
const FRAGMENT = `
precision mediump float;uniform sampler2D u_texture;uniform sampler2D u_fringe;uniform vec2 u_light;uniform float u_opacity;uniform float u_case;varying vec2 v_uv;varying vec3 v_normal;varying vec3 v_original;varying vec3 v_material;
float light(vec3 n){return .55+.35*max(0.,dot(normalize(n),normalize(vec3(-.6,-.7,1.))))+.1*max(0.,dot(normalize(n),normalize(vec3(.8,.1,.8))));}
void main(){vec4 tex=texture2D(u_texture,v_uv);if(v_material.x>.5){float alpha=min(tex.a,texture2D(u_fringe,v_uv).a);if(alpha<.004)discard;gl_FragColor=vec4(tex.rgb*alpha,alpha);return;}float rim=u_case*v_material.y;float casing=u_case*v_material.z;if(tex.a<.004&&max(rim,casing)<.5)discard;float delta=clamp(light(v_normal)/light(v_original),.76,1.23);vec3 pigment=mix(tex.rgb,vec3(.38,.43,.47),casing)*delta*vec3(1.+u_light.x*.025,1.-u_light.y*.018,1.+u_light.y*.035);float alpha=mix(tex.a,1.,max(rim,casing))*u_opacity;gl_FragColor=vec4(pigment*alpha,alpha);}`;

export function createMeshGpu(
  canvas: HTMLCanvasElement,
  gl: VolumeGraphics,
  mesh: VolumeMesh,
  repeat = false,
  extent = 1.3,
  solidCase = false
) {
  const program = gl.createProgram(),
    vertex = gl.createShader(gl.VERTEX_SHADER),
    fragment = gl.createShader(gl.FRAGMENT_SHADER);
  if (!program || !vertex || !fragment) {
    gl.deleteProgram(program);
    gl.deleteShader(vertex);
    gl.deleteShader(fragment);
    return null;
  }
  for (const [shader, source] of [
    [vertex, VERTEX],
    [fragment, FRAGMENT],
  ] as const) {
    gl.shaderSource(shader, source);
    gl.compileShader(shader);
    gl.attachShader(program, shader);
  }
  gl.linkProgram(program);
  gl.deleteShader(vertex);
  gl.deleteShader(fragment);
  if (!gl.getProgramParameter(program, gl.LINK_STATUS)) {
    gl.deleteProgram(program);
    return null;
  }
  const vertices = gl.createBuffer(),
    indices = gl.createBuffer(),
    texture = gl.createTexture();
  if (!vertices || !indices || !texture) {
    gl.deleteBuffer(vertices);
    gl.deleteBuffer(indices);
    gl.deleteTexture(texture);
    gl.deleteProgram(program);
    return null;
  }
  gl.bindBuffer(gl.ARRAY_BUFFER, vertices);
  gl.bufferData(gl.ARRAY_BUFFER, mesh.vertices, gl.STATIC_DRAW);
  gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER, indices);
  gl.bufferData(gl.ELEMENT_ARRAY_BUFFER, mesh.indices, gl.STATIC_DRAW);
  const attributes = [
    ['a_position', 3, 0],
    ['a_normal', 3, 12],
    ['a_uv', 2, 24],
  ] as const;
  const locations = attributes.map(([name, count, offset]) => ({
    location: gl.getAttribLocation(program, name),
    count,
    offset,
  }));
  const poseUniform = gl.getUniformLocation(program, 'u_pose'),
    lightUniform = gl.getUniformLocation(program, 'u_light'),
    opacityUniform = gl.getUniformLocation(program, 'u_opacity'),
    textureUniform = gl.getUniformLocation(program, 'u_texture'),
    fringeUniform = gl.getUniformLocation(program, 'u_fringe'),
    extentUniform = gl.getUniformLocation(program, 'u_extent'),
    caseUniform = gl.getUniformLocation(program, 'u_case');
  const poseValues = new Float32Array(2),
    lightValues = new Float32Array(2);
  let active = true,
    ready = false,
    masked = false;
  let fringeTexture: WebGLTexture | null = null;
  const uploadTexture = (target: WebGLTexture, image: TexImageSource, tiled: boolean) => {
    gl.bindTexture(gl.TEXTURE_2D, target);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, tiled ? gl.REPEAT : gl.CLAMP_TO_EDGE);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, tiled ? gl.REPEAT : gl.CLAMP_TO_EDGE);
    gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, gl.RGBA, gl.UNSIGNED_BYTE, image);
  };
  return {
    upload(image: TexImageSource, fringe?: TexImageSource) {
      if (!active) return;
      masked = false;
      if (fringe) {
        fringeTexture ??= gl.createTexture();
        if (!fringeTexture) {
          ready = false;
          return;
        }
        gl.activeTexture(gl.TEXTURE0 + 1);
        uploadTexture(fringeTexture, fringe, false);
        masked = true;
      }
      gl.activeTexture(gl.TEXTURE0);
      uploadTexture(texture, image, repeat);
      ready = true;
    },
    draw(pose: VolumePose, warm = 0, cool = 0, opacity = 1) {
      if (!active || !ready) return false;
      gl.useProgram(program);
      gl.bindBuffer(gl.ARRAY_BUFFER, vertices);
      gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER, indices);
      for (const attribute of locations) {
        if (attribute.location < 0) continue;
        gl.enableVertexAttribArray(attribute.location);
        gl.vertexAttribPointer(
          attribute.location,
          attribute.count,
          gl.FLOAT,
          false,
          32,
          attribute.offset
        );
      }
      gl.activeTexture(gl.TEXTURE0);
      gl.bindTexture(gl.TEXTURE_2D, texture);
      gl.uniform1i(textureUniform, 0);
      if (masked) {
        gl.activeTexture(gl.TEXTURE0 + 1);
        gl.bindTexture(gl.TEXTURE_2D, fringeTexture);
      }
      gl.uniform1i(fringeUniform, masked ? 1 : 0);
      poseValues[0] = pose.yaw;
      poseValues[1] = pose.pitch;
      lightValues[0] = warm;
      lightValues[1] = cool;
      gl.uniform2fv(poseUniform, poseValues);
      gl.uniform2fv(lightUniform, lightValues);
      gl.uniform1f(opacityUniform, opacity);
      gl.uniform1f(extentUniform, extent);
      gl.uniform1f(caseUniform, Number(solidCase));
      gl.viewport(0, 0, canvas.width, canvas.height);
      gl.drawElements(gl.TRIANGLES, mesh.indices.length, gl.UNSIGNED_SHORT, 0);
      return true;
    },
    dispose() {
      if (!active) return;
      active = false;
      if (fringeTexture) gl.deleteTexture(fringeTexture);
      gl.deleteTexture(texture);
      gl.deleteBuffer(vertices);
      gl.deleteBuffer(indices);
      gl.deleteProgram(program);
    },
  };
}
