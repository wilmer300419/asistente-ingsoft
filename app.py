"""
Asistente Inteligente de Ingeniería de Software
Prototipo Flask que integra un LLM (Gemini, vía Google AI Studio API).

Arquitectura:  Navegador  ->  Flask (/api/chat)  ->  API de Gemini  ->  respuesta
La clave API vive solo en el servidor (variable de entorno), nunca en el navegador.
"""
import csv
import hmac
import io
import logging
import os
import sqlite3
import time
from collections import defaultdict, deque
from contextlib import closing
from datetime import datetime, timezone

from dotenv import load_dotenv
from flask import Flask, Response, jsonify, render_template, request

load_dotenv()

API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
FORM_URL = os.getenv("FORM_URL", "").strip()

DB_PATH = os.getenv("DB_PATH", os.path.join(os.path.dirname(os.path.abspath(__file__)), "registros.db"))
ADMIN_TOKEN = os.getenv("ADMIN_TOKEN", "").strip()

MAX_CHARS = 1500          # longitud máxima de una pregunta
MAX_HISTORY = 10          # mensajes previos que se envían al modelo
RATE_LIMIT = 20           # peticiones por minuto por IP

SYSTEM_PROMPT = """Rol: eres un asistente virtual especializado en Ingeniería de Software.

Objetivo: ayudar a estudiantes universitarios a comprender conceptos relacionados con el desarrollo de software.

Instrucciones:
- Responde siempre en español, con lenguaje claro y académico.
- Explica los conceptos mediante ejemplos prácticos.
- Organiza las respuestas en pasos cuando sea necesario.
- Si no tienes información suficiente, indícalo expresamente y pide los datos que faltan.
- Si la pregunta es ambigua, formula dos o tres preguntas aclaratorias antes de responder.
- No inventes fuentes bibliográficas, enlaces, DOI ni datos estadísticos. Si te piden referencias, menciona solo obras que conozcas con certeza (autor y título) y advierte que el estudiante debe verificarlas.
- Advierte cuando una respuesta deba verificarse con documentación técnica oficial.
- Si la pregunta no tiene relación con ingeniería de software o tecnología, indícalo con amabilidad y redirige al tema.

Formato de respuesta (usa Markdown):
**Definición:** una o dos frases.
**Explicación:** el desarrollo del concepto.
**Ejemplo:** un caso práctico o fragmento de código.
**Recomendación práctica:** un consejo accionable o qué verificar.
"""

app = Flask(__name__)
if os.getenv("TRUST_PROXY") == "1":  # detrás de Render: toma la IP real del visitante
    from werkzeug.middleware.proxy_fix import ProxyFix
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("asistente")

_client = None
if API_KEY:
    from google import genai
    _client = genai.Client(api_key=API_KEY)

_hits = defaultdict(deque)

# ---------------------------------------------------------------- SQLite
def db():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con


def init_db():
    with closing(db()) as con, con:
        con.execute("""
            CREATE TABLE IF NOT EXISTS registros (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                creado TEXT NOT NULL,
                sesion TEXT,
                pregunta TEXT NOT NULL,
                respuesta TEXT,
                modelo TEXT,
                demo INTEGER NOT NULL DEFAULT 0,
                latencia_ms INTEGER,
                estado TEXT NOT NULL DEFAULT 'ok',
                evaluacion TEXT DEFAULT '',
                error_identificado TEXT DEFAULT '',
                mejora_prompt TEXT DEFAULT ''
            )""")


def log_registro(sesion, pregunta, respuesta, demo, latencia_ms, estado):
    """Guarda cada interacción. Un fallo al guardar nunca debe romper el chat."""
    try:
        with closing(db()) as con, con:
            con.execute(
                "INSERT INTO registros (creado, sesion, pregunta, respuesta, modelo, demo, latencia_ms, estado)"
                " VALUES (?,?,?,?,?,?,?,?)",
                (datetime.now(timezone.utc).isoformat(timespec="seconds"), sesion[:64], pregunta,
                 respuesta, MODEL, int(demo), latencia_ms, estado),
            )
    except Exception:
        log.exception("No se pudo guardar el registro")


def admin_ok() -> bool:
    """Con ADMIN_TOKEN: exige el token. Sin token: solo permite acceso desde el mismo equipo."""
    if ADMIN_TOKEN:
        given = request.args.get("token") or request.headers.get("X-Admin-Token", "")
        return hmac.compare_digest(given, ADMIN_TOKEN)
    return request.remote_addr in ("127.0.0.1", "::1")


init_db()


@app.after_request
def allow_google_sites(resp):
    """Permite incrustar la app en Google Sites (Insertar > URL) sin abrirla a cualquier sitio."""
    resp.headers["Content-Security-Policy"] = (
        "frame-ancestors 'self' https://sites.google.com https://*.google.com https://*.googleusercontent.com"
    )
    return resp


def form_embed_url() -> str:
    if not FORM_URL:
        return ""
    if "embedded=true" in FORM_URL:
        return FORM_URL
    return FORM_URL + ("&" if "?" in FORM_URL else "?") + "embedded=true"


def rate_limited(ip: str) -> bool:
    now = time.time()
    q = _hits[ip]
    while q and now - q[0] > 60:
        q.popleft()
    if len(q) >= RATE_LIMIT:
        return True
    q.append(now)
    return False


