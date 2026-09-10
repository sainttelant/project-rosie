# Project Rosie — Voice-Over Script
*ElevenLabs / self-recorded · talking head + screen recording · ~2:55*

---

**ElevenLabs settings:** Stability 0.45, Similarity 0.80, Style 0.20.
Warm, personal, unhurried. Not a pitch — a story.

`[pause]` = 0.5s breath. `[long pause]` = ~1s beat.

---

## SECTION 1 — THE STORY [0:00–0:50]
*Talking head. Relaxed. Like you're telling a friend.*

About a month ago, [pause] on a Sunday morning,
I was having breakfast and watching the news.

And I came across this story — [pause]
a man in Australia had used AI to design a personalized cancer vaccine
for his dog. [pause] And the treatment actually worked.

[long pause]

I couldn't shake that thought.
[pause] If Paul can do this — [pause] why can't we make this available
to the six million dogs dying from cancer every year? [pause] In the US alone.

[long pause]

Here's the problem.

Paul is an ML veteran with access to a research lab.
[pause] He had three months, [pause] a university compute cluster,
and the knowledge to stitch together half a dozen
specialized bioinformatics tools by hand.

Most vet oncologists have none of that.
[pause] They have a patient in front of them, [pause] and a clock ticking.

[long pause]

---

## SECTION 2 — THE SOLUTION [0:50–1:10]
*Still talking head. One step calmer.*

So I built Project Rosie.

A full neoantigen vaccine pipeline — [pause]
mutation analysis, binding affinity prediction, candidate ranking,
clinical report, mRNA synthesis specification —
all connected, [pause] all automated,
and wrapped in a multimodal clinical assistant powered by Gemma 4.

Any vet oncologist. [pause] No bioinformatician. [pause] Under an hour.

Let me show you.

---

## SECTION 3 — THE DEMO [1:10–2:08]
*Screen recording of rosie.kiraklabs.com*

**[1:10–1:18]** *Landing page → file upload form*

The vet uploads the tumor sequencing file.

---

**[1:18–1:32]** *VcfAdvisor advisory note appears inline*

Before the pipeline even starts, [pause]
Gemma 4 reads the file structure and flags anything
that could waste an hour of compute.

Here — tumor-only sample, no matched normal. [pause]
Flagged upfront, in plain English. [pause]
Submit still works. Nothing is blocked.

---

**[1:32–1:47]** *Pipeline timeline — stages firing one by one*

The pipeline runs on cloud infrastructure.
Each stage fires a live status update — [pause]
annotation, neoantigen prediction, candidate ranking,
report generation, mRNA design. [pause]
No polling. No page refresh.

---

**[1:47–1:57]** *Clinical report — scroll to candidate table + binding affinity chart*

Gemma 4 reads the binding affinity charts
and the full candidate data — multimodally — [pause]
and writes a plain-language clinical report.
Something a vet can act on [pause] without a PhD.

---

**[1:57–2:03]** *Sensitivity panel — IC50 slider drag*

The vet adjusts thresholds. [pause]
Gemma explains the tradeoff in plain English, on demand.

---

**[2:03–2:08]** *Chat widget open + download buttons*

The output: a clinical report [pause] and a synthesis spec —
ready to send to an RNA manufacturing lab.

---

## SECTION 4 — THE CLOSE [2:08–2:35]
*Back to talking head*

What took Paul three months [pause] now takes under an hour.

[long pause]

And here's what I find most exciting.

Dogs get the same cancers humans do —
driven by the same mutations, [pause] in the same genes.

Every canine case that runs through this pipeline
is pre-clinical comparative oncology data.

The playbook we build for dogs [pause] is the playbook for humans.

[long pause]

---

## SECTION 5 — THE CLOSE CARD [2:35–2:55]
*Text on screen: "6 million dogs · $15 per case · Open source"*

Six million dogs. [pause] One pipeline. [pause] Fifteen dollars a case.

[long pause]

Project Rosie. [pause]
Starting with the patients who can't speak for themselves.

---

## EDIT GUIDE

| Time | Visual |
|------|--------|
| 0:00–0:50 | Talking head |
| 0:50–1:10 | Talking head — or cut to product logo |
| 1:10–2:08 | Screen recording — cut on each VO beat |
| 2:08–2:35 | Talking head |
| 2:35–2:55 | Text card then title card |

**Music:** Soft ambient piano 0:00–1:10, drops to near-silence under demo,
returns at 2:08, gentle swell at 2:30, fade under title card.
