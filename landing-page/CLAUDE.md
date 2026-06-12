# Persift Landing Page — Agent Handover

## Project
Scroll-driven React landing page for Persift — a Chrome extension that autonomously finds early-career jobs and applies to them. Builder: Himanshu Jarodiya (CS @ ASU, founder). **Launch target: June 7 2026.**

Dev server: `pnpm dev`

## Stack
React 18 + TypeScript + Vite + Framer Motion v12 + pnpm

## Scroll Architecture
- `src/App.tsx`: 900vh spacer + sticky 100vh stage. Progress via `useScroll` → mirrored into a plain `useMotionValue(0)` via `useEffect` subscription. **Never pass raw `scrollYProgress` to `useTransform` — Framer Motion v12 uses WAAPI for scroll-linked values which requires offsets in [0,1] and breaks when scene keyframes go negative or exceed 1.**
  ```ts
  const progress = useMotionValue(0)
  useEffect(() => scrollYProgress.on("change", (v) => progress.set(v)), [])
  ```
- `src/scroll/Scene.tsx`: each scene gets 1/9 of the progress band. Transition style D — incoming slides up 50px + scales 0.95→1, outgoing fades.
- `src/scroll/SceneContext.tsx`: `useSceneProgress()` returns 0→1 within the current scene's band.
- 9 scenes: Scene0Hero → Scene1Chaos → Scene2Install → Scene2Setup → Scene3Machine → Scene4Overnight → Scene5Morning → Scene6Analytics → Scene7Ask

## Design System (`src/index.css`)
- `--bg` #0c0a08, `--amber` #f0a341, `--ink` #f3ece1, `--green` #5fd07f
- `--ink-soft`, `--ink-faint`, `--ink-mute`, `--amber-soft`, `--line`

## Fonts
- **Plus Jakarta Sans 700/800** — hero headlines (`Scene0Hero.tsx`), Chrome store card title
- **Spectral 300 italic** — amber italic accent line (hero second line)
- **Fraunces 500** — Scene7Ask closing punch line ONLY ("Stop applying. Start waking up to interviews."). **Do NOT use Fraunces anywhere else.**
- **Inter 400/500/600** — body
- **Roboto 400** — Chrome web store UI

## Copy Rules
- Say "early-career roles" not "internships" — covers new grads too
- Never say "while you sleep" / "you sleep, Persift works" — overused, already used 4+ times, user rejected
- Keep copy punchy and specific. Not explanatory.

---

## Improvement Tracker: `.claude/IMPROVEMENTS.md`
Full detail in that file. Status summary:

### ✅ Done
1. **Hero copy** — "You qualify for hundreds of roles. / Apply to all of them." + subline
2. **Scroll smoothness** (partial) — spring removed, WAAPI fixed, transition D implemented
4. **Chrome Web Store title** — "Job applications on autopilot." (Plus Jakarta Sans 700)
5. **Remove "Install once…" copy line** — deleted entirely
6. **Setup scene** — "What happens next" section added to ExtensionPopup, cards aligned
8. **Machine scene discovery timing** — card fades in at p=[0.18,0.28] not from start
9. **Machine scene duplicate Anthropic** — fixed with Math.floor (not Math.round) on rawIndex
10. **Replace Linear with Figma** — Greenhouse ATS, green/light theme, Design Engineer Intern

### Also completed (prev sessions, not in tracker)
- **Fixed topbar** — `position: fixed; top: 0; z-index: 110` in App.tsx. Sticky stage offset to `top: 64, height: calc(100vh - 64px)`. Header has `background: rgba(12,10,8,0.88)` + `backdropFilter: blur(8px)`.
- **Machine scene APPLY_END**: 0.88 → 0.72. needsYou threshold: 0.90 → 0.73.
- **Overnight scene**: full redesign — 5 companies, pipeline dots, fixed-width columns, progressive clock, pulsing amber dot.
- **Scene5Morning / Scene6Analytics**: DashboardShell `maxHeight="calc(100vh - 200px)"`, reduced padding, scenes use `height: 100%; justifyContent: flex-start; padding: 24px 24px 0`.
- **Scene6Analytics**: removed "Silence past 3 weeks inferred as rejection" line. Reduced to 4 ROWS (Stripe, Anthropic, Figma, Linear), chart height 150→100px.
- **Hero scene**: Plus Jakarta Sans 700, amber glow, ambient toasts added then removed (user rejected). Join Waitlist button restyled to match Get Early Access (borderRadius 9, same gradient).
- **Brand / logo**: funnel icon replaced. Current state: `src/components/Brand.tsx` uses a hand-drawn geometric P on a 24×30 SVG grid with `fillRule="evenodd"` circle punch-through. **UNFIXED** — the P mark still renders incorrectly (bowl direction broken). Do not attempt further SVG path fixes without testing each arc direction carefully. See Logo Issue section below.

