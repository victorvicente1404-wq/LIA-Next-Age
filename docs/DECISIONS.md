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

**Decisão:** memórias explícitas são persistidas em SQLite pelo serviço da Lia e recuperadas para o contexto de conversa.

**Motivo:** o modelo pode ser substituído sem perder os dados da assistente, e o usuário mantém controle sobre o que é guardado.

**Consequências:**
- A interface permite criar, listar, pesquisar e apagar memórias.
- Preferências salvas explicitamente são incluídas no contexto; outras memórias são recuperadas por busca local FTS5 quando disponível.
- A API informa quantas memórias foram usadas e permite desativar a recuperação em uma chamada.
- A gravação é explícita; não há extração silenciosa de toda conversa.
- A recuperação usa dados salvos como contexto, nunca como comandos executáveis.
- O backend SQLite/FTS5 do OpenJarvis está sendo avaliado, mas o checkout fixado usa uma extensão Rust obrigatória. O armazenamento próprio da Lia continua sendo o caminho mínimo e previsível no Android.

## ADR-003 — Ferramentas e Lia Dev com fronteiras de segurança

**Decisão:** o modelo nunca recebe acesso irrestrito ao shell ou ao sistema de arquivos.

**Fluxo obrigatório para futuras ações de desenvolvimento:**
1. Resolver o workspace autorizado e validar que o caminho permanece dentro dele.
2. Produzir um plano estruturado com operações tipadas.
3. Exibir comandos, arquivos afetados e diff previsto.
4. Solicitar aprovação explícita para escrita, instalação, execução ou operações externas.
5. Executar com limites de tempo e saída. Até existir uma sandbox em nível de sistema operacional implementada e validada, comandos aprovados rodam como processos locais e devem ser tratados como código confiável do projeto.
6. Registrar o resultado e oferecer rollback por Git quando aplicável.

**Proibido:** transformar texto livre do modelo em comando de shell com `shell=True`, aceitar caminhos arbitrários ou ativar autonomia irrestrita por padrão.

## ADR-004 — OpenJarvis como primitiva reutilizável, não dependência obrigatória

**Decisão:** integrar primitivas OpenJarvis atrás de interfaces da Lia e manter adaptadores próprios pequenos para os requisitos móveis.

**Motivo:** OpenJarvis já fornece motores OpenAI-compatible, agentes, registries, ferramentas e memória pesquisável. Porém, seu pacote completo e algumas extensões nativas podem ser pesados para o Android. A Lia deve aproveitar essas primitivas quando instaladas, sem tornar o funcionamento básico dependente delas.

**Próximos passos:**
- Reutilizar agentes simples/orchestrator e o runtime de ferramentas do OpenJarvis após validar a instalação no Termux.
- Manter os contratos de chat, memória e permissões pertencentes à aplicação Lia.
- Avaliar o backend FTS5 do OpenJarvis separadamente da memória pessoal explícita.
