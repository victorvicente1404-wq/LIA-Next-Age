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
- Reutilizar o motor local OpenJarvis quando vantajoso, sem delegar a ele a identidade, o planejamento ou a política de ferramentas da Lia.
- Manter os contratos de chat, memória e permissões pertencentes à aplicação Lia.
- Avaliar o backend FTS5 do OpenJarvis separadamente da memória pessoal explícita.

## ADR-005 — Registry e política de ferramentas pertencem à Lia

**Decisão:** a Lia mantém seu próprio registry de ferramentas, catálogo de permissões e política fail-closed. O módulo `LiaOrchestrator` controla o loop de decisão e despacho; OpenJarvis fornece somente um runtime de inferência opcional.

**Primeira allowlist:** `calculator` (aritmética limitada, sem `eval`) e `memory_search` (consulta somente leitura à memória explícita).

**Governança:** cada chamada é despachada pelo `LiaOrchestrator` através do registry e da política fail-closed da Lia. Ferramentas desconhecidas, fora da allowlist ou não somente de leitura são negadas.

**Consequências:** 
- O agente não recebe shell, escrita de arquivos, Git mutável, web, mensageria, calendário ou automação doméstica.
- O adaptador direto llama.cpp continua funcionando sem OpenJarvis, sem ferramentas e sem fallback remoto.
- A resposta da API informa agente, número de chamadas de ferramenta e turnos do agente.
- A integração é opcional e ainda precisa de validação com o GGUF real e no ambiente Android.


## ADR-006 — Orquestrador cognitivo pertence à Lia

**Decisão:** o loop de decisão, planejamento curto, despacho de ferramentas e limites de execução pertencem ao módulo `LiaOrchestrator`. Os backends de inferência oferecem somente a operação `complete`; não definem a política nem a identidade do agente.

**Implementação inicial:**
- Para tarefas multi-etapas, o modelo pode propor um objetivo e até seis etapas curtas; o plano é exibido na interface e não concede permissões.
- A execução continua restrita às ferramentas allowlisted, com limite de quatro decisões e uma síntese final.

- O modelo local pode propor um plano estruturado de até seis etapas, uma resposta final ou uma chamada de ferramenta JSON.
- Cada iteração aceita no máximo uma ferramenta; o loop tem até quatro decisões e uma síntese final.
- Todas as chamadas passam pelo registry e pela política fail-closed da Lia.
- Ferramentas desconhecidas ou não autorizadas retornam falha sem despacho.
- O registry valida campos obrigatórios, tipos, limites de tamanho e rejeita parâmetros extras antes de despachar qualquer ferramenta; o subconjunto inicial de schemas é deliberadamente plano e escalar.
- A saída de ferramenta é marcada como dado não confiável no contexto seguinte.
- llama.cpp HTTP e OpenJarvis LlamaCppEngine usam o mesmo orquestrador. OpenJarvis é opcional e substituível.
- O caminho simples continua disponível com `use_tools=false`; não existe fallback remoto.

**Limitações conhecidas:** allowlist inicial limitada a calculadora e busca de memória; ainda não há plano persistente, agentes autônomos separados, tarefas interrompíveis, ferramentas de escrita ou conectores. A validação real com GGUF e Android continua pendente. Os perfis especialistas iniciais são descritos no ADR-007.


## ADR-007 — Especialistas como perfis subordinados ao orquestrador

**Decisão:** os primeiros especialistas da Lia são perfis de instrução e allowlists de ferramentas, não agentes autônomos nem modelos separados. O único loop de decisão continua em `LiaOrchestrator`.

**Perfis iniciais:**
- `general`: conversa geral, calculadora e busca de memória explícita.
- `memory`: recuperação de memórias salvas; somente `memory_search`.
- `engineering`: explicações de engenharia e tecnologia; sem acesso ao workspace, terminal ou Git pelo chat.

**Governança:**
- O modelo pode selecionar no máximo um perfil especializado por resposta.
- Cada perfil recebe somente sua própria lista de ferramentas permitidas; a política global continua fail-closed.
- Nenhum perfil cria permissões, ferramentas, memória ou inferência separadas.
- Todos usam o mesmo modelo local, a mesma memória da Lia e o mesmo orquestrador.
- Novos perfis só devem ganhar ferramentas depois que os contratos, validações e aprovações correspondentes existirem.

**Limitações:** seleção de perfil é uma decisão do modelo e pode não ocorrer em modelos locais menos capazes. Os perfis iniciais não executam ações externas nem acessam recursos de Lia Dev.

## ADR-008 — API local e pareamento seguro entre dispositivos

**Decisão:** o núcleo da Lia permanece acessível somente por loopback até existir autenticação e pareamento de dispositivos. Estar na mesma rede Wi-Fi não é prova de identidade nem autorização.

**Limites obrigatórios antes de habilitar acesso pela rede:**
- Transporte HTTPS com certificado validado; nunca enviar credenciais ou áudio por HTTP em uma LAN.
- Pareamento iniciado e aprovado pelo usuário no dispositivo principal, usando código/QR de uso único, aleatório, de curta duração e limitado a uma tentativa bem definida.
- Tokens de dispositivo com escopo mínimo, expiração, rotação e revogação individual. Segredos não aparecem em URLs, logs ou mensagens de erro; armazenar somente hashes de tokens de longa duração.
- Proteção contra replay por nonce/expiração, validação estrita de origem e proteção CSRF nas rotas mutáveis.
- Limites de tentativas, tamanho de payload e concorrência, além de registro local de pareamentos, revogações e ações sensíveis.
- Nenhuma rota de pareamento pode conceder acesso automaticamente a workspaces, Lia Dev, arquivos ou operações de escrita. Cada capacidade exige escopo explícito e aprovação correspondente.
- O modo local sem pareamento continua funcional e não depende de serviço externo, conta hospedada ou API de inferência.

