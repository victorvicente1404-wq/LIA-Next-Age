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

**Implementação inicial de Git:**
- Operações tipadas disponíveis: criar branch, trocar para branch local não protegida, commit de arquivos rastreados explicitamente selecionados e reverter o commit atual criando um novo commit inverso.
- `main` e `master` são protegidas contra commit e reversão; troca para essas branches é bloqueada na Lia Dev.
- Cada operação exige proposta e aprovação separada; propostas expiram em cinco minutos e são de uso único.
- Trocas/criações de branch e reversões exigem árvore de trabalho limpa. Commits validam o diff selecionado, não incluem paths staged não selecionados e bloqueiam arquivos secretos e pathspecs com curingas.
- Git hooks são desabilitados durante essas operações. Isso não substitui uma sandbox de sistema operacional.

**Próximos passos:**
- Reutilizar agentes simples/orchestrator e o runtime de ferramentas do OpenJarvis após validar a instalação no Termux.
- Manter os contratos de chat, memória e permissões pertencentes à aplicação Lia.
- Avaliar o backend FTS5 do OpenJarvis separadamente da memória pessoal explícita.

## ADR-005 — Registry e política de ferramentas pertencem à Lia

**Decisão:** a Lia mantém seu próprio registry de ferramentas, catálogo de permissões e política fail-closed. O OpenJarvis fornece o loop de orquestração quando disponível, mas não define sozinho o que a Lia pode executar.

**Primeira allowlist:** `calculator` (aritmética limitada, sem `eval`) e `memory_search` (consulta somente leitura à memória explícita).

**Governança:** cada chamada é validada pela política antes do despacho usando o hook `before_tool_call` do `OrchestratorAgent`. Ferramentas desconhecidas, ferramentas fora da allowlist e ferramentas que não sejam somente de leitura são negadas. O agente recebe o histórico de conversa já preparado pela API.

**Consequências:** 
- O agente não recebe shell, escrita de arquivos, Git mutável, web, mensageria, calendário ou automação doméstica.
- O adaptador direto llama.cpp continua funcionando sem OpenJarvis, sem ferramentas e sem fallback remoto.
- A resposta da API informa agente, número de chamadas de ferramenta e turnos do agente.
- A integração é opcional e ainda precisa de validação com o GGUF real e no ambiente Android.


## ADR-006 — Orquestrador cognitivo pertence à Lia

**Decisão:** o loop de decisão, planejamento curto, despacho de ferramentas e limites de execução pertencem ao módulo `LiaOrchestrator`. Os backends de inferência oferecem somente a operação `complete`; não definem a política nem a identidade do agente.

**Implementação inicial:**\n- Para tarefas multi-etapas, o modelo pode propor um objetivo e até seis etapas curtas; o plano é exibido na interface e não concede permissões.\n- A execução continua restrita às ferramentas allowlisted, com limite de quatro decisões e uma síntese final.\n
- O modelo local escolhe entre uma resposta final estruturada ou uma chamada de ferramenta JSON.
- Cada iteração aceita no máximo uma ferramenta; o loop tem limite rígido de quatro etapas.
- Todas as chamadas passam pelo registry e pela política fail-closed da Lia.
- Ferramentas desconhecidas ou não autorizadas retornam falha sem despacho.
- A saída de ferramenta é marcada como dado não confiável no contexto seguinte.
- llama.cpp HTTP e OpenJarvis LlamaCppEngine usam o mesmo orquestrador. OpenJarvis é opcional e substituível.
- O caminho simples continua disponível com `use_tools=false`; não existe fallback remoto.

**Limitações conhecidas:** allowlist inicial limitada a calculadora e busca de memória; ainda não há plano persistente, agentes especialistas, tarefas interrompíveis, ferramentas de escrita ou conectores. A validação real com GGUF e Android continua pendente.
