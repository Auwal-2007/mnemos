/**
 * HeroOrbit — the living knowledge network.
 *
 * What it depicts, and why it is not decoration:
 *
 *   Sources (brass, outer shell) feed inward toward the core; evidence
 *   (teal) forms in an inner shell; the core is the answer. Edges only ever
 *   run inward, so the shape reads as *consolidation* — material entering an
 *   archive and being distilled — rather than a generic "AI particle sphere".
 *
 * Technical notes:
 *  - Raw Three.js rather than React-Three-Fiber: R3F v9 requires React 19 and
 *    this app is on React 18. One engine, direct control, ~11 kB gzipped.
 *  - Points are a single `Points` object with a custom shader, not dozens of
 *    meshes, so the whole scene is one draw call for nodes plus one for edges.
 *  - The render loop stops when the tab is hidden or the element leaves the
 *    viewport, and never starts at all under `prefers-reduced-motion` — the
 *    static frame is rendered once instead.
 */

import { useEffect, useRef } from 'react';
import {
  AdditiveBlending,
  BufferAttribute,
  BufferGeometry,
  Color,
  LineBasicMaterial,
  LineSegments,
  PerspectiveCamera,
  Points,
  Scene,
  ShaderMaterial,
  WebGLRenderer,
} from 'three';
import { useMotionPreference } from '../../lib/motion';
import './HeroOrbit.css';

interface HeroOrbitProps {
  className?: string;
  /** Height in CSS pixels at desktop; the container is fluid. */
  density?: number;
}

interface Node {
  radius: number;
  theta: number;
  phi: number;
  speed: number;
  size: number;
  warm: number;
}

function buildNodes(count: number): Node[] {
  const nodes: Node[] = [];
  for (let index = 0; index < count; index += 1) {
    // Three shells: inner evidence, mid structure, outer sources.
    const shellRoll = Math.random();
    const radius = shellRoll < 0.34 ? 1.05 + Math.random() * 0.18 : shellRoll < 0.7 ? 1.5 + Math.random() * 0.22 : 2.0 + Math.random() * 0.3;
    nodes.push({
      radius,
      theta: Math.random() * Math.PI * 2,
      phi: Math.acos(2 * Math.random() - 1),
      speed: (0.06 + Math.random() * 0.1) * (radius > 1.6 ? -1 : 1),
      size: 1.1 + Math.random() * 1.5,
      // Outer nodes are warmer (brass: the human record); inner ones teal.
      warm: radius > 1.75 ? 1 : Math.random() * 0.35,
    });
  }
  return nodes;
}

