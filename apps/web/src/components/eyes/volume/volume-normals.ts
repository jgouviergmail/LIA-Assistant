/** Smooth normals of the final triangulated sheet, computed once at asset load. */
export function smoothSurfaceNormals(vertices: number[], indices: readonly number[]) {
  const normals = new Float64Array((vertices.length / 8) * 3);
  for (let triangle = 0; triangle < indices.length; triangle += 3) {
    const a = indices[triangle] * 8,
      b = indices[triangle + 1] * 8,
      c = indices[triangle + 2] * 8;
    const ux = vertices[b] - vertices[a],
      uy = vertices[b + 1] - vertices[a + 1],
      uz = vertices[b + 2] - vertices[a + 2];
    const vx = vertices[c] - vertices[a],
      vy = vertices[c + 1] - vertices[a + 1],
      vz = vertices[c + 2] - vertices[a + 2];
    // The unnormalised cross product weights each triangle by its area.
    const nx = uy * vz - uz * vy,
      ny = uz * vx - ux * vz,
      nz = ux * vy - uy * vx;
    for (let corner = 0; corner < 3; corner++) {
      const offset = indices[triangle + corner] * 3;
      normals[offset] += nx;
      normals[offset + 1] += ny;
      normals[offset + 2] += nz;
    }
  }
  for (let vertex = 0; vertex < normals.length / 3; vertex++) {
    const offset = vertex * 3;
    const length = Math.hypot(normals[offset], normals[offset + 1], normals[offset + 2]);
    if (length === 0) continue;
    vertices[vertex * 8 + 3] = normals[offset] / length;
    vertices[vertex * 8 + 4] = normals[offset + 1] / length;
    vertices[vertex * 8 + 5] = normals[offset + 2] / length;
  }
}
