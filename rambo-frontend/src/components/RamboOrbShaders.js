export const ramboOrbVertexShader = /* glsl */ `
  attribute float aRandom;
  attribute float aPhase;

  uniform float uTime;
  uniform float uPixelRatio;
  uniform float uBaseSize;
  uniform float uRotationSpeed;
  uniform float uPerspective; // calibration distance — keep close to camera.position.z

  varying float vAlpha;
  varying float vRandom;

  mat3 rotateY(float a) {
    float c = cos(a), s = sin(a);
    return mat3(c, 0.0, s, 0.0, 1.0, 0.0, -s, 0.0, c);
  }
  mat3 rotateX(float a) {
    float c = cos(a), s = sin(a);
    return mat3(1.0, 0.0, 0.0, 0.0, c, -s, 0.0, s, c);
  }

  void main() {
    vec3 pos = position;
    float rad = length(position); // original radius — stable for the fade

    pos = rotateY(uTime * uRotationSpeed) * pos;
    pos = rotateX(uTime * uRotationSpeed * 0.35) * pos;

    // Layered drift: a slow radial breath plus a tangential swirl so the cloud
    // churns like plasma instead of sitting as a rigid shell.
    float breath = sin(uTime * 0.6 + aPhase * 6.2831) * 0.045;
    float swirl  = sin(uTime * 0.9 + rad * 3.0 + aPhase * 6.2831) * 0.03;
    pos += normalize(pos) * breath;
    pos += vec3(-pos.y, pos.x, pos.z * 0.2) * swirl * 0.15;

    vec4 mvPosition = modelViewMatrix * vec4(pos, 1.0);
    gl_Position = projectionMatrix * mvPosition;

    float dist = -mvPosition.z;

    // uPerspective keeps the size multiplier ~1.0 at the camera's working
    // distance, so uBaseSize is close to the real on-screen pixel size.
    gl_PointSize = uBaseSize * uPixelRatio * (uPerspective / dist) * (0.3 + aRandom * 0.9);

    // Fade particles by radius so the outer cloud dissolves into wisps and
    // there is no crisp circular boundary (ORB_RADIUS ~ 1.8).
    float radialFade = 1.0 - smoothstep(1.7, 2.7, rad);

    vAlpha = (0.22 + 0.78 * aRandom) * radialFade;
    vRandom = aRandom;
  }
`;

export const ramboOrbFragmentShader = /* glsl */ `
  precision mediump float;

  uniform vec3 uColor;
  uniform vec3 uColorCore;

  varying float vAlpha;
  varying float vRandom;

  void main() {
    vec2 c = gl_PointCoord - vec2(0.5);
    float d = length(c);
    if (d > 0.5) discard;

    float glow = smoothstep(0.5, 0.0, d);
    float core = smoothstep(0.18, 0.0, d);

    vec3 color = mix(uColor, uColorCore, core);
    gl_FragColor = vec4(color, glow * vAlpha);
  }
`;

// Plasma nucleus — billboarded quad with fbm noise, replaces the old Sprite core
export const ramboPlasmaVertexShader = /* glsl */ `
  varying vec2 vUv;
  void main() {
    vUv = uv;
    gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
  }
`;

export const ramboPlasmaFragmentShader = /* glsl */ `
  precision mediump float;
  uniform float uTime;
  uniform float uBreath;
  uniform vec3 uColor;
  varying vec2 vUv;

  float hash(vec2 p) {
    p = fract(p * vec2(127.1, 311.7));
    p += dot(p, p + 17.5);
    return fract(p.x * p.y);
  }

  float noise(vec2 p) {
    vec2 i = floor(p);
    vec2 f = fract(p);
    f = f * f * (3.0 - 2.0 * f);
    return mix(
      mix(hash(i), hash(i + vec2(1.0, 0.0)), f.x),
      mix(hash(i + vec2(0.0, 1.0)), hash(i + vec2(1.0, 1.0)), f.x),
      f.y
    );
  }

  float fbm(vec2 p) {
    float v = 0.0; float a = 0.5;
    for (int i = 0; i < 6; i++) {
      v += a * noise(p);
      p = p * 2.3 + vec2(1.7, 9.2);
      a *= 0.5;
    }
    return v;
  }

  void main() {
    vec2 uv = vUv * 2.0 - 1.0;
    float dist = length(uv);
    if (dist > 1.0) discard;

    float t = uTime * 0.35;
    vec2 q = vec2(
      fbm(uv * 1.5 + vec2(t * 0.10, 0.0)),
      fbm(uv * 1.5 + vec2(0.0,      t * 0.13))
    );
    vec2 r = vec2(
      fbm(uv * 2.0 + q + vec2(t * 0.06, t * 0.08)),
      fbm(uv * 2.0 + q + vec2(8.3, 2.8))
    );
    float f = fbm(uv * 1.2 + r * 0.7);

    float radial = 1.0 - smoothstep(0.0, 1.0, dist);
    radial = pow(radial, 1.2 + uBreath * 0.25);
    float plasma = mix(f, 1.0, 0.35) * radial;

    vec3 colWarm = vec3(1.0, 0.96, 0.85);
    vec3 col = mix(uColor * 0.4, uColor * 1.6, plasma);
    col = mix(col, colWarm, pow(plasma, 2.5));

    gl_FragColor = vec4(col, plasma * (0.85 + uBreath * 0.12));
  }
`;

// Shared by rings AND spokes — same rotation math as the particle shader so
// everything in the scene tumbles together instead of drifting apart.
export const ramboOrbLineVertexShader = /* glsl */ `
  uniform float uTime;
  uniform float uRotationSpeed;

  mat3 rotateY(float a) {
    float c = cos(a), s = sin(a);
    return mat3(c, 0.0, s, 0.0, 1.0, 0.0, -s, 0.0, c);
  }
  mat3 rotateX(float a) {
    float c = cos(a), s = sin(a);
    return mat3(1.0, 0.0, 0.0, 0.0, c, -s, 0.0, s, c);
  }

  void main() {
    vec3 pos = position;
    pos = rotateY(uTime * uRotationSpeed) * pos;
    pos = rotateX(uTime * uRotationSpeed * 0.35) * pos;
    gl_Position = projectionMatrix * modelViewMatrix * vec4(pos, 1.0);
  }
`;

export const ramboOrbLineFragmentShader = /* glsl */ `
  precision mediump float;
  uniform vec3 uColor;
  uniform float uOpacity;

  void main() {
    gl_FragColor = vec4(uColor, uOpacity);
  }
`;
