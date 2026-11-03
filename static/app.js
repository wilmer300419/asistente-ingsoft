const log = document.getElementById("log");
const form = document.getElementById("form");
const input = document.getElementById("input");
const sendBtn = document.getElementById("send");
const empty = document.getElementById("empty");

const session = (crypto.randomUUID ? crypto.randomUUID() : String(Date.now()));
let history = []; // [{role: "user"|"model", text}]

function render(md) {
  if (window.marked && window.DOMPurify) {
    return DOMPurify.sanitize(marked.parse(md));
  }
  const p = document.createElement("p");
  p.textContent = md;
  return p.outerHTML;
}

function addMessage(kind, text, opts = {}) {
  if (empty) empty.remove();
  const wrap = document.createElement("div");
  wrap.className = "msg " + kind;
  const who = document.createElement("div");
  who.className = "who";
  who.textContent = kind === "user" ? "Tú" : kind === "error" ? "Error" : "Asistente";
  const bubble = document.createElement("div");
  bubble.className = "bubble";
  if (kind === "bot") bubble.innerHTML = render(text);
  else bubble.textContent = text;
  wrap.append(who, bubble);
  if (kind === "bot" && !opts.demo) {
    const note = document.createElement("div");
    note.className = "note";
    note.textContent = "Respuesta generada por IA: verifícala con documentación técnica antes de usarla.";
    wrap.append(note);
  }
  log.append(wrap);
  log.scrollTop = log.scrollHeight;
  return wrap;
}

async function ask(question) {
  question = question.trim();
  if (!question) return;
  addMessage("user", question);
  input.value = "";
  input.style.height = "auto";
  sendBtn.disabled = true;
  const typing = addMessage("bot", "Pensando…", { demo: true });
  typing.querySelector(".bubble").classList.add("typing");

  try {
    const res = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message: question, history, session }),
    });
    const data = await res.json();
    typing.remove();
    if (!res.ok) {
      addMessage("error", data.error || "Ocurrió un error inesperado.");
    } else {
      addMessage("bot", data.answer, { demo: data.demo });
      history.push({ role: "user", text: question }, { role: "model", text: data.answer });
    }
  } catch (e) {
    typing.remove();
    addMessage("error", "No hay conexión con el servidor. Verifica que Flask siga en ejecución.");
  } finally {
    sendBtn.disabled = false;
    input.focus();
  }
}

form.addEventListener("submit", (e) => { e.preventDefault(); ask(input.value); });
input.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); form.requestSubmit(); }
});
input.addEventListener("input", () => {
  input.style.height = "auto";
  input.style.height = Math.min(input.scrollHeight, 160) + "px";
});
document.getElementById("tests").addEventListener("click", (e) => {
  const b = e.target.closest("button[data-q]");
  if (b) ask(b.dataset.q);
});
document.getElementById("clear").addEventListener("click", () => location.reload());
