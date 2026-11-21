import { FormEvent, useEffect, useRef, useState } from "react";
import DevPanel from "./DevPanel";
import MemoryPanel from "./MemoryPanel";
import PairingPanel from "./PairingPanel";

type Message = {
  role: "user" | "assistant";
  content: string;
  memoriesUsed?: number;
  engine?: string;
  externalTraffic?: boolean;
  agent?: string;
  specialist?: string;
  toolCalls?: number;
  plan?: string[];
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

type ActiveTab = "chat" | "memory" | "devices" | "dev";

type VoiceStatus = {
  transcription_configured: boolean;
  synthesis_configured: boolean;
  processing: string;
};

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
  const [voiceStatus, setVoiceStatus] = useState<VoiceStatus | null>(null);
  const [recording, setRecording] = useState(false);
  const [voiceBusy, setVoiceBusy] = useState(false);
  const [playingMessage, setPlayingMessage] = useState<number | null>(null);
  const recorderRef = useRef<MediaRecorder | null>(null);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const audioUrlRef = useRef<string | null>(null);

  useEffect(() => {
    return () => {
      const recorder = recorderRef.current;
      if (recorder) {
        recorder.ondataavailable = null;
        recorder.onstop = null;
        recorder.onerror = null;
        recorder.stream.getTracks().forEach((track) => track.stop());
        if (recorder.state !== "inactive") recorder.stop();
        recorderRef.current = null;
      }
      audioRef.current?.pause();
      audioRef.current = null;
      if (audioUrlRef.current) URL.revokeObjectURL(audioUrlRef.current);
      audioUrlRef.current = null;
    };
  }, []);

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
    fetch("/api/v1/voice/status")
      .then((response) => {
        if (!response.ok) throw new Error("Status de voz indisponível.");
        return response.json() as Promise<VoiceStatus>;
      })
      .then((status) => { if (active) setVoiceStatus(status); })
      .catch(() => { if (active) setVoiceStatus(null); });
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

  async function submitMessage(content: string) {
    const normalized = content.trim();
    if (!normalized || busy) return;

    const nextMessages: Message[] = [...messages, { role: "user", content: normalized }];
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
        specialist?: string;
        tool_calls?: number;
        plan?: string[];
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
            specialist: data.specialist ?? "general",
            toolCalls: data.tool_calls ?? 0,
            plan: data.plan ?? [],
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

  async function sendMessage(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    await submitMessage(draft);
  }

  async function toggleRecording() {
    if (recording) {
      recorderRef.current?.stop();
      setRecording(false);
      return;
    }
    if (!voiceStatus?.transcription_configured) {
      setError("O reconhecimento local ainda não está configurado. Configure o servidor whisper.cpp.");
      return;
    }
    if (!navigator.mediaDevices?.getUserMedia || !window.MediaRecorder) {
      setError("Este navegador não oferece gravação de áudio compatível.");
      return;
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const preferredMime = "audio/webm;codecs=opus";
      const recorder = MediaRecorder.isTypeSupported(preferredMime)
        ? new MediaRecorder(stream, { mimeType: preferredMime })
        : new MediaRecorder(stream);
      const chunks: BlobPart[] = [];
      recorder.ondataavailable = (event) => {
        if (event.data.size > 0) chunks.push(event.data);
      };
      recorder.onstop = async () => {
        stream.getTracks().forEach((track) => track.stop());
        recorderRef.current = null;
        const audio = new Blob(chunks, { type: recorder.mimeType || "audio/webm" });
        if (!audio.size) {
          setError("Nenhum áudio foi capturado.");
          return;
        }
        setVoiceBusy(true);
        setError("");
        try {
          const response = await fetch("/api/v1/voice/transcriptions", {
            method: "POST",
            headers: { "Content-Type": audio.type || "audio/webm" },
            body: audio,
          });
          const data = (await response.json()) as { text?: string; detail?: string };
          if (!response.ok) throw new Error(data.detail ?? "Não foi possível transcrever o áudio.");
          if (data.text) await submitMessage(data.text);
        } catch (cause) {
          setError(cause instanceof Error ? cause.message : "Falha ao reconhecer a fala.");
        } finally {
          setVoiceBusy(false);
        }
      };
      recorder.onerror = () => {
        stream.getTracks().forEach((track) => track.stop());
        recorderRef.current = null;
        setRecording(false);
        setError("A gravação foi interrompida pelo navegador.");
      };
      recorderRef.current = recorder;
      recorder.start();
      setRecording(true);
      setError("");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Não foi possível acessar o microfone.");
    }
  }

  async function speakMessage(content: string, index: number) {
    if (!voiceStatus?.synthesis_configured || playingMessage !== null) return;
    setPlayingMessage(index);
    setError("");
    try {
      const response = await fetch("/api/v1/voice/speech", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text: content }),
      });
      if (!response.ok) {
        const data = (await response.json()) as { detail?: string };
        throw new Error(data.detail ?? "Não foi possível sintetizar a resposta.");
      }
      const audioUrl = URL.createObjectURL(await response.blob());
      const audio = new Audio(audioUrl);
      audioUrlRef.current = audioUrl;
      audioRef.current = audio;
      const cleanup = () => {
        URL.revokeObjectURL(audioUrl);
        if (audioUrlRef.current === audioUrl) audioUrlRef.current = null;
        if (audioRef.current === audio) audioRef.current = null;
        setPlayingMessage(null);
      };
      audio.onended = cleanup;
      audio.onerror = () => {
        cleanup();
        setError("O navegador não conseguiu reproduzir o áudio.");
      };
      await audio.play();
    } catch (cause) {
      audioRef.current?.pause();
      audioRef.current = null;
      if (audioUrlRef.current) URL.revokeObjectURL(audioUrlRef.current);
      audioUrlRef.current = null;
      setPlayingMessage(null);
      setError(cause instanceof Error ? cause.message : "Falha ao reproduzir a resposta.");
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
            className={activeTab === "devices" ? "tab active" : "tab"}
            onClick={() => setActiveTab("devices")}
          >
            Dispositivos
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
        ) : activeTab === "devices" ? (
          <PairingPanel />
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
                        <>
                          {voiceStatus?.synthesis_configured && (
                            <button
                              type="button"
                              className="message-speak"
                              onClick={() => void speakMessage(message.content, index)}
                              disabled={playingMessage !== null}
                            >
                              {playingMessage === index ? "Reproduzindo…" : "Ouvir"}
                            </button>
                          )}
                          <small className="message-meta">
                            {message.engine ?? "local"} · {message.externalTraffic ? "tráfego externo" : "somente local"}
                            {(message.memoriesUsed ?? 0) > 0 && ` · ${message.memoriesUsed} memórias usadas`}
                            {message.agent && ` · ${message.agent}`}
                            {message.specialist && message.specialist !== "general" && ` · perfil ${message.specialist}`}
                            {(message.toolCalls ?? 0) > 0 && ` · ${message.toolCalls} ferramentas`}
                            {message.plan && message.plan.length > 0 && ` · plano: ${message.plan.join(" → ")}`}
                          </small>
                        </>
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
              <button
                type="button"
                className={recording ? "voice-button recording" : "voice-button"}
                onClick={() => void toggleRecording()}
                disabled={busy || historyLoading || voiceBusy || !voiceStatus?.transcription_configured}
                aria-label={recording ? "Parar gravação" : "Gravar mensagem"}
                title={recording ? "Parar gravação" : "Gravar mensagem"}
              >
                {recording ? "Parar" : "Mic"}
              </button>
              <button type="submit" disabled={busy || historyLoading || voiceBusy || !draft.trim()}>
                {busy || voiceBusy ? "…" : "Enviar"}
              </button>
            </form>
            <footer className="footer-note">
              {recording
                ? "Gravando… toque em Parar para transcrever localmente"
                : voiceBusy
                  ? "Reconhecendo sua fala no mecanismo local…"
                  : voiceStatus?.transcription_configured || voiceStatus?.synthesis_configured
                    ? `Voz local: ${voiceStatus.transcription_configured ? "reconhecimento" : "sem reconhecimento"} · ${voiceStatus.synthesis_configured ? "síntese" : "sem síntese"}`
                    : "Voz local ainda não configurada"}
              {" · "}
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
