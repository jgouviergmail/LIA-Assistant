/** CSS used values can round an exact 44px target to 43.999992 in Firefox. */
export const cssPixels = (value: number | undefined) => Math.round((value ?? 0) * 1000) / 1000;
