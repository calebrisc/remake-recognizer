# Remake Recognizer

Finds underground rap remakes of classic songs by comparing what I call melodic DNA. The short version: a lot of underground tracks are built on flips of older beats, and you can catch them by looking at the *shape* of the melody instead of the actual audio. Sample detection tools miss these because nothing was sampled — the melody was replayed. The shape survives even when the sound doesn't.

## How the matching works

`beat_matcher_v5.py` does the whole pipeline:

1. Demucs splits the track into stems and keeps the "other" stem (melody, synths, guitar — the part that carries the hook).
2. A CQT pass pulls out dominant frequency events and turns them into directional movements: up a third, down a fifth, hold, etc.
3. It then looks for repeating direction sequences with self-consistent jump sizes. That repeating sequence is the song's DNA.
4. Candidate tracks get the same treatment, tempo-matched, and cross-checked. If the DNA shows up, it's probably a remake.

The key insight is that averages kill everything. Every version of this that averaged energy over time windows produced mush where every song looked the same. What works is event-based encoding: a new entry only when something actually happens (a drum hit, a vocal onset, a melody change). Dense songs get long DNA, sparse songs get short DNA, and that's correct behavior.

## The Quality DNA format (v3)

Beyond matching, there's a second encoding that describes an entire song as a sequence of 9-character codons, one per sonic event:

```
[gap][vocal energy][vocal freq][drum energy][drum freq][melody energy][melody freq][bass energy][bass freq]
```

Gap character is time since the last event (`.` = instant, `_` = long silence). Energy runs `_` (dead) through `5` (max). Frequency zones run `L` (sub-bass) to `T` (above 4kHz). All four stems are normalized against the same global max, so a `2` on vocals and a `2` on bass mean the same actual loudness — v2 normalized per-stem and it made every mix look flat, which was wrong.

A 3-minute song comes out to somewhere between 300 and 1500 codons depending on density. The DNA describes what a song *is*; rating it is a separate problem (see `brain_response_all.txt` for the start of that).

## What's in this repo

The data is here so you can actually see what the encodings look like without running anything:

- `all_tracks_dna_v3.txt` — full v3 DNA for all 138 tracks in my test corpus. This is the current format. (`_v2` files are older normalization, kept for comparison.)
- `dna_cache/` — extracted DNA for the original songs I search against (Beat It, Billie Jean, Juicy, etc.)
- `results/` — per-track flow analysis output
- `*_batch.json` — YouTube search batches by artist, used to build the corpus
- `song_ratings.json` — my manual ratings, intended as training data for the rating algorithm
- `CATCHUP.md` — working notes with the full design history and the reasoning behind the format decisions

Audio itself isn't included, only links and derived data. The pipeline downloads via yt-dlp when you run it.

## Setup

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

You'll also need demucs and yt-dlp available. First run on a song is slow (stem separation); results get cached.

## Usage

```bash
# Process an original song (one time, builds DNA cache):
python beat_matcher_v5.py original "Beat It" "https://youtube.com/watch?v=..."

# Search for remakes automatically:
python beat_matcher_v5.py search "Beat It"

# Test a specific candidate:
python beat_matcher_v5.py test "Beat It" "https://youtube.com/watch?v=..."

# List cached originals:
python beat_matcher_v5.py list
```

## Caveats

This is a personal research project, not a product. The matcher works well enough to have found real remakes I didn't know about, but the rating side ("is this remake actually good") is unfinished — it needs more human training data than one person's ratings. If you do something interesting with the DNA format I'd genuinely like to hear about it.
