import { FormEvent, useEffect, useState } from "react";
import DevPanel from "./DevPanel";
import MemoryPanel from "./MemoryPanel";

type Message = {
  role: "user" | "assistant";
  content: string;
  memoriesUsed?: number;
  engine?: string;
  externalTraffic?: boolean;
  agent?: string;
  toolCalls?: number;
};

type Conversation = {
  id: string;
  title: string;
  created_at: string;
  updated_at: string;
};

type StoredConversation = Conversation & {
  messages: Array<{ id: number; role: "user" | "assistant"; content: string; created_at: string }>;
};

type CoreHealth = {
  status: string;
  inference: string;
};

type ActiveTab = "chat" | "memory" | "dev";

export default function App() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [health, setHealth] = useState<CoreHealth | null>(null);
  const [error, setError] = useState("");
  const [activeTab, setActiveTab] = useState<ActiveTab>("chat");
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [currentConversationId, setCurrentConversationId] = useState<string | null>(null);
  const [historyLoading, setHistoryLoading] = useState(true);

  useEffect(() => {
    let active = true;
    async function restoreLatestConversation() {
      try {
        const response = await fetch("/api/v1/conversations?limit=30");
        if (!response.ok) throw new Error("Não foi possível carregar o histórico.");
        const items = (await response.json()) as Conversation[];
        if (!active) return;
        setConversations(items);
        if (items.length > 0) {
          const latest = await fetch(`/api/v1/conversations/${items[0].id}`);
          if (!latest.ok) throw new Error("Não foi possível restaurar a conversa.");
          const detail = (await latest.json()) as StoredConversation;
          if (!active) return;
          setCurrentConversationId(detail.id);
          setMessages(detail.messages.map((message) => ({
            role: message.role,
            content: message.content,
          })));
        }
      } catch (cause) {
        if (active) setError(cause instanceof Error ? cause.message : "Falha ao carregar histórico.");
      } finally {
        if (active) setHistoryLoading(false);
      }
    }
    void restoreLatestConversation();
    return () => { active = false; };
  }, []);

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
      let conversationId = currentConversationId;
      if (!conversationId) {
        const created = await fetch("/api/v1/conversations", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ title: "Nova conversa" }),
        });
        if (!created.ok) throw new Error("Não foi possível iniciar uma conversa.");
        const conversation = (await created.json()) as Conversation;
        conversationId = conversation.id;
        setCurrentConversationId(conversationId);
        setConversations((current) => [conversation, ...current]);
      }

      const response = await fetch("/api/v1/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ messages: nextMessages.slice(-40), conversation_id: conversationId }),
      });
      const data = (await response.json()) as {
        content?: string;
        engine?: string;
        external_traffic?: boolean;
        memories_used?: number;
        agent?: string;
        tool_calls?: number;
        detail?: string | { message?: string };
      };
      if (!response.ok) {
        const detail =
          typeof data.detail === "string" ? data.detail : data.detail?.message;
        throw new Error(detail ?? "Não consegui falar com o modelo local.");
      }
      if (data.content) {
        setMessages((current) => [
          ...current,
          {
            role: "assistant",
            content: data.content!,
            memoriesUsed: data.memories_used ?? 0,
            engine: data.engine ?? "local",
            externalTraffic: data.external_traffic ?? false,
            agent: data.agent ?? "simple",
            toolCalls: data.tool_calls ?? 0,
          },
        ]);
        const history = await fetch("/api/v1/conversations?limit=30");
        if (history.ok) setConversations((await history.json()) as Conversation[]);
      }
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Falha ao enviar mensagem.");
    } finally {
      setBusy(false);
    }
  }

  async function openConversation(conversationId: string) {
    if (!conversationId) {
      startNewConversation();
      return;
    }
    if (busy) return;
    setBusy(true);
    setError("");
    try {
      const response = await fetch(`/api/v1/conversations/${conversationId}`);
      if (!response.ok) throw new Error("Não foi possível abrir essa conversa.");
      const detail = (await response.json()) as StoredConversation;
      setCurrentConversationId(detail.id);
      setMessages(detail.messages.map((message) => ({
        role: message.role,
        content: message.content,
      })));
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Falha ao abrir conversa.");
    } finally {
      setBusy(false);
    }
  }

  function startNewConversation() {
    if (busy) return;
    setCurrentConversationId(null);
    setMessages([]);
    setDraft("");
    setError("");
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

        <nav className="tabs" aria-label="Seções da Lia">
          <button
            type="button"
            className={activeTab === "chat" ? "tab active" : "tab"}
            onClick={() => setActiveTab("chat")}
          >
            Conversa
          </button>
          <button
            type="button"
            className={activeTab === "memory" ? "tab active" : "tab"}
            onClick={() => setActiveTab("memory")}
          >
            Memória
          </button>
          <button
            type="button"
            className={activeTab === "dev" ? "tab active" : "tab"}
            onClick={() => setActiveTab("dev")}
          >
            Lia Dev
          </button>
        </nav>

        {activeTab === "dev" ? (
          <DevPanel />
        ) : activeTab === "memory" ? (
          <MemoryPanel />
        ) : (
          <>
            <div className="conversation-toolbar">
              <label htmlFor="conversation-select">Histórico</label>
              <select
                id="conversation-select"
                value={currentConversationId ?? ""}
                onChange={(event) => void openConversation(event.target.value)}
                disabled={busy || historyLoading}
              >
                <option value="">Nova conversa</option>
                {conversations.map((conversation) => (
                  <option key={conversation.id} value={conversation.id}>{conversation.title}</option>
                ))}
              </select>
              <button type="button" onClick={startNewConversation} disabled={busy}>Nova conversa</button>
            </div>
            <div className="conversation" aria-live="polite">
              {historyLoading ? (
                <div className="thinking">Restaurando seu histórico…</div>
              ) : messages.length === 0 ? (
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
                      {message.role === "assistant" && (
                        <small className="message-meta">
                          {message.engine ?? "local"} · {message.externalTraffic ? "tráfego externo" : "somente local"}
                          {(message.memoriesUsed ?? 0) > 0 && ` · ${message.memoriesUsed} memórias usadas`}{message.agent && ` · ${message.agent}`}{(message.toolCalls ?? 0) > 0 && ` · ${message.toolCalls} ferramentas`}
                        </small>
                      )}
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
                disabled={busy || historyLoading}
              />
              <button type="submit" disabled={busy || historyLoading || !draft.trim()}>
                {busy ? "…" : "Enviar"}
              </button>
            </form>
            <footer className="footer-note">
              {health?.inference === "local_endpoint_configured"
                ? "Inferência configurada para o servidor local · nenhum fallback remoto"
                : "Inicie o núcleo Python e o servidor llama.cpp para conversar"}
            </footer>
          </>
        )}
      </section>
    </main>
  );
}
