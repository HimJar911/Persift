import { motion, useTransform, type MotionValue } from "framer-motion"
import { useSceneProgress } from "../scroll/SceneContext"
import { useIsMobile } from "../hooks/useIsMobile"
import { SurfaceFrame, WorkdaySurface, GreenhouseSurface } from "../components/Surfaces"

/* ---------- Card 1 · LinkedIn job search ---------- */

const LINKEDIN_JOBS = [
  { company: "Stripe", role: "Software Engineer Intern", loc: "San Francisco, CA", applicants: "1,284 applicants", easy: false },
  { company: "Figma", role: "Software Engineer Intern", loc: "San Francisco, CA", applicants: "892 applicants", easy: true },
  { company: "Notion", role: "Software Engineer Intern", loc: "New York, NY", applicants: "2,103 applicants", easy: false },
  { company: "Ramp", role: "Software Engineer Intern", loc: "New York, NY", applicants: "640 applicants", easy: false },
  { company: "Vercel", role: "Software Engineer Intern", loc: "Remote", applicants: "1,571 applicants", easy: false },
]

function LinkedInSurface() {
  return (
    <SurfaceFrame
      url="linkedin.com/jobs/search?keywords=software+engineer+intern"
      accent="#0a66c2"
      width={312}
    >
      <div style={{ display: "flex", flexDirection: "column", gap: 9 }}>
        <span style={{ fontSize: 11, fontWeight: 700, color: "#0a66c2" }}>1,284 results</span>
        {LINKEDIN_JOBS.map((j) => (
          <div key={j.company} style={{ display: "flex", gap: 9, alignItems: "flex-start" }}>
            <div
              style={{
                width: 28,
                height: 28,
                borderRadius: 5,
                background: "#eaf1f8",
                color: "#0a66c2",
                fontSize: 11,
                fontWeight: 700,
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                flexShrink: 0,
              }}
            >
              {j.company[0]}
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: 1, flex: 1, minWidth: 0 }}>
              <span style={{ fontSize: 11.5, fontWeight: 600, color: "#1c1a17" }}>{j.role}</span>
              <span style={{ fontSize: 10.5, color: "#3a4a40" }}>{j.company}</span>
              <span style={{ fontSize: 9.5, color: "#8a857d" }}>
                {j.loc} · {j.applicants}
              </span>
              {j.easy && (
                <span
                  style={{
                    marginTop: 2,
                    alignSelf: "flex-start",
                    fontSize: 9,
                    fontWeight: 600,
                    color: "#0a66c2",
                    background: "#e6f0fa",
                    borderRadius: 4,
                    padding: "1px 6px",
                  }}
                >
                  Easy Apply
                </span>
              )}
            </div>
          </div>
        ))}
      </div>
    </SurfaceFrame>
  )
}

/* ---------- Card 4 · Gmail inbox ---------- */

const GMAIL_ROWS = [
  { subject: "Update on your application — Software Engineer…", sender: "recruiting@company.com", time: "1:47 AM", red: true },
  { subject: "Thank you for applying to Figma", sender: "Figma Recruiting", time: "12:58 AM", red: false },
  { subject: "Your application has been received — Notion", sender: "Notion Careers", time: "12:21 AM", red: false },
  { subject: "Next steps for your Ramp application", sender: "Ramp Talent", time: "11:34 PM", red: false },
  { subject: "We've moved forward with other candidates…", sender: "no-reply@greenhouse.io", time: "11:09 PM", red: true },
]

function GmailSurface() {
  return (
    <SurfaceFrame url="mail.google.com/mail" accent="#ea4335" width={306}>
      <div style={{ display: "flex", flexDirection: "column" }}>
        {GMAIL_ROWS.map((r, i) => (
          <div
            key={i}
            style={{
              display: "flex",
              alignItems: "center",
              gap: 9,
              padding: "8px 6px",
              borderTop: i === 0 ? "none" : "1px solid #efece6",
              background: r.red ? "#fbeceb" : "transparent",
            }}
          >
            <span
              style={{
                width: 6,
                height: 6,
                borderRadius: "50%",
                background: r.red ? "#d6584a" : "#0a66c2",
                flexShrink: 0,
              }}
            />
            <div style={{ display: "flex", flexDirection: "column", gap: 1, flex: 1, minWidth: 0 }}>
              <span
                style={{
                  fontSize: 11,
                  fontWeight: 600,
                  color: r.red ? "#7a342c" : "#1c1a17",
                  whiteSpace: "nowrap",
                  overflow: "hidden",
                  textOverflow: "ellipsis",
                }}
              >
                {r.subject}
              </span>
              <span style={{ fontSize: 9.5, color: "#8a857d" }}>{r.sender}</span>
            </div>
            <span style={{ fontSize: 9, color: "#8a857d", flexShrink: 0 }}>{r.time}</span>
          </div>
        ))}
      </div>
    </SurfaceFrame>
  )
}

/* ---------- Card 5 · Google Sheets tracker ---------- */

