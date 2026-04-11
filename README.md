# DJ Claudito Beat Matcher

Finds underground rap remakes of classic songs using melodic DNA contour matching.

## Setup

```bash
python -m venv venv
source venv/bin/activate  # or venv\Scripts\activate on Windows
pip install -r requirements.txt
```

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

## How it works

1. **Demucs** separates the "other" stem (melody/synths/guitar) from drums, bass, vocals
2. **CQT** extracts dominant frequency events and directional movements
3. **DNA patterns** found: repeating direction sequences with self-consistent jump sizes
4. Candidates get separated, tempo-matched, and DNA cross-checked
5. Any DNA matches = likely remake
