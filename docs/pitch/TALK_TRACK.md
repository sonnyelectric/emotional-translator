# Talk track: Emotional Translator (table-side, Berkeley Startup Sprint, 2026-11-20)

Sources: `docs/research/R1`-`R5` (cited as R1..R5 plus section). Reconciled with `docs/research/SYNTHESIS.md` s4 (pitch-safe and do-not-say lists) and its corrections.

Rubric tags: **[P]** Problem and user evidence (25), **[U]** Usefulness and product experience (25), **[T]** Technical execution (25), **[D]** Differentiation and next-step business (15), **[C]** Demo clarity (10).

Wording rules (R3 s6, R2 s4): say "detected vocal cues" and "sounds angry". Never "reads your feelings", "true emotion", "detects sarcasm" or "lie detector". Say "people with hearing loss", not "deaf people", for the numbers. Do not say when or where the app was built.

---

## A. The 3-minute version (about 430 spoken words)

**Beat 1. Hook (0:00-0:20) [P]**
SAY: "Picture reading live captions in a meeting. Someone says: 'I'm fine.' The captions say: I'm fine. What the captions do not show is that it was said through tears. The words arrived. The tone did not."
(This is a thought exercise, not a claim about a real person. Do not present it as a true story.)
POINT: Nothing yet. Make eye contact. Laptop is on the idle screen.

**Beat 2. Problem and evidence (0:20-0:50) [P]**
SAY: "The WHO projects nearly 2.5 billion people will have some degree of hearing loss by 2050 (R3 s1). In the US, about 15 percent of adults, 37.5 million, report some trouble hearing. That is self-reported, so it is not a count of Deaf people (R3 s1). The WHO lists social isolation and loneliness among the effects of unaddressed hearing loss (R3 s1). And captions drop tone. In a 2023 CHI study with 16 Deaf and hard-of-hearing participants, a caption style that showed emotion did better than conventional captions at showing emotion and emphasis (R3 s1, R4 s1). Another study with 28 DHH viewers found no significant difference between three emotive caption styles (SYNTHESIS s4 line 6). So this is early, not proven."
POINT: Hold up one finger per number if it helps. No slides needed.

**Beat 3. Live demo (0:50-2:10) [U][C]**
SAY: "Here it is live. I press Start." (Press START on the LIVE screen. Disclose once: "Transcription audio goes to ElevenLabs; the tone model runs on this laptop." R4 s4 Q4, docs/DEMO.md.)

Say each line into the mic with a pause between (exact delivery notes in `REHEARSAL.md`):
1. Neutral: "The meeting starts at three o'clock tomorrow." POINT: words appear faint (provisional), then settle; little or no cloud. "Flat voice, no strong cue."
2. Angry: "I told you three times, and nobody listened!" POINT: a jagged cloud around the words. "Jagged shape, warm color. Shape and color change with the detected cue, and so does intensity."
3. Sad: "I just feel really tired of trying." POINT: a rounded, drooping cloud, slower. "Different shape, not only a different color, so it still works if you cannot tell the colors apart (R5 s5, WCAG 1.4.1)."
4. Happy: "We got the grant, I cannot believe it!" POINT: buoyant lobed cloud.
5. Words versus voice: say angrily, "Oh great, that's just perfect." POINT: the "Words and voice differ" badge on that sentence. "The words read positive. The voice carries an angry cue. We do not say sarcasm. We say they differ. That can be sarcasm, a joke, a quote, or the model being wrong (R5 s4)."
POINT: Click one phrase to open the inspector. "These are relative model scores for the 2-second window, not certainty."
If a line misses, say so plainly: "That one missed. These are estimates, and I rehearsed these lines." Move on.

**Beat 4. How it works in one breath (2:10-2:30) [T]**
SAY: "ElevenLabs Scribe v3 Live streams the words with timestamps. A model, emotion2vec plus Large, runs on this laptop and scores the vocal tone in two-second windows. The backend lines those scores up with the exact words. A small text model in the browser compares word sentiment to vocal tone for the differ flag." (R1 s1, R2 s2-3, R5 s4.)
POINT: Gesture at laptop, then the screen. Do not give latency numbers unless you have the measured p50/p95 from `docs/live/` (R2 s3: none published).

**Beat 5. Differentiation (2:30-2:50) [D]**
SAY: "Google already ships Expressive Captions on Android. It uses capital letters for intensity, stretches words like "amaaazing", and labels sounds. It is on-device and English-only, rolled out in the US, UK, Canada and Australia on newer Android phones (SYNTHESIS s4 line 7, check 7). Credit to them. Researchers at RIT tested this idea with Deaf users too. What is different here: it runs in a browser on any device, each cloud is anchored to the exact words with shape and color rather than capital letters, and it flags when words and voice disagree. We did not find a shipped caption product that does that. That is 'not found', not proof that none exists (R4 s0, s2)."
POINT: Point at the Differ badge again.

**Beat 6. Business next step and close (2:50-3:00) [D][P]**
SAY: "Next step is a small study with Deaf and hard-of-hearing users, then campus disability services as first buyer, since a captioning obligation and a buyer already exist (R4 s3). Free for individuals. Willingness to pay is untested, so I will not claim it. Today I am asking two or three of you for three minutes of feedback. Thank you."
(If you gathered feedback today, add one real, permitted sentence from `USER_FEEDBACK.md`. Otherwise do not mention it.)

---

## B. The 60-second version (rushed judge, about 150 spoken words)

> Captions give you the words but drop the tone. Someone says "I'm fine" through tears, and the caption just says "I'm fine." The WHO projects nearly 2.5 billion people will have some hearing loss by 2050, and a 16-person study found captions that show emotion beat conventional ones at conveying it.
>
> Watch. [Press Start. Say angrily:] "I told you three times, and nobody listened!" That jagged cloud is a detected vocal cue, anchored to those exact words. [Say sadly:] "I just feel really tired of trying." Rounded, different shape. [Say angrily:] "Oh great, that's just perfect." The words read positive, the voice does not, so it flags "words and voice differ".
>
> ElevenLabs Scribe v3 Live gives words and timing; a tone model runs on this laptop; the backend aligns them. Google has Expressive Captions on Android, English-only. Ours is browser-based, word-anchored, and flags word-voice gaps. Next: a study with Deaf and hard-of-hearing users.

Rubric tags for the 60 s version: problem [P], demo [U][C], build [T], differentiation and next step [D].

---

## C. If the judge interrupts

- Answer the question first, then return to the beat you were on. Answers are in `JUDGE_QA.md`.
- If the live demo fails, switch to the "if live fails" script in `REHEARSAL.md`. Never present replay as live.

## D. Claims we do not make

- No accuracy figure for our setup. The emotion2vec paper numbers are for the original model, on acted data (R2 s4), not for emotion2vec+ Large.
- No latency figure unless measured and written down in `docs/live/`.
- No "works for autistic people", "helps cochlear implant users", or "works in all languages": these are hypotheses (R3 s2, s4; R2 s4).
- No EU deployment claim. "We have not assessed EU deployment; schools and workplaces would need legal review." (R3 s6, R4 s3.)
- Do not show or describe the mockup's "Disdain/Sarcasm", "Embarrassment" or weight sliders as working. They are not built (PLAN D5).
- Do not say Google's captions are US-only or that Google lacks word-level analysis (SYNTHESIS s4). Do not say "first" or "nobody does this".
- Do not quote ElevenLabs credit counts; the prize is confirmed on the event page (https://luma.com/yog7cocv) but credit counts are unverified.
- Do not disparage FunASR/emotion2vec (their license s4.2, R2 s5).