def demo_answer(question: str) -> str:
    return (
        "**[Modo demostración: no hay clave API configurada]**\n\n"
        f"Pregunta recibida: *{question}*\n\n"
        "**Definición:** respuesta simulada para probar la interfaz.\n\n"
        "**Explicación:** el servidor Flask recibió tu pregunta, pero como falta "
        "`GEMINI_API_KEY` no la envió al modelo.\n\n"
        "**Ejemplo:** crea un archivo `.env` con tu clave de Google AI Studio.\n\n"
        "**Recomendación práctica:** reinicia el servidor después de guardar la clave."
    )


def ask_llm(question: str, history: list) -> str:
    from google.genai import types

    contents = []
    for m in history[-MAX_HISTORY:]:
        role = "user" if m.get("role") == "user" else "model"
        text = str(m.get("text", ""))[:MAX_CHARS * 3]
        if text:
            contents.append(types.Content(role=role, parts=[types.Part(text=text)]))
    contents.append(types.Content(role="user", parts=[types.Part(text=question)]))

    response = _client.models.generate_content(
        model=MODEL,
        contents=contents,
        config=types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT,
            temperature=0.4,       # baja: respuestas más precisas y menos inventadas
            max_output_tokens=1500,
        ),
    )
    return (response.text or "").strip() or "El modelo no devolvió texto. Intenta reformular la pregunta."


@app.get("/")
def index():
    return render_template("index.html", model=MODEL, demo=_client is None, form_url=FORM_URL)


@app.get("/encuesta")
def encuesta():
    return render_template("encuesta.html", embed_url=form_embed_url(), form_url=FORM_URL)


@app.get("/registros")
def registros():
    if not admin_ok():
        return jsonify(error="No autorizado."), 403
    with closing(db()) as con:
        rows = con.execute("SELECT * FROM registros ORDER BY id DESC LIMIT 500").fetchall()
        total = con.execute("SELECT COUNT(*) FROM registros").fetchone()[0]
    return render_template("registros.html", rows=rows, total=total, token=request.args.get("token", ""))


@app.put("/api/registros/<int:rid>")
def actualizar_registro(rid):
    if not admin_ok():
        return jsonify(error="No autorizado."), 403
    d = request.get_json(silent=True) or {}
    vals = [str(d.get(k, ""))[:2000] for k in ("evaluacion", "error_identificado", "mejora_prompt")]
    with closing(db()) as con, con:
        cur = con.execute(
            "UPDATE registros SET evaluacion=?, error_identificado=?, mejora_prompt=? WHERE id=?", (*vals, rid))
    if cur.rowcount == 0:
        return jsonify(error="Registro no encontrado."), 404
    return jsonify(ok=True)


@app.get("/registros.csv")
def registros_csv():
    if not admin_ok():
        return jsonify(error="No autorizado."), 403
    with closing(db()) as con:
        rows = con.execute("SELECT * FROM registros ORDER BY id").fetchall()
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(["id", "fecha_utc", "sesion", "pregunta", "respuesta", "modelo", "demo", "latencia_ms",
                "estado", "evaluacion", "error_identificado", "mejora_prompt"])
    for r in rows:
        w.writerow([r["id"], r["creado"], r["sesion"], r["pregunta"], r["respuesta"], r["modelo"], r["demo"],
                    r["latencia_ms"], r["estado"], r["evaluacion"], r["error_identificado"], r["mejora_prompt"]])
    # utf-8-sig para que Excel abra bien las tildes
    return Response("\ufeff" + out.getvalue(), mimetype="text/csv; charset=utf-8",
                    headers={"Content-Disposition": "attachment; filename=registros_pruebas.csv"})


@app.get("/health")
def health():
    return jsonify(status="ok", model=MODEL, demo=_client is None)


@app.post("/api/chat")
def chat():
    if rate_limited(request.remote_addr or "?"):
        return jsonify(error="Demasiadas preguntas seguidas. Espera un minuto e intenta de nuevo."), 429

    data = request.get_json(silent=True) or {}
    question = str(data.get("message", "")).strip()
    history = data.get("history", [])
    if not isinstance(history, list):
        history = []
    sesion = str(data.get("session", ""))

    if not question:
        return jsonify(error="Escribe una pregunta antes de enviar."), 400
    if len(question) > MAX_CHARS:
        return jsonify(error=f"La pregunta supera {MAX_CHARS} caracteres. Acórtala e intenta de nuevo."), 400

    started = time.time()
    if _client is None:
        answer = demo_answer(question)
        log_registro(sesion, question, answer, True, 0, "ok")
        return jsonify(answer=answer, demo=True)

    try:
        answer = ask_llm(question, history)
        ms = int((time.time() - started) * 1000)
        log.info("pregunta=%d chars, respuesta=%d chars, %d ms", len(question), len(answer), ms)
        log_registro(sesion, question, answer, False, ms, "ok")
        return jsonify(answer=answer, demo=False)
    except Exception as exc:  # error de red, cuota, clave inválida...
        log.exception("Fallo al consultar el modelo: %s", exc)
        log_registro(sesion, question, None, False, int((time.time() - started) * 1000), "error")
        return jsonify(error="No se pudo consultar el modelo. Revisa la clave API, la cuota o tu conexión."), 502


if __name__ == "__main__":
    app.run(debug=os.getenv("FLASK_DEBUG") == "1", port=int(os.getenv("PORT", 5000)))
