# CrossCheck AI / Self-Contradiction Detector

Paste any AI-generated answer (or a whole chat transcript) and this tool
cross-checks its internal consistency, flags claims that contradict each other
across turns, and verifies factual claims against live web search — a "lie
detector" for LLM output.

It targets a known multi-turn weakness: LLMs lose track of earlier claims over a
long conversation and will confidently restate something that contradicts what
they said several turns ago.

**Try it in 10 seconds:** load the built-in example — the AI says the capital of
France is Paris, then three turns later says Berlin. The tool flags the
contradiction across turns and web-verifies that Berlin is wrong.

---

## Quick Start

**Requirements:** Python 3.10+, and [Ollama](https://ollama.com/download)
(a free local AI runner). No API keys, no accounts, no cost.

```bash
# 1. Install the free local AI engine, then pull a model (one time)
#    Download Ollama from https://ollama.com/download first, then:
ollama pull llama3.2

# 2. Get the app
git clone https://github.com/<your-username>/ai-fact-checker.git
cd ai-fact-checker

# 3. Create a virtual environment and activate it
python -m venv venv
venv\Scripts\activate        # Windows
# source venv/bin/activate   # macOS/Linux

# 4. Install dependencies
pip install -r requirements.txt

# 5. Run
uvicorn main:app --reload
```

Then open **http://127.0.0.1:8000**, click **Load Example**, and hit **Analyze**.

> Everything runs on the user's own machine — the AI (via Ollama) and the app.
> Nothing is billed to anyone.

---

## Stack

- **Python / FastAPI** backend
- **Ollama** running a **local LLM** (default `llama3.2`) for claim extraction,
  contradiction classification, and verification judgments — **no API key, no
  cost**
- **DuckDuckGo search** (`ddgs`) for live fact verification — also free
- Vanilla HTML/CSS/JS single-page UI (diff-style highlighting)

> **100% free, no API keys.** All the AI runs locally through Ollama, and web
> search uses DuckDuckGo. Nothing is billed to anyone — the only requirement is
> that Ollama is installed and running on the machine hosting the app.

---

## Configuration (optional)

The defaults work out of the box; you only need this to change the model or
point at a remote Ollama server.

```bash
cp .env.example .env    # Windows: copy .env.example .env
```

| Variable       | Default                     | Purpose                          |
| -------------- | --------------------------- | -------------------------------- |
| `OLLAMA_MODEL` | `llama3.2`                  | Which local model to use         |
| `OLLAMA_HOST`  | `http://127.0.0.1:11434`    | Where the Ollama server is       |

Want it faster or smarter? Swap the model — e.g. `ollama pull llama3.2:1b` for
speed, or a larger model for quality — and set `OLLAMA_MODEL` accordingly. No
code changes needed.

---

## Notes on behavior

- **Ollama not running?** The app still starts. Every stage falls back to
  illustrative dummy data so you can see the full UI and flow.
- **Speed:** local models run on your CPU/GPU, so an analysis takes a few
  seconds to ~a minute depending on your hardware and transcript length —
  slower than a paid cloud API, but free.
- **Input format:** the UI parses lines prefixed with `User:` and `AI:` (or
  `Assistant:`). Only assistant turns are fact-checked.

---

## How it works

The `/api/analyze` endpoint runs a three-stage pipeline:

1. **Claim extraction** (`services/llm_extractor.py`) — for each *assistant* turn,
   the local model extracts atomic, checkable factual claims (opinions and hedges
   are dropped). Turns are processed concurrently; each claim keeps its
   `turn_index`.
2. **Contradiction detection** (`services/contradiction_checker.py`) — candidate
   claim pairs (from *different* turns, sharing at least one meaningful keyword)
   are sent to the model with a strict "contradictory or not" prompt. Pairs run
   concurrently.
3. **Web verification** (`services/web_search.py`) — each claim is searched on
   DuckDuckGo and the results are handed to the model, which returns
   **True / False / Unverified** plus sources.

Stages 2 and 3 are independent and run concurrently. All model calls go through
`services/llm_client.py`, which talks to the local Ollama server, parses model
JSON defensively (handles markdown fences and stray prose), and never lets a
single failed call crash the request.

---

## Known failure modes (a.k.a. "who checks the checker?")

Using an LLM to judge another LLM's output has real failure modes. This project
mitigates them deliberately rather than pretending they don't exist:

- **The checker hallucinates a contradiction that isn't there.** This is the
  biggest risk. Two mitigations: (1) a cheap keyword pre-filter so we only ask
  about topically-related pairs from different turns — unrelated claims never
  get a chance to be spuriously flagged; (2) a conservative prompt that must
  default to *not contradictory* unless the two claims cannot both be true of the
  same subject at the same time.
- **Extraction paraphrases the claim** so it can't be located as an exact
  substring in the original message. The UI falls back to appending the extracted
  claim below the turn rather than silently dropping the highlight.
- **Verification over-trusts weak search results.** The prompt forces
  `Unverified` when results are thin, irrelevant, or conflicting instead of
  guessing, and the sources are shown so a human can judge for themselves.
- **DuckDuckGo rate-limiting / empty results.** Searches are wrapped so a failure
  yields `Unverified` for that claim instead of crashing the analysis.
- **The judge model can still be wrong.** Verification is an assist, not an
  oracle — always follow the linked sources for anything that matters.

### A good evaluation set

To measure the checker itself, build a small labeled set of transcripts:
- **True positives:** transcripts with a planted cross-turn contradiction
  (Paris→Berlin, "released in 2019"→"released in 2021").
- **True negatives (hard):** transcripts with claims that *look* related but are
  compatible ("Paris is the capital" + "Paris has ~2M residents") — these catch
  the checker's tendency to over-flag.
- **Verification set:** claims with known ground truth (mix of true, false, and
  genuinely ambiguous) to measure the True/False/Unverified calibration.

Track precision on contradictions especially — a false contradiction is worse
than a missed one for this tool's credibility.

---

## Project layout

```
ai-fact-checker/
├── main.py                       # FastAPI app + /api/analyze pipeline
├── models.py                     # Pydantic request/response models
├── requirements.txt
├── .env.example
├── services/
│   ├── llm_client.py             # shared local Ollama client + defensive JSON parsing
│   ├── llm_extractor.py          # claim extraction
│   ├── contradiction_checker.py  # pairwise contradiction detection
│   └── web_search.py             # DuckDuckGo + local-model verification
└── static/                       # single-page UI (index.html, app.js, style.css)
```
