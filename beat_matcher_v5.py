#!/usr/bin/env python3
"""
DJ Claudito Beat Matcher v5 — DNA Contour Matching

Finds remakes of classic songs by comparing melodic DNA patterns.
Uses demucs to isolate the "other" stem (melody/synths/guitar),
extracts directional movement events from CQT, finds repeating
DNA patterns with consistent jump sizes, and searches for those
patterns in candidate tracks.

Usage:
    # Process an original (builds DNA cache):
    python beat_matcher_v5.py original "Beat It" "https://youtube.com/watch?v=..."

    # Search for remakes:
    python beat_matcher_v5.py search "Beat It" "query1" "query2" ...

    # Test a specific candidate against an original:
    python beat_matcher_v5.py test "Beat It" "https://youtube.com/watch?v=..."

    # List cached originals:
    python beat_matcher_v5.py list
"""

import subprocess
import os
import sys
import json
import re
import numpy as np

# Force unbuffered output so progress shows in real time
os.environ["PYTHONUNBUFFERED"] = "1"
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(line_buffering=True)

# Base directory — defaults to script location, override with DJ_CLAUDITO_DIR env var
SD = os.environ.get("DJ_CLAUDITO_DIR", os.path.dirname(os.path.abspath(__file__)))
CLIP_DIR = os.path.join(SD, "clips")
SEP_DIR = os.path.join(SD, "separated")
DNA_DIR = os.path.join(SD, "dna_cache")
RESULTS_DIR = os.path.join(SD, "results")

# yt-dlp — use venv version if it exists, otherwise assume it's on PATH
_venv_ytdlp = os.path.join(SD, "venv/bin/yt-dlp")
YTDLP = _venv_ytdlp if os.path.exists(_venv_ytdlp) else "yt-dlp"

for d in [CLIP_DIR, SEP_DIR, DNA_DIR, RESULTS_DIR]:
    os.makedirs(d, exist_ok=True)

SR = 22050


# ── Utilities ─────────────────────────────────────────────

def safe_name(name):
    return re.sub(r'[^a-zA-Z0-9_]', '_', name.lower()).strip('_')


def get_tempo(y, sr=SR):
    import librosa
    t, _ = librosa.beat.beat_track(y=y, sr=sr)
    return float(np.array(t).flatten()[0])


# ── Download ──────────────────────────────────────────────

def download_audio(url, output_name, max_seconds=None):
    suffix = "_full" if max_seconds is None else f"_{max_seconds}s"
    output_path = os.path.join(CLIP_DIR, f"{output_name}{suffix}.wav")
    if os.path.exists(output_path):
        return output_path
    cmd = [YTDLP, url, "-x", "--audio-format", "wav",
           "-o", os.path.join(CLIP_DIR, f"{output_name}{suffix}.%(ext)s"),
           "--no-playlist", "--quiet"]
    if max_seconds:
        cmd.extend(["--postprocessor-args", f"ffmpeg:-t {max_seconds}"])
    try:
        result = subprocess.run(cmd, capture_output=True, timeout=120, text=True)
    except subprocess.TimeoutExpired:
        return None
    return output_path if os.path.exists(output_path) else None


