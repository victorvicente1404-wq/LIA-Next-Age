import { FormEvent, useState } from "react";
import { setActiveDeviceId, storeApprovedPairing } from "./pairing";

type PairingClientProps = {
  onPaired: (deviceId: string) => void;
};

type PairingRequestResponse = {
  request_id: string;
  pairing_code: string;
  expires_in_seconds: number;
};

export default function PairingClient({ onPaired }: PairingClientProps) {
  const [deviceName, setDeviceName] = useState("Meu celular");
  const [request, setRequest] = useState<PairingRequestResponse | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  async function createRequest(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const response = await fetch("/api/v1/pairing/requests", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ device_name: deviceName.trim(), scopes: ["chat", "voice"] }),
        cache: "no-store",
      });
      const data = await response.json() as PairingRequestResponse & { detail?: string };
      if (!response.ok) throw new Error(data.detail ?? "Não foi possível solicitar o pareamento.");
      setRequest(data);
      setNotice("Solicitação criada. Agora aprove este dispositivo no painel local da Lia.");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Falha ao criar solicitação.");
    } finally {
      setBusy(false);
    }
  }

  async function verifyApproval() {
    if (!request) return;
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const response = await fetch(
        "/api/v1/pairing/requests/" + request.request_id + "/status",
        { cache: "no-store" },
      );
      const data = await response.json() as { status?: string; detail?: string };
      if (!response.ok) throw new Error(data.detail ?? "Não foi possível verificar a aprovação.");
      if (data.status === "pending") {
        setNotice("Ainda aguardando aprovação no dispositivo principal.");
      } else if (data.status === "approved") {
        await storeApprovedPairing(request.request_id, request.pairing_code);
        setActiveDeviceId(request.request_id);
        setNotice("Dispositivo pareado. Abrindo o chat seguro da Lia…");
        onPaired(request.request_id);
      } else {
        setError("Esta solicitação expirou ou foi bloqueada. Crie uma nova solicitação.");
        setRequest(null);
      }
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Falha ao verificar o pareamento.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="pairing-panel" aria-labelledby="pairing-client-title">
      <div className="pairing-heading">
        <div>
          <h2 id="pairing-client-title">Conectar este dispositivo à Lia</h2>
          <p>O pareamento é aprovado no dispositivo principal. Nenhum serviço de IA na nuvem é necessário.</p>
        </div>
      </div>
      <div className="pairing-safety-note">
        A conexão exige HTTPS, aprovação manual e uma chave local não extraível. Este dispositivo receberá apenas acesso ao chat e à voz.
      </div>
      {!request ? (
        <form className="pairing-approve-form" onSubmit={(event) => void createRequest(event)}>
          <label htmlFor="pairing-device-name">Nome deste dispositivo</label>
          <input
            id="pairing-device-name"
            value={deviceName}
            maxLength={64}
            onChange={(event) => setDeviceName(event.target.value)}
            required
          />
          <button type="submit" disabled={busy || !deviceName.trim()}>
            {busy ? "Conectando…" : "Solicitar pareamento"}
          </button>
        </form>
      ) : (
        <div className="pairing-card">
          <div className="pairing-card-heading">
            <strong>{deviceName}</strong>
            <small>Expira em {Math.floor(request.expires_in_seconds / 60)} minutos</small>
          </div>
          <p className="pairing-request-meta">No dispositivo principal, abra a aba Dispositivos e confirme que este nome corresponde ao aparelho que está tentando conectar.</p>
          <p className="pairing-request-meta">Digite o código abaixo no painel local para aprovar:</p>
          <p className="pairing-request-meta"><code>{request.pairing_code}</code></p>
          <button type="button" onClick={() => void verifyApproval()} disabled={busy}>
            {busy ? "Verificando…" : "Já aprovei — verificar"}
          </button>
          <button type="button" className="pairing-cancel" onClick={() => setRequest(null)} disabled={busy}>
            Cancelar e gerar outro código
          </button>
        </div>
      )}
      {error && <div className="pairing-error" role="alert">{error}</div>}
      {notice && <div className="pairing-notice" role="status">{notice}</div>}
    </section>
  );
}
