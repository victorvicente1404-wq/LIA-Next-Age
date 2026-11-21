import { FormEvent, useEffect, useState } from "react";

type MemoryKind = "fact" | "preference" | "knowledge" | "note";
type MemoryItem = {
  id: number;
  kind: MemoryKind;
  key: string | null;
  content: string;
  created_at: string;
};

const kindLabels: Record<MemoryKind, string> = {
  fact: "Fato",
  preference: "Preferência",
  knowledge: "Conhecimento",
  note: "Nota",
};

export default function MemoryPanel() {
  const [items, setItems] = useState<MemoryItem[]>([]);
  const [kind, setKind] = useState<MemoryKind>("fact");
  const [key, setKey] = useState("");
  const [content, setContent] = useState("");
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  async function loadMemories(search = query) {
    setLoading(true);
    setError("");
    try {
      const response = await fetch(`/api/v1/memories?q=${encodeURIComponent(search)}&limit=100`);
      const data = (await response.json()) as MemoryItem[] | { detail?: string };
      if (!response.ok) throw new Error((data as { detail?: string }).detail ?? "Falha ao carregar memória.");
      setItems(data as MemoryItem[]);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Falha ao carregar memória.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void loadMemories("");
  }, []);

  async function saveMemory(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!content.trim() || saving) return;
    setSaving(true);
    setError("");
    try {
      const response = await fetch("/api/v1/memories", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          kind,
          key: key.trim() || null,
          content: content.trim(),
        }),
      });
      const data = (await response.json()) as MemoryItem | { detail?: string };
      if (!response.ok) throw new Error((data as { detail?: string }).detail ?? "Não foi possível salvar.");
      setContent("");
      setKey("");
      setQuery("");
      await loadMemories("");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Falha ao salvar memória.");
    } finally {
      setSaving(false);
    }
  }

  async function deleteMemory(id: number) {
    if (!window.confirm("Apagar esta memória permanentemente?")) return;
    try {
      const response = await fetch(`/api/v1/memories/${id}`, { method: "DELETE" });
      if (!response.ok) throw new Error("Não foi possível apagar a memória.");
      setItems((current) => current.filter((item) => item.id !== id));
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Falha ao apagar memória.");
    }
  }

  return (
    <section className="memory-panel">
      <div className="dev-heading">
        <div>
          <div className="eyebrow">MEMÓRIA PERSISTENTE · LOCAL</div>
          <h2>O que a Lia deve lembrar?</h2>
          <p>Você escolhe o que entra na memória. Nada desta tela é salvo automaticamente.</p>
        </div>
        <span className="readonly-label">Sob seu controle</span>
      </div>

      <form className="memory-form" onSubmit={saveMemory}>
        <div className="memory-form-row">
          <label>
            Tipo
            <select value={kind} onChange={(event) => setKind(event.target.value as MemoryKind)}>
              <option value="fact">Fato</option>
              <option value="preference">Preferência</option>
              <option value="knowledge">Conhecimento</option>
              <option value="note">Nota</option>
            </select>
          </label>
          <label>
            Identificador (opcional)
            <input value={key} onChange={(event) => setKey(event.target.value)} placeholder="Ex.: idioma_resposta" maxLength={200} />
          </label>
        </div>
        <label>
          Conteúdo
          <textarea
            value={content}
            onChange={(event) => setContent(event.target.value)}
            placeholder="Escreva algo que você quer que a Lia guarde…"
            rows={3}
            maxLength={10000}
            required
          />
        </label>
        <div className="memory-form-actions">
          <span>Armazenado no SQLite do seu dispositivo.</span>
          <button type="submit" disabled={saving || !content.trim()}>
            {saving ? "Salvando…" : "Salvar memória"}
          </button>
        </div>
      </form>

      <div className="memory-list-heading">
        <h3>Memórias salvas <span>{items.length}</span></h3>
        <form
          className="memory-search"
          onSubmit={(event) => {
            event.preventDefault();
            void loadMemories(query);
          }}
        >
          <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Pesquisar…" />
          <button type="submit">Buscar</button>
        </form>
      </div>

      {error && <p className="dev-error" role="alert">{error}</p>}
      {loading ? (
        <p className="dev-message">Carregando memórias…</p>
      ) : items.length === 0 ? (
        <div className="empty-workspaces">
          <strong>Nenhuma memória encontrada.</strong>
          <p>Adicione uma lembrança acima. Você poderá apagá-la quando quiser.</p>
        </div>
      ) : (
        <div className="memory-list">
          {items.map((item) => (
            <article className="memory-item" key={item.id}>
              <div className="memory-item-top">
                <span className={`memory-kind kind-${item.kind}`}>{kindLabels[item.kind]}</span>
                {item.key && <code>{item.key}</code>}
                <button type="button" onClick={() => void deleteMemory(item.id)} aria-label="Apagar memória">Apagar</button>
              </div>
              <p>{item.content}</p>
              <small>{new Date(item.created_at).toLocaleString()}</small>
            </article>
          ))}
        </div>
      )}
    </section>
  );
}