def search_candidates(song_name, extra_queries=None, max_per_query=10):
    """Search SoundCloud and YouTube for remake candidates.
    Returns deduplicated list of (id, title, duration, platform)."""

    # Title-based noise filter
    SKIP_WORDS = ["slowed", "reverb", "sped up", "type beat", "instrumental",
                  "karaoke", "acapella", "a cappella", "tutorial", "reaction",
                  "drum cover", "guitar cover", "piano cover", "lullaby",
                  "8d audio", "bass boosted", "ringtone", "nightcore"]

    def is_noise(title):
        t = title.lower()
        return any(w in t for w in SKIP_WORDS)

    # Build search queries
    queries_sc = [
        f"{song_name} freestyle",
        f"{song_name} remix rap",
        f"{song_name} rap",
        f'"{song_name}"',
    ]
    queries_yt = [
        f"{song_name} freestyle rap",
        f"{song_name} rap remake",
        f'"{song_name}" rap -tutorial -cover -karaoke -instrumental',
    ]

    if extra_queries:
        for q in extra_queries:
            queries_sc.append(q)
            queries_yt.append(q)

    all_candidates = []
    seen_titles = set()  # dedupe by normalized title

    def norm_title(t):
        return re.sub(r'[^a-z0-9]', '', t.lower())

    # SoundCloud first (better for underground)
    for query in queries_sc:
        print(f"   [SC] {query}")
        cmd = [YTDLP, f"scsearch{max_per_query}:{query}",
               "--dump-json", "--no-download", "--flat-playlist", "--quiet"]
        try:
            result = subprocess.run(cmd, capture_output=True, timeout=60, text=True)
        except subprocess.TimeoutExpired:
            continue
        for line in result.stdout.strip().split("\n"):
            if not line.strip():
                continue
            try:
                data = json.loads(line)
                title = data.get("title", "")
                duration = data.get("duration") or 0
                vid_id = data.get("id", "")
                url = data.get("webpage_url", "")

                if not (30 < duration < 600):
                    continue
                if is_noise(title):
                    continue
                nt = norm_title(title)
                if nt in seen_titles:
                    continue
                seen_titles.add(nt)
                all_candidates.append((vid_id, title, duration, "soundcloud", url))
            except json.JSONDecodeError:
                continue

    # YouTube backup
    for query in queries_yt:
        print(f"   [YT] {query}")
        cmd = [YTDLP, f"ytsearch{max_per_query}:{query}",
               "--dump-json", "--no-download", "--flat-playlist", "--quiet"]
        try:
            result = subprocess.run(cmd, capture_output=True, timeout=60, text=True)
        except subprocess.TimeoutExpired:
            continue
        for line in result.stdout.strip().split("\n"):
            if not line.strip():
                continue
            try:
                data = json.loads(line)
                title = data.get("title", "")
                duration = data.get("duration") or 0
                vid_id = data.get("id", "")
                url = data.get("webpage_url", f"https://youtube.com/watch?v={vid_id}")

                if not (30 < duration < 600):
                    continue
                if is_noise(title):
                    continue
                nt = norm_title(title)
                if nt in seen_titles:
                    continue
                seen_titles.add(nt)
                all_candidates.append((vid_id, title, duration, "youtube", url))
            except json.JSONDecodeError:
                continue

    return all_candidates


# ── Demucs Separation ────────────────────────────────────

def separate_other(audio_path, song_id):
    other_path = os.path.join(SEP_DIR, f"{song_id}_other.wav")
    if os.path.exists(other_path):
        return other_path

    import torch
    import soundfile as sf
    import librosa
    from demucs.pretrained import get_model
    from demucs.apply import apply_model

    print(f"   Separating {song_id}...")
    model = get_model("htdemucs")
    model.eval()

    audio_np, file_sr = sf.read(audio_path)
    if audio_np.ndim == 1:
        audio_np = np.stack([audio_np, audio_np])
    else:
        audio_np = audio_np.T
    wav = torch.from_numpy(audio_np).float()

    if file_sr != model.samplerate:
        channels = [librosa.resample(wav[ch].numpy(), orig_sr=file_sr, target_sr=model.samplerate)
                    for ch in range(wav.shape[0])]
        wav = torch.from_numpy(np.stack(channels)).float()

    if wav.shape[0] == 1:
        wav = wav.repeat(2, 1)
    wav = wav.unsqueeze(0)

    with torch.no_grad():
        sources = apply_model(model, wav)

    other_idx = list(model.sources).index("other")
    other = sources[0, other_idx].numpy().T
    sf.write(other_path, other, model.samplerate)
    return other_path


# ── CQT Event Extraction ────────────────────────────────

def get_events(y, sr=SR):
    import librosa
    cqt = np.abs(librosa.cqt(y, sr=sr, hop_length=512, n_bins=84, bins_per_octave=12))
    frame_max = np.max(cqt, axis=0)
    threshold = np.percentile(frame_max, 20)

    dominant = []
    for t in range(cqt.shape[1]):
        if frame_max[t] > threshold:
            dominant.append(int(np.argmax(cqt[:, t])))
        else:
            dominant.append(-1)

    events = []
    for i in range(1, len(dominant)):
        if dominant[i] == -1 or dominant[i - 1] == -1:
            continue
        diff = dominant[i] - dominant[i - 1]
        if diff != 0:
            events.append({
                "frame": i,
                "dir": "U" if diff > 0 else "D",
                "bin": dominant[i],
                "jump": abs(diff)
            })
    return events


# ── DNA Pattern Finding ──────────────────────────────────

