"""
Fix Agent — generates before/after code patches for security findings.
Uses rule-based fixes; can be swapped for LLM-powered fixes via HF API.
"""

import asyncio
from typing import AsyncGenerator

# Rule-based fix templates keyed by finding ID / pattern name
FIX_TEMPLATES = {
    "SEC-001": {
        "title": "Fix: Parameterized SQL Query",
        "before": "const query = `SELECT * FROM users WHERE id = '${req.params.id}'`;\nconst result = await db.execute(query);",
        "after": "const query = 'SELECT * FROM users WHERE id = ?';\nconst result = await db.execute(query, [req.params.id]);",
        "explanation": "Replaced string interpolation with parameterized query. The DB driver handles escaping, preventing SQL injection.",
    },
    "SEC-002": {
        "title": "Fix: Move Secret to Environment Variable",
        "before": "const API_SECRET = 'sk-live-abc123...';",
        "after": "const API_SECRET = process.env.API_SECRET;\nif (!API_SECRET) throw new Error('API_SECRET env var is required');",
        "explanation": "Moved hardcoded secret to an environment variable with a runtime guard.",
    },
    "SEC-003": {
        "title": "Fix: Replace eval() with Safe Parser",
        "before": "const result = eval(req.body.expression);",
        "after": "const { evaluate } = require('mathjs');\nconst result = evaluate(req.body.expression);",
        "explanation": "Replaced eval() with mathjs.evaluate(), which is sandboxed and cannot execute arbitrary code.",
    },
    "SEC-004": {
        "title": "Fix: Safe Deserialization",
        "before": "model = pickle.loads(uploaded_data)",
        "after": "from safetensors.torch import load_file\n\nif not filepath.endswith('.safetensors'):\n    raise ValueError('Only .safetensors accepted')\nmodel_state = load_file(filepath)\nmodel.load_state_dict(model_state)",
        "explanation": "Replaced pickle with safetensors, which cannot execute arbitrary code during loading.",
    },
    "SEC-005": {
        "title": "Fix: Bcrypt Password Hashing",
        "before": "const hash = crypto.createHash('md5').update(password).digest('hex');",
        "after": "const bcrypt = require('bcrypt');\nconst SALT_ROUNDS = 12;\nconst hash = await bcrypt.hash(password, SALT_ROUNDS);",
        "explanation": "Replaced MD5 with bcrypt (12 rounds). MD5 is broken; bcrypt is designed for password storage.",
    },
}


class FixAgent:
    async def generate_fixes(self, findings: list[dict], code: str) -> AsyncGenerator[tuple[str, dict], None]:
        fixes_generated = 0

        for i, finding in enumerate(findings):
            await asyncio.sleep(0.8)

            pct = int(((i + 1) / len(findings)) * 100)
            yield "progress", {
                "agent": "fix",
                "percent": pct,
                "filesScanned": i + 1,
                "message": f"Generating fix for {finding.get('title', 'finding')}...",
            }

            finding_id = finding.get("id", "")
            fix_template = FIX_TEMPLATES.get(finding_id)

            if fix_template:
                fixes_generated += 1
                yield "fix_ready", {
                    "agent": "fix",
                    "findingId": finding_id,
                    **fix_template,
                }

        yield "progress", {
            "agent": "fix",
            "percent": 100,
            "filesScanned": len(findings),
            "message": f"{fixes_generated} patches generated",
        }
