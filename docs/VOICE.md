# Voz local da Lia

A camada de voz é opcional e independente do modelo de conversação. Ela não usa a API de fala do navegador nem provedores hospedados.

## Componentes

- **Reconhecimento:** servidor local `whisper.cpp`, endpoint HTTP `/inference`.
- **Síntese:** executável local Piper e um modelo de voz Piper (`.onnx`).
- **Interface:** grava áudio com `MediaRecorder`, envia para o núcleo e coloca a transcrição no fluxo normal de chat. Respostas podem ser reproduzidas sob demanda.

O núcleo só aceita o endpoint STT em HTTP loopback (`localhost`, `127.0.0.1` ou `::1`). Não configure URL pública: o áudio do usuário não deve sair da máquina.

## Configuração

No arquivo de ambiente do serviço, configure os componentes que estiverem instalados:

```dotenv
LIA_VOICE_STT_URL=http://127.0.0.1:8178/inference
LIA_VOICE_TIMEOUT=90
LIA_VOICE_MAX_AUDIO_BYTES=20971520
LIA_PIPER_BIN=/caminho/para/piper
LIA_PIPER_MODEL=/caminho/para/voz/pt_BR-voice-medium.onnx
```

Inicie o servidor `whisper.cpp` localmente na porta configurada e o Piper com o executável e modelo de voz compatíveis com o sistema operacional. Os binários e modelos não são baixados automaticamente pelo núcleo. Isso evita downloads silenciosos, alterações no ambiente e dependências de fornecedores externos.

O Piper é chamado com argumentos fixos, sem shell, e a saída WAV é temporária. O texto enviado à síntese tem limite de 4.000 caracteres. O áudio de entrada tem limite configurável (20 MiB por padrão).

## API

- `GET /api/v1/voice/status`: informa quais motores estão configurados.
- `POST /api/v1/voice/transcriptions`: recebe o áudio bruto no corpo HTTP; o `Content-Type` deve ser um formato de áudio aceito.
- `POST /api/v1/voice/speech`: recebe `{"text":"..." }` e retorna `audio/wav`.

O status indica configuração, não garante que o processo externo esteja ativo. Se o servidor local não responder, a transcrição retorna erro sem fallback remoto.

## Segurança e limitações atuais

- Não há gravação contínua nem microfone sempre ligado.
- O usuário inicia e encerra cada gravação manualmente.
- O navegador precisa oferecer `MediaRecorder` e permissão de microfone; normalmente isso exige HTTPS ou contexto local seguro.
- O núcleo e o painel Lia Dev continuam vinculados ao loopback por padrão. Existe agora uma API opt-in de pareamento com HTTPS, aprovação local, tokens limitados, assinatura anti-replay e revogação. Ela ainda não tem interface no frontend nem cliente Android; não exponha o serviço até integrar e validar esses clientes. Consulte [DEVICE_PAIRING.md](DEVICE_PAIRING.md).
- O primeiro corte não instala modelos, não baixa vozes e não altera o sistema operacional.
- A compatibilidade e o desempenho em Android ainda precisam de validação em um runtime local Android. A camada atual é um adaptador de núcleo, não uma promessa de execução no celular sem configuração.

## Próximas melhorias

- Interface de pareamento no frontend e cliente Android com armazenamento seguro do token e assinatura de requisições.
- Seleção e gerenciamento de vozes instaladas.
- Detecção de silêncio/VAD e conversação por turnos sem gravação manual.
- Testes de latência, consumo de RAM e qualidade em dispositivos Android.