def find_all_dna(events, min_repeats=3, max_patterns=25):
    """Find all distinct DNA patterns: direction sequences with consistent jumps."""
    dnas = []
    seen_dirs = set()

    for phrase_len in range(4, 12):
        for i in range(len(events) - phrase_len):
            chunk = events[i:i + phrase_len]
            dirs = "".join(e["dir"] for e in chunk)
            jumps = [e["jump"] for e in chunk]

            mean_jump = np.mean(jumps)
            if mean_jump < 1:
                continue
            cv = np.std(jumps) / mean_jump
            if cv > 0.5:
                continue
            if dirs in seen_dirs:
                continue

            # Count matches in the original
            count = 0
            for j in range(len(events) - phrase_len):
                chunk2 = events[j:j + phrase_len]
                if "".join(e["dir"] for e in chunk2) != dirs:
                    continue
                jumps2 = [e["jump"] for e in chunk2]
                mean2 = np.mean(jumps2)
                if mean2 < 1:
                    continue
                if np.std(jumps2) / mean2 > 0.5:
                    continue
                ratio = max(mean_jump, mean2) / min(mean_jump, mean2)
                if ratio > 2.0:
                    continue
                count += 1

            if count >= min_repeats:
                seen_dirs.add(dirs)
                dnas.append({
                    "dirs": dirs,
                    "count": count,
                    "avg_jump": float(mean_jump),
                    "phrase_len": phrase_len
                })

    dnas.sort(key=lambda x: x["phrase_len"] * x["count"], reverse=True)
    return dnas[:max_patterns]


def count_dna_matches(dna, target_events):
    """Count how many times a DNA pattern appears in target events."""
    dirs = dna["dirs"]
    orig_avg = dna["avg_jump"]
    plen = dna["phrase_len"]

    count = 0
    for j in range(len(target_events) - plen):
        chunk = target_events[j:j + plen]
        if "".join(e["dir"] for e in chunk) != dirs:
            continue
        jumps = [e["jump"] for e in chunk]
        mean_j = np.mean(jumps)
        if mean_j < 1:
            continue
        if np.std(jumps) / mean_j > 0.5:
            continue
        ratio = max(orig_avg, mean_j) / min(orig_avg, mean_j)
        if ratio > 2.0:
            continue
        count += 1
    return count


# ── DNA Cache ────────────────────────────────────────────

def save_dna_cache(song_name, dnas, tempo):
    path = os.path.join(DNA_DIR, f"{safe_name(song_name)}.json")
    with open(path, "w") as f:
        json.dump({"song": song_name, "tempo": tempo, "dnas": dnas}, f, indent=2)
    return path


def load_dna_cache(song_name):
    path = os.path.join(DNA_DIR, f"{safe_name(song_name)}.json")
    if not os.path.exists(path):
        return None
    with open(path) as f:
        return json.load(f)


# ── Commands ─────────────────────────────────────────────

def cmd_original(song_name, youtube_url):
    """Process an original song: download, separate, find DNAs, cache."""
    sname = safe_name(song_name)

    print(f"Processing original: {song_name}")

    # Download
    print("   Downloading...")
    clip_path = download_audio(youtube_url, sname, None)
    if not clip_path:
        print("   FAILED: download error")
        return

    # Separate
    other_path = separate_other(clip_path, sname)

    # Get tempo from raw track
    import librosa
    raw_y, _ = librosa.load(clip_path, sr=SR)
    tempo = get_tempo(raw_y)
    print(f"   Tempo: {tempo:.0f} BPM")

    # Extract events and find DNAs
    other_y, _ = librosa.load(other_path, sr=SR)
    events = get_events(other_y)
    print(f"   {len(events)} events extracted")

    dnas = find_all_dna(events)
    print(f"   {len(dnas)} DNA patterns found")

    # Cache
    cache_path = save_dna_cache(song_name, dnas, tempo)
    print(f"   Cached to {cache_path}")

    # Show top DNAs
    for i, d in enumerate(dnas[:10]):
        print(f"   #{i}: {d['dirs']} (len={d['phrase_len']}, repeats={d['count']}x, avg_jump={d['avg_jump']:.1f})")


