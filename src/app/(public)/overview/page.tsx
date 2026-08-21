import type { Metadata } from "next"
import { Badge } from "@/components/ui/badge"

export const metadata: Metadata = {
  title: "Personalized mRNA Cancer Vaccines for Dogs — A Canadian Feasibility Question",
  description:
    "An open-source neoantigen design pipeline for canine tumours, what it does and does not prove, and the clinical and regulatory questions I am trying to answer in Canada.",
  openGraph: {
    title: "Personalized mRNA Cancer Vaccines for Dogs — A Canadian Feasibility Question",
    description:
      "An open-source neoantigen design pipeline for canine tumours, what it does and does not prove, and the clinical and regulatory questions I am trying to answer in Canada.",
    type: "article",
    url: "https://rosie.kiraklabs.com/overview",
    images: [{ url: "/project-rosie-cover.png", width: 1536, height: 1024, alt: "Project Rosie" }],
  },
  twitter: {
    card: "summary_large_image",
    title: "Personalized mRNA Cancer Vaccines for Dogs — A Canadian Feasibility Question",
    description:
      "An open-source neoantigen design pipeline for canine tumours, and the clinical and regulatory questions I am trying to answer in Canada.",
    images: ["/project-rosie-cover.png"],
  },
}

const DM = { fontFamily: "var(--font-dm-sans), sans-serif" } as const

const OUTPUTS = [
  {
    title: "Ranked neoantigen candidates",
    body: "Somatic variants annotated with Ensembl VEP against the canine ROS_Cfam_1.0 reference, then scored for DLA class I binding with pVACtools and NetMHCpan. Ranking is a transparent ~50-line composite of predicted affinity and tumour VAF — not a black box.",
  },
  {
    title: "A synthesis-ready mRNA construct",
    body: "A multi-epitope construct, codon-optimized against a canine codon table, with 5′UTR, 3′UTR and a poly-A(60) tail, emitted as FASTA.",
  },
  {
    title: "A plain-language clinical report",
    body: "A 400–600 word summary of the candidates and the confidence behind them, written for the clinician rather than the bioinformatician.",
  },
  {
    title: "A formal synthesis specification",
    body: "A manufacturer-facing document — cap chemistry, nucleoside substitution, LNP composition, RNA integrity thresholds. Rendered from a fixed template, deliberately not model-generated, because a drifted QC threshold is how a tool gets dismissed.",
  },
]

const SIGNALS = [
  {
    tag: "19 Aug 2026",
    tagStyle: "border-primary/30 text-primary bg-primary/5",
    title: "The first positive Phase 3 for an individualized neoantigen therapy",
    body:
      "Merck and Moderna reported that INTerpath-001 met its primary endpoint of recurrence-free survival and its key secondary endpoint of distant metastasis-free survival, in completely resected stage IIB–IV melanoma. It is the first positive Phase 3 readout both for an individualized neoantigen therapy and for an mRNA-based cancer therapy.",
    href: "https://www.merck.com/news/merck-and-moderna-announce-phase-3-interpath-001-trial-of-intismeran-autogene-plus-keytruda-met-endpoints-of-recurrence-free-survival-rfs-and-distant-metastasis-free-survival-dmfs-in-patient/",
    linkText: "Merck announcement",
  },
  {
    tag: "17 Aug 2026",
    tagStyle: "border-amber-500/30 text-amber-600 bg-amber-500/5",
    title: "The same approach, in dogs, now funded",
    body:
      "Paul Conyngham, a Sydney ML engineer, designed a personalized mRNA vaccine for his own dog Rosie, a Staffordshire bull terrier with mast cell cancer. His company Gamgee launched with a $4M seed led by Founders Fund and is running studies in Australia with UNSW, the University of Queensland and the Garvan Institute. Worth stating plainly: Gamgee has disclosed that Rosie relapsed after a later surgery, and the case had no control arm and concurrent treatments. I read it as evidence of feasibility, not of efficacy.",
    href: "https://www.gamgee.io/",
    linkText: "Gamgee",
  },
  {
    tag: "Context",
    tagStyle: "border-blue-500/30 text-blue-600 bg-blue-500/5",
    title: "Dogs are already a recognised comparative oncology model",
    body:
      "The NCI Comparative Oncology Trials Consortium runs trials in dogs with spontaneously occurring tumours precisely because those tumours resemble human disease in ways engineered models do not. Twenty academic centres participate. The Ontario Veterinary College is the only Canadian member.",
    href: "https://ccr.cancer.gov/comparative-oncology-program/trials-consortium",
    linkText: "NCI COTC",
  },
]

