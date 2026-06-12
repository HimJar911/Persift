import { useState, useEffect, useRef } from "react"
import { motion, AnimatePresence } from "framer-motion"

// ─── Logos ────────────────────────────────────────────────────────────────────

function RampLogo({ size = 14 }: { size?: number }) {
  return (
    <svg width={size * 3.2} height={size} viewBox="0 0 64 20" fill="none">
      <text x="0" y="16" fontSize="18" fontWeight="700" fill="#2d2926" fontFamily="Arial, sans-serif">ramp</text>
      <path d="M54 14 Q58 8 64 10" stroke="#2d2926" strokeWidth="2.5" fill="none" strokeLinecap="round"/>
    </svg>
  )
}

function DoorDashLogo({ size = 14 }: { size?: number }) {
  return (
    <svg width={size * 1.4} height={size} viewBox="0 0 28 20" fill="none">
      <path d="M4 2 C4 2 20 2 22 2 C26 2 28 6 28 10 C28 14 26 18 22 18 L14 18 L14 14 L20 14 C22 14 23 12.5 23 10 C23 7.5 22 6 20 6 L8 6 Z" fill="#FF3008"/>
    </svg>
  )
}

function ShieldAILogo({ size = 14 }: { size?: number }) {
  return (
    <svg width={size * 4} height={size} viewBox="0 0 80 20" fill="none">
      <rect x="0" y="2" width="14" height="14" rx="2" fill="#1a1a1a" opacity="0.15"/>
      <path d="M3 4 L7 2 L11 4 L11 10 C11 13 7 16 7 16 C7 16 3 13 3 10 Z" fill="#1a1a1a"/>
      <text x="18" y="15" fontSize="13" fontWeight="700" fill="#1a1a1a" fontFamily="Arial, sans-serif">Shield AI</text>
    </svg>
  )
}

// ─── Data ─────────────────────────────────────────────────────────────────────

type ATS = "greenhouse" | "lever" | "ashby"
type Phase = "spotlight" | "sliding" | "filling" | "clicking" | "submitted" | "gmail" | "closing"

const JANE = {
  firstName: "Jane",
  lastName: "Doe",
  fullName: "Jane Doe",
  email: "jane.doe@example.com",
  phone: "(555) 867-5309",
  location: "Seattle, WA",
  linkedin: "linkedin.com/in/janedoe",
  website: "janedoe.dev",
  company: "Doe Labs",
  school: "University of Washington",
  degree: "B.S. Computer Science",
  resume: "Jane_Doe_Resume.pdf",
  essay: "Recently I built a tool that automatically tracks internship applications across multiple job boards and organizes them into a single dashboard...",
  whyUs: "I am drawn to organizations that solve technically challenging problems with real-world impact...",
}

const JOBS = [
  {
    company: "Ramp",
    role: "Software Engineer, AI Forward Deployed",
    ats: "ashby" as ATS,
    url: "jobs.ashbyhq.com/ramp/ai-forward-deployed",
    logoBg: "#f5f0eb",
    logoColor: "#2d2926",
    location: "San Francisco, CA",
    match: 91,
    seconds: 38,
  },
  {
    company: "DoorDash",
    role: "Principal Software Engineer, Ads",
    ats: "greenhouse" as ATS,
    url: "job-boards.greenhouse.io/doordash/jobs/5521",
    logoBg: "#fff1f0",
    logoColor: "#FF3008",
    location: "New York, NY",
    match: 88,
    seconds: 41,
  },
  {
    company: "Shield AI",
    role: "Product Manager, AI Platforms",
    ats: "lever" as ATS,
    url: "jobs.lever.co/shieldai/r4991",
    logoBg: "#f0f2f5",
    logoColor: "#1a1a1a",
    location: "San Diego, CA",
    match: 94,
    seconds: 35,
  },
]

type Job = typeof JOBS[0]

const PHASE_MS = {
  spotlight: 1800,
  sliding:   500,
  filling:   2800,
  clicking:  400,
  submitted: 1000,
  gmail:     1000,
  closing:   500,
}

const APPLIED_BASE = 17

// ─── Field component ──────────────────────────────────────────────────────────

function Field({
  label, value, filled, required, type = "text", wide = false,
}: {
  label: string; value: string; filled: boolean; required?: boolean; type?: string; wide?: boolean
}) {
  return (
    <div style={{ marginBottom: 7 }}>
      <div style={{ fontSize: 7.5, color: "#555", marginBottom: 2, fontWeight: 500 }}>
        {label}{required && <span style={{ color: "#e53e3e" }}> *</span>}
      </div>
      <div style={{
        minHeight: wide ? 36 : 20,
        border: `1px solid ${filled ? "#5fd07f" : "#d0d0d0"}`,
        borderRadius: 3,
        background: filled ? "rgba(95,208,127,0.06)" : "#fafafa",
        fontSize: 8.5,
        color: "#1a1a1a",
        padding: wide ? "4px 7px" : "0 7px",
        display: "flex",
        alignItems: wide ? "flex-start" : "center",
        transition: "border-color 0.3s, background 0.3s",
        overflow: "hidden",
        lineHeight: 1.5,
      }}>
        {filled ? (
          <motion.span initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ duration: 0.3 }}>
            {value}
          </motion.span>
        ) : (
          <span style={{ color: "#bbb", fontStyle: "italic", fontSize: 8 }}>{type === "select" ? "Select…" : ""}</span>
        )}
      </div>
    </div>
  )
}

function SectionHead({ text }: { text: string }) {
  return <div style={{ fontSize: 8, fontWeight: 700, color: "#333", textTransform: "uppercase", letterSpacing: "0.07em", marginTop: 12, marginBottom: 6, paddingTop: 8, borderTop: "1px solid #eee" }}>{text}</div>
}