def cmd_test(song_name, candidate_url):
    """Test a single candidate against a cached original."""
    import librosa

    cache = load_dna_cache(song_name)
    if not cache:
        print(f"No cached DNA for '{song_name}'. Run 'original' command first.")
        return

    dnas = cache["dnas"]
    orig_tempo = cache["tempo"]

    # Download candidate
    vid_id = candidate_url.split("v=")[-1].split("&")[0] if "v=" in candidate_url else candidate_url
    print(f"Testing candidate: {vid_id}")

    clip_path = download_audio(candidate_url, vid_id, 60)
    if not clip_path:
        print("   FAILED: download error")
        return

    # Separate
    other_path = separate_other(clip_path, vid_id)

    # Tempo match
    raw_y, _ = librosa.load(clip_path, sr=SR)
    cand_tempo = get_tempo(raw_y)

    other_y, _ = librosa.load(other_path, sr=SR)
    other_matched = librosa.effects.time_stretch(other_y, rate=cand_tempo / orig_tempo)

    # Get events and match
    cand_events = get_events(other_matched)

    total_matches = 0
    separating_matches = 0
    for d in dnas:
        c = count_dna_matches(d, cand_events)
        total_matches += c

    print(f"   Total DNA matches: {total_matches}")
    if total_matches > 0:
        print(f"   RESULT: LIKELY REMAKE")
    else:
        print(f"   RESULT: NO MATCH")

    return total_matches


def cmd_search(song_name, extra_queries=None):
    """Search SoundCloud + YouTube for candidates and test each one."""
    import librosa

    cache = load_dna_cache(song_name)
    if not cache:
        print(f"No cached DNA for '{song_name}'. Run 'original' command first.")
        return

    dnas = cache["dnas"]
    orig_tempo = cache["tempo"]

    # Search
    print(f"Searching for remakes of: {song_name}")
    all_candidates = search_candidates(song_name, extra_queries)
    print(f"\n   {len(all_candidates)} candidates after filtering\n")

    # Test each candidate
    scored = []
    for i, (vid_id, title, duration, platform, url) in enumerate(all_candidates):
        print(f"   [{i + 1}/{len(all_candidates)}] [{platform[:2].upper()}] {title[:55]}")

        clip_path = download_audio(url, safe_name(vid_id) if platform == "soundcloud" else vid_id, 60)
        if not clip_path or not os.path.exists(clip_path):
            print(f"      [skip] download failed")
            continue

        other_path = separate_other(clip_path, safe_name(vid_id) if platform == "soundcloud" else vid_id)

        raw_y, _ = librosa.load(clip_path, sr=SR)
        cand_tempo = get_tempo(raw_y)

        other_y, _ = librosa.load(other_path, sr=SR)
        other_matched = librosa.effects.time_stretch(other_y, rate=cand_tempo / orig_tempo)

        cand_events = get_events(other_matched)

        total = sum(count_dna_matches(d, cand_events) for d in dnas)

        result = "LIKELY REMAKE" if total > 0 else "NO MATCH"
        print(f"      DNA matches: {total} — {result}")

        scored.append({
            "video_id": vid_id,
            "title": title,
            "duration": duration,
            "platform": platform,
            "url": url,
            "dna_matches": total,
            "is_remake": total > 0
        })

        # Clean up clip if no match (save space)
        if total == 0:
            for p in [clip_path, other_path]:
                if os.path.exists(p):
                    os.remove(p)

    # Sort by matches
    scored.sort(key=lambda x: x["dna_matches"], reverse=True)

    # Save results
    results_path = os.path.join(RESULTS_DIR, f"{safe_name(song_name)}_search.json")
    with open(results_path, "w") as f:
        json.dump({"song": song_name, "results": scored}, f, indent=2)

    # Print summary
    print(f"\n{'=' * 70}")
    print(f"RESULTS: {song_name}")
    print(f"{'=' * 70}")

    remakes = [s for s in scored if s["is_remake"]]
    print(f"Remakes found: {len(remakes)}/{len(scored)}\n")

    for s in scored:
        marker = "*** REMAKE" if s["is_remake"] else ""
        plat = s["platform"][:2].upper()
        print(f"   {s['dna_matches']:4d} matches | [{plat}] {s['title'][:50]} {marker}")

    return scored


def cmd_list():
    """List all cached originals."""
    print("Cached originals:")
    for f in sorted(os.listdir(DNA_DIR)):
        if f.endswith(".json"):
            with open(os.path.join(DNA_DIR, f)) as fh:
                data = json.load(fh)
            print(f"   {data['song']} — {len(data['dnas'])} DNAs, {data['tempo']:.0f} BPM")


