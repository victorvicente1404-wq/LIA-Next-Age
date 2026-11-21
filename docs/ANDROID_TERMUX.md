# Protótipo atual da Lia no Android com Termux (opcional)

**Este não é ainda o aplicativo Android final.** O repositório atualmente contém um núcleo Python e uma interface web responsiva; o módulo Android nativo ainda será construído. O Termux pode ser usado como ponte de desenvolvimento/runtime sem instalar Ubuntu, Debian, proot ou outra distribuição Linux. O objetivo final é que você instale e abra a Lia como um aplicativo Android, sem precisar administrar sessões de terminal.

Este guia documenta apenas como testar a fundação existente. A inferência é local: o serviço Python encaminha a conversa somente para o servidor llama.cpp configurado. Consulte [a arquitetura Android-first](ANDROID_FIRST.md) para o plano oficial.

## 1. Conferir os requisitos

Abra o Termux e confira:

```bash
node --version
npm --version
python --version
llama-server --version
```

- Node.js 20.19+ (Node 22 é uma boa escolha).
- Python >=3.10 e <3.14 para o serviço atual.
- `llama-server` instalado.
- Um modelo GGUF compatível já baixado.

**Atenção:** o Ubuntu proot que estava sendo usado no desenvolvimento tinha Python 3.14. Não crie o ambiente virtual com esse interpretador: o projeto declara Python <3.14. Instale/seleciona uma versão compatível (por exemplo, Python 3.12) antes de seguir.

## 2. Baixar o projeto

```bash
git clone https://github.com/victorvicente1404-wq/LIA-Next-Age.git
cd LIA-Next-Age
git switch foundation/bootstrap
npm install
```

## 3. Iniciar o modelo local

Em uma sessão do Termux, informe o caminho real do seu arquivo GGUF:

```bash
llama-server -m "$HOME/modelos/seu-modelo.gguf" --host 127.0.0.1 --port 8080
```

O caminho acima é apenas um exemplo: substitua pelo local em que o modelo foi salvo. Para um aparelho com 6 GB de RAM, comece com um modelo quantizado pequeno e contexto conservador; o espaço disponível também é usado pelo Android e pelos demais processos.

## 4. Iniciar o núcleo Python

Em outra sessão:

```bash
cd LIA-Next-Age/services/core
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
export LIA_RUNTIME_BACKEND=auto
export LIA_LLM_BASE_URL=http://127.0.0.1:8080/v1
export LIA_LLM_MODEL=local-model
export LIA_DATA_DIR="$HOME/.lia"
export LIA_DEV_WORKSPACES="$HOME/projects/LIA-Next-Age"
uvicorn lia_core.main:app --host 127.0.0.1 --port 8000
```

Com `auto`, a Lia usa OpenJarvis `LlamaCppEngine` se o pacote estiver instalado nesse ambiente Python; caso contrário, usa o adaptador HTTP direto de llama.cpp. Para forçar o adaptador direto, defina `LIA_RUNTIME_BACKEND=llama.cpp`. Nenhuma opção aciona provedores de IA na nuvem.

Ajuste `LIA_DEV_WORKSPACES` para o caminho real do repositório no seu aparelho. Essa allowlist dá à Lia Dev permissão somente de leitura para navegar e abrir arquivos desse projeto. Separe várias pastas com `:` no Linux/Termux.

Se o executável compatível não se chamar `python3.12`, use o comando da versão Python >=3.10 e <3.14 que você instalou.

## 5. Iniciar a interface

Em uma terceira sessão, na raiz do repositório:

```bash
npm run dev
```

Abra no navegador do próprio aparelho:

```
http://127.0.0.1:5173
```

A interface consulta o núcleo pela proxy local do Vite. O serviço Python fica em `127.0.0.1:8000` e o servidor de inferência em `127.0.0.1:8080`.

## 6. Verificar

- O indicador da interface deve mostrar que o núcleo está conectado.
- Envie uma mensagem curta.
- Se o modelo não estiver ativo, a API retorna erro explícito; ela não tenta Groq, Gemini, OpenRouter ou outro serviço remoto.
- Memórias explícitas ficam no SQLite dentro de `$HOME/.lia` e podem ser gerenciadas na aba Memória.
- A aba Lia Dev lista os workspaces configurados e permite abrir arquivos de texto em modo somente leitura.

## Segurança e limites desta etapa

- Mantenha os serviços vinculados ao loopback. Não troque para `0.0.0.0` nem exponha portas na rede como atalho.
- A API de pareamento já existe no branch de desenvolvimento, mas permanece desativada por padrão. HTTPS, allowlist de origens, aprovação local, escopos, HMAC, nonce anti-replay e revogação foram cobertos por testes automatizados; isso não equivale a validação de TLS, proxy, firewall ou cliente real. Não habilite acesso remoto nesta etapa.
- A memória explícita e a recuperação contextual já existem; não confunda isso com extração automática irrestrita de lembranças.
- Lia Dev já possui leitura controlada, propostas de patch, tarefas predefinidas e operações Git tipadas com aprovação. Use somente workspaces explicitamente autorizados e revise cada proposta.
- A camada de voz via navegador, whisper.cpp e Piper tem testes com mocks/fakes, mas os binários, modelos, formatos reais, latência e qualidade ainda não foram validados no aparelho.
- O fluxo web e o núcleo ainda precisam ser testados no ambiente real do Galaxy. A aplicação Android nativa, Android Keystore e integração com APIs do sistema ainda não existem.
- Termux é opcional para o protótipo; não instale uma distribuição Linux em proot.