// ─── ATS Forms ────────────────────────────────────────────────────────────────

function AshbyForm({ job, filledCount, isClicking }: { job: Job; filledCount: number; isClicking: boolean }) {
  const f = (n: number) => filledCount >= n
  return (
    <div style={{ background: "#fff", fontFamily: "'Inter', sans-serif", padding: "14px 16px 40px" }}>
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 10 }}>
        <div style={{ width: 28, height: 28, borderRadius: 6, background: job.logoBg, display: "flex", alignItems: "center", justifyContent: "center" }}>
          <RampLogo size={10} />
        </div>
        <div>
          <div style={{ fontSize: 11, fontWeight: 700, color: "#000" }}>{job.role}</div>
          <div style={{ fontSize: 8, color: "#888" }}>{job.location} · Hybrid · Full Time</div>
        </div>
      </div>
      <div style={{ display: "flex", borderBottom: "1px solid #e5e5e5", marginBottom: 10 }}>
        {["Overview", "Application"].map((t, i) => (
          <div key={t} style={{ fontSize: 8.5, padding: "5px 10px", color: i === 1 ? "#000" : "#888", borderBottom: i === 1 ? "2px solid #000" : "2px solid transparent", fontWeight: i === 1 ? 600 : 400 }}>{t}</div>
        ))}
      </div>
      <div style={{ background: "#f5f5f5", borderRadius: 4, padding: "6px 10px", marginBottom: 10, display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <span style={{ fontSize: 7.5, color: "#555" }}>✦ Autofill from resume</span>
        <div style={{ background: f(1) ? "#5fd07f" : "#fff", border: "1px solid #ddd", borderRadius: 3, padding: "2px 7px", fontSize: 7.5, color: f(1) ? "#fff" : "#333", transition: "all 0.3s" }}>{f(1) ? "✓ Uploaded" : "Upload file"}</div>
      </div>
      <div style={{ fontSize: 8.5, fontWeight: 700, color: "#000", marginBottom: 8 }}>Basic Details</div>
      <Field label="Legal Name" value={JANE.fullName} filled={f(2)} required />
      <Field label="Email" value={JANE.email} filled={f(3)} required />
      <Field label="Phone" value={JANE.phone} filled={f(4)} />
      <Field label="LinkedIn Profile" value={JANE.linkedin} filled={f(5)} />
      <Field label="Personal Website" value={JANE.website} filled={f(6)} />
      <SectionHead text="Work Authorization" />
      <Field label="Authorized to work in the U.S.?" value="Yes" filled={f(7)} type="select" />
      <Field label="Require sponsorship?" value="No" filled={f(8)} type="select" />
      <Field label="Country of Residence" value="United States" filled={f(9)} type="select" />
      <SectionHead text="Short Answer" />
      <Field label="What's something you've built recently?" value={JANE.essay} filled={f(10)} wide required />
      <Field label="Why are you interested in our mission?" value={JANE.whyUs} filled={f(11)} wide />
      <motion.div
        animate={{ background: isClicking ? ["#1a1a1a", "#fff", "#1a1a1a"] : "#1a1a1a" }}
        transition={{ duration: 0.5, times: [0, 0.3, 1] }}
        style={{ marginTop: 12, height: 24, borderRadius: 4, display: "flex", alignItems: "center", justifyContent: "center" }}
      >
        <motion.span
          animate={{ color: isClicking ? ["#fff", "#1a1a1a", "#fff"] : "#fff" }}
          transition={{ duration: 0.5, times: [0, 0.3, 1] }}
          style={{ fontSize: 9, fontWeight: 600 }}
        >Submit Application</motion.span>
      </motion.div>
    </div>
  )
}

