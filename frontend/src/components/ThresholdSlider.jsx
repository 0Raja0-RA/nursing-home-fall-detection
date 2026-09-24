/**
 * ThresholdSlider.jsx
 * ===================
 * Slider input untuk mengatur threshold durasi (detik).
 * Menampilkan nilai saat ini secara real-time.
 */

export default function ThresholdSlider({
  value,
  onChange,
  min = 1,
  max = 60,
  unit = "s",
}) {
  return (
    <div className="slider-container">
      <div style={{
        display: "flex",
        justifyContent: "space-between",
        alignItems: "baseline",
      }}>
        <label>Durasi Threshold</label>
        <span style={{
          fontSize: "var(--font-size-xl)",
          fontWeight: 700,
          color: "var(--color-primary)",
        }}>
          {value} <span style={{ fontSize: "var(--font-size-sm)", fontWeight: 400 }}>{unit}</span>
        </span>
      </div>

      <input
        type="range"
        min={min}
        max={max}
        step={1}
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
      />

      <div style={{
        display: "flex",
        justifyContent: "space-between",
        fontSize: "var(--font-size-xs)",
        color: "var(--color-text-subtle)",
      }}>
        <span>{min}{unit}</span>
        <span>{max}{unit}</span>
      </div>
    </div>
  );
}
