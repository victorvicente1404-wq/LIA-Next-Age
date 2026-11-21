# Lia — Next Age

Assistente pessoal local-first, modular e extensível.

## Princípios

- **Local-first:** conversação, memória e automações essenciais devem funcionar sem depender de créditos ou cotas de provedores de IA.
- **Integrações desacopladas:** serviços externos (por exemplo, WhatsApp via Evolution API e serviços Google) são conectores opcionais, não o cérebro.
- **Memória independente do modelo:** dados e lembranças pertencem à aplicação, com armazenamento explícito e recuperação contextual.
- **Lia Dev:** agente de engenharia capaz de inspecionar workspaces autorizados, propor alterações revisáveis, mostrar diffs, executar testes e operar Git com aprovação.
- **Segurança por padrão:** permissões mínimas, ações sensíveis sujeitas a aprovação, segredos fora do repositório e histórico de alterações.
- **Evolução incremental:** módulos pequenos, contratos documentados, testes e rollback; preservar funcionalidades úteis dos projetos anteriores sem copiar acoplamentos desnecessários.

## Arquitetura

1. **Interface:** aplicação web responsiva (Vite/React), utilizável no celular e no desktop.
2. **Núcleo:** API Python para conversação, roteamento, políticas e coordenação de ferramentas.
3. **Runtime local:** adaptador OpenJarvis opcional para seu motor LlamaCppEngine; adaptador HTTP direto para llama.cpp como caminho compatível e fallback exclusivamente local.
4. **Histórico e memória:** histórico de conversas em SQLite separado da memória de longo prazo; memória independente do modelo, com gerenciamento explícito, validação e recuperação contextual limitada a cinco itens por turno.
5. **Lia Dev:** interface de exploração, leitura de workspaces autorizados, propostas de patch com diff e tarefas de desenvolvimento predefinidas; aplicação e execução em chamadas separadas com aprovação explícita, hash contra alterações concorrentes, escrita atômica e backup. Propostas pendentes expiram em 30 minutos e são limitadas a 50 por processo; Metadados de rollback são persistidos em `LIA_DATA_DIR/dev-backups/operations.json` e vinculados ao caminho original do workspace; propostas pendentes são descartadas no reinício.
6. **Percepção e voz:** módulos opcionais para áudio, câmera e contexto, sempre com indicadores e consentimento.
7. **Conectores:** adaptadores independentes para WhatsApp, Google e dispositivos domésticos.

## Política de provedores

O modelo local é o padrão. Provedores remotos podem ser configurados voluntariamente como opção, mas nunca devem ser acionados silenciosamente nem ser requisito para o funcionamento básico. A API de chat informa qual motor local respondeu e mantém `external_traffic: false`.

## Segurança

- Não incluir chaves, tokens, senhas ou dados pessoais neste repositório.
- Não executar comandos arbitrários recebidos do modelo.
- Validar caminhos para impedir acesso fora dos workspaces autorizados.
- Exibir o plano e o diff antes de gravar alterações.
- Exigir aprovação para escrita, instalação de dependências, execução de comandos e acesso a dados sensíveis.
- Registrar ações e permitir desfazer alterações sempre que possível.
- A interface e a API de desenvolvimento são vinculadas ao loopback; não as exponha à rede antes de implementar autenticação e pareamento de dispositivos.
- Lia Dev só enxerga pastas adicionadas explicitamente à allowlist `LIA_DEV_WORKSPACES`; leitura de arquivos de segredos é bloqueada.

## Progresso

- [x] Monorepo inicial e regras de engenharia.
- [x] Interface web com chat, gerenciador de memória e painel Lia Dev.
- [x] API Python e health check.
- [x] Adaptador direto local para llama.cpp.
- [x] Adaptador opcional para OpenJarvis LlamaCppEngine, selecionável por configuração.
- [x] Memória SQLite independente do modelo, gerenciamento explícito e recuperação contextual.
- [x] Histórico persistente de conversas em SQLite separado da memória, com sessões, restauração, paginação e exclusão.
- [x] Lia Dev: listar workspaces autorizados, navegar pastas e ler arquivos de texto com limites.
- [x] CI: testes Python, Ruff e build web.
- [x] Lia Dev: proposta de patch com diff, aprovação em endpoint separado, verificação de versão, escrita atômica e backup para rollback.
- [x] Lia Dev: tarefas tipadas e predefinidas (Git status/diff, pytest, Ruff e build web), com prévia, aprovação separada, timeout e saída limitada.
- [ ] Lia Dev: operações Git de escrita (branch, commit, checkout e rollback) com revisão e aprovação.
- [ ] Integrar voz, percepção e conectores opcionais.
- [ ] Integrar agentes e primitivas OpenJarvis sem instalar dependências pesadas obrigatórias no Android.
- [ ] Definir e validar o ambiente de execução quando a fundação estiver pronta (sem exigir Termux nesta etapa).

## Rodar localmente

Consulte [o guia Android/Termux](docs/ANDROID_TERMUX.md), [o guia do núcleo](services/core/README.md) e [as decisões de integração OpenJarvis](docs/DECISIONS.md).

Este repositório é a nova base da Lia. O branch `foundation/bootstrap` é o ambiente de desenvolvimento; a branch `main` permanece intacta até a revisão e validação da fundação.