function GreenhouseForm({ job, filledCount, isClicking }: { job: Job; filledCount: number; isClicking: boolean }) {
  const f = (n: number) => filledCount >= n
  return (
    <div style={{ background: "#fff", fontFamily: "'Inter', sans-serif", padding: "14px 16px 40px" }}>
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 6 }}>
        <div style={{ width: 28, height: 28, borderRadius: 6, background: job.logoBg, display: "flex", alignItems: "center", justifyContent: "center" }}>
          <DoorDashLogo size={16} />
        </div>
        <div style={{ fontSize: 11, fontWeight: 700, color: "#000" }}>{job.company}</div>
      </div>
      <div style={{ fontSize: 10, fontWeight: 700, color: "#1a1a1a", marginBottom: 2 }}>{job.role}</div>
      <div style={{ fontSize: 8, color: "#888", marginBottom: 10 }}>{job.location}</div>
      <div style={{ fontSize: 9, fontWeight: 700, color: "#333", textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: 6 }}>Submit Your Application</div>
      <div style={{ fontSize: 7.5, color: "#888", marginBottom: 8 }}>* indicates required field</div>
      <Field label="First Name" value={JANE.firstName} filled={f(1)} required />
      <Field label="Last Name" value={JANE.lastName} filled={f(2)} required />
      <Field label="Email" value={JANE.email} filled={f(3)} required />
      <Field label="Phone" value={JANE.phone} filled={f(4)} />
      <Field label="Location (City)" value={JANE.location} filled={f(5)} />
      <div style={{ marginBottom: 7 }}>
        <div style={{ fontSize: 7.5, color: "#555", marginBottom: 2, fontWeight: 500 }}>Resume/CV <span style={{ color: "#e53e3e" }}>*</span></div>
        {f(6) ? (
          <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} style={{ border: "1px solid #5fd07f", borderRadius: 3, background: "rgba(95,208,127,0.06)", padding: "4px 7px", fontSize: 8, color: "#1a1a1a" }}>
            📄 {JANE.resume}
          </motion.div>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: 3 }}>
            {["Attach", "Dropbox", "Google Drive"].map(b => (
              <div key={b} style={{ border: "1px solid #ccc", borderRadius: 14, padding: "3px 8px", fontSize: 7.5, color: "#555", textAlign: "center" }}>{b}</div>
            ))}
          </div>
        )}
      </div>
      <Field label="LinkedIn Profile" value={JANE.linkedin} filled={f(7)} required />
      <SectionHead text="Education" />
      <Field label="School" value={JANE.school} filled={f(8)} type="select" />
      <Field label="Degree" value={JANE.degree} filled={f(9)} type="select" />
      <SectionHead text="Work Authorization" />
      <Field label="Authorized to work in the U.S.?" value="Yes" filled={f(10)} type="select" required />
      <Field label="Require sponsorship?" value="No" filled={f(11)} type="select" required />
      <SectionHead text="Self-Identification (Voluntary)" />
      <Field label="Gender" value="Woman" filled={f(12)} type="select" />
      <Field label="Race/Ethnicity" value="White (Not Hispanic or Latino)" filled={f(12)} type="select" />
      <motion.div
        animate={{ background: isClicking ? ["#1a1a1a", "#fff", "#1a1a1a"] : "#1a1a1a" }}
        transition={{ duration: 0.5, times: [0, 0.3, 1] }}
        style={{ marginTop: 12, height: 24, borderRadius: 3, border: "1px solid #1a1a1a", display: "flex", alignItems: "center", justifyContent: "center" }}
      >
        <motion.span
          animate={{ color: isClicking ? ["#fff", "#1a1a1a", "#fff"] : "#fff" }}
          transition={{ duration: 0.5, times: [0, 0.3, 1] }}
          style={{ fontSize: 9, fontWeight: 600 }}
        >Submit Application</motion.span>
      </motion.div>
    </div>
  )
}

function RadioField({ label, value, filled, required }: { label: string; value: string; filled: boolean; required?: boolean }) {
  const options = label.includes("Export") ? ["A United States Citizen", "Lawful permanent resident", "A protected individual", "Other"] : ["Yes", "No"]
  return (
    <div style={{ display: "flex", marginBottom: 16, gap: 10 }}>
      <div style={{ width: "38%", fontSize: 8, color: "#4a4a4a", flexShrink: 0, textAlign: "right", paddingTop: 1 }}>
        {label}{required && <span style={{ color: "#e05c3a" }}> *</span>}
      </div>
      <div style={{ flex: 1, display: "flex", flexDirection: "column", gap: 5 }}>
        {options.map(opt => (
          <div key={opt} style={{ display: "flex", alignItems: "center", gap: 7 }}>
            <div style={{
              width: 11, height: 11, borderRadius: "50%",
              border: `1.5px solid ${filled && opt === value ? "#5fd07f" : "#bbb"}`,
              background: filled && opt === value ? "#5fd07f" : "transparent",
              flexShrink: 0, transition: "all 0.3s",
            }} />
            <span style={{ fontSize: 8, color: filled && opt === value ? "#111" : "#888" }}>{opt}</span>
          </div>
        ))}
      </div>
    </div>
  )
}

function LeverSectionHead({ text }: { text: string }) {
  return (
    <div style={{
      fontSize: 7, fontWeight: 700, color: "#666",
      textTransform: "uppercase", letterSpacing: "0.12em",
      marginTop: 18, marginBottom: 14,
      paddingTop: 14, borderTop: "1px solid #e8e8e8",
      paddingLeft: "calc(38% + 10px)",
    }}>{text}</div>
  )
}

function LeverField({ label, value, filled, required }: { label: string; value: string; filled: boolean; required?: boolean }) {
  return (
    <div style={{ display: "flex", alignItems: "center", marginBottom: 16, gap: 10 }}>
      <div style={{ width: "38%", fontSize: 8, color: "#4a4a4a", flexShrink: 0, textAlign: "right" }}>
        {label}{required && <span style={{ color: "#e05c3a" }}> *</span>}
      </div>
      <div style={{
        flex: 1, height: 22, border: `1px solid ${filled ? "#5fd07f" : "#ccc"}`,
        borderRadius: 2, background: filled ? "rgba(95,208,127,0.04)" : "#fff",
        fontSize: 8.5, color: "#111", padding: "0 8px",
        display: "flex", alignItems: "center",
        transition: "border-color 0.3s, background 0.3s",
      }}>
        {filled && <motion.span initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ duration: 0.25 }}>{value}</motion.span>}
      </div>
    </div>
  )
}

