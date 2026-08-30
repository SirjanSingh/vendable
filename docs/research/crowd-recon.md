# Crowd recon — who else is building, and what the bar looks like

Researched 2026-08-29, seven days before the 5 Sep deadline.

## The crowd is large and it is building right now

GitHub repos matching "razorpay" + "buildathon" in name or description: **~402**, almost all
created between **21–29 Aug 2026**. Nearly all have 0 stars. Everyone is sprinting the final
week, same as us.

Only 4 repos use the `razorpay-buildathon` topic tag, so the tag is useless as a census —
the name/description search is the better signal.

## Track distribution — the Track 1 thesis holds, empirically

Sampled repo names and descriptions:

| Repo | Track (inferred) |
|---|---|
| `PRANEETHWARANK/RevGuard-AI` | Risk Manager |
| `LordCenk/merchant-risk-engine` | Risk Manager |
| `venegallarupesh-source/merchantguard-ai` | Risk Manager |
| `Aashwalayan/revenue-recovery-agent` | Revenue Recovery |
| `manga-pannel-130/RecoverAI` | Revenue Recovery |
| `AdithyaAbburi/RecoverAI` | Revenue Recovery |
| `N1CK99925/MoneyOS` | Revenue Recovery |
| `srikrishna0603/razorpay-buildathon` | Revenue Recovery |
| `OmnitriX-7/AegisPay-Controller` | Risk / Finance |
| `Akash-1271/agentpay` | **Agentic Commerce** |

**Revenue Recovery and Risk Manager dominate. Agentic Commerce and Finance Controller are
thin. Open Track is nearly invisible.** This is the 23 Aug prediction confirmed by evidence
rather than reasoning — and note "RecoverAI" was independently chosen as a name by at least
two separate people, which is what a saturated track looks like from the outside.

Track 1 remains the right call.

## The bar to beat

`srikrishna0603/razorpay-buildathon` — "Revenue Resilience AI" — is the most mature
submission found and should be treated as the benchmark:

- 18 commits, real history
- **A deterministic policy engine gating an LLM that only *diagnoses* — zero execution
  authority**
- SQLite WAL for exactly-once recovery semantics
- A failure-injection test suite
- React / Vite / Tailwind frontend
- `DECISIONS.md`, `REVIEW_REQUEST.md`, `CHANGELOG_SUBMISSION.md`

Two things to take from it. First, the strongest competitor independently arrived at
**"LLM proposes, deterministic engine disposes"** — so that architecture is table stakes at
the top of the field, not a differentiator. Vendable must have it *and* something more.
Second, they are writing decision documents. So should we.

Most of the other 400 repos are almost certainly far behind this — empty descriptions,
single-digit commits, hours between creation and last update.

## Nobody is building in public

No Reddit threads (`r/developersIndia`, `r/india`), no Medium/Hashnode postmortems, no
YouTube pitch videos yet, no build-in-public X threads. Only "I applied" LinkedIn posts.

Absence of evidence is itself a finding: **the field is heads-down in private repos.** A
public build-in-public thread would be differentiated — though it also tips your idea to 400
competitors with days left. Recommendation: publish *after* submitting, not before.

Incidental: a LinkedIn post credits **Mohit Paddhariya**, a Razorpay intern, with building
the buildathon pipeline itself.

## Cassandra — the builder's own prior win, mined for process

Sirjan Singh + Kshitij Verma. **1st place, Arize track, Google Cloud Rapid Agent Hackathon**
(14,000+ participants). Devpost: `devpost.com/software/cassandra-jilmgy`. Repo:
`github.com/SirjanSingh/cassandra`. Video: `youtu.be/6a_CFiQ6L24`.

An 8-step closed loop over AI-agent failures: watch live Phoenix traces → diagnose failure
type → root-cause → synthesize an adversarial eval set from the single failure → evaluate the
current prompt → patch it → replay the original failing question → red-team the fix.
Architecture: Gemini 2.5 Flash Lite on Vertex, ADK `LoopAgent` on Agent Engine, Arize Phoenix,
a custom FastAPI MCP server, Cloud Run dashboard, Firestore state.

### The transferable lessons

1. **Core logic was deliberately kept framework-free, plain Python, unit-testable with zero
   cloud dependency.** This is why it survived demo day. Repeat it exactly.
2. **Scope a closed loop, not a feature list.** One loop demoed running end-to-end beat
   breadth. Maps directly onto Razorpay's own language: *"every money action explainable,
   bounded and gated."*
3. **Anticipate your own failure mode in the architecture.** They filtered `session_id="test"`
   to stop Cassandra supervising itself during its own replay runs. Vendable's equivalent:
   the buyer agent must not be able to mint its own mandate, and the audit log must not be
   writable by the payment path it audits.
4. **When the platform has a gap, state it and route around it in the open.** Phoenix had no
   "create experiment" primitive, so they evaluated live against the real agent and reframed
   that as the more honest result. Judges read this as integrity, not weakness.
5. **Demo the loop running, sub-60-seconds, with a visible before/after.** Not slides.
6. **Name what is explicitly out of scope.** They scoped future work (PII detection,
   confidence-gated auto-deploy, fleet supervision) rather than claiming completeness.
7. Named challenges were honest and specific: debugging their own observability tooling before
   they could trust it; preventing self-supervision loops; recognising **weak patches** that
   fixed one case without generalising. This is exactly the register `what-broke.md` needs.

Note: one search summary attributed Cassandra to a "HackCrux Hackathon." That is wrong —
Devpost is authoritative. Do not repeat it.

## What judges say separates winners

From Devpost's own organizer guides and judging writeups:

- The preliminary cut is **brutally functional**: does it install, does it run. Polish cannot
  rescue something broken live.
- **Selectivity beats breadth.** Cramming features to compensate loses the judges' thread.
- Demo video: elevator pitch in the **first ~10 seconds**, then how it works, then a real,
  visual, interactive demo. No team backstory, no scene-setting.
- "Could this become a real ongoing thing" is an explicit criterion in several rubrics.

## Razorpay hiring signals

- Their `/ai-builders` framing wants people who "see every workflow as an agent loop, speak in
  prompts and GitHub links" and can show something **shipped**, not coursework.
- Fresher interviews reportedly centre on walking through a system you built end to end —
  **including what you would change now.** Expect to defend architecture decisions, not recite
  theory.
- A deployed project making real API calls outranks any credential.
- Razorpay recently hired senior AI leaders from Microsoft, Salesforce and Cred. The AI org is
  scaling; this pipeline is genuine, not a token gesture.
- The per-track judging language on the buildathon page is close to a leaked rubric. Build to
  satisfy the exact phrases.
