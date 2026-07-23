"""Bedrock RAG orchestration for the Building Energy Code & Standards Assistant.

- Embeds the user query with Titan (default ``amazon.titan-embed-text-v2:0``).
- Retrieves top-k chunks from the FAISS store, filtered by the codes the user selected.
- Calls Bedrock ``Converse`` on the configured LLM (default ``mistral.mistral-large-2402-v1:0``)
  with a strict "answer only from the provided context, with citations" system prompt.
- Streams tokens back as they arrive via ``ConverseStream``.
"""

from __future__ import annotations

import json
import logging
import os
import threading
from pathlib import Path
from typing import Iterator, List, Optional, Sequence

import boto3
import numpy as np

from code_compliance.retriever.faiss_store import FaissStore, RetrievedChunk
from code_compliance.retriever.s3_sync import download_bundles

logger = logging.getLogger(__name__)

# --- Model configuration (all overridable via env) ------------------------------------
# Mistral Large (24.02) is the default because it is the strongest model with
# confirmed on-demand access in ca-central-1 for AWS account 834599497928:
#   - Amazon Nova family is NOT offered in ca-central-1.
#   - Anthropic Claude 3 models are listed but blocked by AWS Marketplace subscription.
#   - Mistral Large gives the cleanest Converse output (no chat-template leakage) and
#     the strongest instruction-following of the accessible options -> best for strict
#     citation-only RAG answers on bilingual (EN/FR) NECB text.
#
# Verified alternatives in ca-central-1 (drop in via BEDROCK_MODEL_ID env var):
#   mistral.mistral-large-2402-v1:0    - default; strongest instruction-following
#   meta.llama3-70b-instruct-v1:0      - strong reasoning; may need stop-seq tuning
#   mistral.mixtral-8x7b-instruct-v0:1 - mid-tier fallback
#   meta.llama3-8b-instruct-v1:0       - fast/cheap fallback
#   mistral.mistral-7b-instruct-v0:2   - smallest fallback
BEDROCK_MODEL_ID = os.getenv("BEDROCK_MODEL_ID", "mistral.mistral-large-2402-v1:0")
BEDROCK_EMBED_MODEL_ID = os.getenv("BEDROCK_EMBED_MODEL_ID", "amazon.titan-embed-text-v2:0")
BEDROCK_EMBED_DIM = int(os.getenv("BEDROCK_EMBED_DIM", "1024"))
BEDROCK_REGION = os.getenv("BEDROCK_REGION", os.getenv("AWS_REGION", "ca-central-1"))
CODE_ASSISTANT_KB_BUCKET = os.getenv("CODE_ASSISTANT_KB_BUCKET", "")
LOCAL_INDEX_DIR = Path(os.getenv("CODE_ASSISTANT_INDEX_DIR", "/tmp/code_assistant_indexes"))
MAX_HISTORY_TURNS = int(os.getenv("CODE_ASSISTANT_MAX_HISTORY", "6"))

_SYSTEM_PROMPT = """You are the CanBuildAI Building Codes & Standards Assistant, an expert on Canadian building codes including the National Energy Code for Buildings (NECB), the National Building Code (NBC), and related standards.

Rules you MUST follow:
1. Answer ONLY using the information in the CONTEXT section below. If the context does not contain the answer, say so plainly and suggest which section of the code the user might consult.
2. Every factual statement MUST be followed by a citation in square brackets referring to the numbered source snippets, e.g. [1] or [2, 3].
3. When quoting numerical requirements (RSI, U-values, %, W/m²·K, climate zones), quote them exactly as they appear in the context and cite the source.
4. Prefer the most recent code edition when the user has selected more than one and they differ. Point out the difference and cite both. Never mix requirements from different codes (NECB vs NBC) without saying which code you are citing.
5. Do NOT invent section numbers, table numbers, or page numbers. If they are not in the context, do not fabricate them.
6. Keep answers concise, structured, and practitioner-oriented. Use bullet points for lists of requirements and Markdown tables when comparing several values.
7. Format any mathematical formulas using LaTeX delimiters so they render nicely: use $...$ for inline math (e.g. $U = 1/R$) and $$...$$ for display math on its own line. Prefer LaTeX for equations, exponents, subscripts, fractions and units with superscripts (e.g. $\\mathrm{W/(m^2 \\cdot K)}$). Plain prose values (e.g. "0.290 W/(m²·K)") do not need LaTeX.
"""


