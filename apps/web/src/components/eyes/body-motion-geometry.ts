/** Pure geometry for temporary whole-body motion; coordinates are relative em. */
export interface BodyMotionSpace {
  minX: number;
  maxX: number;
  minY: number;
  maxY: number;
  roaming: boolean;
}
export interface BodyViewport {
  left: number;
  top: number;
  width: number;
  height: number;
}
export interface BodyBox extends BodyViewport {
  fontSize: number;
}
export interface BodyMotionPose {
  x: number;
  y: number;
  roll: number;
  sx: number;
  sy: number;
}

const ORNAMENT_MARGIN_EM = 0.3;
const LOCAL_TRAVEL_EM = 0.7;
const MIN_REQUESTED_SCALE = 0.05;

function finite(value: number, fallback = 0): number {
  return Number.isFinite(value) ? value : fallback;
}

function rectangle(value: BodyViewport): BodyViewport {
  return {
    left: finite(value.left),
    top: finite(value.top),
    width: Math.max(0, finite(value.width)),
    height: Math.max(0, finite(value.height)),
  };
}

function measuredBox(value: BodyBox): BodyBox {
  const fontSize = finite(value.fontSize, 1);
  return { ...rectangle(value), fontSize: fontSize > 0 ? fontSize : 1 };
}

function requestedPose(value: BodyMotionPose): BodyMotionPose {
  return {
    x: finite(value.x),
    y: finite(value.y),
    roll: finite(value.roll),
    sx: Math.max(MIN_REQUESTED_SCALE, finite(value.sx, 1)),
    sy: Math.max(MIN_REQUESTED_SCALE, finite(value.sy, 1)),
  };
}

function contains(box: BodyBox, viewport: BodyViewport): boolean {
  return (
    box.left >= viewport.left &&
    box.top >= viewport.top &&
    box.left + box.width <= viewport.left + viewport.width &&
    box.top + box.height <= viewport.top + viewport.height
  );
}

function atRest(pose: BodyMotionPose): boolean {
  return pose.x === 0 && pose.y === 0 && pose.roll === 0 && pose.sx === 1 && pose.sy === 1;
}

/**
 * Safe destinations for any roll at the largest authored scale. The origin
 * always stays available for the terminal pose; projection guards that origin
 * separately if viewport changes or the user's anchor lies near an edge.
 */
export function bodyMotionSpace(
  box: BodyBox,
  viewport: BodyViewport,
  roaming: boolean,
  maxScale = 1.3
): BodyMotionSpace {
  const measured = measuredBox(box);
  const visible = rectangle(viewport);
  const margin = measured.fontSize * ORNAMENT_MARGIN_EM;
  const radius =
    Math.hypot(measured.width / 2 + margin, measured.height / 2 + margin) *
    Math.max(1, finite(maxScale, 1.3));
  if (
    !measured.width ||
    !measured.height ||
    !Number.isFinite(radius) ||
    radius * 2 >= Math.min(visible.width, visible.height)
  ) {
    return { minX: 0, maxX: 0, minY: 0, maxY: 0, roaming: false };
  }
  const originX = visible.left - measured.left - measured.width / 2;
  const originY = visible.top - measured.top - measured.height / 2;
  const limit = roaming ? Infinity : LOCAL_TRAVEL_EM;
  return {
    minX: Math.max(-limit, Math.min(0, finite((originX + radius) / measured.fontSize))),
    maxX: Math.min(
      limit,
      Math.max(0, finite((originX + visible.width - radius) / measured.fontSize))
    ),
    minY: Math.max(-limit, Math.min(0, finite((originY + radius) / measured.fontSize))),
    maxY: Math.min(
      limit,
      Math.max(0, finite((originY + visible.height - radius) / measured.fontSize))
    ),
    roaming,
  };
}

/** A reserve, not permanent layout: its derivative is zero at the resting pose. */
function ornamentReserve(pose: BodyMotionPose): number {
  const halfAngle = ((pose.roll % 360) * Math.PI) / 360;
  const departure = Math.max(
    Math.hypot(pose.x, pose.y) / LOCAL_TRAVEL_EM,
    Math.abs(Math.sin(halfAngle)) / Math.sin(Math.PI / 24),
    Math.abs(pose.sx - 1) / 0.2,
    Math.abs(pose.sy - 1) / 0.2
  );
  const weight = Math.min(1, departure);
  return weight * weight * (3 - 2 * weight);
}

/** Actual deformed body plus a continuous reserve, normalized before scaling. */
function halfBounds(pose: BodyMotionPose, box: BodyBox) {
  const angle = ((pose.roll % 360) * Math.PI) / 180;
  const cosine = Math.abs(Math.cos(angle));
  const sine = Math.abs(Math.sin(angle));
  const magnitude = Math.max(pose.sx, pose.sy);
  const sx = pose.sx / magnitude;
  const sy = pose.sy / magnitude;
  const margin = box.fontSize * ORNAMENT_MARGIN_EM * ornamentReserve(pose);
  const x = (box.width / 2 + margin) * sx;
  const y = (box.height / 2 + margin) * sy;
  return { x: cosine * x + sine * y, y: sine * x + cosine * y, magnitude, sx, sy };
}

function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value));
}

/**
 * Constrain only the temporary paint, never the saved anchor. If the original
 * resting rectangle fits, identity stays exactly identity even at an edge.
 * The actual body is always contained; the additional ornament reserve grows
 * smoothly away from rest and is periodic across complete revolutions.
 * A smaller viewport may uniformly reduce the requested scale below its input
 * floor: an arbitrarily small visible frame cannot contain a fixed-size body.
 */
export function projectBodyMotion(
  desired: BodyMotionPose,
  box: BodyBox,
  viewport: BodyViewport
): BodyMotionPose {
  const pose = requestedPose(desired);
  const measured = measuredBox(box);
  const visible = rectangle(viewport);
  if (!visible.width || !visible.height || !measured.width || !measured.height) {
    return { ...pose, x: 0, y: 0 };
  }
  if (atRest(pose) && contains(measured, visible)) return pose;

  const bounds = halfBounds(pose, measured);
  const magnitude = Math.min(
    bounds.magnitude,
    visible.width / (2 * bounds.x),
    visible.height / (2 * bounds.y)
  );
  const halfX = bounds.x * magnitude;
  const halfY = bounds.y * magnitude;
  const centreX = measured.left + measured.width / 2;
  const centreY = measured.top + measured.height / 2;
  const x = clamp(
    centreX + pose.x * measured.fontSize,
    visible.left + halfX,
    visible.left + visible.width - halfX
  );
  const y = clamp(
    centreY + pose.y * measured.fontSize,
    visible.top + halfY,
    visible.top + visible.height - halfY
  );
  return {
    x: finite((x - centreX) / measured.fontSize),
    y: finite((y - centreY) / measured.fontSize),
    roll: pose.roll,
    sx: bounds.sx * magnitude,
    sy: bounds.sy * magnitude,
  };
}
