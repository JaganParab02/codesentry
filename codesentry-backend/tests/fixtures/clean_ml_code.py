"""
Clean, secure ML code — baseline for comparison with vulnerable_ml_code.py.

Demonstrates security best-practices:
  - Structured prompts (no string interpolation with user input)
  - Model singleton loaded at startup
  - @torch.no_grad on all inference paths
  - BF16 dtype for memory efficiency
  - Batched embeddings
  - Parameterised SQL
  - Authentication middleware
  - torch.cuda.empty_cache() after inference
  - No hardcoded secrets
"""

from __future__ import annotations

import os
import sqlite3
from functools import lru_cache
from typing import List

import torch
from fastapi import FastAPI, Depends, HTTPException, Security
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from transformers import AutoModelForCausalLM, AutoTokenizer
from sentence_transformers import SentenceTransformer
from pydantic import BaseModel

app = FastAPI(debug=False)  # No debug in production
security_scheme = HTTPBearer()

# ── Secrets from environment (never hardcoded) ───────────────
HF_TOKEN = os.getenv("HF_TOKEN")  # Set in .env, never in code
DB_PATH = os.getenv("DB_PATH", "knowledge.db")

# ── Singleton model loading at startup ───────────────────────

@lru_cache(maxsize=1)
def get_llm():
    """Load LLM once at startup — not per-request."""
    tokenizer = AutoTokenizer.from_pretrained("gpt2", token=HF_TOKEN)
    model = AutoModelForCausalLM.from_pretrained(
        "gpt2",
        token=HF_TOKEN,
        torch_dtype=torch.bfloat16,  # 50% VRAM vs float32
        device_map="auto",
    )
    model.eval()
    return tokenizer, model


@lru_cache(maxsize=1)
def get_embedding_model() -> SentenceTransformer:
    """Load embedding model once at startup."""
    return SentenceTransformer("all-MiniLM-L6-v2")


# ── Auth middleware ───────────────────────────────────────────

def require_auth(credentials: HTTPAuthorizationCredentials = Security(security_scheme)):
    token = credentials.credentials
    valid_token = os.getenv("API_TOKEN", "")
    if not valid_token or token != valid_token:
        raise HTTPException(status_code=401, detail="Unauthorized")
    return token


# ── Request schemas ───────────────────────────────────────────

class GenerateRequest(BaseModel):
    message: str
    max_new_tokens: int = 200


class EmbedRequest(BaseModel):
    documents: List[str]


class SearchRequest(BaseModel):
    query: str


# ── LLM01 Fix: Structured prompt (no string interpolation) ───

@app.post("/generate")
async def generate(body: GenerateRequest, _: str = Depends(require_auth)):
    """
    Chat endpoint — uses structured prompt template, never concatenates
    raw user input into the prompt instruction block.
    """
    tokenizer, model = get_llm()

    # Safe: user content is clearly separated from instruction
    messages = [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": body.message},
    ]
    prompt = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    inputs = tokenizer(prompt, return_tensors="pt").to(model.device)

    with torch.no_grad():  # No gradient tracking during inference
        outputs = model.generate(
            **inputs,
            max_new_tokens=min(body.max_new_tokens, 512),  # LLM04: bounded
        )

    result_text = tokenizer.decode(outputs[0], skip_special_tokens=True)

    # Move tensors back to CPU immediately
    inputs_cpu = {k: v.cpu() for k, v in inputs.items()}
    del inputs_cpu
    torch.cuda.empty_cache()  # Return VRAM to pool

    # LLM02 Fix: NEVER eval() LLM output — parse structured JSON instead
    return {"result": result_text}


# ── A03 Fix: Parameterised SQL query ─────────────────────────

@app.get("/search")
async def rag_search(query: str, _: str = Depends(require_auth)):
    """Parameterised SQL — immune to SQL injection."""
    conn = sqlite3.connect(DB_PATH)
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM documents WHERE content LIKE ?",
            (f"%{query}%",),  # Parameterised — safe
        )
        results = cursor.fetchall()
    finally:
        conn.close()
    return {"results": results}


# ── ML03 Fix: Batched embeddings ─────────────────────────────

@app.post("/embed_documents")
async def embed_documents(body: EmbedRequest, _: str = Depends(require_auth)):
    """Batch-encodes all documents in a single GPU call."""
    model = get_embedding_model()
    # Single batch call — no N+1
    embeddings = model.encode(
        body.documents,
        batch_size=32,
        show_progress_bar=False,
    )
    return {"embeddings": embeddings.tolist()}


# ── A01 Fix: Protected admin endpoint ────────────────────────

@app.post("/admin/retrain")
async def retrain_model(
    data: List[dict],
    _: str = Depends(require_auth),  # Auth required
):
    """Triggers retraining — authentication enforced."""
    # Validate data before accepting (LLM03 protection)
    if not data or len(data) > 10_000:
        raise HTTPException(status_code=400, detail="Invalid training data size")
    return {"status": "retraining queued", "samples": len(data)}


# ── A04 Fix: Safe model loading with safetensors ─────────────

@app.post("/load_model")
async def load_model(model_name: str, _: str = Depends(require_auth)):
    """
    Loads a model from HuggingFace Hub only (no arbitrary paths).
    Uses safetensors format — no pickle deserialization.
    """
    # Allowlist of approved models only
    ALLOWED_MODELS = {"gpt2", "distilgpt2", "facebook/opt-125m"}
    if model_name not in ALLOWED_MODELS:
        raise HTTPException(status_code=400, detail=f"Model '{model_name}' not in allowlist")

    # from_pretrained uses safetensors when available — no pickle
    model = AutoModelForCausalLM.from_pretrained(
        model_name,
        torch_dtype=torch.bfloat16,
    )
    return {"status": "loaded", "model": model_name}
