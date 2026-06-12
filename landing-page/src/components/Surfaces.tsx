import { type ReactNode } from "react"

/* ---------- browser-window shell (shared across scenes) ---------- */

export function SurfaceFrame({
  url,
  accent,
  children,
  width,
}: {
  url: string
  accent: string
  children: ReactNode
  width: number | string
}) {
  return (
    <div
      style={{
        width,
        maxWidth: "90vw",
        borderRadius: 12,
        overflow: "hidden",
        background: "#fbfaf8",
        border: "1px solid rgba(0,0,0,0.12)",
        boxShadow: "0 24px 50px -20px rgba(0,0,0,0.7)",
        color: "#1c1a17",
        fontFamily: "var(--font-sans)",
      }}
    >
      {/* browser chrome */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: 8,
          padding: "8px 11px",
          background: "#ece9e4",
          borderBottom: "1px solid rgba(0,0,0,0.08)",
        }}
      >
        <span style={{ display: "flex", gap: 5 }}>
          <span style={{ width: 8, height: 8, borderRadius: "50%", background: "#e06c5b" }} />
          <span style={{ width: 8, height: 8, borderRadius: "50%", background: "#e3b14a" }} />
          <span style={{ width: 8, height: 8, borderRadius: "50%", background: "#7bb86f" }} />
        </span>
        <span
          style={{
            flex: 1,
            background: "#fbfaf8",
            border: "1px solid rgba(0,0,0,0.08)",
            borderRadius: 6,
            padding: "3px 9px",
            fontSize: 10,
            color: "#6a655e",
            whiteSpace: "nowrap",
            overflow: "hidden",
            textOverflow: "ellipsis",
            display: "flex",
            alignItems: "center",
            gap: 5,
          }}
        >
          <span style={{ width: 6, height: 6, borderRadius: "50%", background: accent, flexShrink: 0 }} />
          {url}
        </span>
      </div>
      <div style={{ padding: 12 }}>{children}</div>
    </div>
  )
}

/* ---------- Workday account wall ---------- */

function WorkdayField({ label }: { label: string }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 3 }}>
      <span style={{ fontSize: 9, color: "#6a655e", fontWeight: 500 }}>{label}</span>
      <div style={{ height: 24, borderRadius: 4, background: "#fff", border: "1px solid #d8d3ca" }} />
    </div>
  )
}

export function WorkdaySurface({ width = 262 }: { width?: number | string }) {
  return (
    <SurfaceFrame url="wd3.myworkdayjobs.com/Company/job/Apply" accent="#f59e0b" width={width}>
      <div style={{ display: "flex", flexDirection: "column", gap: 9 }}>
        <span style={{ fontSize: 9, color: "#0875e1", fontWeight: 600 }}>Step 3 of 7</span>
        <span style={{ fontSize: 14, fontWeight: 700, color: "#2f2b26" }}>Create an Account</span>
        <span style={{ fontSize: 10, color: "#6a655e", lineHeight: 1.4 }}>
          To continue your application for Software Engineer Intern, you need a Workday account.
        </span>
        <WorkdayField label="First Name" />
        <WorkdayField label="Last Name" />
        <WorkdayField label="Email" />
        <WorkdayField label="Password" />
        <div
          style={{
            marginTop: 2,
            height: 30,
            borderRadius: 5,
            background: "#0875e1",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            color: "#fff",
            fontSize: 11,
            fontWeight: 600,
          }}
        >
          Create Account &amp; Continue
        </div>
        <span style={{ fontSize: 9.5, color: "#6a655e", textAlign: "center" }}>
          Already have an account? <span style={{ color: "#0875e1" }}>Sign in.</span>
        </span>
      </div>
    </SurfaceFrame>
  )
}

/* ---------- Greenhouse application form (static) ---------- */

function GreenhouseField({ label, value, empty }: { label: string; value?: string; empty?: boolean }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 3 }}>
      <span style={{ fontSize: 9, color: "#3a4a40", fontWeight: 500 }}>{label}</span>
      <div
        style={{
          height: 24,
          borderRadius: 4,
          background: "#fff",
          border: "1px solid #cdd9d0",
          display: "flex",
          alignItems: "center",
          padding: "0 8px",
          fontSize: 10,
          color: empty ? "#b3aea6" : "#2f3a33",
        }}
      >
        {value ?? ""}
      </div>
    </div>
  )
}

export function GreenhouseSurface({ width = 268 }: { width?: number | string }) {
  return (
    <SurfaceFrame url="boards.greenhouse.io/company/jobs/apply" accent="#3aa76d" width={width}>
      <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
        <span style={{ fontSize: 11.5, fontWeight: 700, color: "#2f3a33" }}>Apply for this job</span>
        <GreenhouseField label="Name" value="Jordan Reyes" />
        <GreenhouseField label="Email" value="jordan.reyes@berkeley.edu" />
        <GreenhouseField label="Phone" empty />
        <div style={{ display: "flex", flexDirection: "column", gap: 3 }}>
          <span style={{ fontSize: 9, color: "#3a4a40", fontWeight: 500 }}>Resume</span>
          <div
            style={{
              height: 24,
              borderRadius: 4,
              background: "#eef5f0",
              border: "1px solid #cdd9d0",
              display: "flex",
              alignItems: "center",
              gap: 6,
              padding: "0 8px",
              fontSize: 10,
              color: "#2f3a33",
            }}
          >
            <span style={{ width: 7, height: 7, borderRadius: 2, background: "#3aa76d" }} />
            resume_v12_final.pdf
          </div>
        </div>
        <GreenhouseField label="LinkedIn URL" value="linkedin.com/in/jordanreyes" />
        <div style={{ display: "flex", flexDirection: "column", gap: 3 }}>
          <span style={{ fontSize: 9, color: "#3a4a40", fontWeight: 500 }}>How did you hear about us?</span>
          <div
            style={{
              height: 24,
              borderRadius: 4,
              background: "#fff",
              border: "1px solid #cdd9d0",
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
              padding: "0 8px",
              fontSize: 10,
              color: "#b3aea6",
            }}
          >
            Select an option
            <span style={{ color: "#9aa39c" }}>▾</span>
          </div>
        </div>
        <div
          style={{
            marginTop: 2,
            height: 30,
            borderRadius: 5,
            background: "#3aa76d",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            color: "#fff",
            fontSize: 11,
            fontWeight: 600,
          }}
        >
          Submit Application
        </div>
      </div>
    </SurfaceFrame>
  )
}