const SHEET_ROWS = [
  { c: "Stripe", role: "SWE Intern", date: "Oct 12", status: "No response", tone: "grey" },
  { c: "Google", role: "SWE Intern", date: "Oct 14", status: "Rejected", tone: "red" },
  { c: "Amazon", role: "SDE Intern", date: "Oct 18", status: "OA Pending", tone: "amber" },
  { c: "Apple", role: "SE Intern", date: "Oct 22", status: "No response", tone: "grey" },
  { c: "Meta", role: "SWE Intern", date: "Oct 25", status: "No response", tone: "grey" },
  { c: "Figma", role: "Eng Intern", date: "Oct 28", status: "…", tone: "grey" },
]

const STATUS_COLOR: Record<string, string> = {
  red: "#c0564a",
  amber: "#b9852f",
  grey: "#8a857d",
}

function SheetSurface() {
  return (
    <SurfaceFrame url="docs.google.com/spreadsheets — Job Applications Fall 2024" accent="#1f8a52" width={320}>
      <div style={{ display: "flex", flexDirection: "column" }}>
        {/* header row */}
        <div style={{ display: "flex", borderBottom: "1.5px solid #d4cfc7", paddingBottom: 5, marginBottom: 3 }}>
          {["Company", "Role", "Date Applied", "Status"].map((h) => (
            <span key={h} style={{ flex: 1, fontSize: 9.5, fontWeight: 700, color: "#55504a" }}>
              {h}
            </span>
          ))}
        </div>
        {SHEET_ROWS.map((r, i) => (
          <div
            key={i}
            style={{
              display: "flex",
              alignItems: "center",
              padding: "5px 0",
              borderTop: i === 0 ? "none" : "1px solid #efece6",
            }}
          >
            <span style={{ flex: 1, fontSize: 10, color: "#2f2b26", fontWeight: 500 }}>{r.c}</span>
            <span style={{ flex: 1, fontSize: 10, color: "#55504a" }}>{r.role}</span>
            <span style={{ flex: 1, fontSize: 10, color: "#55504a" }}>{r.date}</span>
            <span style={{ flex: 1, fontSize: 10, fontWeight: 600, color: STATUS_COLOR[r.tone] }}>
              {r.status}
            </span>
          </div>
        ))}
      </div>
    </SurfaceFrame>
  )
}

/* ---------- a single positioned, rotated, parallaxed card ---------- */

function Stacked({
  children,
  x,
  y,
  rot,
  depth,
  p,
}: {
  children: React.ReactNode
  x: number
  y: number
  rot: number
  depth: number
  p: MotionValue<number>
}) {
  // each card drifts slightly inward as the scene progresses (parallax by depth)
  const ty = useTransform(p, [0, 1], [depth * 26, 0])
  const tx = useTransform(p, [0, 1], [depth * -14, 0])
  return (
    <motion.div
      style={{
        position: "absolute",
        left: `calc(50% + ${x}px)`,
        top: `calc(50% + ${y}px)`,
        x: tx,
        y: ty,
        rotate: rot,
        translateX: "-50%",
        translateY: "-50%",
      }}
    >
      {children}
    </motion.div>
  )
}

export function Scene1Chaos() {
  const p = useSceneProgress()
  const isMobile = useIsMobile()

  return (
    <div
      style={{
        position: "relative",
        width: "100%",
        height: "100%",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
      }}
    >
      {isMobile ? (
        // mobile: 3 cards, gentle rotation, scaled to stay fully on-screen
        <div style={{ position: "relative", width: "100%", height: 480, transform: "scale(0.62)" }}>
          <Stacked p={p} x={-58} y={-150} rot={-3} depth={2}>
            <LinkedInSurface />
          </Stacked>
          <Stacked p={p} x={66} y={10} rot={3} depth={1}>
            <GmailSurface />
          </Stacked>
          <Stacked p={p} x={-46} y={168} rot={-2} depth={2}>
            <SheetSurface />
          </Stacked>
        </div>
      ) : (
        // desktop: dense overlapping pile of surfaces
        <div style={{ position: "relative", width: 720, height: 520, transform: "scale(0.9)" }}>
          <Stacked p={p} x={-150} y={-70} rot={-7} depth={3}>
            <SheetSurface />
          </Stacked>
          <Stacked p={p} x={155} y={-95} rot={6} depth={3}>
            <LinkedInSurface />
          </Stacked>
          <Stacked p={p} x={175} y={95} rot={-4} depth={2}>
            <GreenhouseSurface />
          </Stacked>
          <Stacked p={p} x={-175} y={100} rot={5} depth={2}>
            <WorkdaySurface />
          </Stacked>
          <Stacked p={p} x={-5} y={5} rot={-2} depth={1}>
            <GmailSurface />
          </Stacked>
        </div>
      )}

      {/* a darkening vignette to push the eye inward */}
      <div
        style={{
          position: "absolute",
          inset: 0,
          background: "radial-gradient(120% 90% at 50% 50%, transparent 40%, rgba(7,5,4,0.85) 100%)",
          pointerEvents: "none",
        }}
      />
    </div>
  )
}