const LIMITS = [
  "The public demo case is an enriched public dataset, not a patient. It is there to show the outputs end to end, not to report a result.",
  "Nothing here has been validated in a wet lab. No construct from this pipeline has been synthesized, and no animal has been treated.",
  "Binding prediction is prediction. Predicted DLA class I affinity is a filter for candidates, not evidence of immunogenicity, and the canine allele reference data is far thinner than the human equivalent.",
  "The pipeline starts from a VCF, not from raw reads. Alignment and somatic calling are assumed upstream.",
  "I am a software engineer, not a veterinarian, immunologist or bioinformatician by training. Every clinical judgement here needs someone who is.",
]

const QUESTIONS = [
  "Whether a CFIA autogenous-biologic or research-use pathway could realistically support an investigator-led canine study in Canada — or whether that assumption is wrong at the root.",
  "What a defensible first study actually looks like: indication, endpoints, control arm, and the number of dogs needed to learn anything real.",
  "Where GMP-grade mRNA and LNP formulation for a batch of one can be sourced in Canada, and what per-batch release testing genuinely costs.",
  "What the honest failure modes are — the reasons an experienced veterinary oncologist would expect this not to work.",
]

export default function OverviewPage() {
  return (
    <div className="max-w-3xl mx-auto w-full px-5 sm:px-6 pt-10 pb-20">
      <Badge
        variant="outline"
        className="text-xs font-semibold px-2 py-0.5 rounded-md border-primary/30 text-primary bg-primary/5 mb-4"
      >
        Overview
      </Badge>

      <h1 className="text-3xl sm:text-4xl font-bold tracking-tight mb-4 leading-tight" style={DM}>
        Personalized mRNA cancer vaccines for dogs — a Canadian feasibility question
      </h1>

      <p className="text-muted-foreground leading-relaxed mb-4">
        I&apos;m Shashank Padala, a software engineer in Toronto. I previously led AI projects at Amazon. Over the past
        few months I built and open-sourced an end-to-end neoantigen design pipeline for canine tumours: from a somatic
        variant call file to a ranked candidate list and a synthesis-ready mRNA construct.
      </p>
      <p className="text-muted-foreground leading-relaxed mb-8">
        I built it because I lost my own dog to cancer, and because the published accounts of this approach suggested it
        was closer to reach than I expected. This page exists so I don&apos;t have to explain all of that in an email. It
        covers what the pipeline does, what it does not prove, and the questions I&apos;m trying to answer.
      </p>

      <div className="flex flex-wrap gap-3 mb-14">
        <a
          href="/demo"
          className="text-sm px-5 py-2.5 rounded-lg bg-hero-gradient text-primary-foreground font-semibold hover:opacity-90 transition-opacity shadow-md shadow-primary/20"
        >
          See a case end to end →
        </a>
        <a
          href="https://github.com/shashank-padala/project-rosie"
          target="_blank"
          rel="noopener noreferrer"
          className="text-sm px-5 py-2.5 rounded-lg border border-border/60 bg-card font-semibold hover:border-primary/30 transition-colors"
        >
          Source on GitHub
        </a>
      </div>

      <section className="mb-14">
        <h2 className="text-xl font-bold mb-1.5" style={DM}>
          What it produces
        </h2>
        <p className="text-muted-foreground text-sm mb-6">
          One tumour VCF in. Roughly an hour of cloud compute, about $15. Four artifacts out.
        </p>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          {OUTPUTS.map((o, i) => (
            <div key={o.title} className="rounded-2xl border border-border/60 bg-card p-5 shadow-sm">
              <div className="text-xs font-mono text-muted-foreground/50 mb-2">
                {String(i + 1).padStart(2, "0")}
              </div>
              <h3 className="font-semibold text-foreground mb-1.5 text-sm" style={DM}>
                {o.title}
              </h3>
              <p className="text-muted-foreground text-sm leading-relaxed">{o.body}</p>
            </div>
          ))}
        </div>
      </section>

      <section className="mb-14">
        <h2 className="text-xl font-bold mb-1.5" style={DM}>
          Why I think this is worth asking about now
        </h2>
        <p className="text-muted-foreground text-sm mb-6">
          Two of these happened within five days of each other in August 2026.
        </p>
        <div className="flex flex-col gap-4">
          {SIGNALS.map((s) => (
            <div key={s.title} className="rounded-2xl border border-border/60 bg-card p-6 shadow-sm">
              <Badge
                variant="outline"
                className={`text-xs font-semibold px-2 py-0.5 rounded-md mb-3 ${s.tagStyle}`}
              >
                {s.tag}
              </Badge>
              <h3 className="font-semibold text-foreground mb-2" style={DM}>
                {s.title}
              </h3>
              <p className="text-muted-foreground text-sm leading-relaxed mb-3">{s.body}</p>
              <a
                href={s.href}
                target="_blank"
                rel="noopener noreferrer"
                className="text-sm text-primary font-medium hover:underline"
              >
                {s.linkText} ↗
              </a>
            </div>
          ))}
        </div>
      </section>

      <section className="mb-14">
        <h2 className="text-xl font-bold mb-1.5" style={DM}>
          What I am not claiming
        </h2>
        <p className="text-muted-foreground text-sm mb-6">
          The fastest way to waste an expert&apos;s time is to make them extract this list themselves.
        </p>
        <div className="rounded-2xl border border-amber-500/20 bg-amber-500/5 p-6">
          <ul className="flex flex-col gap-3.5">
            {LIMITS.map((l) => (
              <li key={l} className="text-sm leading-relaxed text-foreground/80 flex gap-3">
                <span className="text-amber-600/60 shrink-0 mt-0.5">—</span>
                <span>{l}</span>
              </li>
            ))}
          </ul>
        </div>
      </section>

      <section className="mb-14">
        <h2 className="text-xl font-bold mb-1.5" style={DM}>
          What I&apos;m trying to find out
        </h2>
        <p className="text-muted-foreground text-sm mb-6">
          The computational side turned out to be the easy part. These are the questions I can&apos;t answer alone.
        </p>
        <ol className="flex flex-col gap-4">
          {QUESTIONS.map((q, i) => (
            <li key={q} className="flex gap-4">
              <span className="text-sm font-mono text-primary/50 shrink-0 pt-0.5">
                {String(i + 1).padStart(2, "0")}
              </span>
              <span className="text-sm leading-relaxed text-foreground/80">{q}</span>
            </li>
          ))}
        </ol>
      </section>

      <section className="rounded-2xl border border-border/60 bg-secondary/30 px-6 py-6">
        <h2 className="text-lg font-bold mb-2" style={DM}>
          If any of this is in your field
        </h2>
        <p className="text-muted-foreground text-sm leading-relaxed mb-4">
          I&apos;m at an early stage and actively looking for input from people who know the clinical, regulatory and
          manufacturing reality well enough to tell me where I&apos;m wrong. A short conversation is genuinely useful to
          me, including one that concludes this isn&apos;t worth pursuing. And if it turns out to be worth pursuing, I&apos;d
          want to build it alongside the people who actually know the field rather than around them.
        </p>
        <div className="flex flex-wrap gap-4 text-sm">
          <a href="/writeup" className="text-primary font-medium hover:underline">
            Full technical writeup →
          </a>
          <a href="/docs" className="text-primary font-medium hover:underline">
            Pipeline explainers →
          </a>
          <a href="/docs/architecture" className="text-primary font-medium hover:underline">
            Architecture diagram →
          </a>
        </div>
      </section>
    </div>
  )
}
