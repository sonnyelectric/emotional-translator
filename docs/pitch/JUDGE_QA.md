# Judge Q&A: the 12 hardest likely questions

Short, honest answers. Sources: `docs/research/R1`-`R5`. Fill bracketed items from your own measurements. If you did not measure it, say "I have not measured that." Reconciled with `SYNTHESIS.md` s4.

**1. How accurate is it?**
"I do not have an accuracy number for this setup, and I will not invent one. The model's paper reports about 72 percent on an acted four-class benchmark for the original emotion2vec, not for the Plus Large version we use. Its worst reported result was natural Mandarin TV speech (R2 s4). We use rehearsed lines and I will tell you when it misses. A real accuracy test is the first thing we would do next." Cite: R2 s4.

**2. Isn't emotion AI pseudoscience?**
"The strongest critique, Barrett and colleagues in 2019, is about inferring inner feelings from faces. They find expressions vary by culture, situation and person (R3 s6, R4 s4 Q1). So we do not claim to read feelings. We show a detected vocal cue, with uncertainty, that the reader can switch off. The scores are relative model support, not certainty. The goal is a second channel that listeners hear naturally and captions drop."

**3. Where does the audio go? Privacy?**
"Live transcription audio is streamed to ElevenLabs Scribe. The emotion model runs on this laptop, so audio is not sent anywhere for tone scoring. Normal sessions are not stored (docs/DEMO.md). I have not reviewed ElevenLabs retention terms (R4 s5), so I will not promise anything about their side. Voice emotion is biometric-adjacent, so it should be opt-in, and we store no emotion profiles." Cite: docs/DEMO.md, R4 s4 Q4.

**4. EU AI Act?**
"Article 5(1)(f) bans inferring emotions in workplace and education settings, except for medical or safety reasons (R3 s6). A classroom pilot in the EU could fall under it. We have not assessed EU deployment and I am not a lawyer. Our design points: the reader chooses it for themselves, it shows a cue about the speaker's voice, it stores nothing and reports to no institution. Whether that is enough is a legal question. We would start US-first and get counsel." Cite: R3 s6, R4 s3.

**5. How is this different from Google Expressive Captions?**
"Google ships it on Android: capital letters for intensity, stretched words, sound labels, on-device, English only, in the US, UK, Canada and Australia on Android 15 and above (SYNTHESIS s3 check 7). Credit to them, and their reach beats ours. Ours is browser-based, shows a shape and color anchored to the exact words, and flags when the words and the voice differ. I do not know whether Google's system works at word level, so I will not claim it does not (R4 s4 Q3)."

**6. How is this different from Hume?**
"Hume is a developer API that scores vocal expression. It is not an end-user caption product (R4 s1, s4 Q2). We are the product layer: word-aligned display, local model, and the differ flag. Honestly, Hume could add this. Our edge is focus on accessibility and privacy. I could not verify Hume's current pricing or word-level support (R4 s5)."

**7. What is the latency?**
"[FILL from the docs/live benchmark: p50/p95 from end of phrase to cloud, and window scoring time.] No published latency exists for this model on a laptop (R2 s3), so only our own measurement counts. Known limit: emotion is scored in 2-second windows, so a cue is smeared across about five words (R4 s2). Long speech can also delay when Scribe commits text (docs/DEMO.md)."

**8. What if it is wrong?**
"It will be sometimes. That is why scores are shown as relative support, the cloud is a soft cue and not a verdict, the reader can toggle it off, and the inspector shows the underlying scores. The differ flag says 'tone and words differ', never 'insincere' or 'sarcastic' (R5 s4). Research has not shown that automatic audio-emotion captions help: a study with 28 DHH viewers found no significant difference between three emotive caption styles (SYNTHESIS s4 line 6). A user study is the next step."

**9. What is the business model?**
"Free for individual Deaf and hard-of-hearing users. Paid per-seat or per-hour for institutions: campus disability services first, then telehealth, then creator tools (R4 s3, my reasoning, not sourced). Willingness to pay is untested. Market numbers vary widely by analyst, roughly $3-5B for speech analytics (R4 s3), so I treat them as context, not a forecast. Our variable cost is Scribe at $0.22 per hour of audio (R1 s2) plus local compute."

**10. Why ElevenLabs?**
"Scribe v3 Live gives streaming words with word-level timestamps, which our alignment depends on (R1 s1). Without precise timing we could not anchor the cloud to the right words. It is central to the product, not a bolt-on. At $0.22 per hour it also keeps cost low (R1 s2). We use the raw WebSocket so we can see every message type."

**11. Who actually asked for this? Where is your user evidence?**
"Published research: a 16-person study with Deaf and hard-of-hearing users, and a 24-person study where participants wanted toggles and preferred clean text with color over cartoon icons (R3 s1). Our own evidence is [FILL: N attendee interviews today, with their permission; otherwise say 'none yet beyond the literature']. I will not present anything I did not hear."

**12. Doesn't it misjudge accents, disabled speakers or other languages?**
"Likely, yes. I found no evaluation of bias by accent, age or gender, and none on short clips or spontaneous speech (R2 s4). Speakers with atypical voices may be misclassified; that is a general concern for which I have no source (R3 s6). That is a real limit. The user chooses to view it, and cues are about the voice, not a score on the person."

## Bonus short answers
- "Does it translate?" No. Scribe transcribes in the language spoken and does not translate (R1 s3). Translation is future scope.
- "Did you build the emotion model?" No. emotion2vec+ Large is by its authors, run via FunASR; we credit them (R2 s5). We built the product and the alignment.
- "Is the mockup what you built?" The mockup shows categories and weight sliders we did not build. We show only the model's real labels (PLAN D5).
- "Does it work for autistic people?" We do not claim that. Research is mixed (R3 s2). It is an optional extra channel for anyone, and we would ask autistic users before making claims.
