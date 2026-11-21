const DATABASE_NAME = "lia-device-credentials";
const DATABASE_VERSION = 1;
const STORE_NAME = "devices";

export interface DeviceCredential {
  deviceId: string;
  signingKey: CryptoKey;
}

interface StoredCredential extends DeviceCredential {}

function validateDeviceId(deviceId: string): void {
  if (!/^[a-f0-9]{32}$/i.test(deviceId)) {
    throw new Error("Identificador de dispositivo inválido.");
  }
}

function openCredentialDatabase(): Promise<IDBDatabase> {
  if (typeof indexedDB === "undefined" || !globalThis.crypto?.subtle) {
    throw new Error("Este navegador não oferece armazenamento seguro de credenciais.");
  }

  return new Promise((resolve, reject) => {
    const request = indexedDB.open(DATABASE_NAME, DATABASE_VERSION);
    request.onupgradeneeded = () => {
      if (!request.result.objectStoreNames.contains(STORE_NAME)) {
        request.result.createObjectStore(STORE_NAME);
      }
    };
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error ?? new Error("Não foi possível abrir o armazenamento local."));
    request.onblocked = () => reject(new Error("O armazenamento local está bloqueado por outra versão da Lia."));
  });
}

/**
 * Derive a non-extractable HMAC key from the one-time pairing secret.
 * The raw pairing code is never persisted or sent with authenticated requests.
 */
export async function deriveDeviceCredential(
  deviceId: string,
  pairingCode: string,
): Promise<DeviceCredential> {
  validateDeviceId(deviceId);
  if (pairingCode.length < 40 || pairingCode.length > 64) {
    throw new Error("Código de pareamento inválido.");
  }
  if (!globalThis.crypto?.subtle) {
    throw new Error("A criptografia do navegador exige um contexto seguro HTTPS.");
  }

  const digest = await crypto.subtle.digest(
    "SHA-256",
    new TextEncoder().encode(pairingCode),
  );
  const signingKey = await crypto.subtle.importKey(
    "raw",
    digest,
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"],
  );
  return { deviceId, signingKey };
}

/** Persist the non-extractable CryptoKey using IndexedDB structured cloning. */
export async function saveDeviceCredential(
  credential: DeviceCredential,
): Promise<void> {
  validateDeviceId(credential.deviceId);
  if (credential.signingKey.extractable) {
    throw new Error("A chave do dispositivo precisa ser não extraível.");
  }

  const database = await openCredentialDatabase();
  try {
    await new Promise<void>((resolve, reject) => {
      const transaction = database.transaction(STORE_NAME, "readwrite");
      transaction.objectStore(STORE_NAME).put(
        { deviceId: credential.deviceId, signingKey: credential.signingKey } satisfies StoredCredential,
        credential.deviceId,
      );
      transaction.oncomplete = () => resolve();
      transaction.onerror = () => reject(transaction.error ?? new Error("Falha ao salvar a chave do dispositivo."));
      transaction.onabort = () => reject(transaction.error ?? new Error("O armazenamento da chave foi cancelado."));
    });
  } finally {
    database.close();
  }
}

/** Derive and persist a device key after the owner approves the pairing request. */
export async function storeApprovedPairing(
  deviceId: string,
  pairingCode: string,
): Promise<void> {
  const credential = await deriveDeviceCredential(deviceId, pairingCode);
  await saveDeviceCredential(credential);
}

/** Load a non-extractable device key; null means this browser has not paired. */
export async function loadDeviceCredential(
  deviceId: string,
): Promise<DeviceCredential | null> {
  validateDeviceId(deviceId);
  const database = await openCredentialDatabase();
  try {
    return await new Promise<DeviceCredential | null>((resolve, reject) => {
      const transaction = database.transaction(STORE_NAME, "readonly");
      const request = transaction.objectStore(STORE_NAME).get(deviceId);
      request.onsuccess = () => {
        const stored = request.result as StoredCredential | undefined;
        resolve(stored ? { deviceId: stored.deviceId, signingKey: stored.signingKey } : null);
      };
      request.onerror = () => reject(request.error ?? new Error("Falha ao ler a chave do dispositivo."));
      transaction.onabort = () => reject(transaction.error ?? new Error("A leitura da chave foi cancelada."));
    });
  } finally {
    database.close();
  }
}

export async function removeDeviceCredential(deviceId: string): Promise<void> {
  validateDeviceId(deviceId);
  const database = await openCredentialDatabase();
  try {
    await new Promise<void>((resolve, reject) => {
      const transaction = database.transaction(STORE_NAME, "readwrite");
      transaction.objectStore(STORE_NAME).delete(deviceId);
      transaction.oncomplete = () => resolve();
      transaction.onerror = () => reject(transaction.error ?? new Error("Falha ao apagar a chave do dispositivo."));
      transaction.onabort = () => reject(transaction.error ?? new Error("A remoção da chave foi cancelada."));
    });
  } finally {
    database.close();
  }
}

/**
 * Create the signed headers required by the paired-device API.
 * pathAndQuery must exactly match the URL path and query sent by fetch().
 */
export async function createDeviceAuthHeaders(
  credential: DeviceCredential,
  method: string,
  pathAndQuery: string,
): Promise<Record<string, string>> {
  validateDeviceId(credential.deviceId);
  if (credential.signingKey.extractable) {
    throw new Error("A chave do dispositivo precisa ser não extraível.");
  }

  const timestamp = String(Math.floor(Date.now() / 1000));
  const nonceBytes = crypto.getRandomValues(new Uint8Array(16));
  const nonce = Array.from(nonceBytes, (value) => value.toString(16).padStart(2, "0")).join("");
  const message = method.toUpperCase() + "\n" + pathAndQuery + "\n" + timestamp + "\n" + nonce;
  const signatureBuffer = await crypto.subtle.sign(
    "HMAC",
    credential.signingKey,
    new TextEncoder().encode(message),
  );
  const signature = Array.from(
    new Uint8Array(signatureBuffer),
    (value) => value.toString(16).padStart(2, "0"),
  ).join("");

  return {
    "X-Lia-Device-ID": credential.deviceId,
    "X-Lia-Timestamp": timestamp,
    "X-Lia-Nonce": nonce,
    "X-Lia-Signature": signature,
  };
}
