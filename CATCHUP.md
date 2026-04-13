# DJ Claudito — Session Catchup (2026-04-12/13)

## What Happened This Session

Major development session on the Quality DNA system. Started from scratch, iterated through multiple versions, ended with a working DNA encoding system and the beginning of a rating algorithm that still needs human training data.

## The Quality DNA System (v3 — current)

### What It Does
Takes any song, separates it into 4 stems (vocals, drums, melody, bass) using Demucs, then encodes the entire song as a sequence of **codons** — one per sonic event.

### Codon Format (9 characters each)
```
[gap][V energy][V freq][D energy][D freq][M energy][M freq][B energy][B freq]
```

- **Position 1 — Event gap** (time since last event):
  `.` instant (<50ms) | `:` very fast | `-` fast | `=` moderate | `~` slow | `_` gap

- **Positions 2-3 — Vocals** [energy][freq zone]
- **Positions 4-5 — Drums** [energy][freq zone]
- **Positions 6-7 — Melody** [energy][freq zone]
- **Positions 8-9 — Bass** [energy][freq zone]

- **Energy**: `_` dead(<.05) | `1` quiet | `2` low | `3` mid | `4` loud | `5` max
- **Freq zones**: `L` sub(<100Hz) | `l` low(<250) | `m` mid(<500) | `M` hi-mid(<1k) | `h` high(<2k) | `H` bright(<4k) | `T` top(>4k)

### Key Design Decisions (DO NOT UNDO THESE)
1. **NO AVERAGES** — User has been extremely clear. Averages destroy meaningful data. Every metric that averaged got rejected.
2. **Event-based timing** — Codons are NOT fixed time windows. Each codon boundary is triggered by an actual sonic event (drum hit, vocal onset, melody change, bass change). This means DNA length varies — dense songs have more codons. A 3-minute song might have 300-1500 codons.
3. **Shared normalization** — All 4 stems normalized against the SAME global maximum. So energy levels reflect actual relative loudness in the mix. (v2 had per-stem normalization which made everything look equal — that was wrong.)
4. **Song flow, not artist flow** — The DNA describes what the WHOLE SONG is doing at each moment, not just what the vocalist is doing. Every element gets equal representation.
5. **The DNA describes what a song IS. Rating comes separately.** The DNA is a description layer. The rating/quality assessment is a separate algorithm ("brain algorithm") that reads the DNA.

### What's In The Repo

**DNA output files:**
- `all_tracks_dna_v3.txt` — Full v3 DNA (shared normalization) for all 138 tracks. THIS IS THE CURRENT VERSION.
- `playlist_dna_v2.txt` — Earlier version (per-stem normalization, only playlist). Outdated.
- `all_tracks_dna_v2.txt` — Earlier version for all tracks. Outdated.
- `song_flow_dna.txt` — Earlier 4-char codon format (leader/support/together/direction). Outdated.
- `full_song_dna.txt` — Earlier VDMB energy-only format. Outdated.

**Analysis/rating files:**
- `song_ratings.json` — Attempted quality ratings 0.1-10 for all 138 tracks. THE RATINGS ARE CURRENTLY WRONG/INVERTED. The scoring components don't distinguish good from bad — they measure structural properties that don't map to quality. Needs human training data to calibrate.
- `brain_response_all.txt` — Expectation/surprise/resolution analysis. Numbers are too similar across songs to be useful yet.
- `full_dna_results.json` — Transition analysis (gentle/violent percentages) for all tracks.
- `song_flow_results.json` — Earlier song-flow analysis with leader/handoff metrics.

**Batch files (YouTube URL lists):**
- `redonkulous_batch.json` — User's Haitian trap playlist (31 tracks)
- `21savage_batch.json`, `juicewrld_batch.json`, `joeybadass_batch.json`, `kanye_batch.json`, `kanye_tyler_batch.json`, `metroboomin_batch.json`, `lilwayne_batch.json`, `wayne_snoop_batch.json`, `metro_tory_batch.json` — Artist top-10 batches

**Separated stems:** `separated/` directory has all 138+ tracks fully separated into vocals/drums/other/bass WAV files. These are large but essential — they take 10-20 seconds each to generate on MacBook, much longer on Steam Deck.

**Results:** `results/` directory has per-track flow analysis JSON files (the old metric system — vocal consistency, rhythm alignment, etc). These are from the earlier approach and mostly superseded by the DNA system.

## What Works
- DNA encoding is solid. The v3 codons accurately describe what every element is doing at every moment.
- 138 tracks fully processed with separated stems and DNA.
- Event-based timing captures the actual rhythm of the song, not arbitrary time windows.
- Shared normalization shows real relative loudness between stems.

## What Doesn't Work Yet
- **Quality rating** — We can describe a song perfectly but can't determine if it's good or bad from the description alone. The scoring attempt (song_ratings.json) has the scale inverted and the components don't actually correlate with quality.
- **"Brain algorithm"** — The expectation/surprise/resolution detector produced numbers that were too similar across all songs. Needs rethinking.
- **Human training data** — We need the user to rate ~20-30 songs so we can find which DNA patterns correlate with "good."

## Key Insights From The Session
1. **Pitch instability can be GOOD** — If vocals follow the instrumental's pitch contour (vocal-instrumental coherence), "unstable" pitch is actually musicality. Thuggin' Under GOD scored #1 on this.
2. **Repetition can be good or bad** — Patience (good repetition, soulful) vs Gucci Gang (bad repetition). The difference isn't detectable from energy/transition data alone.
3. **Flow isn't smoothness** — Soldier Walk has the "roughest" transitions but flows perfectly because the constant switching IS the flow. Flow is whether each moment BELONGS next to the last, regardless of how much changes.
4. **Frequency architecture matters** — Songs where each element has its own frequency zone (bass low, melody mid, voice bright) feel more intentional. This is in the DNA via freq zone characters.
5. **The "brain response" to music involves expectation, surprise, and resolution** — But we haven't figured out how to detect this from the DNA yet. The current attempt just measures statistical variance, not musical meaning.
6. **The DNA is a new language** — Nobody else is building human-readable per-event descriptions of every element's energy and frequency position across entire songs. This is genuinely novel.

## Next Steps
1. Get user ratings on 20-30 songs to train the quality algorithm
2. Rethink the brain algorithm — probably needs to understand musical patterns (harmony, rhythm) not just energy envelopes
3. Consider the frequency architecture + expectation/surprise/resolution as separate algorithm layers that read the DNA
4. The DNA itself might need more data per codon eventually — but get the rating working on current data first

## Tech Notes
- Python 3.12 venv (rebuilt from 3.9 due to yt-dlp/SSL issues on Mac)
- yt-dlp 2026.3.17, demucs htdemucs model
- matplotlib installed for visualizations
- deno installed for yt-dlp JS runtime
- The `separated/` and `clips/` directories are LARGE (many GB of WAV files). The `.gitignore` should exclude them.
- All DNA/analysis output files are small (text/JSON) and should be committed.
