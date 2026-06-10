import os
import json
import re
import urllib.request
import asyncio
from typing import List, Tuple, Optional
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

try:
    from ddgs import DDGS
except ImportError:
    from duckduckgo_search import DDGS

app = FastAPI(title="CrossCheck AI")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

class Message(BaseModel): role: str; content: str
class TranscriptRequest(BaseModel): messages: List[Message]
class Claim(BaseModel): id: str; text: str; turn_index: int
class Contradiction(BaseModel): claim1_id: str; claim2_id: str; explanation: str; contradictory: bool
class Source(BaseModel): title: str; url: str
class VerificationResult(BaseModel): claim_id: str; search_query: str; status: str; explanation: str; sources: List[Source] = Field(default_factory=list)
class AnalysisResponse(BaseModel): transcript: List[Message]; claims: List[Claim]; contradictions: List[Contradiction]; verifications: List[VerificationResult]

DEFAULT_HOST = os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434").rstrip("/")
DEFAULT_MODEL = os.getenv("OLLAMA_MODEL", "llama3.2")

def _extract_json_blob(text: str) -> str:
    fence = re.search(r"```(?:json)?\s*(.*?)```", text.strip(), re.DOTALL)
    text = fence.group(1).strip() if fence else text.strip()
    if text and text[0] in "{[": return text
    candidates = [m for m in (re.search(r"\{.*\}", text, re.DOTALL), re.search(r"\[.*\]", text, re.DOTALL)) if m]
    return min(candidates, key=lambda m: m.start()).group(0) if candidates else text

def parse_json(text: str, default):
    try: return json.loads(_extract_json_blob(text)) if text else default
    except (json.JSONDecodeError, ValueError): return default

def _complete_sync(prompt: str, max_tokens: int = 1024):
    payload = {"model": DEFAULT_MODEL, "messages": [{"role": "user", "content": prompt}], "stream": False, "format": "json", "options": {"temperature": 0.0, "num_predict": max_tokens}}
    req = urllib.request.Request(f"{DEFAULT_HOST}/api/chat", json.dumps(payload).encode(), headers={'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(req, timeout=120.0) as resp:
            return json.loads(resp.read().decode()).get("message", {}).get("content", "")
    except Exception as e:
        print(f"LLM call failed: {e}")
        return ""

async def complete_json(prompt: str, default, max_tokens: int = 1024):
    return parse_json(await asyncio.to_thread(_complete_sync, prompt, max_tokens), default)

async def extract_claims(messages: List[Message]) -> List[Claim]:
    async def extract_one(turn_index: int, content: str):
        data = await complete_json(f'Extract facts from assistant. Return exactly `{{"claims": ["c1"]}}`\n\n"{content}"', {"claims": []})
        raw = data if isinstance(data, list) else data.get("claims", []) if isinstance(data, dict) else []
        return [Claim(id="", text=str(c.get("claim") or c.get("text") or "") if isinstance(c, dict) else str(c), turn_index=turn_index) for c in raw if str(c).strip()]
        
    results = await asyncio.gather(*(extract_one(i, msg.content) for i, msg in enumerate(messages) if msg.role == "assistant"))
    claims = []
    for turn_claims in results:
        for claim in turn_claims:
            if claim.text.strip():
                claim.id = f"c{len(claims)+1}"
                claims.append(claim)
    return claims

async def find_contradictions(claims: List[Claim]) -> List[Contradiction]:
    stopwords = {"the", "a", "is", "are", "of", "in", "to", "and", "or", "for", "with", "that", "this", "it"}
    pairs = [(a, b) for i, a in enumerate(claims) for b in claims[i+1:] if a.turn_index != b.turn_index and (set(re.findall(r"[a-z0-9]+", a.text.lower())) - stopwords) & (set(re.findall(r"[a-z0-9]+", b.text.lower())) - stopwords)]
    
    async def check_one(a: Claim, b: Claim):
        data = await complete_json(f'Are these DIRECTLY contradictory? Return `{{"contradictory": true/false, "explanation": "..."}}`\nClaim 1: {a.text}\nClaim 2: {b.text}', {"contradictory": False, "explanation": ""})
        if isinstance(data, dict) and data.get("contradictory") is True:
            return Contradiction(claim1_id=a.id, claim2_id=b.id, explanation=data.get("explanation", ""), contradictory=True)
        return None
        
    return [r for r in await asyncio.gather(*(check_one(a, b) for a, b in pairs)) if r]

def _fix_mojibake(text: str) -> str:
    try: return text.encode("latin-1").decode("utf-8") if text and ("Ã" in text or "Â" in text) else text
    except Exception: return text

async def verify_claims(claims: List[Claim]) -> List[VerificationResult]:
    def search_sync(query: str):
        try:
            with DDGS() as ddgs: return list(ddgs.text(query, max_results=4))
        except Exception: return []

    async def verify_one(c: Claim):
        results = await asyncio.to_thread(search_sync, c.text)
        sources = [Source(title=_fix_mojibake(r.get("title", "")), url=r.get("href", "") or r.get("url", "")) for r in results]
        context = "\n".join(f"- {_fix_mojibake(r.get('title',''))}: {_fix_mojibake(r.get('body',''))}" for r in results) or "(no results)"
        
        data = await complete_json(f'Verify claim using only these search results. Return `{{"status": "True"|"False"|"Unverified", "explanation": "..."}}`\nClaim: {c.text}\nResults: {context}', {"status": "Unverified", "explanation": "No results"})
        status = data.get("status") if isinstance(data, dict) and data.get("status") in ("True", "False", "Unverified") else "Unverified"
        return VerificationResult(claim_id=c.id, search_query=c.text, status=status, explanation=_fix_mojibake(data.get("explanation", "") if isinstance(data, dict) else ""), sources=sources)
        
    return list(await asyncio.gather(*(verify_one(c) for c in claims))) if claims else []

@app.post("/api/analyze", response_model=AnalysisResponse)
async def analyze_transcript(request: TranscriptRequest):
    claims = await extract_claims(request.messages)
    contradictions, verifications = await asyncio.gather(find_contradictions(claims), verify_claims(claims))
    return AnalysisResponse(transcript=request.messages, claims=claims, contradictions=contradictions, verifications=verifications)

static_dir = os.path.join(os.path.dirname(__file__), "static")
os.makedirs(static_dir, exist_ok=True)
app.mount("/", StaticFiles(directory=static_dir, html=True), name="static")