def cmd_flow(audio_path_or_url, song_name=None):
    """Analyze flow/quality of a track. Separates all 4 stems and measures flow metrics."""
    import librosa
    import soundfile as sf_mod
    import torch

    sname = safe_name(song_name or audio_path_or_url)

    # Download if URL
    if audio_path_or_url.startswith("http"):
        print(f"Downloading {song_name or audio_path_or_url}...")
        clip_path = download_audio(audio_path_or_url, sname, 60)
        if not clip_path:
            print("   FAILED: download error")
            return
    else:
        clip_path = audio_path_or_url

    # Separate ALL 4 stems
    stems = {}
    stem_names = ["drums", "bass", "other", "vocals"]
    all_exist = all(os.path.exists(os.path.join(SEP_DIR, f"{sname}_{s}.wav")) for s in stem_names)

    if not all_exist:
        from demucs.pretrained import get_model
        from demucs.apply import apply_model

        print("   Separating all stems...")
        model = get_model("htdemucs")
        model.eval()
        audio_np, file_sr = sf_mod.read(clip_path)
        if audio_np.ndim == 1:
            audio_np = np.stack([audio_np, audio_np])
        else:
            audio_np = audio_np.T
        wav = torch.from_numpy(audio_np).float()
        if file_sr != model.samplerate:
            channels = [librosa.resample(wav[ch].numpy(), orig_sr=file_sr, target_sr=model.samplerate)
                        for ch in range(wav.shape[0])]
            wav = torch.from_numpy(np.stack(channels)).float()
        if wav.shape[0] == 1:
            wav = wav.repeat(2, 1)
        wav = wav.unsqueeze(0)
        with torch.no_grad():
            sources = apply_model(model, wav)
        source_names = list(model.sources)
        for i, name in enumerate(source_names):
            p = os.path.join(SEP_DIR, f"{sname}_{name}.wav")
            sf_mod.write(p, sources[0, i].numpy().T, model.samplerate)
        print("   All stems saved")
    else:
        print("   [cached] all stems")

    # Load stems
    hop = 512
    vocals, _ = librosa.load(os.path.join(SEP_DIR, f"{sname}_vocals.wav"), sr=SR)
    drums, _ = librosa.load(os.path.join(SEP_DIR, f"{sname}_drums.wav"), sr=SR)
    other, _ = librosa.load(os.path.join(SEP_DIR, f"{sname}_other.wav"), sr=SR)
    bass, _ = librosa.load(os.path.join(SEP_DIR, f"{sname}_bass.wav"), sr=SR)

    v_rms = librosa.feature.rms(y=vocals, hop_length=hop)[0]
    d_rms = librosa.feature.rms(y=drums, hop_length=hop)[0]
    o_rms = librosa.feature.rms(y=other, hop_length=hop)[0]
    b_rms = librosa.feature.rms(y=bass, hop_length=hop)[0]

    def norm(x):
        mx = x.max()
        return x / mx if mx > 0 else x

    v_n, d_n, o_n, b_n = norm(v_rms), norm(d_rms), norm(o_rms), norm(b_rms)

    # 1. Vocal consistency
    v_active = v_n[v_n > 0.1]
    vocal_consistency = 1.0 - float(np.std(v_active)) if len(v_active) > 0 else 0
    vocal_presence = float(len(v_active) / len(v_n))

    # 2. Rhythm alignment
    drum_onsets = librosa.onset.onset_detect(y=drums, sr=SR, hop_length=hop, units='frames')
    if len(drum_onsets) > 0:
        aligned = sum(1 for o in drum_onsets
                      if v_n[max(0, o-3):min(len(v_n), o+4)].max() > 0.15)
        rhythm_alignment = float(aligned / len(drum_onsets))
    else:
        rhythm_alignment = 0

    # 3. Space score
    min_len = min(len(v_n), len(o_n), len(b_n))
    instrumental = o_n[:min_len] + b_n[:min_len]
    correlation = float(np.corrcoef(v_n[:min_len], instrumental)[0, 1])
    space_score = -correlation

    # 4. Smoothness
    v_diffs = np.abs(np.diff(v_n))
    smoothness = max(0, min(1, 1.0 - float(np.mean(v_diffs)) * 10))

    # 5. Bar structure
    tempo_arr, beats = librosa.beat.beat_track(y=drums, sr=SR, hop_length=hop)
    tempo = float(np.array(tempo_arr).flatten()[0])
    bar_structure = 0
    if len(beats) > 16:
        v_beats = librosa.util.sync(v_n.reshape(1, -1), beats, aggregate=np.mean)[0]
        bar_scores = []
        for bar_len in [4, 8]:
            if len(v_beats) > bar_len * 3:
                sims = [float(np.corrcoef(v_beats[i:i+bar_len], v_beats[i+bar_len:i+bar_len*2])[0, 1])
                        for i in range(len(v_beats) - bar_len * 2)
                        if np.std(v_beats[i:i+bar_len]) > 0.01 and np.std(v_beats[i+bar_len:i+bar_len*2]) > 0.01]
                sims = [s for s in sims if not np.isnan(s)]
                if sims:
                    bar_scores.append(float(np.mean(sims)))
        bar_structure = max(bar_scores) if bar_scores else 0

    # 6. Vocal clarity
    v_flatness = float(np.mean(librosa.feature.spectral_flatness(y=vocals)))
    vocal_clarity = (1 - v_flatness) * 100

    # 7. Pitch stability
    f0, voiced, voicing_prob = librosa.pyin(vocals, fmin=80, fmax=600, sr=SR, hop_length=hop)
    voiced_f0 = f0[~np.isnan(f0)]
    pitch_stability = 1.0 - min(1.0, float(np.std(voiced_f0)) / float(np.mean(voiced_f0))) if len(voiced_f0) > 10 else 0

    results = {
        "song": song_name or sname,
        "vocal_consistency": round(vocal_consistency, 3),
        "vocal_presence": round(vocal_presence, 3),
        "rhythm_alignment": round(rhythm_alignment, 3),
        "space_score": round(space_score, 3),
        "smoothness": round(smoothness, 3),
        "bar_structure": round(bar_structure, 3),
        "vocal_clarity": round(vocal_clarity, 1),
        "pitch_stability": round(pitch_stability, 3),
        "tempo": round(tempo, 0),
    }

    # Save
    flow_path = os.path.join(RESULTS_DIR, f"{sname}_flow.json")
    with open(flow_path, "w") as f:
        json.dump(results, f, indent=2)

    print(f"\n   Flow Analysis: {song_name or sname}")
    print(f"   {'─' * 40}")
    for k, v in results.items():
        if k != "song":
            print(f"   {k:<22} {v}")
    print(f"\n   Saved to {flow_path}")

    return results


