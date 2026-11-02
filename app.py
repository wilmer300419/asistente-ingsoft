"""
Asistente Inteligente de Ingeniería de Software
Prototipo Flask que integra un LLM (Gemini, vía Google AI Studio API).

Arquitectura:  Navegador  ->  Flask (/api/chat)  ->  API de Gemini  ->  respuesta
La clave API vive solo en el servidor (variable de entorno), nunca en el navegador.
"""
import logging
import os
import time
from collections import defaultdict, deque

from dotenv import load_dotenv
from flask import Flask, jsonify, render_template, request

load_dotenv()

API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
FORM_URL = os.getenv("FORM_URL", "").strip()

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
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("asistente")

_client = None
if API_KEY:
    from google import genai
    _client = genai.Client(api_key=API_KEY)

_hits = defaultdict(deque)


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

    if not question:
        return jsonify(error="Escribe una pregunta antes de enviar."), 400
    if len(question) > MAX_CHARS:
        return jsonify(error=f"La pregunta supera {MAX_CHARS} caracteres. Acórtala e intenta de nuevo."), 400

    if _client is None:
        return jsonify(answer=demo_answer(question), demo=True)

    try:
        started = time.time()
        answer = ask_llm(question, history)
        log.info("pregunta=%d chars, respuesta=%d chars, %.1fs", len(question), len(answer), time.time() - started)
        return jsonify(answer=answer, demo=False)
    except Exception as exc:  # error de red, cuota, clave inválida...
        log.exception("Fallo al consultar el modelo: %s", exc)
        return jsonify(error="No se pudo consultar el modelo. Revisa la clave API, la cuota o tu conexión."), 502


if __name__ == "__main__":
    app.run(debug=os.getenv("FLASK_DEBUG") == "1", port=int(os.getenv("PORT", 5000)))
