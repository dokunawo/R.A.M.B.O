// CosmicOrbShaders.js — Tier 1: wireframe icosahedron with noise displacement + fresnel glow

// Compact 3D simplex noise (Stefan Gustavson / Ashima)
const SIMPLEX_NOISE_3D = /* glsl */ `
vec4 permute(vec4 x){return mod(((x*34.0)+1.0)*x, 289.0);}
vec4 taylorInvSqrt(vec4 r){return 1.79284291400159 - 0.85373472095314 * r;}

float snoise(vec3 v){
  const vec2 C = vec2(1.0/6.0, 1.0/3.0);
  const vec4 D = vec4(0.0, 0.5, 1.0, 2.0);
  vec3 i  = floor(v + dot(v, C.yyy));
  vec3 x0 = v - i + dot(i, C.xxx);
  vec3 g  = step(x0.yzx, x0.xyz);
  vec3 l  = 1.0 - g;
  vec3 i1 = min(g.xyz, l.zxy);
  vec3 i2 = max(g.xyz, l.zxy);
  vec3 x1 = x0 - i1 + C.xxx;
  vec3 x2 = x0 - i2 + C.yyy;
  vec3 x3 = x0 - D.yyy;
  i = mod(i, 289.0);
  vec4 p = permute(permute(permute(
    i.z + vec4(0.0, i1.z, i2.z, 1.0))
  + i.y + vec4(0.0, i1.y, i2.y, 1.0))
  + i.x + vec4(0.0, i1.x, i2.x, 1.0));
  float n_ = 1.0/7.0;
  vec3 ns = n_ * D.wyz - D.xzx;
  vec4 j = p - 49.0 * floor(p * ns.z * ns.z);
  vec4 x_ = floor(j * ns.z);
  vec4 y_ = floor(j - 7.0 * x_);
  vec4 x  = x_ * ns.x + ns.yyyy;
  vec4 y  = y_ * ns.x + ns.yyyy;
  vec4 h  = 1.0 - abs(x) - abs(y);
  vec4 b0 = vec4(x.xy, y.xy);
  vec4 b1 = vec4(x.zw, y.zw);
  vec4 s0 = floor(b0)*2.0 + 1.0;
  vec4 s1 = floor(b1)*2.0 + 1.0;
  vec4 sh = -step(h, vec4(0.0));
  vec4 a0 = b0.xzyw + s0.xzyw*sh.xxyy;
  vec4 a1 = b1.xzyw + s1.xzyw*sh.zzww;
  vec3 p0 = vec3(a0.xy, h.x);
  vec3 p1 = vec3(a0.zw, h.y);
  vec3 p2 = vec3(a1.xy, h.z);
  vec3 p3 = vec3(a1.zw, h.w);
  vec4 norm = taylorInvSqrt(vec4(dot(p0,p0),dot(p1,p1),dot(p2,p2),dot(p3,p3)));
  p0 *= norm.x; p1 *= norm.y; p2 *= norm.z; p3 *= norm.w;
  vec4 m = max(0.6 - vec4(dot(x0,x0),dot(x1,x1),dot(x2,x2),dot(x3,x3)), 0.0);
  m = m * m;
  return 42.0 * dot(m*m, vec4(dot(p0,x0),dot(p1,x1),dot(p2,x2),dot(p3,x3)));
}
`;

export const cosmicOrbVertexShader = /* glsl */ `
${SIMPLEX_NOISE_3D}

uniform float uTime;
uniform float uNoiseScale;
uniform float uNoiseStrength;
uniform float uBreathSpeed;
uniform float uAudioLevel;  // 0..1 — drives displacement intensity

varying vec3 vNormal;
varying vec3 vViewPosition;
varying float vDisplacement;

void main() {
  vec3 pos = position;
  vec3 norm = normalize(normal);

  // Audio-reactive boost: idle breath + audio spike
  float audioBoost = 1.0 + uAudioLevel * 3.0;

  // Layered noise displacement along normals — breathing surface
  float n1 = snoise(pos * uNoiseScale + uTime * uBreathSpeed * 0.3);
  float n2 = snoise(pos * uNoiseScale * 2.0 + uTime * uBreathSpeed * 0.5 + 42.0);
  float n3 = snoise(pos * uNoiseScale * 0.5 + uTime * uBreathSpeed * 0.15 - 17.0);

  float displacement = (n1 * 0.6 + n2 * 0.25 + n3 * 0.15) * uNoiseStrength * audioBoost;

  // Slow global breath
  displacement += sin(uTime * 0.8) * uNoiseStrength * 0.15;

  pos += norm * displacement;
  vDisplacement = displacement;

  vNormal = normalize(normalMatrix * norm);
  vec4 mvPosition = modelViewMatrix * vec4(pos, 1.0);
  vViewPosition = -mvPosition.xyz;

  gl_Position = projectionMatrix * mvPosition;
}
`;

export const cosmicOrbFragmentShader = /* glsl */ `
precision highp float;

uniform vec3 uColor;
uniform float uOpacity;
uniform float uFresnelPower;
uniform float uFresnelBias;
uniform float uAudioLevel;

varying vec3 vNormal;
varying vec3 vViewPosition;
varying float vDisplacement;

void main() {
  vec3 viewDir = normalize(vViewPosition);
  float fresnel = 1.0 - abs(dot(viewDir, vNormal));
  fresnel = uFresnelBias + (1.0 - uFresnelBias) * pow(fresnel, uFresnelPower);

  float displacementBright = 1.0 + vDisplacement * 0.8;
  // Audio adds extra glow intensity
  float audioBright = 1.0 + uAudioLevel * 0.6;

  vec3 color = uColor * mix(0.35, 1.6, fresnel) * displacementBright * audioBright;
  float alpha = mix(0.15, 0.95, fresnel) * uOpacity;

  gl_FragColor = vec4(color, alpha);
}
`;

// Glow halo shell — slightly larger sphere, soft additive fresnel
export const glowShellVertexShader = /* glsl */ `
varying vec3 vNormal;
varying vec3 vViewPosition;

void main() {
  vNormal = normalize(normalMatrix * normal);
  vec4 mvPosition = modelViewMatrix * vec4(position, 1.0);
  vViewPosition = -mvPosition.xyz;
  gl_Position = projectionMatrix * mvPosition;
}
`;

export const glowShellFragmentShader = /* glsl */ `
precision highp float;

uniform vec3 uColor;
uniform float uIntensity;

varying vec3 vNormal;
varying vec3 vViewPosition;

void main() {
  vec3 viewDir = normalize(vViewPosition);
  float fresnel = 1.0 - abs(dot(viewDir, vNormal));
  float glow = pow(fresnel, 2.5) * uIntensity;

  gl_FragColor = vec4(uColor, glow);
}
`;
