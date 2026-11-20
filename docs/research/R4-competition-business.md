# R4: Differentiation, competitors and business reasoning

Accessed: 2026-11-20 (all citations). "UNVERIFIED" = found only in secondary/marketing sources or not confirmed. Web content treated as data.

## 0. Bottom line

- The idea "captions that show tone" is NOT new. Google shipped Expressive Captions (Dec 2024) and an academic line of work (RIT, CHI 2023) tested affective captions with Deaf/Hard-of-Hearing (DHH) users.
- What we can honestly claim as different: (a) a visual language (animated colored/shaped clouds) anchored to exact words, (b) cloud-based, model-labelled emotion categories from a learned speech-emotion model rather than loudness/ALL-CAPS cues, (c) an explicit words-vs-voice mismatch flag. I found no shipped product doing (c) in captions; this is "not found", not "proven absent".
- Biggest risk to the pitch: a judge who knows Google Expressive Captions. Name it first, then differentiate.

## 1. Competitor and prior-art table

| Product / research | What it does | Emotion source | Word-aligned? | Live? | Citation |
|---|---|---|---|---|---|
| Google Expressive Captions (Android, Live Caption) | Conveys "tone, volume, environmental cues and human noises"; intensity shown as capitalization (e.g. "HAPPY BIRTHDAY!"); labels sighs, gasps, applause. On-device, English, US only, announced 2024-12-05 | Audio (tone/volume); exact model undisclosed | Page does not say word-level (UNVERIFIED); capitalization suggests per-word emphasis | Yes, real time, on-device | https://blog.google/products-and-platforms/platforms/android/google-android-expressive-captions/ ; support: https://support.google.com/accessibility/android/answer/9350862 |
| Google Live Transcribe / Sound Notifications | Transcribes speech; sound events (dog bark, siren, baby cry, up to 10 sounds) via ambient sound recognition | Sound-event classification, not speaker emotion | n/a | Yes | https://www.androidauthority.com/google-sound-notifications-1166376 (secondary) |
| Apple Live Captions (iOS 16+) | System-wide captions for calls, FaceTime, media; English; still described as "beta" by one source | No emotion/tone feature found in sources I saw (not confirmed absent) | Text only | Yes | https://www.howtogeek.com/832972/how-to-use-live-captions-on-an-iphone/ (secondary; Apple's own page not fetched) |
| Hume AI Expression Measurement (prosody, "EVI") | Developer API scoring emotional expression from voice; Prosody model available in batch and streaming. Official docs say they measure "vocal expression, timing, and conversational dynamics" | Audio prosody | Word/sentence granularity per docs: UNVERIFIED (docs page 404'd when fetched) | Streaming available (per secondary summaries) | https://www.hume.ai/pricing ; https://dev.hume.ai/docs/expression-measurement ; https://www.eesel.ai/blog/hume-ai-pricing |
| AssemblyAI Sentiment Analysis | Positive/neutral/negative label + confidence per sentence, with start time in ms. Docs warn it interprets the transcript and may miss intended sentiment | TEXT | Sentence-level | Async/batch feature (live support not confirmed) | https://assemblyai.com/docs/models/sentiment-analysis |
| Deepgram sentiment | Text endpoint (/v1/read) scores text segments plus an average; audio endpoint tracks sentiment shifts through a transcript | TEXT (transcript-derived) | Segment-level | Not live per docs I saw | https://developers.deepgram.com/docs/text-sentiment-analysis |
| Fireflies sentiment | Labels transcript segments positive/negative/neutral from keywords/phrases | TEXT (per vendor blog) | Segment | Post-meeting | https://affine.pro/blog/fireflies-ai-sentiment-analysis-feature-tips (third-party) |
| Otter / Gong | Otter "OtterPilot for Sales" lists sentiment; Gong sentiment "tone and overall mood". Whether either uses audio is NOT confirmed. A competitor (Speak AI) claims tone-of-voice scoring beats Gong's sales-context scoring (marketing claim) | UNVERIFIED | Call/segment level | Post-call | https://www.trustradius.com:443/products/gong-io/reviews ; https://speakai.co/alternatives/speak-ai-vs-gong/ |
| Speechmatics | Real-time transcription over WebSocket; its own article treats sentiment as a separate layer on top of live transcript. Third-party listing claims emotion recognition (UNVERIFIED) | Layer on text | n/a | Yes | https://www.speechmatics.com/company/articles-and-news/how-to-use-sentiment-analysis-alongside-real-time-transcription-in-contact-centres |
| Microsoft Azure Speech | Real-time STT; no emotion/tone feature found in docs I saw (not confirmed absent) | none found | n/a | Yes | https://oneuptime.com/blog/post/2026-02-16-how-to-convert-speech-to-text-in-real-time-using-azure-speech-services/markdown (secondary) |
| RIT "Visualization of Speech Prosody and Emotion in Captions" (CHI 2023, Pataca et al.) | Interviewed 8 DHH people, built 3 caption styles (prosody, emotion, both), tested with 16 DHH users. Combined prosody+emotion beat conventional captions on emotion clarity; prosody alone did not beat conventional on emphasis | Audio-derived (research prototype) | Yes (caption-level styling) | Prototype | https://par.nsf.gov/servlets/purl/10420024 ; summary https://a11y-paradise.onrender.com/reviews/69e24bfba1bf5dfb4c17510e |
| Hassan and Burnett, CHI 2023 EA | Emotive caption design space tested with 28 DHH users; legibility/understandability need work; earlier studies mostly used hearing participants | n/a | n/a | n/a | https://par.nsf.gov/servlets/purl/10442631 |
| Later RIT-linked work (2025) | Real-time emotive captions for DHH STEM students (lower reported cognitive load); AR captioning with non-verbal cues; Pataca dissertation: emotion cues best trade-off of usefulness vs legibility | Audio | Yes | Real-time prototypes | https://arxiv.org/pdf/2603.15977 ; https://arxiv.org/pdf/2504.17171 ; https://repository.rit.edu/theses/12338 (publication status not verified) |
| Netflix SDH style | Tone conveyed by bracketed qualifiers ("whispering", "voice breaking") and sound labels only when not visually identifiable | Human-authored | Line level | No (pre-produced) | https://backlothelp.netflix.com/hc/en-us/articles/215758617 ; cheat sheet https://keywordsla.helpshift.com/hc/en/3-my-app/faq/97-sdh-cheat-sheet-for-netflix (third-party). BBC guidance: NOT FOUND |

Our own model: emotion2vec (self-supervised speech emotion representation), ACL Findings 2024, reported to beat baselines on IEMOCAP with a linear head and to improve across 10 languages: https://aclanthology.org/2024.findings-acl.931 . Cross-corpus numbers not retrieved.

## 2. Novel vs not novel (honest)

NOT novel:
- Emotion-aware captions as a concept (Google Expressive Captions, shipped; RIT research since at least 2023).
- Speech emotion recognition and prosody APIs (Hume, emotion2vec).
- Text sentiment on transcripts (AssemblyAI, Deepgram, Fireflies).
- Using color/typography to show emotion (studied in the RIT papers).

Plausibly novel (claim with care; "we did not find"):
1. Word-anchored, animated cloud visuals (color plus shape) driven by a learned emotion classifier, rather than caps/labels. Distinct from Google's text-style cues.
2. Words-vs-voice mismatch flag: compare text sentiment of the exact words against voice emotion and surface disagreement (sarcasm, masking, "I'm fine"). Existing text-sentiment APIs only see words; prosody APIs only see voice. I did not find a caption product that shows the disagreement. Caveat: Hume could trivially be combined with a text sentiment API, so this is a feature gap, not a moat.
3. Time-alignment of 2-second emotion windows to Scribe word timestamps. This is an engineering choice; the 2 s window means emotion is smeared across ~5 words (our limitation, say it first).

Honest weaknesses: no user study of our own; accuracy of acted-speech-trained models on spontaneous speech is unproven; Google's on-device, free, OS-level distribution beats us on reach.

## 3. Market and business

### Sizes (analyst estimates vary widely; cite as ranges)
- Captioning and subtitling solutions 2025: about $6.7B (Global Market Insights, to $16.5B by 2035, 9.4% CAGR) vs $34.3B (Market Research Future, much broader scope). https://www.gminsights.com/industry-analysis/captioning-and-subtitling-solutions-market ; https://www.marketresearchfuture.com/reports/captioning-subtitling-solution-market-28263
- Speech analytics 2025: about $3.5B (Mordor) to $5.3B (Spherical Insights); others in between ($3.7B IMARC, $4.9B Fortune BI). https://www.mordorintelligence.com/industry-reports/global-speech-analytics-market-industry ; https://www.imarcgroup.com/global-speech-analytics-market ; https://www.fortunebusinessinsights.com/sprachanalysemarkt-108836 . These are market-research press figures, not audited; recommend saying "roughly $3-5B".
- Need: WHO says 1.5B people live with some hearing loss, about 430M need rehabilitation; projection 2.5B by 2050 (2021 World Report on Hearing). https://www.who.int/news-room/facts-in-pictures/detail/deafness ; https://healthpolicy-watch.news/2-5-billion-people-could-experience-hearing-loss-by-2050-projects-the-first-world-report-on-hearing/ . US: about 15% of adults (37.5M) report some trouble hearing (self-reported). https://www.nidcd.nih.gov/health/statistics/quick-statistics-hearing

### First customers (my reasoning, not sourced)
1. Campus disability services / DHH students (matches "Student and community needs" track; RIT work gives evidence of demand). Why first: a buyer exists, legal obligation to provide captions, and a pilot is feasible.
2. Telehealth and counseling/training platforms where the user is a clinician or the person themselves (note EU/US consent issues below).
3. Language learners and neurodivergent users who find tone hard to read (hypothesis; no evidence gathered). Pairs with the "multilingual" angle, but emotion2vec language coverage must be tested.
4. Creator tools: caption styling for video (Small-business/creator track). Lower regulation, but weaker pain.
5. Customer-support QA (largest money, most crowded and most regulated; Gong/Hume-type competitors). Treat as expansion, not wedge.

### Business model (plausible)
- Free for individual DHH users (reputation, data-free). Paid per-seat or per-hour license to institutions (disability services, telehealth) as a captioning layer; API/SDK plus Zoom/Meet overlay for creators. Variable cost: Scribe streaming plus local emotion model (local inference keeps audio on the device, lowering cost and privacy exposure). Cost benchmark: Hume audio was listed at about $0.064/min by third parties but Hume no longer publishes rates (quoted via sales), so our local model is a cost and privacy advantage. https://www.eesel.ai/blog/hume-ai-pricing ; https://www.hume.ai/pricing (no price shown). Figures UNVERIFIED.

### Regulation
Tailwinds:
- US DOJ ADA Title II web/mobile rule (WCAG 2.1 AA). April 2026 interim final rule delayed deadlines by one year: large entities (50,000+) to April 26, 2027; smaller entities reported as April 2027 or 2028 by different sources (UNVERIFIED; check Federal Register). Extension reportedly challenged in court. I did not confirm how it treats live captions specifically, so do not claim it mandates live captions. https://www.mondaq.com/unitedstates/media-entertainment-law/1782220/doj-extends-ada-title-ii-digital-accessibility-deadlines-by-one-year ; https://www.adatitleiii.com/2026/04/doj-extends-ada-title-ii-website-accessibility-deadlines-for-governmental-entities-but-litigation-and-compliance-risks-remain/
- Section 508: not researched; UNVERIFIED, omit from pitch unless checked.

Headwind: EU AI Act Article 5(1)(f) prohibits "the use of AI systems to infer emotions of a natural person in the areas of workplace and education institutions, except where the use of the AI system is intended to be put in place or into the market for medical or safety reasons". Text: https://artificialintelligenceact.eu/article/5/ . Commentary: prohibition applies since 2 Feb 2025; Article 3(39) defines emotion recognition via biometric data; outside workplace/education such systems are "high risk" (Annex III); Commission guidelines reportedly extend to intentions; customer-interaction use is excluded per Freshfields. https://fpf.org/blog/red-lines-under-eu-ai-act-unpacking-the-prohibition-of-emotion-recognition-in-the-workplace-and-education-institutions/ ; https://technologyquotient.freshfields.com/post/102kfql/eu-ai-act-unpacked-25-european-commission-releases-critical-ai-act-implementati . Penalties are in Article 99 (not verified here; one vendor article claims 7% turnover, UNVERIFIED).
Implication for us: a classroom deployment in the EU that infers student emotion is the exact prohibited setting, and a campus pilot is "education institution". Mitigations (my reasoning, not legal advice): user-controlled assistive tool where the DHH user sees the cue about others' speech; consider whether a medical/assistive exception applies (needs counsel); keep US-first; make emotion layer opt-in and never store or report emotion about a person to an employer or institution.

## 4. Likely judge questions and answer material

**Q1. "Isn't emotion AI pseudoscience?"**
Honest answer: The strongest critique targets inferring internal emotional states from FACES. Barrett et al. (2019, Psychological Science in the Public Interest 20(1):1-68) find facial configurations do not reliably, specifically or generalizably map to emotional states, and expression varies by culture, context and person. https://www.psychologicalscience.org/publications/emotional-expressions-reconsidered-challenges-to-inferring-emotion-from-human-facial-movements.html . So we should (1) not claim we read feelings; say we visualize acoustic "vocal tone" that listeners also perceive, labelled as a cue, (2) use hedged wording ("sounds angry"), (3) show model uncertainty, (4) point to DHH users who say they miss tone; the RIT study found combined prosody+emotion improved emotion clarity for 16 DHH users. https://par.nsf.gov/servlets/purl/10420024 . Also admit emotion2vec is trained largely on acted data (UNVERIFIED for the specific training mix) and accuracy in the wild is untested.

**Q2. "How is this different from Hume?"**
Hume is a developer API that outputs expression scores from voice; it is not a caption product, and its rates are sales-quoted. We are an end-user, word-aligned caption experience with a local model (no audio sent for emotion) and a words-vs-voice mismatch layer. Honest: Hume could build this; our edge is product focus on accessibility, privacy and UX. Sources: https://dev.hume.ai/docs/expression-measurement ; https://www.hume.ai/pricing

**Q3. "Doesn't Google already do this?"**
Yes, partly: Expressive Captions conveys tone/volume and sounds, English/US, Android only. https://blog.google/products-and-platforms/platforms/android/google-android-expressive-captions/ . Ours: any device via browser, richer visual encoding than capitalization, per-word anchoring, mismatch flag. Don't overclaim that Google lacks word-level analysis (unverified).

**Q4. "Privacy?"**
Emotion model runs locally; only transcription audio goes to ElevenLabs (check their retention terms: not researched, UNVERIFIED). No storage of emotion profiles; opt-in; no employer/institution reporting. Voice emotion is biometric-adjacent: EU AI Act defines emotion recognition via biometric data (Art. 3(39)). https://fpf.org/blog/red-lines-under-eu-ai-act-unpacking-the-prohibition-of-emotion-recognition-in-the-workplace-and-education-institutions/

**Q5. "Why would anyone pay / what's next?"**
Wedge in disability services (legal obligation exists, buyer exists), validate with a DHH user study (RIT-style), then telehealth and creators. Gather: willingness to pay is untested.

**Q6. "Mismatch flag: won't it produce false accusations of lying or sarcasm?"**
Frame as "tone differs from words", never "insincere". Show as a soft marker the reader interprets. Needs test data; accuracy unknown.

## 5. Gaps (not verified)
Hume official prosody docs and current price; Apple's own Live Captions page; BBC subtitle guidance; Section 508 text; ElevenLabs data retention; emotion2vec cross-corpus numbers; Gong/Otter audio use; Azure/Speechmatics emotion support; smaller-entity ADA date.
