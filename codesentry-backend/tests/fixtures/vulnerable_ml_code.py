"""
Deliberately vulnerable ML code for testing CodeSentry's detection capabilities.

Contains:
  - Prompt injection (LLM01)
  - Insecure output handling / eval (LLM02)
  - Hardcoded HuggingFace token (LLM06 / A07)
  - Insecure pickle deserialization (A04 / CWE-502)
  - GPU tensor never moved to CPU (memory leak)
  - N+1 embedding calls in loop
  - FP32 when FP16 would suffice
  - Missing @torch.no_grad on inference
  - Model loaded inside request handler
  - SQL injection in RAG query
  - Debug mode enabled
"""

import os
import pickle
import sqlite3

from flask import Flask, request, jsonify

app = Flask(__name__)
app.config["DEBUG"] = True  # A05: Security Misconfiguration

# ── A07 / LLM06: Hardcoded API key ──────────────────────────
HF_TOKEN = "hf_abcXYZabcXYZabcXYZabcXYZabcXYZ12"
OPENAI_API_KEY = "sk-proj-aaaabbbbccccddddeeeeffffgggghhhhiiiijjjj"

# ── Database (for RAG demo) ──────────────────────────────────
DB_PATH = "knowledge.db"


def get_db():
    return sqlite3.connect(DB_PATH)


# ── A04 / CWE-502: Insecure pickle deserialization ──────────
@app.route("/load_model", methods=["POST"])
def load_model():
    """Loads a model from a user-supplied file path — insecure!"""
    model_path = request.json.get("model_path")
    # VULNERABILITY: pickle.load from untrusted user-controlled path
    with open(model_path, "rb") as f:
        model = pickle.load(f)  # noqa: S301 — CWE-502
    return jsonify({"status": "loaded"})


# ── LLM01: Prompt Injection ──────────────────────────────────
@app.route("/generate", methods=["POST"])
def generate():
    """Chat endpoint that directly concatenates user input into the prompt."""
    user_input = request.json.get("message", "")
    # VULNERABILITY: user input concatenated directly — prompt injection
    prompt = f"You are a helpful assistant. User says: {user_input}"

    # Model loaded INSIDE handler on every request (performance issue)
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer

    tokenizer = AutoTokenizer.from_pretrained("gpt2", token=HF_TOKEN)
    model = AutoModelForCausalLM.from_pretrained(
        "gpt2",
        token=HF_TOKEN,
        torch_dtype=torch.float32,  # ML04: FP32 wastes 2x VRAM
    )

    # ML02: Missing @torch.no_grad — gradients computed unnecessarily
    inputs = tokenizer(prompt, return_tensors="pt").to("cuda")
    outputs = model.generate(**inputs, max_new_tokens=200)
    # Tensor stays on GPU — memory leak (ML01)
    result = tokenizer.decode(outputs[0])

    # LLM02: LLM output piped directly to eval()
    eval(result)  # noqa: S307 — EXTREMELY DANGEROUS

    return jsonify({"result": result})


# ── A03: SQL Injection in RAG query ─────────────────────────
@app.route("/search", methods=["GET"])
def rag_search():
    """RAG knowledge base search — SQL injection vulnerability."""
    query = request.args.get("q", "")
    conn = get_db()
    cursor = conn.cursor()
    # VULNERABILITY: unsanitised user input in SQL query
    sql = f"SELECT * FROM documents WHERE content LIKE '%{query}%'"
    cursor.execute(sql)  # noqa: S608 — SQL injection
    results = cursor.fetchall()
    conn.close()
    return jsonify({"results": results})


# ── ML03: N+1 embedding calls ────────────────────────────────
@app.route("/embed_documents", methods=["POST"])
def embed_documents():
    """Embeds each document individually in a loop instead of batching."""
    import torch
    from sentence_transformers import SentenceTransformer

    documents = request.json.get("documents", [])
    model = SentenceTransformer("all-MiniLM-L6-v2")

    embeddings = []
    for doc in documents:  # N+1: one GPU call per document
        emb = model.encode(doc)  # Should batch all at once
        embeddings.append(emb.tolist())

    return jsonify({"embeddings": embeddings})


# ── No authentication on sensitive endpoint ──────────────────
@app.route("/admin/retrain", methods=["POST"])
def retrain_model():
    """Triggers model retraining — no auth check!"""
    # A01: Broken Access Control — no authentication
    training_data = request.json.get("data", [])
    # Just store without any validation (LLM03: training data poisoning)
    return jsonify({"status": "retraining started", "samples": len(training_data)})


# ── Path traversal in file upload ────────────────────────────
@app.route("/upload_weights", methods=["POST"])
def upload_weights():
    """Saves uploaded model weights — path traversal vulnerability."""
    filename = request.json.get("filename", "model.bin")
    data = request.json.get("data", "")
    # VULNERABILITY: filename not sanitised — path traversal possible
    save_path = os.path.join("/models", filename)
    with open(save_path, "wb") as f:
        f.write(data.encode())
    return jsonify({"saved": save_path})


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
