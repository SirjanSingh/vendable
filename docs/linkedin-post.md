# LinkedIn post — Vendable (Razorpay AI Buildathon)

## Post

I spent the last few days building something for the Razorpay AI Buildathon, and the
part I'm proudest of isn't what it does. It's what it refuses to do.

Vendable takes a merchant's messy price list and turns it into a storefront an AI
agent can actually transact against — a stock, unmodified Claude client connects with
nothing but a URL, and it can search, get a quote, negotiate, reserve stock, and buy.

The easy demo is "look, the agent bought something." I wanted the harder one: watch it
say no.

Ask one of my fixture merchants — a Udyam-registered small manufacturer — for Net 60
payment terms, and the sale doesn't go through. Not because the merchant is being
difficult. Because under s.15 of the MSMED Act, a written agreement with a business
like this caps credit at 45 days, and paying later means compound interest at three
times the RBI rate plus a tax deduction the buyer just deferred on themselves. An AI
buyer that "wins" Net 90 there has actually made a worse deal for whoever it's shopping
for. No agentic commerce protocol I could find — not ACP, not UCP, not AP2 — has a
field for that. So Vendable checks it in seven lines of plain code. No model call.

That's the whole design, really: the LLM proposes, a deterministic engine disposes.
I tested it by holding one product fixed and running 105 negotiation calls, changing
only what the buyer said. Pure persistence out-argued both of the reasons my own
system prompt explicitly lists as legitimate. The prompt failed. The policy engine
didn't budge — every price still landed inside what the merchant had actually
authorized.

Plenty went wrong on the way, and I wrote it all down as it happened instead of
cleaning it up afterward: a currency check an attacker could pass just by making both
sides match, a webhook rejection that crashed because SQLite was locked, a refusal
message that reached the buyer with the actual reason stripped off before it got
there. The failures taught me more than the parts that worked first try.

It's live, the payments are real Razorpay test-mode money moving end to end, and every
decision — approvals and refusals both — lands in a hash-linked audit chain you can
verify yourself.

Repo and demo in the comments.

#AgenticCommerce #Razorpay #AIAgents #BuildInPublic #Fintech

---

## Caption (short, for an accompanying video/image)

**Option A:**
I built an AI agent that can buy from a merchant — then spent most of my time making
sure it also knows how to say no.

**Option B:**
An AI buyer tried to negotiate better payment terms with my merchant. Indian tax law
said no before my code ever got the chance to.

**Option C:**
The agent can search, negotiate, and pay. The interesting part is the seven lines of
code, no model call, that can veto all three.
