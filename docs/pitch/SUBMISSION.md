# Submission draft (edit before submitting; deadline 4 PM PT)

Required: working app or reproducible demo, short backup video, user and problem, user feedback, tools used. Sources: `docs/research/R1`-`R5`.

## Project
**Emotional Translator**: live captions that also show how something was said.

## User and problem
People who read captions, especially people with hearing loss, get the words but not the tone. A line like "I'm fine" looks the same whether it was said warmly or through tears. The WHO projects nearly 2.5 billion people will have some degree of hearing loss by 2050, and about 15 percent of US adults (37.5 million) report some trouble hearing (self-reported, not a count of Deaf people) (R3 s1). A 2023 CHI study with 16 Deaf and hard-of-hearing participants found an emotion-based caption style beat conventional captions at showing emotion and emphasis, at some cost to legibility (R3 s1). Studies are small, so we treat the need as supported by early research, not proven. Other possible users (cochlear-implant users, language learners, some neurodivergent people) are hypotheses, and we position the tool as an optional second channel, not a fix for anyone (R3 s2-s4).

## What it does
- Streams live speech and shows the transcript, with provisional words that settle into stable text.
- Draws a colored, shaped cloud around the exact words for the detected vocal cue (shape and color, so it does not rely on color alone). Intensity changes size and saturation.
- Flags "Words and voice differ" when text sentiment and detected vocal tone point opposite ways. It does not claim sarcasm.
- Phrase inspector showing relative model scores; toggles for labels, a color-blind-safe palette and reduced motion.
- A labeled replay mode that plays saved events through the same UI (never presented as live).

## How it is built
The browser captures mic audio (AudioWorklet, 16 kHz PCM) and streams it to a FastAPI backend. The backend relays audio to ElevenLabs Scribe v3 Live for words and timestamps (R1) and runs emotion2vec+ Large locally in two-second windows for nine-category scores (R2). The backend aligns window scores to the Scribe word timestamps. In the browser, a DistilBERT SST-2 model (transformers.js, Web Worker) scores text sentiment for the differ flag (R5 s4). React/Vite renders text and animated SVG clouds.

## Tools used
- ElevenLabs Scribe v3 Live (realtime speech-to-text with word timestamps), `scribe_v3_live` over WebSocket.
- emotion2vec+ Large (`iic/emotion2vec_plus_large`) via FunASR / ModelScope. Attribution: emotion2vec+ by the emotion2vec authors, used under the FunASR MODEL_LICENSE; we do not redistribute the weights (R2 s5).
- transformers.js with `distilbert-base-uncased-finetuned-sst-2-english` (Apache-2.0 base model) (R5 s4).
- FastAPI (Python) backend; React and Vite frontend.
- Claude Code (AI coding assistant).
- Replit: [FILL only if actually used; otherwise delete this line].

## Limitations (stated plainly)
- Detected vocal cues are model estimates, not true feelings. Scores are relative support (R2 s2).
- emotion2vec+ Large has no published benchmark; paper numbers are for the original model on acted data (R2 s4). No accuracy figure is claimed for this app. [FILL measured results if any.]
- Two-second windows smear a cue across several words (R4 s2).
- Voice, accent and noise may affect results; atypical speakers may be misclassified. Not tested for bias.
- Live audio goes to ElevenLabs for transcription; we have not reviewed their retention terms (R4 s5).
- Text sentiment is a binary movie-review model; it can be noisy on short lines (R5 s4).
- Not validated for accessibility use. No clinical claims. EU deployment (AI Act Art. 5(1)(f), workplace and education) not assessed (R3 s6).
- Prior art: Google Expressive Captions and RIT research exist (R4 s1). We did not find a shipped caption product with a words-vs-voice flag (not proof of absence).

## Reproducing the demo
See `docs/SETUP.md` and `docs/DEMO.md`. Live mode needs an ElevenLabs key and the downloaded model. Keyless replay: [FILL exact command (for example the replay start or `npm run build:replay`) and the fixture name once verified].

## Backup video
[FILL link] (shot list in `BACKUP_VIDEO.md`; any replay segment is labeled on screen.)

## User feedback
Fill in only what people actually said, with their permission. Do not paraphrase into praise. If none, write "None collected yet."

| # | Who (role only, anonymous unless they agreed to be named) | Date and place | What they said (their words) | Permission to quote (Y/N) | What we would change |
|---|---|---|---|---|---|
| 1 | | | | | |
| 2 | | | | | |
| 3 | | | | | |

Summary (written after the table, one or two sentences, claiming nothing the table does not show): [FILL]
