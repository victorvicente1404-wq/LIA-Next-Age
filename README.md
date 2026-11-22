# Lia — Next Age

Assistente pessoal local-first, modular e extensível.

## Princípios

- **Android-first:** o celular é a plataforma principal; a primeira versão utilizável deve instalar e funcionar diretamente no Android.
- **Local-first:** conversação, memória e automações essenciais devem funcionar sem depender de créditos ou cotas de provedores de IA.
- **PC complementar:** desktop pode executar o mesmo núcleo, mas o celular não depende de um PC ou servidor hospedado.
- **Integrações desacopladas:** serviços externos (por exemplo, WhatsApp via Evolution API e serviços Google) são conectores opcionais, não o cérebro.
- **Memória independente do modelo:** dados e lembranças pertencem à aplicação, com armazenamento explícito e recuperação contextual.
- **Lia Dev:** agente de engenharia capaz de inspecionar workspaces autorizados, propor alterações revisáveis, mostrar diffs, executar testes e operar Git com aprovação.
- **Segurança por padrão:** permissões mínimas, ações sensíveis sujeitas a aprovação, segredos fora do repositório e histórico de alterações.
- **Evolução incremental:** módulos pequenos, contratos documentados, testes e rollback; preservar funcionalidades úteis dos projetos anteriores sem copiar acoplamentos desnecessários.

## Arquitetura-alvo

1. **Aplicativo Android nativo (principal):** interface, voz, permissões, notificações, integração com recursos do aparelho e ciclo de vida dos serviços. Kotlin/Android APIs; Compose é a direção preferida.
2. **Núcleo compartilhado da Lia:** identidade, políticas, orquestração, memória, histórico, ferramentas e Lia Dev. Não deve depender de navegador, Termux ou PC.
3. **Inferência local:** contrato substituível com llama.cpp como backend suportado. No Android, avaliar runtime nativo/NDK versus llama-server no Termux; sem fallback remoto silencioso.
4. **Termux opcional:** ponte de desenvolvimento e runtime inicial sem Ubuntu, Debian, proot ou outra distribuição Linux. Não é a experiência final obrigatória.
5. **PC complementar:** reutiliza os contratos e a lógica central, com launcher, interface e runtime locais próprios.
6. **Dados e conectores:** SQLite e armazenamento local; Google, WhatsApp e casa inteligente como integrações independentes e autorizadas.

A arquitetura e a sequência estão detalhadas em [Android-first](docs/ANDROID_FIRST.md). Os limites entre Android, núcleo e runtime estão em [contratos de plataforma](docs/PLATFORM_CONTRACTS.md).

## Política de provedores

O modelo local é o padrão. Provedores remotos podem ser configurados voluntariamente como opção, mas nunca devem ser acionados silenciosamente nem ser requisito para o funcionamento básico. A API de chat informa qual motor local respondeu e mantém external_traffic: false.

## Segurança

- Não incluir chaves, tokens, senhas ou dados pessoais neste repositório.
- Não executar comandos arbitrários recebidos do modelo.
- Validar caminhos para impedir acesso fora dos workspaces autorizados.
- Exibir o plano e o diff antes de gravar alterações.
- Exigir aprovação para escrita, instalação de dependências, execução de comandos e acesso a dados sensíveis.
- Registrar ações e permitir desfazer alterações sempre que possível.
- A interface e Lia Dev permanecem locais por padrão. A API de pareamento remoto é opt-in, exige HTTPS, aprovação local, escopos mínimos, assinatura com nonce de uso único e revogação; a integração de cliente ainda não foi validada em Android. Consulte [o protocolo de pareamento](docs/DEVICE_PAIRING.md).
- Lia Dev só enxerga pastas adicionadas explicitamente à allowlist LIA_DEV_WORKSPACES; leitura de arquivos de segredos é bloqueada.
- Recursos de Android usam permissões e APIs oficiais do sistema. Acesso por Acessibilidade é opcional e exige ativação manual; não há promessa de controle irrestrito do sistema.

## Progresso da fundação atual

- [x] Monorepo inicial e regras de engenharia.
- [x] Interface web responsiva com chat, gerenciador de memória e painel Lia Dev.
- [x] API Python e health check.
- [x] Adaptadores locais para llama.cpp e OpenJarvis LlamaCppEngine.
- [x] Memória SQLite independente do modelo, gerenciamento explícito e recuperação contextual.
- [x] Histórico persistente de conversas em SQLite separado da memória.
- [x] Lia Dev com workspaces allowlisted, leitura controlada, patches revisáveis, tarefas predefinidas e operações Git tipadas com aprovação.
- [x] CI: testes Python, Ruff e build web.
- [x] Primeira camada de voz local via navegador, whisper.cpp e Piper (mocks/fakes na CI; runtime real no Android ainda não validado).
- [x] API inicial de pareamento e helper web com HMAC, nonce anti-replay, escopos e revogação (sem validação ponta a ponta em Android).
- [x] Orquestrador próprio da Lia, com loop limitado e ferramentas locais allowlisted.
- [x] Perfis especialistas subordinados ao mesmo orquestrador.
- [x] Decisão de produto Android-first documentada.
- [x] Contratos neutros de plataforma definidos para orientar o cliente nativo.
- [ ] Revisão final de segurança e concorrência da Lia Dev.
- [ ] Cliente Android nativo, armazenamento de credenciais via Android Keystore e ponte local com o núcleo.
- [x] Backend nativo llama.cpp compilado para Android arm64; no Galaxy A37, o GGUF Qwen 2.5 1.5B foi carregado com sucesso. A qualidade da geração e o fluxo de conversa ainda estão em validação.
- [ ] Runtime de inferência e voz validados em dispositivo Android real.
- [ ] Integrações Android (notificações, arquivos, câmera, acessibilidade opcional e automações) implementadas uma por uma com permissões explícitas.
- [ ] Validar desktop como plataforma complementar.
- [ ] Integração final da fundação após revisão e testes.

## Estado do repositório

A branch foundation/bootstrap concentra o desenvolvimento ativo. A main não deve receber esta fundação até que a revisão e os testes exigidos estejam concluídos. Consulte a [comparação de branches](https://github.com/victorvicente1404-wq/LIA-Next-Age/compare/main...foundation/bootstrap) e o [PR #5](https://github.com/victorvicente1404-wq/LIA-Next-Age/pull/5).
