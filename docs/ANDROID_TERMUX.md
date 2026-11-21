# Rodar a Lia no Android/Termux

Este guia prepara a fundação atual no Android. A inferência é local: o serviço Python encaminha a conversa somente para o servidor llama.cpp configurado.

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
export LIA_LLM_BASE_URL=http://127.0.0.1:8080/v1
export LIA_LLM_MODEL=local-model
export LIA_DATA_DIR="$HOME/.lia"
uvicorn lia_core.main:app --host 127.0.0.1 --port 8000
```

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
- Memórias explícitas ficam no SQLite dentro de `$HOME/.lia`.

## Segurança e limites desta etapa

- Os servidores são vinculados ao loopback. Não troque para `0.0.0.0` nem exponha portas na rede: autenticação e pareamento de dispositivos ainda não foram implementados.
- A memória já persiste, mas a extração automática e a injeção contextual ainda não foram implementadas.
- Voz, visão, automações domésticas e Lia Dev ainda são etapas futuras.
- Esta fundação ainda precisa ser compilada e testada no ambiente real do aparelho.