class CodeAssistantService:
    """Long-lived service object. One per process."""

    def __init__(self):
        self.bedrock_runtime = boto3.client("bedrock-runtime", region_name=BEDROCK_REGION)
        self.store: Optional[FaissStore] = None
        self.registry: List[dict] = []
        self._ready = False
        self._lock = threading.Lock()

    # ---------------------------------------------------------------- startup
    def load(self, registry: List[dict]) -> None:
        """Download bundles from S3 (if configured) and load FAISS indexes."""
        with self._lock:
            if self._ready:
                return
            self.registry = registry
            enabled_ids = [c["id"] for c in registry if c.get("enabled", True)]

            if CODE_ASSISTANT_KB_BUCKET:
                logger.info("Downloading KB bundles from s3://%s/kb/", CODE_ASSISTANT_KB_BUCKET)
                try:
                    download_bundles(
                        bucket=CODE_ASSISTANT_KB_BUCKET,
                        code_ids=enabled_ids,
                        local_root=LOCAL_INDEX_DIR,
                        region=BEDROCK_REGION,
                    )
                except Exception as e:  # noqa: BLE001
                    logger.exception("Failed to download KB bundles: %s", e)
            else:
                logger.warning("CODE_ASSISTANT_KB_BUCKET not set; assuming indexes already present at %s",
                               LOCAL_INDEX_DIR)

            self.store = FaissStore.load_dir(LOCAL_INDEX_DIR, registry)
            self._ready = True
            logger.info("Code assistant ready. Loaded codes: %s", self.store.available_codes())

    def is_ready(self) -> bool:
        return self._ready and self.store is not None and len(self.store.indexes) > 0

    def available_codes(self) -> List[dict]:
        """Public view of registry entries plus load status."""
        loaded = set(self.store.available_codes()) if self.store else set()
        out = []
        for c in self.registry:
            if not c.get("enabled", True):
                continue
            out.append({
                "id": c["id"],
                "label": c["label"],
                "long_name": c.get("long_name", c["label"]),
                "jurisdiction": c.get("jurisdiction"),
                "language": c.get("language", "en"),
                "default_selected": c.get("default_selected", False),
                "loaded": c["id"] in loaded,
            })
        return out

    # ---------------------------------------------------------------- retrieval
    def _embed_query(self, text: str) -> np.ndarray:
        body = json.dumps({
            "inputText": text[:8000],
            "dimensions": BEDROCK_EMBED_DIM,
            "normalize": True,
        })
        resp = self.bedrock_runtime.invoke_model(
            modelId=BEDROCK_EMBED_MODEL_ID,
            contentType="application/json",
            accept="application/json",
            body=body,
        )
        payload = json.loads(resp["body"].read())
        return np.asarray(payload["embedding"], dtype="float32")

    def retrieve(
        self,
        question: str,
        selected_codes: Sequence[str],
        top_k: int = 6,
    ) -> List[RetrievedChunk]:
        if not self.is_ready():
            raise RuntimeError("Code assistant is not ready (no indexes loaded)")
        codes = [c for c in selected_codes if c in self.store.available_codes()] or self.store.available_codes()
        vec = self._embed_query(question)
        return self.store.search(vec, codes=codes, top_k=top_k)

    # ---------------------------------------------------------------- generation
    def _build_messages(
        self,
        question: str,
        hits: List[RetrievedChunk],
        history: Optional[List[dict]],
    ) -> tuple[list[dict], str]:
        context_lines = []
        for i, h in enumerate(hits, start=1):
            header = f"[{i}] {h.citation()}"
            context_lines.append(f"{header}\n{h.text}")
        context_block = "\n\n---\n\n".join(context_lines) if context_lines else "(no context retrieved)"

        # Truncate history to the last N turns to keep prompts small.
        trimmed_history = (history or [])[-2 * MAX_HISTORY_TURNS:]
        messages: list[dict] = []
        for turn in trimmed_history:
            role = turn.get("role")
            content = (turn.get("content") or "").strip()
            if role not in ("user", "assistant") or not content:
                continue
            messages.append({"role": role, "content": [{"text": content}]})

        user_content = (
            f"CONTEXT:\n{context_block}\n\n"
            f"QUESTION:\n{question}\n\n"
            "Answer using only the CONTEXT above. Cite sources as [1], [2], etc."
        )
        messages.append({"role": "user", "content": [{"text": user_content}]})
        return messages, context_block

    def answer_stream(
        self,
        question: str,
        selected_codes: Sequence[str],
        history: Optional[List[dict]] = None,
        top_k: int = 6,
    ) -> Iterator[dict]:
        """Yield events (dicts) for SSE streaming.

        Event types:
          - {"type": "citations", "citations": [...]}    (once, before generation)
          - {"type": "delta", "text": "..."}              (many, as tokens arrive)
          - {"type": "done", "usage": {...}}              (final)
          - {"type": "error", "message": "..."}           (on failure)
        """
        try:
            hits = self.retrieve(question, selected_codes=selected_codes, top_k=top_k)
        except Exception as e:  # noqa: BLE001
            yield {"type": "error", "message": f"Retrieval failed: {e}"}
            return

        yield {"type": "citations", "citations": [h.to_dict() for h in hits]}

        messages, _ = self._build_messages(question, hits, history)

        try:
            resp = self.bedrock_runtime.converse_stream(
                modelId=BEDROCK_MODEL_ID,
                system=[{"text": _SYSTEM_PROMPT}],
                messages=messages,
                inferenceConfig={
                    "maxTokens": 1024,
                    "temperature": 0.2,
                    "topP": 0.9,
                },
            )
        except Exception as e:  # noqa: BLE001
            logger.exception("Bedrock converse_stream failed")
            yield {"type": "error", "message": f"LLM call failed: {e}"}
            return

        usage: dict = {}
        try:
            for event in resp["stream"]:
                if "contentBlockDelta" in event:
                    delta = event["contentBlockDelta"].get("delta", {})
                    text = delta.get("text")
                    if text:
                        yield {"type": "delta", "text": text}
                elif "metadata" in event:
                    md = event["metadata"]
                    if "usage" in md:
                        usage = md["usage"]
                elif "messageStop" in event:
                    pass
        except Exception as e:  # noqa: BLE001
            logger.exception("Streaming error")
            yield {"type": "error", "message": f"Stream error: {e}"}
            return

        yield {"type": "done", "usage": usage, "model_id": BEDROCK_MODEL_ID}


# Singleton accessor -------------------------------------------------------------------
_service: Optional[CodeAssistantService] = None


def get_service() -> CodeAssistantService:
    global _service
    if _service is None:
        _service = CodeAssistantService()
    return _service
