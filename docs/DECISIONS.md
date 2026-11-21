# Decisões de arquitetura

## ADR-001 — Inferência local como caminho padrão

**Decisão:** a primeira implementação de conversa usa o endpoint OpenAI-compatible do llama.cpp, com um adaptador opcional para o motor OpenJarvis `LlamaCppEngine`.

**Motivo:** o usuário já possui `llama-server` no Termux. Um adaptador HTTP pequeno mantém a compatibilidade Android, enquanto o adaptador OpenJarvis reutiliza a primitiva de inferência quando o pacote está instalado.

**Consequências:**
- A aplicação não exige chaves de provedores de IA.
- Falha do modelo local retorna erro explícito; não existe fallback remoto automático.
- `LIA_RUNTIME_BACKEND=auto` prefere OpenJarvis quando disponível e usa o adaptador direto local quando não estiver instalado.
- `LIA_RUNTIME_BACKEND=openjarvis` exige o pacote; `LIA_RUNTIME_BACKEND=llama.cpp` força o adaptador direto.
- O OpenJarvis checkout `c5a7766e` declara Python >=3.10,<3.14. A branch principal mais recente passou a declarar >=3.11,<3.14. O ambiente Python 3.14 do proot continua incompatível.
- O pacote OpenJarvis tem uma árvore de dependências maior; não é obrigatório no caminho Android mínimo.

## ADR-002 — Memória separada do modelo

**Decisão:** memórias explícitas são persistidas em SQLite pelo serviço da Lia.

**Motivo:** o modelo pode ser substituído sem perder os dados da assistente.

**Consequências:**
- A primeira versão permite salvar, listar, pesquisar e apagar entradas.
- A gravação é explícita; não há extração silenciosa de toda conversa.
- Recuperação contextual, níveis de confiança, origem, expiração e aprovação de extrações serão definidos em uma etapa própria.
- O backend SQLite/FTS5 do OpenJarvis está sendo avaliado, mas o checkout fixado usa uma extensão Rust obrigatória. O armazenamento próprio da Lia continua sendo o caminho mínimo e previsível no Android.

## ADR-003 — Ferramentas e Lia Dev com fronteiras de segurança

**Decisão:** o modelo nunca recebe acesso irrestrito ao shell ou ao sistema de arquivos.

**Fluxo obrigatório para futuras ações de desenvolvimento:**
1. Resolver o workspace autorizado e validar que o caminho permanece dentro dele.
2. Produzir um plano estruturado com operações tipadas.
3. Exibir comandos, arquivos afetados e diff previsto.
4. Solicitar aprovação explícita para escrita, instalação, execução ou operações externas.
5. Executar em sandbox com limites de tempo, saída e recursos.
6. Registrar o resultado e oferecer rollback por Git quando aplicável.

**Proibido:** transformar texto livre do modelo em comando de shell com `shell=True`, aceitar caminhos arbitrários ou ativar autonomia irrestrita por padrão.

## ADR-004 — OpenJarvis como primitiva reutilizável, não dependência obrigatória

**Decisão:** integrar primitivas OpenJarvis atrás de interfaces da Lia e manter adaptadores próprios pequenos para os requisitos móveis.

**Motivo:** OpenJarvis já fornece motores OpenAI-compatible, agentes, registries, ferramentas e memória pesquisável. Porém, seu pacote completo e algumas extensões nativas podem ser pesados para o Android. A Lia deve aproveitar essas primitivas quando instaladas, sem tornar o funcionamento básico dependente delas.

**Próximos passos:**
- Reutilizar agentes simples/orchestrator e o runtime de ferramentas do OpenJarvis após validar a instalação no Termux.
- Manter os contratos de chat, memória e permissões pertencentes à aplicação Lia.
- Avaliar o backend FTS5 do OpenJarvis separadamente da memória pessoal explícita.