**Consequência:** o uso do microfone pelo navegador no próprio dispositivo pode ser desenvolvido localmente, mas o acesso celular-PC pela rede fica bloqueado até que o fluxo de identidade, transporte, autorização e revogação seja implementado e testado. Não abrir o servidor em `0.0.0.0` como atalho.

**Ameaças consideradas:** dispositivos desconhecidos na LAN, páginas web maliciosas tentando acessar serviços locais, roubo/reuso de tokens, replay de solicitações e exposição acidental de dados pessoais ou workspaces.

**Status da implementação inicial:**
- `LIA_PAIRING_ENABLED=false` mantém o acesso remoto à API bloqueado, mesmo que o processo escute em uma interface LAN. O modo local continua acessível por loopback.
- Solicitações remotas exigem HTTPS, têm código de 256 bits, expiração de cinco minutos, até cinco tentativas de aprovação e limite de criação por origem.
- A aprovação ocorre localmente. O `request_id` torna-se o `device_id`; o dispositivo deriva uma chave HMAC não extraível a partir do SHA-256 do código de 256 bits. O endpoint de aprovação nunca devolve o segredo, e o código bruto não é enviado em requisições autenticadas. Apenas o digest é persistido.
- Os escopos são `chat`, `voice` e `memory:read` opcional. Sem `memory:read`, o chat remoto não recebe memórias nem ferramentas de consulta à memória. Escrita de memória e Lia Dev continuam locais.
- Requisições autenticadas exigem HMAC-SHA256, timestamp e nonce persistido de uso único. Dispositivos podem ser revogados localmente.
- Origens não locais continuam classificadas como remotas mesmo quando chegam por um proxy local, reduzindo o risco de DNS rebinding/proxy bypass. Origens locais de navegador são validadas contra a allowlist quando o pareamento está ativo.
- O protocolo e o backend têm testes automatizados. A interface de aprovação, armazenamento protegido do token no cliente, integração Android, certificados reais e configuração de firewall ainda não foram validados. Não habilitar acesso remoto em produção até concluir esses itens.



## ADR-009 — Android como plataforma principal

**Decisão:** a Lia será Android-first. O primeiro produto utilizável deve ser um aplicativo instalável que funcione diretamente no celular, sem exigir PC, servidor hospedado, distribuição Linux ou cotas de IA na nuvem. PC é uma plataforma complementar.

**Responsabilidades:**
- O aplicativo Android nativo será dono da interface principal, permissões, voz, notificações, integrações do sistema e ciclo de vida de serviços.
- O núcleo compartilhado continuará dono da identidade, políticas, orquestração, memória, histórico, ferramentas e Lia Dev; ele não pode pressupor que roda em Termux, navegador ou PC.
- llama.cpp continua como backend local suportado. Será avaliado um runtime Android nativo/NDK contra llama-server no Termux, medindo RAM, temperatura, bateria e ciclo de vida antes de escolher o caminho definitivo.
- Termux é uma ponte opcional para desenvolvimento e protótipo, sem exigir Ubuntu, Debian, proot ou outra distribuição Linux. A experiência final não exigirá que o usuário opere terminal.
- Desktop reutilizará os mesmos contratos e lógica, sem se tornar servidor obrigatório para o celular.

**Permissões Android:** usar APIs oficiais e o menor privilégio possível. Notificações exigem acesso de listener concedido pelo usuário; interação ampla com UI pode usar Accessibility Service opcional, ativado manualmente e explicado; câmera, microfone e localização usam permissões adequadas; arquivos usam Storage Access Framework/scoped storage; tarefas em segundo plano respeitam WorkManager/foreground service e as restrições do Android. Não prometer controle irrestrito de outros apps ou configurações protegidas.

**Consequências:** o repositório ainda não contém módulo Android nativo. A implementação começa após concluir a revisão da fundação atual e definir contratos de plataforma. A documentação de arquitetura está em docs/ANDROID_FIRST.md. A fundação Python/web continua aproveitável como núcleo e protótipo, não como produto Android final.


## ADR-010 — Contratos neutros de plataforma para Android-first

**Decisão:** antes de criar o cliente Android nativo, Lia define contratos versionados e independentes de transporte para inferência, ciclo de vida do modelo, histórico, memória, áudio, permissões, execução de ferramentas e ponte local.

**Regras:**
- Kotlin/Android e Python podem ter implementações internas diferentes, mas preservam os mesmos schemas, estados, limites e semântica.
- Chamadas in-process são preferidas. Uma ponte HTTP local só existe quando o runtime precisa de isolamento, vinculada a loopback, com segredo de sessão curto e allowlist estrita.
- Inferência local é padrão e declara explicitamente tráfego externo. Falha local não aciona nuvem silenciosamente.
- Histórico e memória permanecem separados. Memórias são explícitas e nunca viram instruções executáveis.
- Permissões são consultadas por capacidade estreita; concessão de permissão não substitui aprovação de ação sensível.
- Ferramentas de escrita usam proposta expirada, prévia legível e aprovação separada. Lia Dev continua uma superfície de confiança superior e isolada do chat comum.
- Os contratos exigem fixtures e testes compartilhados entre implementações.

**Consequências:** a implementação Android pode evoluir sem duplicar decisões de produto ou depender do navegador/Termux. O contrato não significa que runtime Android, Keystore, voz nativa ou JNI já estejam implementados. O documento normativo está em [PLATFORM_CONTRACTS.md](PLATFORM_CONTRACTS.md).
