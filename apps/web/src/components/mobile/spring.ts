export type Spring = { damping: number; stiffness: number; mass: number };

// Damped harmonic oscillator, sampled for the browser's Web Animations API.
// The physical constants come directly from Reanimated's mobile tokens.
export function springSamples(from: number, to: number, spring: Spring, duration = 800) {
  const frequency = Math.sqrt(spring.stiffness / spring.mass);
  const damping = spring.damping / (2 * Math.sqrt(spring.stiffness * spring.mass));
  return Array.from({ length: 61 }, (_, index) => {
    const t = (index / 60) * duration / 1000;
    let displacement: number;
    if (damping < 1) {
      const damped = frequency * Math.sqrt(1 - damping * damping);
      displacement = Math.exp(-damping * frequency * t) * (Math.cos(damped * t) + damping * frequency / damped * Math.sin(damped * t));
    } else if (damping === 1) {
      displacement = Math.exp(-frequency * t) * (1 + frequency * t);
    } else {
      const a = -frequency * (damping - Math.sqrt(damping * damping - 1));
      const b = -frequency * (damping + Math.sqrt(damping * damping - 1));
      displacement = (b * Math.exp(a * t) - a * Math.exp(b * t)) / (b - a);
    }
    return index === 60 ? to : to + (from - to) * displacement;
  });
}
