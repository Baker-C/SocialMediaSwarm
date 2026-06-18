import '../../styles/sigil.css';

type SigilProps = {
  /** Rendered pixel size (square). */
  size?: number;
  /** Disable rotation/pulse (also auto-disabled under prefers-reduced-motion). */
  animated?: boolean;
  className?: string;
};

// 24 runic ticks evenly spaced around the rotating ring.
const TICKS = Array.from({ length: 24 }, (_, i) => i * 15);
// 6 nodes on the inner ring — the bound daemons of the Seal.
const NODES = Array.from({ length: 6 }, (_, i) => i * 60);

function polar(cx: number, cy: number, r: number, deg: number): [number, number] {
  const rad = (deg - 90) * (Math.PI / 180);
  return [cx + r * Math.cos(rad), cy + r * Math.sin(rad)];
}

/**
 * Solomon's Seal — an animated occult sigil. Two interlocked triangles
 * (the hexagram / Seal of Solomon) bound by counter-rotating runic rings.
 * The visual anchor of the brand.
 */
export function Sigil({ size = 240, animated = true, className = '' }: SigilProps) {
  const cls = `sigil ${animated ? 'sigil--animated' : ''} ${className}`.trim();
  return (
    <svg
      className={cls}
      width={size}
      height={size}
      viewBox="0 0 240 240"
      fill="none"
      role="img"
      aria-label="Solomon's Seal"
      xmlns="http://www.w3.org/2000/svg"
    >
      {/* faint outer halo */}
      <circle className="sigil-halo" cx="120" cy="120" r="116" />

      {/* outer ring */}
      <circle className="sigil-ring" cx="120" cy="120" r="112" />

      {/* rotating runic tick ring */}
      <g className="sigil-spin-slow">
        {TICKS.map((deg) => {
          const [x1, y1] = polar(120, 120, 100, deg);
          const [x2, y2] = polar(120, 120, deg % 45 === 0 ? 90 : 95, deg);
          return <line key={deg} className="sigil-tick" x1={x1} y1={y1} x2={x2} y2={y2} />;
        })}
      </g>

      {/* counter-rotating dashed ring */}
      <circle className="sigil-ring-dashed sigil-spin-rev" cx="120" cy="120" r="84" />

      {/* the Seal of Solomon — three interlocked triangles (ninefold star) */}
      <g className="sigil-seal sigil-breathe">
        {[0, 40, 80].map((deg) => (
          <polygon
            key={deg}
            className="sigil-tri"
            points="120,40 189,160 51,160"
            transform={`rotate(${deg} 120 120)`}
          />
        ))}
        <circle className="sigil-inner-ring" cx="120" cy="120" r="58" />
      </g>

      {/* six bound nodes on the inner ring */}
      <g className="sigil-spin-slow">
        {NODES.map((deg) => {
          const [cx, cy] = polar(120, 120, 58, deg);
          return <circle key={deg} className="sigil-node" cx={cx} cy={cy} r="3.5" />;
        })}
      </g>

      {/* pulsing core */}
      <circle className="sigil-core-glow sigil-pulse" cx="120" cy="120" r="20" />
      <circle className="sigil-core" cx="120" cy="120" r="7" />
    </svg>
  );
}
