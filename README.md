# Asistente Inteligente de Ingeniería de Software

Prototipo Flask que conecta una interfaz web con un LLM (Gemini) mediante la API de Google AI Studio.

```
Navegador --> Flask (/api/chat) --> API de Gemini --> Flask --> Navegador
```

## Ejecutar en local

```bash
python -m venv venv
venv\Scripts\activate          # Windows   (Linux/Mac: source venv/bin/activate)
pip install -r requirements.txt
copy .env.example .env         # Linux/Mac: cp .env.example .env
# edita .env y pega GEMINI_API_KEY (clave de https://aistudio.google.com/apikey)
python app.py
```

Abre http://127.0.0.1:5000. Sin clave API la app corre en modo demostración.

## Desplegar en Render (opcional)

- Build command: `pip install -r requirements.txt`
- Start command: `gunicorn app:app`
- Variables de entorno: `GEMINI_API_KEY`, `GEMINI_MODEL`, `FORM_URL`

## Seguridad

- La clave API solo existe en el servidor (variable de entorno); `.env` está en `.gitignore`.
- Límite de longitud por pregunta y de 20 peticiones por minuto por IP.
- La salida del modelo se sanea con DOMPurify antes de mostrarse.
