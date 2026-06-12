export function SceneBridge() {
  return (
    <div style={{
      width: "100%",
      height: "100%",
      display: "flex",
      flexDirection: "column",
      alignItems: "center",
      justifyContent: "center",
      padding: "0 24px",
      gap: 32,
    }}>
      <div style={{ textAlign: "center", display: "flex", flexDirection: "column", gap: 16, maxWidth: 640 }}>
        <h2 style={{
          margin: 0,
          fontFamily: "'Plus Jakarta Sans', sans-serif",
          fontWeight: 800,
          fontSize: "clamp(36px, 6vw, 68px)",
          letterSpacing: "-0.03em",
          lineHeight: 1.05,
          color: "var(--ink)",
        }}>
          Meet Persift.
        </h2>
        <p style={{
          margin: 0,
          fontFamily: "Inter, sans-serif",
          fontWeight: 400,
          fontSize: "clamp(15px, 1.5vw, 19px)",
          color: "var(--ink-soft)",
          lineHeight: 1.6,
        }}>
          Finds early-career roles, tailors your resume to each one, and submits applications — all on its own.
        </p>
      </div>

      <div style={{
        display: "flex",
        gap: 12,
        flexWrap: "wrap",
        justifyContent: "center",
      }}>
        {[
          "Finds roles before they hit LinkedIn",
          "Tailors your resume per company",
          "Tracks every application automatically",
        ].map((item) => (
          <span key={item} style={{
            fontSize: 13,
            fontWeight: 500,
            color: "var(--amber-soft)",
            background: "rgba(240,163,65,0.08)",
            border: "1px solid rgba(240,163,65,0.2)",
            borderRadius: 999,
            padding: "6px 14px",
          }}>
            {item}
          </span>
        ))}
      </div>
    </div>
  )
}
