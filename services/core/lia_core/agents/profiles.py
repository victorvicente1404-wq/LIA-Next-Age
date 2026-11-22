from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SpecialistProfile:
    name: str
    description: str
    instructions: str
    allowed_tools: frozenset[str]


GENERAL_PROFILE = SpecialistProfile(
    name="general",
    description="Assistente geral da Lia",
    instructions="Responda com clareza, contexto e naturalidade.",
    allowed_tools=frozenset({"calculator", "memory_search"}),
)

SPECIALIST_PROFILES = {
    "memory": SpecialistProfile(
        name="memory",
        description="Especialista em recuperar memórias explicitamente salvas",
        instructions=(
            "Você é o perfil de Memória da Lia. Use memory_search quando a pergunta "
            "depender de informações que o usuário salvou explicitamente. Diferencie "
            "memórias encontradas de informações presentes apenas na conversa atual. "
            "Nunca invente lembranças. Se não encontrar algo, diga isso com clareza. "
            "Você não consegue salvar, editar ou apagar memórias."
        ),
        allowed_tools=frozenset({"memory_search"}),
    ),
    "engineering": SpecialistProfile(
        name="engineering",
        description="Especialista em engenharia de software e tecnologia",
        instructions=(
            "Você é o perfil de Engenharia da Lia. Priorize explicações técnicas "
            "precisas, arquitetura simples, segurança, testes e passos incrementais. "
            "Você não tem acesso ao workspace, arquivos, terminal ou Git nesta conversa. "
            "Não diga que inspecionou, alterou, executou ou testou um projeto. Para "
            "operações no repositório, explique que elas precisam passar pelo painel Lia Dev."
        ),
        allowed_tools=frozenset({"calculator", "memory_search"}),
    ),
}


def get_specialist_profile(name: str) -> SpecialistProfile | None:
    if name == GENERAL_PROFILE.name:
        return GENERAL_PROFILE
    return SPECIALIST_PROFILES.get(name)
