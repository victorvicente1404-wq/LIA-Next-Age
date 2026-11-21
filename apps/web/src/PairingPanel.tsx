import { FormEvent, useEffect, useState } from "react";

type PairingRequest = {
  request_id: string;
  device_name: string;
  requested_scopes: string[];
  created_at: number;
  expires_at: number;
  attempts: number;
};

type PairedDevice = {
  device_id: string;
  device_name: string;
  scopes: string[];
  created_at: number;
  expires_at: number;
  revoked: boolean;
};

function formatTime(timestamp: number): string {
  return new Date(timestamp * 1000).toLocaleString();
}

function scopeLabel(scope: string): string {
  const labels: Record<string, string> = {
    chat: "Conversa",
    voice: "Voz",
    "memory:read": "Leitura de memória",
  };
  return labels[scope] ?? scope;
}

async function readError(response: Response): Promise<string> {
  try {
    const data = (await response.json()) as { detail?: string };
    return data.detail ?? "A operação não foi concluída.";
  } catch {
    return "A operação não foi concluída.";
  }
}

export default function PairingPanel() {
  const [requests, setRequests] = useState<PairingRequest[]>([]);
  const [devices, setDevices] = useState<PairedDevice[]>([]);
  const [codes, setCodes] = useState<Record<string, string>>({});
  const [confirmRevoke, setConfirmRevoke] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  async function refresh() {
    setLoading(true);
    setError("");
    try {
      const [requestResponse, deviceResponse] = await Promise.all([
        fetch("/api/v1/pairing/requests", { cache: "no-store" }),
        fetch("/api/v1/pairing/devices", { cache: "no-store" }),
      ]);
      if (!requestResponse.ok) throw new Error(await readError(requestResponse));
      if (!deviceResponse.ok) throw new Error(await readError(deviceResponse));
      setRequests((await requestResponse.json()) as PairingRequest[]);
      setDevices((await deviceResponse.json()) as PairedDevice[]);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Não foi possível consultar os dispositivos.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void refresh();
  }, []);

  async function approve(event: FormEvent<HTMLFormElement>, request: PairingRequest) {
    event.preventDefault();
    const pairingCode = (codes[request.request_id] ?? "").trim();
    if (!pairingCode) {
      setError("Digite o código exibido no dispositivo que está solicitando o pareamento.");
      return;
    }
    setLoading(true);
    setError("");
    setNotice("");
    try {
      const response = await fetch(
        "/api/v1/pairing/requests/" + request.request_id + "/approve",
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ pairing_code: pairingCode }),
          cache: "no-store",
        },
      );
      if (!response.ok) throw new Error(await readError(response));
      const result = (await response.json()) as { device_name: string; scopes: string[] };
      setCodes((current) => {
        const next = { ...current };
        delete next[request.request_id];
        return next;
      });
      setNotice(
        result.device_name + " foi aprovado com: " + result.scopes.map(scopeLabel).join(", ") +
        ". Nenhum segredo foi devolvido pelo servidor.",
      );
      await refresh();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Não foi possível aprovar o dispositivo.");
      setLoading(false);
    }
  }

  async function revoke(device: PairedDevice) {
    if (confirmRevoke !== device.device_id) {
      setConfirmRevoke(device.device_id);
      return;
    }
    setLoading(true);
    setError("");
    setNotice("");
    try {
      const response = await fetch("/api/v1/pairing/devices/" + device.device_id, {
        method: "DELETE",
      });
      if (!response.ok) throw new Error(await readError(response));
      setConfirmRevoke(null);
      setNotice("Acesso de " + device.device_name + " revogado.");
      await refresh();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Não foi possível revogar o dispositivo.");
      setLoading(false);
    }
  }

  return (
    <section className="pairing-panel" aria-labelledby="pairing-title">
      <div className="pairing-heading">
        <div>
          <h2 id="pairing-title">Dispositivos pareados</h2>
          <p>
            Aprove solicitações somente quando reconhecer o dispositivo e conferir o código
            exibido nele. A aprovação não revela nem transfere a chave secreta.
          </p>
        </div>
        <button type="button" onClick={() => void refresh()} disabled={loading}>
          {loading ? "Atualizando…" : "Atualizar"}
        </button>
      </div>

      <div className="pairing-safety-note">
        Acesso remoto fica bloqueado por padrão. Para aceitar solicitações pela rede,
        configure HTTPS e habilite o pareamento explicitamente no núcleo.
      </div>

      {error && <div className="pairing-error" role="alert">{error}</div>}
      {notice && <div className="pairing-notice" role="status">{notice}</div>}

      <section className="pairing-section" aria-labelledby="pairing-pending-title">
        <div className="pairing-section-heading">
          <h3 id="pairing-pending-title">Aguardando aprovação</h3>
          <span>{requests.length} solicitação(ões)</span>
        </div>
        {requests.length === 0 ? (
          <p className="pairing-empty">Nenhuma solicitação pendente.</p>
        ) : (
          <div className="pairing-list">
            {requests.map((request) => (
              <article className="pairing-card" key={request.request_id}>
                <div className="pairing-card-heading">
                  <strong>{request.device_name}</strong>
                  <small>Expira: {formatTime(request.expires_at)}</small>
                </div>
                <div className="pairing-scopes">
                  {request.requested_scopes.map((scope) => (
                    <span className="pairing-scope" key={scope}>{scopeLabel(scope)}</span>
                  ))}
                </div>
                <p className="pairing-request-meta">
                  ID <code>{request.request_id}</code> · {request.attempts}/5 tentativas de código
                </p>
                <form className="pairing-approve-form" onSubmit={(event) => void approve(event, request)}>
                  <label htmlFor={"pairing-code-" + request.request_id}>Código exibido no dispositivo</label>
                  <input
                    id={"pairing-code-" + request.request_id}
                    type="password"
                    autoComplete="off"
                    spellCheck={false}
                    maxLength={64}
                    value={codes[request.request_id] ?? ""}
                    onChange={(event) => setCodes((current) => ({
                      ...current,
                      [request.request_id]: event.target.value,
                    }))}
                    placeholder="Cole ou digite o código de pareamento"
                    disabled={loading}
                  />
                  <button type="submit" disabled={loading || !(codes[request.request_id] ?? "").trim()}>
                    Aprovar dispositivo
                  </button>
                </form>
              </article>
            ))}
          </div>
        )}
      </section>

      <section className="pairing-section" aria-labelledby="pairing-devices-title">
        <div className="pairing-section-heading">
          <h3 id="pairing-devices-title">Dispositivos conhecidos</h3>
          <span>{devices.filter((device) => !device.revoked).length} ativos</span>
        </div>
        {devices.length === 0 ? (
          <p className="pairing-empty">Ainda não há dispositivos pareados.</p>
        ) : (
          <div className="pairing-list">
            {devices.map((device) => (
              <article className={device.revoked ? "pairing-card revoked" : "pairing-card"} key={device.device_id}>
                <div className="pairing-card-heading">
                  <strong>{device.device_name}</strong>
                  <span className={device.revoked ? "pairing-state revoked" : "pairing-state"}>
                    {device.revoked ? "Revogado/expirado" : "Ativo"}
                  </span>
                </div>
                <div className="pairing-scopes">
                  {device.scopes.map((scope) => (
                    <span className="pairing-scope" key={scope}>{scopeLabel(scope)}</span>
                  ))}
                </div>
                <p className="pairing-request-meta">
                  Pareado: {formatTime(device.created_at)} · Expira: {formatTime(device.expires_at)}
                </p>
                {!device.revoked && (
                  <div className="pairing-device-actions">
                    {confirmRevoke === device.device_id && (
                      <span>Confirme para cortar o acesso deste dispositivo.</span>
                    )}
                    <button
                      type="button"
                      onClick={() => void revoke(device)}
                      disabled={loading}
                      className={confirmRevoke === device.device_id ? "danger-confirm" : ""}
                    >
                      {confirmRevoke === device.device_id ? "Confirmar revogação" : "Revogar acesso"}
                    </button>
                    {confirmRevoke === device.device_id && (
                      <button type="button" className="pairing-cancel" onClick={() => setConfirmRevoke(null)}>
                        Cancelar
                      </button>
                    )}
                  </div>
                )}
              </article>
            ))}
          </div>
        )}
      </section>
    </section>
  );
}
