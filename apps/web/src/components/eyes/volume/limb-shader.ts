/** Distal-then-parent skinning, with the inverse-transpose of its spatial Jacobian. */
export const LIMB_VERTEX_DECLARATIONS = `
attribute vec4 a_skin; attribute vec4 a_gradient; uniform vec4 u_joints[8];
mat2 spin(float angle){float s=sin(angle),c=cos(angle);return mat2(c,s,-s,c);}
vec2 tangent(vec2 p){return vec2(-p.y,p.x);}
vec4 joint(float index){
  if(index<.5)return u_joints[0];if(index<1.5)return u_joints[1];
  if(index<2.5)return u_joints[2];if(index<3.5)return u_joints[3];
  if(index<4.5)return u_joints[4];if(index<5.5)return u_joints[5];
  if(index<6.5)return u_joints[6];return u_joints[7];
}
void articulate(inout vec3 position,inout vec3 normal){
  vec4 parent=joint(a_skin.x),distal=joint(a_skin.y);
  if(parent.z==0.&&distal.z==0.)return;
  if(a_skin.z==0.&&a_skin.w==0.)return;
  mat2 distalTurn=spin(distal.z*a_skin.w),parentTurn=spin(parent.z*a_skin.z);
  vec2 tip=distalTurn*(position.xy-distal.xy);
  vec2 middle=distal.xy+tip-parent.xy;
  vec2 bent=parentTurn*middle;
  vec2 dx=parentTurn*(distalTurn[0]+tangent(tip)*distal.z*a_gradient.z)
    +tangent(bent)*parent.z*a_gradient.x;
  vec2 dy=parentTurn*(distalTurn[1]+tangent(tip)*distal.z*a_gradient.w)
    +tangent(bent)*parent.z*a_gradient.y;
  position.xy=parent.xy+bent;
  // The fringe normal is a material marker, not a geometric normal.
  if(normal.z>1.5)return;
  float determinant=dx.x*dy.y-dx.y*dy.x;
  normal.xy=vec2(dy.y*normal.x-dx.y*normal.y,-dy.x*normal.x+dx.x*normal.y)/determinant;
}`;
