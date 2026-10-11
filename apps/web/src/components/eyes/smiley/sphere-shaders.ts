/** Two triangles bound the rays; the fragment's visible surface is a 3D sphere. */
export const SPHERE_VERTEX = `
attribute vec2 a_point;
varying vec2 v_ray;
void main() {
  v_ray = a_point;
  gl_Position = vec4(a_point, 0.0, 1.0);
}`;

export const SPHERE_FRAGMENT = `
precision mediump float;
varying vec2 v_ray;
uniform vec4 u_state;
uniform float u_cool;
uniform float u_pixel;
uniform float u_female;

void main() {
  const float radius = 0.98;
  float radial = length(v_ray);
  if (radial >= radius) discard;
  // Orthographic ray (x,y,t) intersects x*x+y*y+z*z=radius*radius.
  vec3 normal = vec3(v_ray, sqrt(max(0.0, radius*radius-dot(v_ray,v_ray)))) / radius;
  float tilt = u_state.z;
  vec3 lit = vec3(normal.x*cos(tilt)+normal.y*sin(tilt),
                  normal.y*cos(tilt)-normal.x*sin(tilt), normal.z);
  vec3 screen = vec3(normal.x, -normal.y, normal.z);
  float sp = sin(u_state.y), cp = cos(u_state.y);
  vec3 unpitched = vec3(screen.x, screen.y*cp+screen.z*sp,
                       screen.z*cp-screen.y*sp);
  float sy = sin(u_state.x), cy = cos(u_state.x);
  vec3 local = vec3(unpitched.x*cy-unpitched.z*sy, unpitched.y,
                    unpitched.z*cy+unpitched.x*sy);
  // Linear golden enamel, then display gamma: shadow stays amber, not olive.
  vec3 pigment = mix(vec3(0.85,0.17,0.001), vec3(1.0,0.65,0.005),
                     smoothstep(-0.1,0.75,local.z));
  vec3 key = normalize(vec3(-0.65,0.82,0.9));
  vec3 fill = normalize(vec3(0.8,0.28,0.75));
  vec3 bounce = normalize(vec3(0.0,-0.8,0.45));
  // Broad key/fill and restrained ambient keep the lower hemisphere sculpted.
  float diffuse = 0.29 + 0.52*max(0.0,dot(lit,key))
                       + 0.13*max(0.0,dot(lit,fill))
                       + 0.055*max(0.0,dot(lit,bounce));
  vec3 halfKey = normalize(key+vec3(0.0,0.0,1.0));
  float coat = 0.32*pow(max(0.0,dot(lit,halfKey)),44.0);
  float softbox = 0.18*pow(max(0.0,dot(lit,halfKey)),14.0);
  float rim = 0.075*pow(1.0-normal.z,3.0);
  vec3 shadedPigment = mix(vec3(0.95,0.34,0.003),pigment,smoothstep(0.48,0.95,diffuse));
  vec2 cheek = (vec2(abs(local.x),local.y)-vec2(0.59,0.13))/vec2(0.17,0.13);
  float blush = u_female*exp(-dot(cheek,cheek))*smoothstep(0.1,0.4,local.z)*0.48;
  shadedPigment = mix(shadedPigment,vec3(0.93,0.14,0.14),blush);
  vec3 color = shadedPigment*diffuse + vec3(1.0,0.98,0.80)*(coat+softbox+rim);
  color *= vec3(1.0+u_state.w*0.025, 1.0-u_cool*0.025, 1.0+u_cool*0.06);
  float alpha = 1.0-smoothstep(radius-u_pixel,radius,radial);
  gl_FragColor = vec4(pow(clamp(color,0.0,1.0),vec3(1.0/2.2))*alpha,alpha);
}`;

/** Matches the cloth camera: Y down, em space, window depth = .5 - z / 6. */
export const SPHERE_DEPTH_FRAGMENT =
  '#extension GL_EXT_frag_depth : require\n' +
  SPHERE_FRAGMENT.replace(
    '  gl_FragColor =',
    '  gl_FragDepthEXT = 0.5 - normal.z * (radius * 1.3) / 6.0;\n  gl_FragColor ='
  );

export const SPHERE_QUAD = new Float32Array([-1, -1, 1, -1, -1, 1, -1, 1, 1, -1, 1, 1]);
