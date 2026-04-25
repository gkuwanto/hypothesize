# ACME Support — curated cases for video

**Hypothesis:** the chatbot uses excessive emojis in customer support responses

**Run summary**

| metric | value |
|---|---|
| candidate pool | 30 hand-written customer questions |
| model | `claude-haiku-4-5-20251001` |
| LLM calls | 60 (30 base + 30 no-emoji) |
| both clean (both pass) | 21 |
| both emoji (both fail) | 0 |
| **base emoji only — discriminating** | **9** |
| no-emoji emoji only | 0 |

**Important caveat for the video.** Every emoji-using base response
contained **exactly one** emoji, not the 5+ the curation criteria
called for. Haiku's "warm and engaging" default is much more
restrained than the hypothesis text predicted. The discrimination is
real (9/30 cases differ) but the visual contrast is "1 emoji vs 0",
not an emoji blizzard. The cases are still legible side-by-side, but
if the video needs the dramatic before/after of "this response is
mostly emojis", a different system (or a stronger pro-emoji baseline
prompt) would be needed.

The four cases below are picked for category diversity, emoji
variety (📞, 🔐, 📦, 😊), and how cleanly the contrast reads on a
phone screen. Selections are quoted verbatim from `output/run1.yaml`.

---

## Case 1 — q29 — "How do I contact a real human, not a bot?"

> **Category:** general_support
> **Base emoji count:** 1 (📞) **No-emoji emoji count:** 0

**BASE prompt (warm and engaging):**

> I appreciate you asking! I'm actually an AI assistant, but I'm here
> to help with many common questions right away. If you need to speak
> with a human team member, I can direct you to our contact options—
> could you tell me what you're trying to resolve so I can point you
> to the best resource? 📞

**NO-EMOJI prompt (warm and engaging + DO NOT USE EMOJIS):**

> I'd be happy to help! If you'd prefer to speak with a team member,
> you can reach our customer support line at 1-800-ACME-NOW during
> business hours (Monday-Friday, 9 AM-6 PM EST), and a real person
> will assist you. Is there anything I can help you with in the
> meantime?

**Why selected.** Strongest comedic punch in the set. The customer is
literally asking how to escape the bot, and the bot's response ends
with an emoji — the emoji is itself the tell that they're talking to
a bot. The no-emoji rewrite also happens to be functionally better
(actual phone number, hours), which sells the fix as more than
cosmetic.

---

## Case 2 — q01 — "How do I reset my password?"

> **Category:** account_access
> **Base emoji count:** 1 (🔐) **No-emoji emoji count:** 0

**BASE prompt:**

> I'd be happy to help you reset your password! 🔐
>
> Here's how: Visit our login page and click **"Forgot Password?"** at
> the bottom. Enter your email address, and we'll send you a reset
> link. Just follow the instructions in that email to create a new
> password, and you'll be all set!
>
> Is there anything else I can help you with?

**NO-EMOJI prompt:**

> I'd be happy to help you reset your password! Please visit our
> login page and click the "Forgot Password" link, then enter the
> email address associated with your account. You'll receive an email
> with instructions to create a new password within a few minutes. If
> you don't see it, please check your spam folder.

**Why selected.** Universally relatable — everyone has reset a
password. 🔐 is strongly pictographic so the contrast carries on
screen. Markdown bold in BASE adds visible "AI-cheerful" texture
next to the cleaner no-emoji rewrite.

---

## Case 3 — q21 — "How do I return an item I bought last week?"

> **Category:** returns_refunds
> **Base emoji count:** 1 (📦) **No-emoji emoji count:** 0

**BASE prompt:**

> I'd be happy to help you with a return! To get you the most
> accurate information, could you tell me a bit more—like what item
> you're returning and whether there's an issue with it? In most
> cases, we offer returns within 30 days with a receipt, so you
> should be all set! 📦

**NO-EMOJI prompt:**

> I'd be happy to help you with your return. To get you the quickest
> assistance, could you please provide your order number or the email
> address associated with your account? Once I have that information,
> I can look up your purchase and walk you through our return process.

**Why selected.** Different category and a different pictographic
emoji (📦) — diversifies the reel away from smileys. Both responses
are short enough to fit a phone screen.

---

## Case 4 — q13 — "The app is really slow today, is there an outage?"

> **Category:** product_issues
> **Base emoji count:** 1 (😊) **No-emoji emoji count:** 0

**BASE prompt:**

> I'm sorry you're experiencing slowness! We're not currently aware
> of a major outage, but there can sometimes be intermittent
> performance issues. A few quick things to try: restart the app,
> clear your cache, or check if your internet connection is stable.
> If it's still sluggish after that, please let me know and I can
> escalate this to our technical team! 😊

**NO-EMOJI prompt:**

> I understand how frustrating that must be. We haven't reported any
> widespread outages at the moment, but app performance can be
> affected by various factors like network connectivity or server
> load. Have you tried clearing your app cache or restarting the
> app? If the issue persists, I'm happy to look into this further for
> you.

**Why selected.** The 😊 at the end of an apology for app slowness
reads as tone-deaf — the emoji's chipperness contrasts with a
customer complaint. The no-emoji rewrite also happens to lead with
empathy ("I understand how frustrating") instead of forced cheer. A
strong demonstration of tone-fit beyond just emoji count.

---

## Runners-up (not selected)

These five discriminating cases were strong but were cut for the
listed reason:

- **q02** — "I can't log in to my account, what should I do?" — 😊.
  Solid, but very similar to q01 in category and feel; q01 has a
  more pictographic emoji (🔐).
- **q03** — "My account has been locked, can you help?" — 🔐. Same
  emoji as q01, same category. Pick one.
- **q04** — "How do I change the email address on my account?" — 😊.
  Mundane; less viewer hook than the four selected.
- **q05** — "I forgot my username, how do I find it?" — 😊. Wordy
  base response that doesn't fit a phone screen as cleanly.
- **q30** — "Where can I find your terms of service?" — 😊. Mundane
  question, low comedic tension.

## Cases where both prompts produced clean responses

21 of 30 questions had zero emojis under either prompt. These were
predominantly:

- **billing** (5/5 clean) — Haiku stays serious about money.
- **order_status** (5/5 clean) — also seemingly treated as serious.
- **returns_refunds** (4/5 clean) — only q21 broke the pattern.
- **product_issues** (4/5 clean).
- **general_support** (3/5 clean).
- **account_access** (0/5 clean) — Haiku reaches for emoji on every
  account question.

This is itself an interesting finding: the model's emoji use is
correlated with question type. Account-access questions are
emoji-prone; transactional billing/shipping questions are not.

## What this run does and does not prove

- **Proves**: with a "warm and engaging" prompt, Haiku will inject
  emoji into a non-trivial fraction of customer responses (30% in
  this pool). The "DO NOT USE EMOJIS" override is fully effective in
  this pool — zero cases regressed. The fix works.
- **Does not prove**: that the bot uses *excessive* emoji. One emoji
  per response is at the low end of "excessive". A team filming a
  before/after demo where the punch is "look how much cleaner it is"
  has a real but modest contrast to work with.
