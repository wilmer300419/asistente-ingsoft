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

## Flujo con las herramientas del taller

1. **GitHub**: sube el proyecto (el `.env` queda fuera por el `.gitignore`).
   ```bash
   git remote add origin https://github.com/TU_USUARIO/asistente-ingsoft.git
   git push -u origin main
   ```
2. **Render**: New > Web Service > conecta el repositorio. Render lee `render.yaml`.
   Pega `GEMINI_API_KEY` (y `FORM_URL`) en Environment. Al terminar tendrás una URL `https://....onrender.com`.
   El plan gratuito se "duerme" tras unos minutos sin uso: abre la URL antes de la sustentación.
3. **Google Forms**: crea el formulario con `FORMULARIO_GOOGLE_FORMS.md`, copia el enlace en `FORM_URL`. La app lo muestra en `/encuesta`.
4. **Google Sites**: Insertar > Insertar URL > pega la URL de Render > Insertar. La app ya permite ser incrustada desde Google Sites.

## Registro de pruebas (SQLite)

Cada pregunta y respuesta se guarda en `registros.db` (SQLite). Para la Fase 4 abre `/registros`
(en local, `http://127.0.0.1:5000/registros`; en Render, `https://TU-URL/registros?token=TU_ADMIN_TOKEN`),
escribe por prueba la evaluación, el error identificado y la mejora del prompt, y descarga todo en CSV.

- En Render gratuito el disco es efímero: el archivo se borra al redesplegar o reiniciar. Descarga el CSV antes de cerrar.
- Los registros guardan lo que escriben los usuarios: no pidas datos personales en la encuesta ni en las preguntas.

## Seguridad

- La clave API solo existe en el servidor (variable de entorno); `.env` está en `.gitignore`.
- Límite de longitud por pregunta y de 20 peticiones por minuto por IP.
- La salida del modelo se sanea con DOMPurify antes de mostrarse.
