# Pareamento seguro entre dispositivos

## Estado

O núcleo contém a primeira implementação da API de pareamento e da autorização remota. **O pareamento vem desativado por padrão** e não há ainda uma tela de configuração no frontend nem armazenamento seguro do token no aplicativo Android. Portanto, não exponha o serviço até concluir a integração do cliente e validar TLS no ambiente real.

O modo local continua funcionando sem pareamento, sem conta hospedada e sem serviço externo.

## Regras de segurança

- Acesso remoto à API exige HTTPS real; requisições remotas em HTTP são recusadas.
- O servidor só aceita origens de navegador listadas exatamente em `LIA_ALLOWED_ORIGINS`. Não use curingas.
- Os controles de aprovação, listagem e revogação só aceitam loopback. Requisições de navegador ao loopback também precisam vir de uma origem permitida.
- Uma solicitação de pareamento expira em 5 minutos. O código é aleatório, de uso único e bloqueado após 5 tentativas incorretas.
- Há limite de 5 solicitações por minuto e por endereço de origem, além de no máximo 10 solicitações pendentes.
- A aprovação acontece no dispositivo principal. O código aleatório de 256 bits, já conhecido pelo dispositivo solicitante, passa a ser seu token Bearer após a aprovação; o endpoint local nunca devolve um segredo.
- Apenas hashes SHA-256 dos tokens são persistidos. Tokens têm validade configurável (30 dias por padrão) e podem ser revogados individualmente.
- Escopos disponíveis são `chat`, `voice` e `memory:read`. O padrão é somente `chat` e `voice`; memória exige solicitação e aprovação explícitas. Sem `memory:read`, o chat remoto não injeta memórias nem habilita ferramentas que consultam a memória. Escrita de memória e Lia Dev não são concedidas; Lia Dev permanece exclusivamente local.
- Cada requisição autenticada exige timestamp com tolerância de 60 segundos, nonce aleatório de uso único e assinatura HMAC-SHA256. Repetir a mesma requisição assinada é recusado.
- Tokens nunca devem ser enviados em URLs, query strings ou logs.

## Configuração

No ambiente do serviço:

```dotenv
LIA_PAIRING_ENABLED=true
LIA_PAIRING_TOKEN_TTL=2592000
LIA_ALLOWED_ORIGINS=https://lia.example
```

Use a origem exata da interface web. Se a interface também for servida localmente em outra origem, inclua-a explicitamente, separada por vírgula. Origens são comparadas literalmente após remover a barra final.

Configure um certificado TLS válido cujo SAN corresponda ao hostname/IP usado pelo celular. O certificado precisa ser confiável pelo sistema do celular. Um certificado autoassinado não confiável não atende ao requisito. A terminação TLS deve ocorrer no próprio servidor ASGI nesta primeira versão; não confie em `X-Forwarded-Proto` enviado por proxies desconhecidos.

Só depois de instalar e validar o certificado, inicie o serviço escutando na interface LAN, por exemplo:

```bash
uvicorn lia_core.main:app --host 0.0.0.0 --port 8443 \
  --ssl-certfile /caminho/cert.pem \
  --ssl-keyfile /caminho/key.pem
```

Restrinja a porta no firewall à rede/dispositivos necessários. Não use este comando sem TLS funcional. Com `LIA_PAIRING_ENABLED=false`, o fluxo de pareamento permanece desativado.

## Fluxo de pareamento

1. O dispositivo remoto, usando HTTPS, envia `POST /api/v1/pairing/requests` com JSON `{"device_name":"Meu celular","scopes":["chat","voice"]}`.
2. A resposta contém `request_id`, um `pairing_code` temporário e os escopos pedidos.
3. No dispositivo principal, consulte `GET /api/v1/pairing/requests` por loopback. Confirme que o nome do dispositivo e o pedido são esperados.
4. Aprove localmente com `POST /api/v1/pairing/requests/{request_id}/approve` e JSON `{"pairing_code":"CODIGO_MOSTRADO_NO_CELULAR"}`.
5. O `request_id` passa a ser o `device_id`. O dispositivo remoto deriva uma chave HMAC de `SHA-256(pairing_code)` e guarda essa chave como não extraível no armazenamento seguro do cliente. A resposta de aprovação contém apenas metadados e nunca retorna o segredo. O código bruto não é enviado novamente depois do pareamento.
6. Liste dispositivos com `GET /api/v1/pairing/devices` e revogue com `DELETE /api/v1/pairing/devices/{device_id}` a partir do dispositivo principal.

A aprovação é uma ação explícita. Criar uma solicitação remota não concede acesso. O segredo de pareamento tem 256 bits de entropia, expira em cinco minutos se não for aprovado e, após aprovação, assume a validade configurada do token.

## Assinatura das requisições

Além de `Authorization: Bearer <token>`, cada chamada remota autenticada deve enviar:

- `X-Lia-Timestamp`: Unix time em segundos.
- `X-Lia-Nonce`: valor aleatório novo, com 16 a 128 caracteres.
- `X-Lia-Signature`: HMAC-SHA256 hexadecimal.

A mensagem assinada é a concatenação UTF-8 dos quatro campos abaixo, separados por uma quebra de linha:

```text
METHOD
/path?query
TIMESTAMP
NONCE
```

A chave HMAC são os bytes do digest SHA-256 do `pairing_code` (não o texto hexadecimal). O cliente deve importar esse digest como uma chave HMAC não extraível e persistir a `CryptoKey` no IndexedDB, ou usar o armazenamento seguro equivalente do sistema operacional. O servidor armazena somente o digest hexadecimal e o usa como chave de verificação. O path inclui a query string, quando houver. Gere um nonce novo para toda requisição e sincronize o relógio do dispositivo. A assinatura não substitui TLS. Não envie o código bruto nem em `Authorization` nem em outro header depois da aprovação.

## Limitações desta etapa

- O frontend ainda não oferece tela de pareamento, armazenamento protegido do token nem assinatura HMAC.
- O aplicativo Android ainda não implementa o cliente de pareamento.
- A leitura remota de memória só existe com o escopo opcional `memory:read`. Escrita de memória, arquivos, Git, terminal e Lia Dev não são acessíveis remotamente.
- Não há suporte a proxy reverso ou CORS cross-origin nesta etapa. `LIA_ALLOWED_ORIGINS` é uma proteção de origem/CSRF, não uma configuração CORS. O cliente web remoto ainda não está pronto; não habilite encaminhamento de headers de proxy sem configurar uma lista de proxies confiáveis e revisar o esquema HTTPS efetivo.
- A validação automatizada cobre aprovação, expiração/uso único, escopos, origem, HTTPS, assinatura, replay, revogação e bloqueio de Lia Dev. Certificados, firewall e comportamento real em Android ainda exigem teste no ambiente de destino.