export function HeroOrbit({ className, density = 150 }: HeroOrbitProps): JSX.Element {
  const mountRef = useRef<HTMLDivElement>(null);
  const reduced = useMotionPreference();

  useEffect(() => {
    const mount = mountRef.current;
    if (!mount) return undefined;

    // Respect a small viewport by thinning the field.
    const isSmall = window.innerWidth < 768;
    const count = Math.round(density * (isSmall ? 0.5 : 1));

    let renderer: WebGLRenderer;
    try {
      renderer = new WebGLRenderer({ antialias: true, alpha: true, powerPreference: 'low-power' });
    } catch {
      // No WebGL (old device, blocked context): the CSS fallback stays visible.
      return undefined;
    }

    renderer.setPixelRatio(Math.min(window.devicePixelRatio, isSmall ? 1.5 : 2));
    renderer.setClearAlpha(0);
    mount.appendChild(renderer.domElement);
    renderer.domElement.style.width = '100%';
    renderer.domElement.style.height = '100%';
    renderer.domElement.setAttribute('aria-hidden', 'true');

    const scene = new Scene();
    const camera = new PerspectiveCamera(46, 1, 0.1, 100);
    camera.position.set(0, 0.35, 6.2);

    const nodes = buildNodes(count);

    // ---- Node points -----------------------------------------------------
    const positions = new Float32Array(count * 3);
    const sizes = new Float32Array(count);
    const warmth = new Float32Array(count);

    const nodeGeometry = new BufferGeometry();
    nodeGeometry.setAttribute('position', new BufferAttribute(positions, 3));
    nodeGeometry.setAttribute('aSize', new BufferAttribute(sizes, 1));
    nodeGeometry.setAttribute('aWarm', new BufferAttribute(warmth, 1));

    const nodeMaterial = new ShaderMaterial({
      transparent: true,
      depthWrite: false,
      blending: AdditiveBlending,
      uniforms: {
        uTeal: { value: new Color('#4fc3b4') },
        uBrass: { value: new Color('#e8b871') },
        uPixelRatio: { value: renderer.getPixelRatio() },
        uOpacity: { value: 1 },
      },
      vertexShader: /* glsl */ `
        attribute float aSize;
        attribute float aWarm;
        varying float vWarm;
        uniform float uPixelRatio;
        void main() {
          vWarm = aWarm;
          vec4 mv = modelViewMatrix * vec4(position, 1.0);
          gl_Position = projectionMatrix * mv;
          float depthFade = smoothstep(9.0, 2.4, -mv.z);
          gl_PointSize = aSize * uPixelRatio * (5.4 / -mv.z) * depthFade;
        }
      `,
      fragmentShader: /* glsl */ `
        varying float vWarm;
        uniform vec3 uTeal;
        uniform vec3 uBrass;
        uniform float uOpacity;
        void main() {
          vec2 uv = gl_PointCoord - vec2(0.5);
          float d = length(uv);
          // Soft round sprite; discard the square corners entirely.
          float alpha = smoothstep(0.5, 0.06, d);
          alpha *= alpha;
          vec3 base = mix(uTeal, uBrass, vWarm);
          base = mix(base, vec3(0.96, 0.94, 0.9), 0.18 * smoothstep(0.16, 0.0, d));
          gl_FragColor = vec4(base, alpha * uOpacity);
        }
      `,
    });

    const points = new Points(nodeGeometry, nodeMaterial);
    scene.add(points);

    // ---- Edges: inner-to-core connections only ---------------------------
    const maxEdges = Math.floor(count * 1.05);
    const edgePositions = new Float32Array(maxEdges * 2 * 3);
    const edgeGeometry = new BufferGeometry();
    edgeGeometry.setAttribute('position', new BufferAttribute(edgePositions, 3));

    const edgeMaterial = new LineBasicMaterial({
      color: new Color('#4fc3b4'),
      transparent: true,
      opacity: 0.14,
      blending: AdditiveBlending,
      depthWrite: false,
    });
    const edges = new LineSegments(edgeGeometry, edgeMaterial);
    scene.add(edges);

    // Deterministic-ish pairing so the picture is stable between frames.
    const pairs: [number, number][] = [];
    for (let index = 0; index < count && pairs.length < maxEdges; index += 1) {
      if (nodes[index].radius < 1.5) continue;
      // Connect outward nodes to a nearer node, but skip most of them: a fully
      // connected graph reads as a wire cage, not a living structure.
      if (Math.random() > 0.42) continue;
      const target = Math.floor(Math.random() * count);
      if (target === index || nodes[target].radius > nodes[index].radius) continue;
      pairs.push([index, target]);
    }

    const toCartesian = (node: Node, time: number): [number, number, number] => {
      const theta = node.theta + time * node.speed;
      const phi = node.phi + Math.sin(time * 0.22 + node.theta) * 0.045;
      const r = node.radius;
      return [
        r * Math.sin(phi) * Math.cos(theta),
        r * Math.cos(phi) * 0.72,
        r * Math.sin(phi) * Math.sin(theta),
      ];
    };

    let pointerX = 0;
    let pointerY = 0;
    let targetX = 0;
    let targetY = 0;

    const onPointerMove = (event: PointerEvent): void => {
      targetX = (event.clientX / window.innerWidth - 0.5) * 2;
      targetY = (event.clientY / window.innerHeight - 0.5) * 2;
    };
    window.addEventListener('pointermove', onPointerMove, { passive: true });

    let frame = 0;
    let elapsed = 0;
    let running = true;
    let last = performance.now();

    const writeFrame = (): void => {
      for (let index = 0; index < count; index += 1) {
        const [x, y, z] = toCartesian(nodes[index], elapsed);
        positions[index * 3] = x;
        positions[index * 3 + 1] = y;
        positions[index * 3 + 2] = z;
        sizes[index] = nodes[index].size;
        warmth[index] = nodes[index].warm;
      }
      nodeGeometry.attributes.position.needsUpdate = true;
      nodeGeometry.attributes.aSize.needsUpdate = true;
      nodeGeometry.attributes.aWarm.needsUpdate = true;

      for (let index = 0; index < pairs.length; index += 1) {
        const [from, to] = pairs[index];
        const a = toCartesian(nodes[from], elapsed);
        const b = toCartesian(nodes[to], elapsed);
        const offset = index * 6;
        edgePositions[offset] = a[0];
        edgePositions[offset + 1] = a[1];
        edgePositions[offset + 2] = a[2];
        edgePositions[offset + 3] = b[0];
        edgePositions[offset + 4] = b[1];
        edgePositions[offset + 5] = b[2];
      }
      edgeGeometry.setDrawRange(0, pairs.length * 2);
      edgeGeometry.attributes.position.needsUpdate = true;
    };

    const resize = (): void => {
      const width = mount.clientWidth || 1;
      const height = mount.clientHeight || 1;
      renderer.setSize(width, height, false);
      camera.aspect = width / height;
      camera.updateProjectionMatrix();
      nodeMaterial.uniforms.uPixelRatio.value = renderer.getPixelRatio();
    };

    const observer = new ResizeObserver(resize);
    observer.observe(mount);
    resize();

    const draw = (): void => {
      // Ease the camera toward the pointer; never snap, which feels twitchy.
      pointerX += (targetX - pointerX) * 0.045;
      pointerY += (targetY - pointerY) * 0.045;
      camera.position.x = pointerX * 0.55;
      camera.position.y = 0.35 - pointerY * 0.38;
      camera.lookAt(0, 0, 0);
      renderer.render(scene, camera);
    };

    const tick = (now: number): void => {
      if (!running) return;
      const delta = Math.min((now - last) / 1000, 0.06);
      last = now;
      elapsed += delta;
      writeFrame();
      draw();
      frame = requestAnimationFrame(tick);
    };

    if (reduced) {
      // One static frame: the structure is still legible, nothing moves.
      elapsed = 3.2;
      writeFrame();
      draw();
    } else {
      frame = requestAnimationFrame(tick);
    }

    // Pause when hidden or scrolled away: a hero should not burn a laptop's
    // battery while the user reads the section below it.
    const onVisibility = (): void => {
      if (reduced) return;
      if (document.hidden) {
        running = false;
        cancelAnimationFrame(frame);
        frame = 0;
      } else if (!running) {
        running = true;
        last = performance.now();
        frame = requestAnimationFrame(tick);
      }
    };
    document.addEventListener('visibilitychange', onVisibility);

    const viewportObserver = new IntersectionObserver(
      (entries) => {
        if (reduced) return;
        const visible = entries.some((entry) => entry.isIntersecting);
        if (!visible && running) {
          running = false;
          cancelAnimationFrame(frame);
          frame = 0;
        } else if (visible && !running) {
          running = true;
          last = performance.now();
          frame = requestAnimationFrame(tick);
        }
      },
      { threshold: 0.01 },
    );
    viewportObserver.observe(mount);

    return () => {
      running = false;
      cancelAnimationFrame(frame);
      document.removeEventListener('visibilitychange', onVisibility);
      window.removeEventListener('pointermove', onPointerMove);
      viewportObserver.disconnect();
      observer.disconnect();
      nodeGeometry.dispose();
      nodeMaterial.dispose();
      edgeGeometry.dispose();
      edgeMaterial.dispose();
      renderer.dispose();
      if (renderer.domElement.parentNode === mount) mount.removeChild(renderer.domElement);
    };
  }, [density, reduced]);

  return (
    <div className={`hero-orbit ${className ?? ''}`.trim()} ref={mountRef}>
      {/* Static fallback: shown before WebGL initialises, when WebGL is
          unavailable, and as the reduced-motion picture. */}
      <svg className="hero-orbit__fallback" viewBox="0 0 400 400" aria-hidden="true">
        <defs>
          <radialGradient id="orbit-core">
            <stop offset="0%" stopColor="var(--accent)" stopOpacity="0.55" />
            <stop offset="100%" stopColor="var(--accent)" stopOpacity="0" />
          </radialGradient>
        </defs>
        <circle cx="200" cy="200" r="150" fill="url(#orbit-core)" />
        <g stroke="var(--accent)" strokeOpacity="0.28" fill="none">
          <ellipse cx="200" cy="200" rx="112" ry="104" />
          <ellipse cx="200" cy="200" rx="150" ry="58" strokeOpacity="0.16" />
          <ellipse cx="200" cy="200" rx="72" ry="140" strokeOpacity="0.13" />
        </g>
        <g fill="var(--brass)">
          <circle cx="200" cy="50" r="3" fillOpacity="0.85" />
          <circle cx="330" cy="230" r="2.4" fillOpacity="0.6" />
          <circle cx="96" cy="286" r="2.8" fillOpacity="0.7" />
          <circle cx="128" cy="112" r="2" fillOpacity="0.55" />
        </g>
        <g fill="var(--accent)">
          <circle cx="200" cy="200" r="5" />
          <circle cx="236" cy="150" r="2.6" fillOpacity="0.8" />
          <circle cx="160" cy="238" r="2.2" fillOpacity="0.7" />
          <circle cx="264" cy="252" r="2" fillOpacity="0.6" />
        </g>
      </svg>
    </div>
  );
}
