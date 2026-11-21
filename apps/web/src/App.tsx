import { FormEvent, useEffect, useState } from "react";

type Message = {
  role: "user" | "assistant";
  content: string;
};

type CoreHealth = {
  status: string;
  inference: string;
};

export default function App() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [health, setHealth] = useState<CoreHealth | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;
    const checkHealth = async () => {
      try {
        const response = await fetch("/health");
        if (!response.ok) throw new Error("Núcleo indisponível");
        const data = (await response.json()) as CoreHealth;
        if (active) setHealth(data);
      } catch {
        if (active) setHealth(null);
      }
    };
    void checkHealth();
    const interval = window.setInterval(checkHealth, 10000);
    return () => {
      active = false;
      window.clearInterval(interval);
    };
  }, []);

  async function sendMessage(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const content = draft.trim();
    if (!content || busy) return;

    const nextMessages: Message[] = [...messages, { role: "user", content }];
    setMessages(nextMessages);
    setDraft("");
    setError("");
    setBusy(true);

    try {
      const response = await fetch("/api/v1/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ messages: nextMessages }),
      });
      const data = (await response.json()) as {
        content?: string;
        detail?: string | { message?: string };
      };
      if (!response.ok) {
        const detail =
          typeof data.detail === "string" ? data.detail : data.detail?.message;
        throw new Error(detail ?? "Não consegui falar com o modelo local.");
      }
      if (data.content) {
        setMessages((current) => [...current, { role: "assistant", content: data.content! }]);
      }
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Falha ao enviar mensagem.");
    } finally {
      setBusy(false);
    }
  }

  const connected = health?.status === "ok";

  return (
    <main className="shell">
      <section className="chat-panel" aria-labelledby="lia-title">
        <header className="topbar">
          <div className="brand">
            <div className="brand-mark">L</div>
            <div>
              <h1 id="lia-title">Lia</h1>
              <span>Assistente pessoal local-first</span>
            </div>
          </div>
          <div className={connected ? "connection online" : "connection offline"}>
            <span className="status-dot" />
            {connected ? "Núcleo conectado" : "Núcleo desconectado"}
          </div>
        </header>

        <div className="conversation" aria-live="polite">
          {messages.length === 0 ? (
            <div className="welcome">
              <div className="welcome-orb">L</div>
              <h2>Olá. Eu sou a Lia.</h2>
              <p>
                Estou sendo construída para funcionar no seu dispositivo, com memória própria
                e sem depender de cotas de inteligência artificial na nuvem.
              </p>
              <div className="feature-row">
                <span>IA local</span>
                <span>Memória independente</span>
                <span>Lia Dev</span>
              </div>
            </div>
          ) : (
            <div className="messages">
              {messages.map((message, index) => (
                <article className={`message ${message.role}`} key={index}>
                  <span className="message-author">{message.role === "user" ? "Você" : "Lia"}</span>
                  <p>{message.content}</p>
                </article>
              ))}
              {busy && <div className="thinking">Lia está pensando localmente…</div>}
            </div>
          )}
        </div>

        {error && <div className="error-banner" role="alert">{error}</div>}

        <form className="composer" onSubmit={sendMessage}>
          <textarea
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            placeholder="Converse com a Lia…"
            aria-label="Mensagem para Lia"
            rows={2}
            disabled={busy}
          />
          <button type="submit" disabled={busy || !draft.trim()}>
            {busy ? "…" : "Enviar"}
          </button>
        </form>
        <footer className="footer-note">
          {health?.inference === "local_endpoint_configured"
            ? "Inferência configurada para o servidor local · nenhum fallback remoto"
            : "Inicie o núcleo Python e o servidor llama.cpp para conversar"}
        </footer>
      </section>
    </main>
  );
}
