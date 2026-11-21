# Decisões de arquitetura

## ADR-001 — Inferência local como caminho padrão

**Decisão:** a primeira implementação de conversa usa o endpoint OpenAI-compatible do llama.cpp.

**Motivo:** o usuário já possui `llama-server` no Termux. Um adaptador HTTP pequeno reduz dependências e permite testar a aplicação sem instalar um framework inteiro no Android.

**Consequências:**
- A aplicação não exige chaves de provedores de IA.
- Falha do modelo local retorna erro explícito; não existe fallback remoto automático.
- O adaptador fica atrás de uma interface para permitir integração posterior com OpenJarvis ou outros runtimes locais.
- OpenJarvis continua sendo avaliado como base de agentes, ferramentas e memória, não uma dependência obrigatória antes de validar compatibilidade com Android e a faixa de Python do ambiente.

## ADR-002 — Memória separada do modelo

**Decisão:** memórias explícitas são persistidas em SQLite pelo serviço da Lia.

**Motivo:** o modelo pode ser substituído sem perder os dados da assistente.

**Consequências:**
- A primeira versão permite salvar, listar, pesquisar e apagar entradas.
- A gravação é explícita; não há extração silenciosa de toda conversa.
- Recuperação contextual, níveis de confiança, origem, expiração e aprovação de extrações serão definidos em uma etapa própria.

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
