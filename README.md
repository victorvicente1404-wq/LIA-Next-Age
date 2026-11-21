# Lia — Next Age

Assistente pessoal local-first, modular e extensível.

## Princípios

- **Local-first:** conversação, memória e automações essenciais devem funcionar sem depender de créditos ou cotas de provedores de IA.
- **Integrações desacopladas:** serviços externos (por exemplo, WhatsApp via Evolution API e serviços Google) são conectores opcionais, não o cérebro da Lia.
- **Memória independente do modelo:** dados e lembranças pertencem à aplicação, com armazenamento explícito e recuperação contextual.
- **Lia Dev:** agente de engenharia capaz de inspecionar workspaces autorizados, propor alterações revisáveis, mostrar diffs, executar testes e operar Git com aprovação.
- **Segurança por padrão:** permissões mínimas, ações sensíveis sujeitas a aprovação, segredos fora do repositório e histórico de alterações.
- **Evolução incremental:** módulos pequenos, contratos documentados, testes e rollback; preservar funcionalidades úteis dos projetos anteriores sem copiar acoplamentos desnecessários.

## Arquitetura-alvo

1. **Interface:** aplicação web responsiva (Vite/React), utilizável no celular e no desktop.
2. **Núcleo:** ciclo de interação, roteamento de intenções, políticas e coordenação de ferramentas.
3. **Runtime local:** servidor de inferência compatível com llama.cpp; OpenJarvis será avaliado/reutilizado como base do backend.
4. **Memória:** armazenamento local versionável, extração, indexação e recuperação controladas pela aplicação.
5. **Lia Dev:** workspace sandbox, operações Git, diffs, testes e terminal com allowlist/aprovação.
6. **Percepção e voz:** módulos opcionais para áudio, câmera e contexto, sempre com indicadores e consentimento.
7. **Conectores:** adaptadores independentes para WhatsApp, Google e dispositivos domésticos.

## Política de provedores

O modelo local é o padrão. Provedores remotos podem ser configurados voluntariamente como opção, mas nunca devem ser acionados silenciosamente nem ser requisito para o funcionamento básico. A interface deve informar qual motor respondeu e quando houve tráfego externo.

## Segurança

- Não incluir chaves, tokens, senhas ou dados pessoais neste repositório.
- Não executar comandos arbitrários recebidos do modelo.
- Validar caminhos para impedir acesso fora dos workspaces autorizados.
- Exibir o plano e o diff antes de gravar alterações.
- Exigir aprovação para escrita, instalação de dependências, execução de comandos e acesso a dados sensíveis.
- Registrar ações e permitir desfazer alterações sempre que possível.

## Plano inicial

- [ ] Definir contratos e estrutura do monorepo.
- [ ] Criar runtime local mínimo e health check.
- [ ] Implementar armazenamento e API de memória.
- [ ] Conectar a interface ao núcleo local.
- [ ] Implementar Lia Dev em sandbox com fluxo de aprovação.
- [ ] Portar seletivamente recursos úteis de LIA-1.0.
- [ ] Adicionar conectores opcionais e testes de integração.

## Estado

Este repositório inicia a nova base da Lia. As decisões arquiteturais devem ser registradas antes de adicionar dependências ou migrar módulos.
