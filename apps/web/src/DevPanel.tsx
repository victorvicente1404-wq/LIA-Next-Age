import { useEffect, useState } from "react";

type Workspace = { id: string; name: string };
type FileEntry = {
  name: string;
  path: string;
  kind: "file" | "directory";
  size: number | null;
};
type FilePreview = { path: string; content: string; size: number };

async function readJson<T>(url: string): Promise<T> {
  const response = await fetch(url);
  const data = (await response.json()) as T | { detail?: string };
  if (!response.ok) {
    const detail = (data as { detail?: string }).detail;
    throw new Error(detail ?? "Não foi possível acessar o workspace.");
  }
  return data as T;
}

export default function DevPanel() {
  const [workspaces, setWorkspaces] = useState<Workspace[]>([]);
  const [workspaceId, setWorkspaceId] = useState("");
  const [directory, setDirectory] = useState(".");
  const [entries, setEntries] = useState<FileEntry[]>([]);
  const [preview, setPreview] = useState<FilePreview | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;
    readJson<Workspace[]>("/api/v1/dev/workspaces")
      .then((items) => {
        if (!active) return;
        setWorkspaces(items);
        if (items.length > 0) setWorkspaceId(items[0].id);
        setLoading(false);
      })
      .catch((cause: unknown) => {
        if (!active) return;
        setError(cause instanceof Error ? cause.message : "Falha ao carregar workspaces.");
        setLoading(false);
      });
    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    if (!workspaceId) {
      setEntries([]);
      return;
    }
    let active = true;
    setLoading(true);
    setError("");
    readJson<FileEntry[]>(
      `/api/v1/dev/workspaces/${workspaceId}/files?path=${encodeURIComponent(directory)}`,
    )
      .then((items) => {
        if (active) setEntries(items);
      })
      .catch((cause: unknown) => {
        if (active) setError(cause instanceof Error ? cause.message : "Falha ao listar arquivos.");
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [workspaceId, directory]);

  async function openEntry(entry: FileEntry) {
    setError("");
    if (entry.kind === "directory") {
      setDirectory(entry.path);
      setPreview(null);
      return;
    }
    try {
      const item = await readJson<FilePreview>(
        `/api/v1/dev/workspaces/${workspaceId}/file?path=${encodeURIComponent(entry.path)}`,
      );
      setPreview(item);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Não foi possível abrir o arquivo.");
    }
  }

  function goUp() {
    if (directory === ".") return;
    const parts = directory.split("/");
    parts.pop();
    setDirectory(parts.length ? parts.join("/") : ".");
    setPreview(null);
  }

  return (
    <section className="dev-panel">
      <div className="dev-heading">
        <div>
          <div className="eyebrow">LIA DEV · WORKSPACE EXPLORER</div>
          <h2>Área de desenvolvimento</h2>
          <p>Inspeção de código em pastas que você autorizou explicitamente.</p>
        </div>
        <span className="readonly-label">Somente leitura</span>
      </div>

      {workspaces.length > 0 && (
        <div className="dev-toolbar">
          <label htmlFor="workspace-select">Workspace</label>
          <select
            id="workspace-select"
            value={workspaceId}
            onChange={(event) => {
              setWorkspaceId(event.target.value);
              setDirectory(".");
              setPreview(null);
            }}
          >
            {workspaces.map((workspace) => (
              <option value={workspace.id} key={workspace.id}>{workspace.name}</option>
            ))}
          </select>
        </div>
      )}

      {loading && <p className="dev-message">Carregando workspace…</p>}
      {error && <p className="dev-error" role="alert">{error}</p>}

      {!loading && workspaces.length === 0 && !error && (
        <div className="empty-workspaces">
          <strong>Nenhuma pasta autorizada ainda.</strong>
          <p>Configure LIA_DEV_WORKSPACES no ambiente do núcleo Python para liberar uma pasta específica.</p>
          <code>LIA_DEV_WORKSPACES=/caminho/do/projeto</code>
        </div>
      )}

      {workspaceId && (
        <div className="dev-browser">
          <div className="file-list">
            <div className="file-list-header">
              <span>{directory}</span>
              <button type="button" onClick={goUp} disabled={directory === "."}>Subir</button>
            </div>
            {entries.map((entry) => (
              <button
                type="button"
                className={`file-entry ${preview?.path === entry.path ? "selected" : ""}`}
                key={entry.path}
                onClick={() => void openEntry(entry)}
              >
                <span className="file-kind">{entry.kind === "directory" ? "▸" : "·"}</span>
                <span>{entry.name}</span>
                {entry.kind === "file" && <small>{entry.size ?? 0} B</small>}
              </button>
            ))}
            {!loading && entries.length === 0 && <p className="dev-message">Pasta vazia.</p>}
          </div>

          <div className="file-preview">
            {preview ? (
              <>
                <div className="file-preview-header">{preview.path}</div>
                <pre>{preview.content}</pre>
              </>
            ) : (
              <div className="preview-placeholder">
                Selecione um arquivo para visualizar o conteúdo.
              </div>
            )}
          </div>
        </div>
      )}

      <p className="dev-footnote">
        A Lia Dev ainda não altera arquivos nem executa comandos. Isso só será habilitado com diff,
        sandbox e aprovação explícita.
      </p>
    </section>
  );
}
