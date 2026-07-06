"""Memoria de LARGO PLAZO del agente (durable, cross-sesión) sobre Supabase/pgvector.

Complementa la memoria de corto plazo (`InMemorySaver` en agent_core), que vive solo
en el proceso. Aquí cada turno se persiste en la tabla `public.agent_memory` y se
recupera contexto relevante en cada consulta.

Recuperación (recall) con degradación elegante:
  1. Historial reciente de la MISMA sesión (continuidad tras reinicios).
  2. Recuerdos relevantes de OTRAS sesiones:
       - semántica con pgvector (`embedding <=> query`) si hay embeddings, o
       - léxica full-text en español si no hay proveedor de embeddings.

Requisitos: backend Supabase (con SQLite se desactiva silenciosamente). El rol de la
app necesita SELECT+INSERT sobre `agent_memory` (ya concedido a `bsg_app`).

Embeddings (opcional): define EMBEDDINGS_API_KEY (+ EMBEDDINGS_BASE_URL / EMBEDDINGS_MODEL)
para activar la búsqueda semántica. Sin eso, funciona en modo léxico.
"""
from __future__ import annotations

import json
import os
import urllib.request

from db import backend_activo, run_query

EMBED_MODEL = os.getenv("EMBEDDINGS_MODEL", "text-embedding-3-small")
EMBED_BASE_URL = os.getenv("EMBEDDINGS_BASE_URL", "https://api.openai.com/v1")
RECALL_K = int(os.getenv("MEMORY_RECALL_K", "4"))


def memory_enabled() -> bool:
    """La memoria de largo plazo solo opera con backend Supabase y si no se desactiva."""
    if os.getenv("AGENT_MEMORY", "on").strip().lower() in {"off", "0", "false"}:
        return False
    return backend_activo() == "supabase"


def _embed(text: str) -> list[float] | None:
    """Genera un embedding con un proveedor OpenAI-compatible. None si no hay clave/soporte."""
    key = os.getenv("EMBEDDINGS_API_KEY")
    if not key or not text.strip():
        return None
    try:
        payload = json.dumps({"model": EMBED_MODEL, "input": text[:8000]}).encode()
        req = urllib.request.Request(
            f"{EMBED_BASE_URL}/embeddings",
            data=payload,
            headers={"content-type": "application/json", "authorization": f"Bearer {key}"},
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())
        return data["data"][0]["embedding"]
    except Exception:  # noqa: BLE001 - la memoria es best-effort; nunca rompe el turno
        return None


def _vec_literal(embedding: list[float]) -> str:
    return "[" + ",".join(f"{x:.6f}" for x in embedding) + "]"


def save_turn(session_id: str, canal: str, rol: str, contenido: str) -> None:
    """Persiste un turno (con embedding si hay proveedor). Best-effort: nunca lanza."""
    if not memory_enabled() or not (contenido or "").strip():
        return
    try:
        emb = _embed(contenido)
        if emb is not None:
            run_query(
                "INSERT INTO agent_memory (session_id, canal, rol, contenido, embedding) "
                "VALUES (?, ?, ?, ?, ?::vector) RETURNING id",
                (session_id, canal, rol, contenido, _vec_literal(emb)),
            )
        else:
            run_query(
                "INSERT INTO agent_memory (session_id, canal, rol, contenido) "
                "VALUES (?, ?, ?, ?) RETURNING id",
                (session_id, canal, rol, contenido),
            )
    except Exception:  # noqa: BLE001
        pass


def recall(session_id: str, query: str, k: int = RECALL_K) -> list[dict]:
    """Recupera recuerdos relevantes: recientes de la sesión + relacionados de otras."""
    if not memory_enabled():
        return []
    out: list[dict] = []
    seen: set[str] = set()
    try:
        recent = run_query(
            "SELECT rol, contenido FROM agent_memory WHERE session_id = ? "
            "ORDER BY created_at DESC LIMIT ?",
            (session_id, k),
        )
        for r in reversed(recent):  # cronológico
            key = r["contenido"][:120]
            if key not in seen:
                seen.add(key)
                out.append({"origen": "sesion", "rol": r["rol"], "contenido": r["contenido"]})
    except Exception:  # noqa: BLE001
        pass

    # Relacionados de otras sesiones: semántico (pgvector) o léxico (full-text).
    try:
        emb = _embed(query)
        if emb is not None:
            rel = run_query(
                "SELECT rol, contenido FROM agent_memory "
                "WHERE embedding IS NOT NULL AND session_id <> ? "
                "ORDER BY embedding <=> ?::vector LIMIT ?",
                (session_id, _vec_literal(emb), k),
            )
        else:
            # Léxico: convierte el AND de plainto_tsquery en OR para recall por
            # relevancia parcial (cualquier término relevante suma, y se rankea).
            rel = run_query(
                "SELECT rol, contenido, "
                "ts_rank(to_tsvector('spanish', contenido), q.query) AS rank "
                "FROM agent_memory "
                "CROSS JOIN (SELECT replace(plainto_tsquery('spanish', ?)::text, '&', '|')::tsquery AS query) q "
                "WHERE session_id <> ? AND q.query::text <> '' "
                "AND to_tsvector('spanish', contenido) @@ q.query "
                "ORDER BY rank DESC LIMIT ?",
                (query, session_id, k),
            )
        for r in rel:
            key = r["contenido"][:120]
            if key not in seen:
                seen.add(key)
                out.append({"origen": "relacionado", "rol": r["rol"], "contenido": r["contenido"]})
    except Exception:  # noqa: BLE001
        pass

    return out


def format_context(recuerdos: list[dict], max_chars: int = 220) -> str:
    """Convierte los recuerdos en un bloque de texto para inyectar en el system prompt."""
    if not recuerdos:
        return ""
    lines = []
    for m in recuerdos:
        txt = m["contenido"].replace("\n", " ").strip()
        if len(txt) > max_chars:
            txt = txt[:max_chars] + "…"
        etiqueta = "usuario" if m["rol"] == "user" else "asistente"
        lines.append(f"- ({m['origen']}/{etiqueta}) {txt}")
    return "\n".join(lines)


def semantic_mode() -> str:
    """Indica si el recall usa embeddings o léxico (para trazabilidad/UI)."""
    return "semantico(pgvector)" if os.getenv("EMBEDDINGS_API_KEY") else "lexico(full-text)"