### ⬜ Remaining (in priority order)

**#7 — Systemic empty space** (deferred, do last)
- Almost every scene has too much padding. Address scene by scene after all other fixes.

**#15 — Logo / Brand mark** (UNFIXED — pick up here)
- User's original logo: `c:\Users\himan\Downloads\Persift Logo (1).svg` — P letterform with circular punch-through, designed at 500×500.
- Problem: the 500×500 paths render as a thin skeleton at 20–26px (stem ~2px, bowl ring sub-pixel).
- Attempted fix: redraw as geometric P on 24×30 grid using `fillRule="evenodd"`. Path: `M9,2 A12,9 0 0 1 9,20 L9,28 L2,28 L2,2 Z` + circle subpath. Arc direction was wrong in multiple attempts — bowl kept rendering backwards or not at all.
- **Next step**: verify the arc direction with a throwaway HTML file before touching Brand.tsx. The correct arc for the bowl: from (9,2) top of ellipse, CW sweep=1, to (9,20) — should pass through (21,11) on the right. Test this independently, then apply.
- User preference: keep `[PersiftMark] Persift` wordmark layout (not `[P]ersift`). The mark should be ~26px tall in the topbar. Default color `var(--ink)`.
- File: `src/components/Brand.tsx`

**#3 — Chaos scene** (blocked)
- Needs cold user research with real students. Don't touch until Himanshu gives the go-ahead.
- File: `src/scenes/Scene1Chaos.tsx`

**#2 — Scroll smoothness** (assess end-to-end after all other fixes)
- Spring removed, WAAPI avoided. Overall feel still not smooth. Revisit when full page is stable.

---

## Key Technical Notes

### Machine Scene (Scene3Machine.tsx)
- Pipeline: Stripe → Anthropic → Figma (3 companies)
- `APPLY_START = 0.44`, `APPLY_END = 0.72`, `BAND = (0.72-0.44)/3 = 0.0933`
- `rawIndex` uses `Math.floor` (not Math.round) to avoid mid-fill company switches
- `fillFrac` uses 0.15 threshold: `Math.max(0, Math.min(1, (f - 0.15) / 0.85))`
- Scene fade-out starts at sceneProgress ≈ 0.757 — APPLY_END must be below this
- needsYou triggers at p >= 0.73

### Overnight Scene (Scene4Overnight.tsx)
- 5 companies, each with `foundIdx`, `tailoredIdx`, `submittedIdx` into a 14-entry TIMES array
- Fixed column widths: `COL_ICON=16`, `COL_PIPELINE=61`, `COL_MATCH=52`, `COL_TIME=72`, `ROW_GAP=10`
- Pipeline dot colors: Found=#f0a341, Tailored=#c084fc, Applied=#5fd07f
- Active company: third dot is a pulsing amber `motion.span` (animate opacity [0.2,1,0.2], 1.4s loop)
- Notion has `foundIdx=tailoredIdx=9` (no separate tailoring step)
- Vercel has `submittedIdx=99` (never submits — scene ends while applying)

### Hero Animation (WorkflowAnimation.tsx + Scene0Hero.tsx)

#### Scene0Hero.tsx
- Mounts `WorkflowAnimation` inside laptop screen cutout at `ANIM_L=538, ANIM_T=37, ANIM_W=501, ANIM_H=331` (image-natural coordinates; image is 1522×688)
- Image + animation wrapped in a cover unit that scales together via `max(100%, calc(100vh * IMG_W/IMG_H))`
- Gradients: bottom 300px fade, left 27%, right 27% — **no top gradient** (was removed, it darkened the screen)