function LeverForm({ job, filledCount, isClicking }: { job: Job; filledCount: number; isClicking: boolean }) {
  const f = (n: number) => filledCount >= n
  return (
    <div style={{ background: "#f4f4f4", fontFamily: "'Inter', sans-serif" }}>
      <div style={{ background: "#fff", padding: "14px 20px", borderBottom: "1px solid #eee", display: "flex", alignItems: "center", gap: 8 }}>
        <svg viewBox="0 0 18 20" width="14" height="16" fill="none">
          <path d="M9 0L0 3.6V10.8C0 15.84 3.96 20 9 20C14.04 20 18 15.84 18 10.8V3.6L9 0Z" fill="#1a1a1a" opacity="0.15"/>
          <path d="M9 1.5L1.5 4.5V10.8C1.5 15 5.1 18.5 9 18.5C12.9 18.5 16.5 15 16.5 10.8V4.5L9 1.5Z" fill="#1a1a1a" opacity="0.5"/>
          <path d="M9 3L3 5.7V10.8C3 14.1 5.7 17 9 17C12.3 17 15 14.1 15 10.8V5.7L9 3Z" fill="#1a1a1a"/>
        </svg>
        <span style={{ fontSize: 11, fontWeight: 600, color: "#1a1a1a", letterSpacing: "-0.01em" }}>Shield AI</span>
      </div>
      <div style={{ padding: "20px 20px 40px" }}>
        <div style={{ marginBottom: 20 }}>
          <div style={{ fontSize: 13, fontWeight: 600, color: "#1a1a1a", marginBottom: 4 }}>{job.role}</div>
          <div style={{ fontSize: 8.5, color: "#888" }}>{job.location} · Full Time · On-Site</div>
        </div>
        <LeverSectionHead text="Submit Your Application" />
        <div style={{ display: "flex", alignItems: "center", marginBottom: 16, gap: 10 }}>
          <div style={{ width: "38%", fontSize: 8, color: "#4a4a4a", flexShrink: 0, textAlign: "right" }}>LinkedIn profile</div>
          <div style={{ flex: 1 }}>
            {f(1) ? (
              <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} style={{ fontSize: 8, color: "#5fd07f", fontWeight: 600 }}>✓ {JANE.linkedin}</motion.div>
            ) : (
              <div style={{ background: "#0a66c2", borderRadius: 20, padding: "5px 10px", display: "inline-flex", alignItems: "center", gap: 5 }}>
                <svg viewBox="0 0 16 16" width="8" height="8" fill="#fff"><path d="M0 1.146C0 .513.526 0 1.175 0h13.65C15.474 0 16 .513 16 1.146v13.708c0 .633-.526 1.146-1.175 1.146H1.175C.526 16 0 15.487 0 14.854V1.146zm4.943 12.248V6.169H2.542v7.225h2.401zm-1.2-8.212c.837 0 1.358-.554 1.358-1.248-.015-.709-.52-1.248-1.342-1.248-.822 0-1.359.54-1.359 1.248 0 .694.521 1.248 1.327 1.248h.016zm4.908 8.212V9.359c0-.216.016-.432.08-.586.173-.431.568-.878 1.232-.878.869 0 1.216.662 1.216 1.634v3.865h2.401V9.25c0-2.22-1.184-3.252-2.764-3.252-1.274 0-1.845.7-2.165 1.193v.025h-.016a5.54 5.54 0 0 1 .016-.025V6.169h-2.4c.03.678 0 7.225 0 7.225h2.4z"/></svg>
                <span style={{ fontSize: 8, color: "#fff", fontWeight: 600 }}>Apply with LinkedIn</span>
              </div>
            )}
          </div>
        </div>
        <div style={{ display: "flex", alignItems: "center", marginBottom: 16, gap: 10 }}>
          <div style={{ width: "38%", fontSize: 8, color: "#4a4a4a", flexShrink: 0, textAlign: "right" }}>Resume/CV <span style={{ color: "#e05c3a" }}>*</span></div>
          <div style={{ flex: 1 }}>
            {f(2) ? (
              <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} style={{ border: "1px solid #5fd07f", borderRadius: 3, background: "rgba(95,208,127,0.05)", padding: "5px 8px", fontSize: 8, color: "#1a1a1a", display: "inline-flex", alignItems: "center", gap: 4 }}>
                📄 {JANE.resume}
              </motion.div>
            ) : (
              <div style={{ display: "inline-flex", alignItems: "center", gap: 5, background: "#e8e8e8", borderRadius: 3, padding: "5px 10px" }}>
                <span style={{ fontSize: 9, color: "#555" }}>📎</span>
                <span style={{ fontSize: 8, color: "#555", textTransform: "uppercase", letterSpacing: "0.08em", fontWeight: 600 }}>Attach Resume/CV</span>
              </div>
            )}
          </div>
        </div>
        <LeverField label="Full name" value={JANE.fullName} filled={f(3)} required />
        <LeverField label="Email" value={JANE.email} filled={f(4)} required />
        <LeverField label="Phone" value={JANE.phone} filled={f(5)} />
        <LeverField label="Current location" value={JANE.location} filled={f(6)} />
        <LeverSectionHead text="Links" />
        <LeverField label="LinkedIn URL" value={JANE.linkedin} filled={f(7)} />
        <LeverField label="GitHub URL" value="github.com/janedoe" filled={f(8)} />
        <LeverSectionHead text="Compliance with Work Authorization" />
        <RadioField label="Are you authorized to work in the United States?" value="Yes" filled={f(9)} required />
        <RadioField label="Will you require sponsorship?" value="No" filled={f(10)} required />
        <LeverSectionHead text="Export Control Requirements" />
        <RadioField label="Export control eligibility" value="A United States Citizen" filled={f(11)} required />
        <LeverSectionHead text="U.S. Equal Employment Opportunity" />
        <div style={{ fontSize: 7.5, color: "#888", lineHeight: 1.5, marginBottom: 10, paddingLeft: "calc(38% + 10px)" }}>Completion is voluntary.</div>
        <div style={{ display: "flex", alignItems: "center", marginBottom: 16, gap: 10 }}>
          <div style={{ width: "38%", fontSize: 8, color: "#4a4a4a", flexShrink: 0, textAlign: "right" }}>Gender</div>
          <div style={{ flex: 1, height: 22, border: `1px solid ${f(12) ? "#5fd07f" : "#ddd"}`, borderRadius: 2, background: f(12) ? "rgba(95,208,127,0.04)" : "#fff", fontSize: 8.5, color: "#111", padding: "0 8px", display: "flex", alignItems: "center", justifyContent: "space-between", transition: "all 0.3s" }}>
            {f(12) ? <motion.span initial={{ opacity: 0 }} animate={{ opacity: 1 }}>Woman</motion.span> : <span style={{ color: "#aaa" }}>Select...</span>}
            <span style={{ color: "#999", fontSize: 9 }}>▾</span>
          </div>
        </div>
        <div style={{ display: "flex", alignItems: "center", marginBottom: 20, gap: 10 }}>
          <div style={{ width: "38%", fontSize: 8, color: "#4a4a4a", flexShrink: 0, textAlign: "right" }}>Race</div>
          <div style={{ flex: 1, height: 22, border: `1px solid ${f(12) ? "#5fd07f" : "#ddd"}`, borderRadius: 2, background: f(12) ? "rgba(95,208,127,0.04)" : "#fff", fontSize: 8.5, color: "#111", padding: "0 8px", display: "flex", alignItems: "center", justifyContent: "space-between", transition: "all 0.3s" }}>
            {f(12) ? <motion.span initial={{ opacity: 0 }} animate={{ opacity: 1 }}>White (Not Hispanic or Latino)</motion.span> : <span style={{ color: "#aaa" }}>Select...</span>}
            <span style={{ color: "#999", fontSize: 9 }}>▾</span>
          </div>
        </div>
        <div style={{ display: "flex", gap: 10 }}>
          <div style={{ width: "38%", flexShrink: 0 }} />
          <div style={{ flex: 1 }}>
            <motion.div
              animate={{ background: isClicking ? ["#111", "#fff", "#111"] : "#111" }}
              transition={{ duration: 0.5, times: [0, 0.3, 1] }}
              style={{ height: 28, borderRadius: 3, border: "1px solid #111", display: "flex", alignItems: "center", justifyContent: "center" }}
            >
              <motion.span
                animate={{ color: isClicking ? ["#fff", "#111", "#fff"] : "#fff" }}
                transition={{ duration: 0.5, times: [0, 0.3, 1] }}
                style={{ fontSize: 9, fontWeight: 500 }}
              >Submit application</motion.span>
            </motion.div>
            <div style={{ marginTop: 10, fontSize: 7, color: "#bbb", textAlign: "center" }}>Jobs powered by Lever</div>
          </div>
        </div>
      </div>
    </div>
  )
}

