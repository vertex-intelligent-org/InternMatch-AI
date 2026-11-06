// Geometry and phases adapted from mobile SplashBowArrowAnimation.js at 4ad7dc0.
const clamp = (n: number) => Math.max(0, Math.min(1, n));
const outQuad = (n: number) => 1 - (1 - clamp(n)) ** 2;
const inOutQuad = (n: number) => { const t = clamp(n); return t < .5 ? 2 * t * t : 1 - (-2 * t + 2) ** 2 / 2; };
const inOutCubic = (n: number) => { const t = clamp(n); return t < .5 ? 4 * t ** 3 : 1 - (-2 * t + 2) ** 3 / 2; };
function flightEase(n: number) {
  const target = clamp(n); let low = 0, high = 1, u = target;
  // Solve x(t) of the original cubic-bezier(.22, 1, .36, 1).
  for (let i = 0; i < 16; i++) {
    u = (low + high) / 2;
    const x = 3 * (1 - u) ** 2 * u * .22 + 3 * (1 - u) * u ** 2 * .36 + u ** 3;
    if (x < target) low = u; else high = u;
  }
  return 1 - (1 - u) ** 3;
}
export const bowGeometry = { targetX: 254, targetY: 44, bowX: 169, bowY: 164, compactDuration: 1800 } as const;
export function bowFrame(elapsed: number) {
  const t = Math.max(0, elapsed) / .6;
  const dx = 85, dy = -120, distance = Math.hypot(dx, dy);
  const draw = inOutCubic((t - 350) / 950);
  const flight = t <= 1550 ? 0 : flightEase((t - 1550) / 1200);
  const tension = t < 1550 ? draw : 1 - outQuad((t - 1550) / 50);
  const u = flight > 0 ? 18 + flight * (distance + 85 - 18) : 43 - draw * 25;
  const intro = outQuad(t / 350);
  return {
    x: bowGeometry.bowX + u * dx / distance,
    y: bowGeometry.bowY + u * dy / distance,
    angle: Math.atan2(dy, dx) * 180 / Math.PI,
    nock: -7 - 25 * tension,
    bowOpacity: intro * (1 - inOutQuad((t - 2200) / 500)),
    arrowOpacity: intro * (1 - inOutQuad((t - 2500) / 350)),
    impact: t >= 2100,
    finished: t >= 3000,
    phase: t < 350 ? 'intro' : t < 1300 ? 'draw' : t < 1550 ? 'hold' : t < 2850 ? 'flight' : 'settled',
  };
}