#### WorkflowAnimation.tsx — key constants
```typescript
const PHASE_MS = {
  opening: 1000, filling: 5000, clicking: 600,
  submitted: 1500, gmail: 1500, closing: 1000,
}
const TOTAL_FIELDS: Record<ATS, number> = { ashby: 12, greenhouse: 12, lever: 12 }
const FORM_HEIGHT: Record<ATS, number>  = { ashby: 420, greenhouse: 500, lever: 780 }
const LOG_LINES: Record<ATS, string[]> = {
  ashby:      ["Detected Ashby ATS", "Parsing 12 fields", "Resume matched", "Submitting…"],
  greenhouse: ["Detected Greenhouse ATS", "Parsing 18 fields", "Resume matched", "Submitting…"],
  lever:      ["Detected Lever ATS", "Parsing 14 fields", "Resume matched", "Submitting…"],
}
```

#### Companies
```typescript
const JOBS = [
  { company: "Ramp",      role: "Software Engineer, AI Forward Deployed", ats: "ashby",      url: "jobs.ashbyhq.com/ramp/ai-forward-deployed",  logoBg: "#f5f0eb", logoColor: "#2d2926" },
  { company: "DoorDash",  role: "Principal Software Engineer, Ads",        ats: "greenhouse", url: "job-boards.greenhouse.io/doordash/jobs/5521", logoBg: "#fff1f0", logoColor: "#FF3008" },
  { company: "Shield AI", role: "Product Manager, AI Platforms",           ats: "lever",      url: "jobs.lever.co/shieldai/r4991",                logoBg: "#f0f2f5", logoColor: "#1a1a1a" },
]
```

#### Fake applicant (Jane Doe — not real data)
```typescript
const JANE = {
  firstName: "Jane", lastName: "Doe", fullName: "Jane Doe",
  email: "jane.doe@example.com", phone: "(555) 867-5309",
  location: "Seattle, WA", linkedin: "linkedin.com/in/janedoe",
  website: "janedoe.dev", company: "Doe Labs",
  school: "University of Washington", degree: "B.S. Computer Science",
  resume: "Jane_Doe_Resume.pdf",
  essay: "Recently I built a tool that automatically tracks internship applications...",
  whyUs: "I am drawn to organizations that solve technically challenging problems...",
}
```

#### Phase loop logic
- `filledCount = Math.floor((scrollY / formH) * totalFields)` — derived from scroll, never independent
- Logs fire at 85% of fill duration: `logInterval = (fillDuration * 0.85) / logLines.length`
- After logs, waits remaining 15% so scroll reaches bottom cleanly, then sets scroll/fill to max
- `setLogs(logLines.slice(0, i + 1))` — always sets full array from start (prevents accumulation across cycles)
- `cancelRef.current` checked at each phase transition; cleanup sets it true

#### Submit button animation (all 3 ATS forms)
```typescript
<motion.div
  animate={{ background: isClicking ? ["#1a1a1a", "#fff", "#1a1a1a"] : "#1a1a1a" }}
  transition={{ duration: 0.5, times: [0, 0.3, 1] }}
>
  <motion.span
    animate={{ color: isClicking ? ["#fff", "#1a1a1a", "#fff"] : "#fff" }}
    transition={{ duration: 0.5, times: [0, 0.3, 1] }}
  >Submit Application</motion.span>
</motion.div>
```
Flash white at 30% of 500ms (150ms), returns to black by 500ms — before 600ms clicking phase ends.

#### ATS form notes
- **Ashby** (Ramp): white bg, autofill banner, tabs, Inter font, 12 fields
- **Greenhouse** (DoorDash): white bg, red DoorDash logo, resume pill buttons (Attach/Dropbox/Drive), SUBMIT YOUR APPLICATION header, 12 fields
- **Lever** (Shield AI): gray `#f4f4f4` page bg, white header with shield SVG, "Apply with LinkedIn" blue pill, "ATTACH RESUME/CV" gray pill, ALL CAPS section headers, radio buttons, generous spacing, 12 fields
- `FORM_HEIGHT: lever: 780` — raised so scroll reaches submit button for Shield AI
- Scroll uses `transition: "transform 0.12s linear"` (no ease-in-out, which caused snapping)

#### Known remaining issues
- Shield AI (Lever) scroll/submit button reach — needs verification in browser that `FORM_HEIGHT=780` is sufficient
- Ashby (Ramp) and Greenhouse (DoorDash) form structure can be refined to better match real screenshots (user deferred: "we'll figure out the exact structure later")

### Approach (user preference)
- Discuss each fix briefly before implementing
- Don't add features beyond what's asked
- No comments in code unless non-obvious
- Test in browser after UI changes