// ─── Confirmation screens ─────────────────────────────────────────────────────

function AshbyConfirm({ job }: { job: Job }) {
  return (
    <div style={{ background: "#fff", height: "100%", display: "flex", alignItems: "center", justifyContent: "center", fontFamily: "'Inter', sans-serif" }}>
      <div style={{ textAlign: "center", padding: "0 24px" }}>
        <div style={{ fontSize: 24, marginBottom: 8 }}>🎉</div>
        <div style={{ fontSize: 11, fontWeight: 700, color: "#000", marginBottom: 4 }}>Application received</div>
        <div style={{ fontSize: 8.5, color: "#666", lineHeight: 1.5 }}>{job.company} will review your application for <strong>{job.role}</strong> and reach out if interested.</div>
      </div>
    </div>
  )
}

function GreenhouseConfirm({ job }: { job: Job }) {
  return (
    <div style={{ background: "#fff", height: "100%", display: "flex", alignItems: "center", justifyContent: "center", fontFamily: "'Inter', sans-serif" }}>
      <div style={{ textAlign: "center", padding: "0 24px" }}>
        <div style={{ width: 32, height: 32, borderRadius: "50%", background: "#e8f5e9", display: "flex", alignItems: "center", justifyContent: "center", margin: "0 auto 10px" }}>
          <span style={{ fontSize: 16, color: "#4caf50" }}>✓</span>
        </div>
        <div style={{ fontSize: 11, fontWeight: 700, color: "#1a1a1a", marginBottom: 4 }}>Application submitted</div>
        <div style={{ fontSize: 8.5, color: "#666", lineHeight: 1.5 }}>Your application for <strong>{job.role}</strong> at <strong>{job.company}</strong> has been received.</div>
      </div>
    </div>
  )
}

function LeverConfirm({ job }: { job: Job }) {
  return (
    <div style={{ background: "#fff", height: "100%", display: "flex", alignItems: "center", justifyContent: "center", fontFamily: "'Inter', sans-serif" }}>
      <div style={{ textAlign: "center", padding: "0 24px" }}>
        <div style={{ fontSize: 11, fontWeight: 700, color: "#000", marginBottom: 4 }}>Thanks for applying to {job.company}!</div>
        <div style={{ fontSize: 8.5, color: "#666", lineHeight: 1.5 }}>We've received your application for {job.role}. We'll be in touch if there's a match.</div>
      </div>
    </div>
  )
}

// ─── Browser page ─────────────────────────────────────────────────────────────