def cmd_flow_batch(track_list_path):
    """Run flow analysis on a batch of tracks from a JSON file.
    File format: [{"name": "Song Name", "url": "youtube/soundcloud url"}, ...]
    """
    with open(track_list_path) as f:
        tracks = json.load(f)

    print(f"Batch flow analysis: {len(tracks)} tracks")
    all_results = {}

    for i, track in enumerate(tracks):
        name = track.get("name", f"track_{i}")
        url = track.get("url", "")
        print(f"\n[{i + 1}/{len(tracks)}] {name}")
        r = cmd_flow(url, name)
        if r:
            all_results[name] = r

    # Save combined
    batch_path = os.path.join(RESULTS_DIR, "batch_flow_results.json")
    with open(batch_path, "w") as f:
        json.dump(all_results, f, indent=2)

    # Print summary table
    print(f"\n{'=' * 100}")
    print("BATCH FLOW RESULTS")
    print(f"{'=' * 100}")
    print(f"{'Track':<30} {'VoxCon':>6} {'VoxPre':>6} {'RhyAlg':>6} {'Space':>6} {'Smooth':>6} {'BarStr':>6} {'Clarit':>6} {'Pitch':>6}")
    print(f"{'-' * 30} {'-' * 6} {'-' * 6} {'-' * 6} {'-' * 6} {'-' * 6} {'-' * 6} {'-' * 6} {'-' * 6}")
    for name, r in all_results.items():
        print(f"{name[:29]:<30} {r['vocal_consistency']:6.3f} {r['vocal_presence']:6.3f} {r['rhythm_alignment']:6.3f} {r['space_score']:6.3f} {r['smoothness']:6.3f} {r['bar_structure']:6.3f} {r['vocal_clarity']:6.1f} {r['pitch_stability']:6.3f}")

    return all_results


# ── Main ─────────────────────────────────────────────────

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    command = sys.argv[1]

    if command == "original" and len(sys.argv) >= 4:
        cmd_original(sys.argv[2], sys.argv[3])
    elif command == "test" and len(sys.argv) >= 4:
        cmd_test(sys.argv[2], sys.argv[3])
    elif command == "search" and len(sys.argv) >= 3:
        extra = sys.argv[3:] if len(sys.argv) > 3 else None
        cmd_search(sys.argv[2], extra)
    elif command == "flow" and len(sys.argv) >= 3:
        name = sys.argv[3] if len(sys.argv) > 3 else None
        cmd_flow(sys.argv[2], name)
    elif command == "flow-batch" and len(sys.argv) >= 3:
        cmd_flow_batch(sys.argv[2])
    elif command == "list":
        cmd_list()
    else:
        print(__doc__)
        sys.exit(1)
