import { useEffect, useState } from "react";

type Workspace = { id: string; name: string };
type FileEntry = {
  name: string;
  path: string;
  kind: "file" | "directory";
  size: number | null;
};
type FilePreview = { path: string; content: string; size: number };
type PatchProposal = {
  proposal_id: string;
  path: string;
  diff: string;
  status: string;
};
type AppliedPatch = {
  operation_id: string;
  workspace_id?: string;
  path: string;
  status: string;
};

async function requestJson<T>(
  url: string,
  init?: RequestInit,
): Promise<T> {
  const response = await fetch(url, init);
  if (response.status === 204) return undefined as T;
  const data = (await response.json()) as T | { detail?: string };
  if (!response.ok) {
    const detail = (data as { detail?: string }).detail;
    throw new Error(detail ?? "Não foi possível concluir a operação.");
  }
  return data as T;
}

export default function DevPanel() {
  const [workspaces, setWorkspaces] = useState<Workspace[]>([]);
  const [workspaceId, setWorkspaceId] = useState("");
  const [directory, setDirectory] = useState(".");
  const [entries, setEntries] = useState<FileEntry[]>([]);
  const [preview, setPreview] = useState<FilePreview | null>(null);
  const [editContent, setEditContent] = useState("");
  const [proposal, setProposal] = useState<PatchProposal | null>(null);
  const [applied, setApplied] = useState<AppliedPatch | null>(null);
  const [rollbacks, setRollbacks] = useState<AppliedPatch[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;
    requestJson<Workspace[]>("/api/v1/dev/workspaces")
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
      setRollbacks([]);
      return;
    }
    let active = true;
    requestJson<AppliedPatch[]>(
      `/api/v1/dev/rollbacks?workspace_id=${encodeURIComponent(workspaceId)}`,
    )
      .then((items) => {
        if (active) setRollbacks(items);
      })
      .catch((cause: unknown) => {
        if (active) setError(cause instanceof Error ? cause.message : "Falha ao carregar rollbacks.");
      });
    return () => {
      active = false;
    };
  }, [workspaceId]);

  useEffect(() => {
    if (!workspaceId) {
      setEntries([]);
      return;
    }
    let active = true;
    setLoading(true);
    setError("");
    requestJson<FileEntry[]>(
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
      setProposal(null);
      setApplied(null);
      return;
    }
    try {
      const item = await requestJson<FilePreview>(
        `/api/v1/dev/workspaces/${workspaceId}/file?path=${encodeURIComponent(entry.path)}`,
      );
      setPreview(item);
      setEditContent(item.content);
      setProposal(null);
      setApplied(null);
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
    setProposal(null);
    setApplied(null);
  }

  async function preparePatch() {
    if (!preview || saving) return;
    setSaving(true);
    setError("");
    try {
      const result = await requestJson<PatchProposal>(
        `/api/v1/dev/workspaces/${workspaceId}/patches`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ path: preview.path, content: editContent }),
        },
      );
      setProposal(result);
      setApplied(null);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Não foi possível preparar o diff.");
    } finally {
      setSaving(false);
    }
  }

  async function cancelProposal() {
    if (!proposal) return;
    try {
      await requestJson<void>(
        `/api/v1/dev/patches/${proposal.proposal_id}`,
        { method: "DELETE" },
      );
    } catch {
      // The proposal may already have expired; clearing the local review remains safe.
    }
    setProposal(null);
  }

  async function approvePatch() {
    if (!proposal || saving) return;
    setSaving(true);
    setError("");
    try {
      const result = await requestJson<AppliedPatch>(
        `/api/v1/dev/patches/${proposal.proposal_id}/apply`,
        { method: "POST" },
      );
      setApplied(result);
      setRollbacks((current) => [
        { ...result, workspace_id: workspaceId },
        ...current.filter((item) => item.operation_id !== result.operation_id),
      ]);
      setProposal(null);
      if (preview) {
        const updated = await requestJson<FilePreview>(
          `/api/v1/dev/workspaces/${workspaceId}/file?path=${encodeURIComponent(preview.path)}`,
        );
        setPreview(updated);
        setEditContent(updated.content);
      }
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Não foi possível aplicar a alteração.");
    } finally {
      setSaving(false);
    }
  }

  async function rollbackPatch(operationId: string) {
    if (saving) return;
    setSaving(true);
    setError("");
    try {
      await requestJson(
        `/api/v1/dev/patches/${operationId}/rollback`,
        { method: "POST" },
      );
      setRollbacks((current) => current.filter((item) => item.operation_id !== operationId));
      setApplied((current) => current?.operation_id === operationId ? null : current);
      if (preview) {
        const restored = await requestJson<FilePreview>(
          `/api/v1/dev/workspaces/${workspaceId}/file?path=${encodeURIComponent(preview.path)}`,
        );
        setPreview(restored);
        setEditContent(restored.content);
      }
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Não foi possível desfazer a alteração.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <section className="dev-panel">
      <div className="dev-heading">
        <div>
          <div className="eyebrow">LIA DEV · WORKSPACE EXPLORER</div>
          <h2>Área de desenvolvimento</h2>
          <p>Inspecione arquivos e prepare alterações com diff antes de qualquer gravação.</p>
        </div>
        <span className="readonly-label">Aprovação obrigatória</span>
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
              setProposal(null);
              setApplied(null);
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
                <textarea
                  className="dev-editor"
                  aria-label="Conteúdo proposto para o arquivo"
                  value={editContent}
                  onChange={(event) => {
                    setEditContent(event.target.value);
                    setProposal(null);
                    setApplied(null);
                  }}
                  spellCheck={false}
                  disabled={saving || Boolean(proposal)}
                />
                {!proposal && !applied && (
                  <div className="patch-actions">
                    <span>Editar aqui não grava o arquivo.</span>
                    <button
                      type="button"
                      onClick={() => void preparePatch()}
                      disabled={saving || editContent === preview.content}
                    >
                      {saving ? "Preparando…" : "Preparar diff"}
                    </button>
                  </div>
                )}
                {proposal && (
                  <div className="patch-review">
                    <div className="patch-review-heading">
                      <strong>Revisão da alteração</strong>
                      <span>O arquivo ainda não foi modificado.</span>
                    </div>
                    <pre className="diff-preview">{proposal.diff || "Nenhuma diferença encontrada."}</pre>
                    <div className="patch-actions">
                      <button
                        type="button"
                        className="secondary-action"
                        onClick={() => void cancelProposal()}
                        disabled={saving}
                      >
                        Cancelar
                      </button>
                      <button type="button" onClick={() => void approvePatch()} disabled={saving}>
                        {saving ? "Aplicando…" : "Aprovar e aplicar"}
                      </button>
                    </div>
                  </div>
                )}
                {applied && (
                  <div className="patch-applied">
                    <span>Alteração aplicada em {applied.path}.</span>
                    <span>O backup foi registrado para rollback.</span>
                  </div>
                )}
              </>
            ) : (
              <div className="preview-placeholder">
                Selecione um arquivo para visualizar e, se desejar, preparar uma alteração.
              </div>
            )}
          </div>
        </div>
      )}


      {rollbacks.length > 0 && (
        <div className="rollback-list">
          <div className="rollback-list-heading">
            <strong>Alterações aplicadas com rollback disponível</strong>
            <span>{rollbacks.length}</span>
          </div>
          {rollbacks.map((item) => (
            <div className="rollback-item" key={item.operation_id}>
              <code>{item.path}</code>
              <button
                type="button"
                onClick={() => void rollbackPatch(item.operation_id)}
                disabled={saving}
              >
                {saving ? "Aguarde…" : "Desfazer"}
              </button>
            </div>
          ))}
        </div>
      )}

      <p className="dev-footnote">
        A proposta mostra o diff e não altera nada. A gravação exige um segundo clique explícito;
        mudanças concorrentes bloqueiam a aplicação. Cada aplicação cria backup para rollback.
        Por enquanto, só arquivos existentes de texto UTF-8 até 256 KiB podem ser alterados.
      </p>
    </section>
  );
}