export function BrowserPage({ job, phase, scrollY, filledCount }: { job: Job; phase: Phase; scrollY: number; filledCount: number }) {
  const isSubmitted = phase === "submitted" || phase === "gmail"
  const isClicking = phase === "clicking"
  const formVisible = phase !== "spotlight"

  return (
    <div style={{ position: "absolute", inset: 0, display: "flex", flexDirection: "column", background: "#0c0a08" }}>
      {/* Address bar — fades in with form */}
      <motion.div
        animate={{ opacity: formVisible ? 1 : 0 }}
        transition={{ duration: 0.5 }}
        style={{ height: 28, background: "#f1f3f4", borderBottom: "1px solid #dadce0", display: "flex", alignItems: "center", gap: 5, padding: "0 10px", flexShrink: 0 }}
      >
        {["←", "→", "↺"].map(s => <span key={s} style={{ fontSize: 10, color: "#aaa" }}>{s}</span>)}
        <div style={{ flex: 1, height: 20, background: "#fff", border: "1px solid #dadce0", borderRadius: 10, display: "flex", alignItems: "center", gap: 4, padding: "0 8px" }}>
          <span style={{ fontSize: 8, color: "#188038" }}>🔒</span>
          <span style={{ fontSize: 8, color: "#444" }}>{job.url}</span>
        </div>
        <div style={{ width: 16, height: 16, borderRadius: "50%", background: "#4285f4", display: "flex", alignItems: "center", justifyContent: "center" }}>
          <span style={{ fontSize: 7, color: "#fff", fontWeight: 700 }}>J</span>
        </div>
      </motion.div>

      {/* Page */}
      <div style={{ flex: 1, position: "relative", overflow: "hidden" }}>
        <AnimatePresence mode="wait">
          {isSubmitted ? (
            <motion.div key="confirm" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} transition={{ duration: 0.35 }} style={{ position: "absolute", inset: 0 }}>
              {job.ats === "ashby" && <AshbyConfirm job={job} />}
              {job.ats === "greenhouse" && <GreenhouseConfirm job={job} />}
              {job.ats === "lever" && <LeverConfirm job={job} />}
            </motion.div>
          ) : (
            <motion.div
              key="form"
              initial={{ opacity: 0 }}
              animate={{ opacity: formVisible ? 1 : 0 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.5 }}
              style={{ position: "absolute", inset: 0 }}
            >
              <div style={{ position: "absolute", top: 0, left: 0, right: 0, transform: `translateY(${-scrollY}px)`, transition: "transform 0.12s linear" }}>
                {job.ats === "ashby" && <AshbyForm job={job} filledCount={filledCount} isClicking={isClicking} />}
                {job.ats === "greenhouse" && <GreenhouseForm job={job} filledCount={filledCount} isClicking={isClicking} />}
                {job.ats === "lever" && <LeverForm job={job} filledCount={filledCount} isClicking={isClicking} />}
              </div>

              {/* Blur overlay during filling */}
              <AnimatePresence>
                {(phase === "filling" || phase === "clicking") && (
                  <motion.div
                    key="blur"
                    initial={{ backdropFilter: "blur(0px)", background: "rgba(0,0,0,0)" }}
                    animate={{ backdropFilter: "blur(6px)", background: "rgba(12,10,8,0.4)" }}
                    exit={{ backdropFilter: "blur(0px)", background: "rgba(0,0,0,0)" }}
                    transition={{ duration: 0.5 }}
                    style={{ position: "absolute", inset: 0 }}
                  />
                )}
              </AnimatePresence>
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </div>
  )
}

// ─── Extension popup ──────────────────────────────────────────────────────────

function LogoMark({ job, size }: { job: Job; size: number }) {
  if (job.ats === "ashby") return <div style={{ width: size, height: size, borderRadius: size * 0.22, background: job.logoBg, display: "flex", alignItems: "center", justifyContent: "center" }}><RampLogo size={size * 0.45} /></div>
  if (job.ats === "greenhouse") return <div style={{ width: size, height: size, borderRadius: size * 0.22, background: job.logoBg, display: "flex", alignItems: "center", justifyContent: "center" }}><DoorDashLogo size={size * 0.6} /></div>
  return <div style={{ width: size, height: size, borderRadius: size * 0.22, background: job.logoBg, display: "flex", alignItems: "center", justifyContent: "center" }}><ShieldAILogo size={size * 0.3} /></div>
}

function ExtensionPopup({ job, phase, logs, appliedCount }: { job: Job; phase: Phase; logs: string[]; appliedCount: number }) {
  const isSubmitted = phase === "submitted" || phase === "gmail"
  const isClicking = phase === "clicking"
  const isSpotlight = phase === "spotlight"

  const spotlightStyle = {
    position: "absolute" as const,
    top: "50%",
    left: "50%",
    transform: "translate(-50%, -50%)",
    width: 240,
  }

  const cornerStyle = {
    position: "absolute" as const,
    top: 28,
    right: 5,
    width: 190,
  }

  return (
    <motion.div
      layout
      animate={isSpotlight ? {
        top: "50%",
        left: "50%",
        x: "-50%",
        y: "-50%",
        right: "auto",
        width: 240,
      } : {
        top: 28,
        left: "auto",
        x: 0,
        y: 0,
        right: 5,
        width: 190,
      }}
      transition={{ duration: 0.5, ease: [0.4, 0, 0.2, 1] }}
      style={{
        position: "absolute",
        background: "#1a1816",
        borderRadius: 10,
        border: `1px solid ${isSubmitted ? "rgba(95,208,127,0.5)" : isSpotlight ? "rgba(240,163,65,0.4)" : "rgba(240,163,65,0.25)"}`,
        overflow: "hidden",
        fontFamily: "'Inter', sans-serif",
        zIndex: 10,
        boxShadow: isSpotlight
          ? `0 12px 48px rgba(0,0,0,0.8), 0 0 0 1px rgba(240,163,65,0.1), 0 0 40px rgba(240,163,65,0.18)`
          : `0 6px 24px rgba(0,0,0,0.7), 0 0 0 1px rgba(240,163,65,0.08), 0 0 20px rgba(240,163,65,0.12)`,
        transition: "border-color 0.3s, box-shadow 0.3s",
        // Initial position so it starts centered
        ...(isSpotlight ? spotlightStyle : {}),
      }}
    >
      {/* Header */}
      <div style={{ padding: "8px 12px", display: "flex", alignItems: "center", justifyContent: "space-between", borderBottom: "0.5px solid #2d2a26" }}>
        <span style={{ fontSize: 11, fontWeight: 600, color: "#faf8f5", letterSpacing: "-0.02em" }}>Persift</span>
        <div style={{ display: "flex", alignItems: "center", gap: 5 }}>
          <motion.div
            animate={{ opacity: isSubmitted ? 1 : [1, 0.3, 1] }}
            transition={isSubmitted ? {} : { duration: 1.2, repeat: Infinity }}
            style={{ width: 6, height: 6, borderRadius: "50%", background: isSubmitted ? "#5fd07f" : isClicking ? "#f0a341" : "#5fd07f" }}
          />
          <span style={{ fontSize: 8.5, color: isSubmitted ? "#5fd07f" : isClicking ? "#f0a341" : "#8a857d" }}>
            {isSubmitted ? "Applied ✓" : isClicking ? "Submitting…" : isSpotlight ? "Ready" : "Applying"}
          </span>
        </div>
      </div>

      {/* Job row */}
      <div style={{ padding: isSpotlight ? "14px 16px" : "9px 12px", borderBottom: "0.5px solid #1e1c1a" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <LogoMark job={job} size={isSpotlight ? 32 : 22} />
          <div style={{ minWidth: 0 }}>
            <div style={{ fontSize: isSpotlight ? 14 : 11, fontWeight: 600, color: "#faf8f5", lineHeight: 1.2 }}>{job.company}</div>
            <div style={{ fontSize: isSpotlight ? 9 : 8, color: "#8a857d", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", marginTop: 1 }}>{job.role}</div>
          </div>
        </div>

        {/* Spotlight-only: match badges */}
        {isSpotlight && (
          <motion.div
            initial={{ opacity: 0, y: 4 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.3, duration: 0.4 }}
            style={{ marginTop: 12, display: "flex", flexDirection: "column", gap: 6 }}
          >
            <div style={{ display: "flex", alignItems: "center", gap: 7 }}>
              <span style={{ fontSize: 10, color: "#5fd07f" }}>✓</span>
              <span style={{ fontSize: 9, color: "#c8c4bc" }}>ATS compatible</span>
            </div>
            <div style={{ display: "flex", alignItems: "center", gap: 7 }}>
              <span style={{ fontSize: 10, color: "#5fd07f" }}>✓</span>
              <span style={{ fontSize: 9, color: "#c8c4bc" }}>Resume matched · <span style={{ color: "#f0a341", fontWeight: 600 }}>{job.match}%</span></span>
            </div>
            <div style={{ display: "flex", alignItems: "center", gap: 7, marginTop: 4 }}>
              <motion.div
                animate={{ opacity: [1, 0.3, 1] }}
                transition={{ duration: 1.2, repeat: Infinity }}
                style={{ width: 6, height: 6, borderRadius: "50%", background: "#f0a341", flexShrink: 0 }}
              />
              <span style={{ fontSize: 9, color: "#f0a341", fontWeight: 500 }}>Applying now…</span>
            </div>
          </motion.div>
        )}
      </div>

      {/* Logs — only shown in corner state */}
      {!isSpotlight && (
        <div style={{ padding: "8px 12px 9px", minHeight: 62 }}>
          <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
            {logs.map((line, i) => {
              const isLast = i === logs.length - 1
              return (
                <motion.div
                  key={i + line}
                  initial={{ opacity: 0, x: -4 }}
                  animate={{ opacity: 1 }}
                  transition={{ duration: 0.2 }}
                  style={{ fontSize: 8, fontFamily: "'Courier New', monospace", lineHeight: 1.6, color: isSubmitted ? "#5fd07f" : isLast ? "#f0a341" : "#8a857d" }}
                >
                  {isLast && !isSubmitted ? "> " : "  "}{line}
                </motion.div>
              )
            })}
          </div>
        </div>
      )}

      {/* Footer */}
      <div style={{ padding: "6px 12px", borderTop: "0.5px solid #1e1c1a", background: "#161412", display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <span style={{ fontSize: 8, color: "#8a857d" }}>Applied today: <span style={{ color: "#f0a341", fontWeight: 600 }}>{appliedCount}</span></span>
        <div style={{ display: "flex", alignItems: "center", gap: 4 }}>
          <span style={{ fontSize: 8, color: "#8a857d" }}>Auto-submit</span>
          <div style={{ width: 22, height: 12, background: "#5fd07f", borderRadius: 7, position: "relative" }}>
            <div style={{ width: 8, height: 8, background: "#1a1816", borderRadius: "50%", position: "absolute", top: 2, right: 2 }} />
          </div>
        </div>
      </div>
    </motion.div>
  )
}

// ─── Gmail notification ───────────────────────────────────────────────────────

function GmailNotif({ job }: { job: Job }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 16, scale: 0.96 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      exit={{ opacity: 0, y: 8, scale: 0.97 }}
      transition={{ type: "spring", stiffness: 340, damping: 28 }}
      style={{
        position: "absolute", bottom: 10, right: 6, width: 210,
        background: "#fff", borderRadius: 8,
        boxShadow: "0 4px 24px rgba(0,0,0,0.28)",
        overflow: "hidden", fontFamily: "'Inter', sans-serif", zIndex: 20,
      }}
    >
      <div style={{ background: "#f8f9fa", padding: "5px 10px", display: "flex", alignItems: "center", gap: 6, borderBottom: "1px solid #eee" }}>
        <svg viewBox="0 0 24 24" width="11" height="11">
          <path fill="#EA4335" d="M24 5.457v13.909c0 .904-.732 1.636-1.636 1.636h-3.819V11.73L12 16.64l-6.545-4.91v9.273H1.636A1.636 1.636 0 0 1 0 19.366V5.457c0-2.023 2.309-3.178 3.927-1.964L5.455 4.64 12 9.548l6.545-4.91 1.528-1.145C21.69 2.28 24 3.434 24 5.457z" />
        </svg>
        <span style={{ fontSize: 8, color: "#444", fontWeight: 600 }}>Gmail</span>
        <span style={{ fontSize: 8, color: "#999", marginLeft: "auto" }}>now</span>
        <span style={{ fontSize: 9, color: "#bbb" }}>×</span>
      </div>
      <div style={{ padding: "9px 11px 10px" }}>
        <div style={{ fontSize: 9, fontWeight: 700, color: "#1a1a1a", marginBottom: 3 }}>
          Thank you for applying to {job.company}
        </div>
        <div style={{ fontSize: 8, color: "#666", lineHeight: 1.5 }}>
          We've received your application for {job.role}. Our team will review and be in touch…
        </div>
      </div>
    </motion.div>
  )
}

// ─── Main ─────────────────────────────────────────────────────────────────────

export const TOTAL_FIELDS: Record<ATS, number> = { ashby: 12, greenhouse: 12, lever: 12 }
export const FORM_HEIGHT: Record<ATS, number> = { ashby: 340, greenhouse: 420, lever: 580 }
export type { Job }
export { JOBS }

const LOG_LINES: (job: Job) => string[] = (job) => [
  "✓ ATS compatible",
  `✓ Resume matched · ${job.match}%`,
  "✓ No cover letter needed",
  `✓ Applied in ${job.seconds} seconds`,
]

export function WorkflowAnimation() {
  const [idx, setIdx] = useState(0)
  const [phase, setPhase] = useState<Phase>("spotlight")
  const [logs, setLogs] = useState<string[]>([])
  const [scrollY, setScrollY] = useState(0)
  const [filledCount, setFilledCount] = useState(0)
  const [appliedCount, setAppliedCount] = useState(APPLIED_BASE)
  const cancelRef = useRef(false)

  useEffect(() => {
    cancelRef.current = false
    let currentIdx = 0
    let totalApplied = APPLIED_BASE

    async function run() {
      while (!cancelRef.current) {
        const job = JOBS[currentIdx % JOBS.length]
        const logLines = LOG_LINES(job)
        const totalFields = TOTAL_FIELDS[job.ats]
        const formH = FORM_HEIGHT[job.ats]

        setIdx(currentIdx % JOBS.length)
        setPhase("spotlight")
        setLogs([])
        setScrollY(0)
        setFilledCount(0)
        await sleep(PHASE_MS.spotlight)
        if (cancelRef.current) break

        // Slide to corner — form fades in simultaneously
        setPhase("sliding")
        await sleep(PHASE_MS.sliding)
        if (cancelRef.current) break

        // Filling — logs lead form by 400ms each
        setPhase("filling")
        const fillDuration = PHASE_MS.filling
        const logInterval = fillDuration / logLines.length

        const fillStart = Date.now()
        const fillLoop = setInterval(() => {
          const elapsed = Date.now() - fillStart
          const pct = Math.min(elapsed / fillDuration, 1)
          setScrollY(pct * formH)
          setFilledCount(Math.floor(pct * totalFields))
        }, 50)

        // Each log line fires then form catches up 400ms later (effectively staggered by logInterval)
        for (let i = 0; i < logLines.length - 1; i++) {
          await sleep(logInterval)
          if (cancelRef.current) { clearInterval(fillLoop); break }
          setLogs(logLines.slice(0, i + 1))
        }
        if (cancelRef.current) { clearInterval(fillLoop); break }

        // Last log line fires early, form finishes
        const remaining = fillDuration - (Date.now() - fillStart)
        if (remaining > 0) await sleep(remaining)
        clearInterval(fillLoop)
        setScrollY(formH)
        setFilledCount(totalFields)
        setLogs(logLines.slice(0, logLines.length - 1))
        await sleep(80)
        if (cancelRef.current) break

        setPhase("clicking")
        await sleep(PHASE_MS.clicking)
        if (cancelRef.current) break

        // Show final "applied" log line + increment counter
        totalApplied += 1
        setAppliedCount(totalApplied)
        setLogs(logLines)
        setPhase("submitted")
        await sleep(PHASE_MS.submitted)
        if (cancelRef.current) break

        setPhase("gmail")
        await sleep(PHASE_MS.gmail)
        if (cancelRef.current) break

        setPhase("closing")
        await sleep(PHASE_MS.closing)
        if (cancelRef.current) break

        currentIdx = (currentIdx + 1) % JOBS.length
      }
    }

    run()
    return () => { cancelRef.current = true }
  }, [])

  const job = JOBS[idx]

  return (
    <div style={{ width: "100%", height: "100%", position: "relative", overflow: "hidden", background: "#0c0a08" }}>
      <AnimatePresence mode="wait">
        <motion.div
          key={job.company}
          initial={{ opacity: 0 }}
          animate={{ opacity: phase === "closing" ? 0 : 1 }}
          transition={{ duration: 0.35 }}
          style={{ position: "absolute", inset: 0 }}
        >
          <BrowserPage job={job} phase={phase} scrollY={scrollY} filledCount={filledCount} />
        </motion.div>
      </AnimatePresence>

      <ExtensionPopup job={job} phase={phase} logs={logs} appliedCount={appliedCount} />

      <AnimatePresence>
        {phase === "gmail" && <GmailNotif key={job.company + "gmail"} job={job} />}
      </AnimatePresence>
    </div>
  )
}

function sleep(ms: number) {
  return new Promise<void>(r => setTimeout(r, ms))
}
