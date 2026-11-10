/** One bounded native mesh/material port. It owns resources, never a frame clock. */
import type { VolumeMesh, VolumePose } from './volume-geometry';
import type { ChannelValues } from '../rig/channels';
import { LIMB_VERTEX_DECLARATIONS } from './limb-shader';
import { createLimbGpu } from './limb-gpu';
import { sourceAlphaTransfer } from './source-alpha';
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
  | 'uniform4fv'
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

export interface MeshDrape {
  shear: number;
  seamY: number;
}

// Ambient, key, sheen and highlight exponent. Fill takes the remaining
// diffuse weight. The resting artwork supplies each material's base shading.
const MATERIALS = {
  original: new Float32Array([0.55, 0.35, 0, 4]),
  soft: new Float32Array([0.66, 0.27, 0.025, 3]),
  satin: new Float32Array([0.57, 0.34, 0.1, 6]),
  hard: new Float32Array([0.46, 0.42, 0.24, 11]),
  casing: new Float32Array([0.61, 0.33, 0.085, 7]),
  woven: new Float32Array([0.68, 0.24, 0.025, 3]),
};
export type SurfaceMaterial = keyof typeof MATERIALS;

const vertexSource = (skinned: boolean) => `
attribute vec3 a_position; attribute vec3 a_normal; attribute vec2 a_uv;
uniform vec2 u_pose; uniform vec2 u_drape; uniform float u_extent; varying vec2 v_uv; varying vec3 v_normal; varying vec3 v_original; varying vec3 v_material;
${skinned ? LIMB_VERTEX_DECLARATIONS : ''}
vec3 turn(vec3 p){float sy=sin(u_pose.x),cy=cos(u_pose.x),sp=sin(u_pose.y),cp=cos(u_pose.y);vec3 q=vec3(p.x*cy+p.z*sy,p.y,p.z*cy-p.x*sy);return vec3(q.x,q.y*cp-q.z*sp,q.y*sp+q.z*cp);}
void main(){
  vec3 position=a_position,normal=a_normal;
  ${skinned ? 'articulate(position,normal);' : ''}
  float freeLength=max(0.,position.y-u_drape.y);
  position.x+=u_drape.x*freeLength;
  normal.y-=u_drape.x*sign(freeLength)*normal.x;
  vec3 p=turn(position);
  gl_Position=vec4(p.x/u_extent,-p.y/u_extent,-p.z/3.0,1.0);
  v_uv=a_uv;v_normal=turn(normal);v_original=a_normal;
  v_material=vec3(step(1.5,a_normal.z),1.-step(.0000001,abs(a_normal.z)),step(a_normal.z,0.));
}`;
// A radial organic normal can have z=0. Only the monitor's casing owns
// opaque wall material; a smooth body's contour retains source alpha.
const FRAGMENT = `
precision mediump float;
uniform sampler2D u_texture,u_fringe;
uniform vec2 u_light,u_alpha_transfer;
uniform vec4 u_surface;
uniform float u_alpha_cutoff,u_opacity,u_case;
varying vec2 v_uv;
varying vec3 v_normal,v_original,v_material;
float light(vec3 n){
  float key=max(0.,dot(n,normalize(vec3(-.6,-.7,1.))));
  float fill=max(0.,dot(n,normalize(vec3(.8,.1,.8))));
  return u_surface.x+u_surface.y*key+(1.-u_surface.x-u_surface.y)*fill;
}
float sheen(vec3 n){
  return pow(max(0.,dot(n,normalize(vec3(-.3,-.35,1.8)))),u_surface.w);
}
void main(){
  vec4 tex=texture2D(u_texture,v_uv);
  tex.a=clamp(tex.a*u_alpha_transfer.x+u_alpha_transfer.y,0.,1.);
  if(v_material.x>.5){
    float alpha=min(tex.a,texture2D(u_fringe,v_uv).a);
    if(alpha<u_alpha_cutoff)discard;
    gl_FragColor=vec4(tex.rgb*alpha,alpha);
    return;
  }
  float rim=u_case*v_material.y;
  float casing=u_case*v_material.z;
  if(tex.a<u_alpha_cutoff&&max(rim,casing)<.5)discard;
  vec3 normal=normalize(v_normal),original=normalize(v_original);
  float delta=clamp(light(normal)/light(original)+u_surface.z*(sheen(normal)-sheen(original)),.76,1.23);
  vec3 pigment=mix(tex.rgb,vec3(.38,.43,.47),casing)*delta*vec3(1.+u_light.x*.025,1.-u_light.y*.018,1.+u_light.y*.035);
  float alpha=mix(tex.a,1.,max(rim,casing))*u_opacity;
  gl_FragColor=vec4(pigment*alpha,alpha);
}`;

export function createMeshGpu(
  canvas: HTMLCanvasElement,
  gl: VolumeGraphics,
  mesh: VolumeMesh,
  repeat = false,
  extent = 1.3,
  solidCase = false,
  alphaFloor = 0,
  material: SurfaceMaterial = 'original'
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
    [vertex, vertexSource(Boolean(mesh.skin))],
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
  const limbGpu = createLimbGpu(gl, program, mesh.skin);
  if (!limbGpu) {
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
    drapeUniform = gl.getUniformLocation(program, 'u_drape'),
    surfaceUniform = gl.getUniformLocation(program, 'u_surface'),
    lightUniform = gl.getUniformLocation(program, 'u_light'),
    opacityUniform = gl.getUniformLocation(program, 'u_opacity'),
    textureUniform = gl.getUniformLocation(program, 'u_texture'),
    fringeUniform = gl.getUniformLocation(program, 'u_fringe'),
    alphaUniform = gl.getUniformLocation(program, 'u_alpha_transfer'),
    alphaCutoffUniform = gl.getUniformLocation(program, 'u_alpha_cutoff'),
    extentUniform = gl.getUniformLocation(program, 'u_extent'),
    caseUniform = gl.getUniformLocation(program, 'u_case');
  const poseValues = new Float32Array(2),
    drapeValues = new Float32Array(2),
    lightValues = new Float32Array(2);
  const alpha = sourceAlphaTransfer(alphaFloor);
  const alphaValues = new Float32Array([alpha.slope, alpha.intercept]);
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
    draw(
      pose: VolumePose,
      warm = 0,
      cool = 0,
      opacity = 1,
      limbs?: Readonly<ChannelValues>,
      drape?: MeshDrape
    ) {
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
      gl.uniform4fv(surfaceUniform, MATERIALS[material]);
      limbGpu.draw(limbs);
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
      drapeValues[0] = drape?.shear ?? 0;
      drapeValues[1] = drape?.seamY ?? 0;
      lightValues[0] = warm;
      lightValues[1] = cool;
      gl.uniform2fv(poseUniform, poseValues);
      gl.uniform2fv(drapeUniform, drapeValues);
      gl.uniform2fv(lightUniform, lightValues);
      gl.uniform2fv(alphaUniform, alphaValues);
      gl.uniform1f(alphaCutoffUniform, alpha.cutoff);
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
      limbGpu.dispose();
      gl.deleteProgram(program);
    },
  };
}
