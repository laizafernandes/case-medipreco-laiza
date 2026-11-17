"""Peça única de IA (Etapa 5): explicação em português do extrato/divergência.

Regras estritas de arquitetura:
1. Recebe APENAS dados estruturados do motor (sem nomes de pessoas — LGPD).
2. Nunca calcula valores.
3. Guardrail obrigatório: toda cifra numérica presente no texto gerado pela IA
   precisa existir nos dados de entrada; caso contrário, o texto é descartado
   e substituído pelo modelo determinístico fixo.
4. Funciona 100% sem IA externa (fallback determinístico).
"""

from __future__ import annotations

import json
import os
import re
import urllib.request
from dataclasses import dataclass
from typing import Any, Callable

from medipreco.formatacao import formatar_brl


@dataclass(frozen=True)
class ResultadoExplicacao:
    texto: str
    usou_ia: bool
    descartado_por_alucinacao: bool


def _extrair_cifras(texto: str) -> set[float]:
    """Extrai números no formato BR (1.234,56 / 718) ou EN (1234.56) para checagem anti-alucinação."""
    tokens = re.findall(r"\d+(?:\.\d{3})+,\d+|\d+,\d+|\d+\.\d+|\d+", texto)
    valores: set[float] = set()
    for t in tokens:
        norm = t.replace(".", "").replace(",", ".") if "," in t else t
        try:
            valores.add(round(float(norm), 2))
        except ValueError:
            continue
    return valores


def _coletar_numeros_permitidos(obj: Any, destino: set[float]) -> None:
    if isinstance(obj, bool):
        return
    if isinstance(obj, (int, float)):
        destino.add(round(float(obj), 2))
        destino.add(round(abs(float(obj)), 2))
    elif isinstance(obj, str):
        for v in _extrair_cifras(obj):
            destino.add(v)
    elif isinstance(obj, dict):
        for v in obj.values():
            _coletar_numeros_permitidos(v, destino)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            _coletar_numeros_permitidos(v, destino)


def validar_cifras_no_texto(texto: str, dados_entrada: dict[str, Any]) -> bool:
    """Retorna True somente se TODA cifra numérica no texto existir nos dados de entrada."""
    permitidos: set[float] = set()
    _coletar_numeros_permitidos(dados_entrada, permitidos)
    encontrados = _extrair_cifras(texto)
    return encontrados.issubset(permitidos)


def gerar_texto_fixo(dados: dict[str, Any]) -> str:
    """Modelo determinístico fixo para cada cenário estruturado do motor."""
    cenario = dados.get("cenario", "generico")

    if cenario == "aurora_corte_vs_rh":
        return (
            f"Cliente {dados['cliente']} ({dados['competencia']}): "
            f"na foto do sistema em {dados['data_corte']} constavam {dados['qtd_foto']} vidas "
            f"({formatar_brl(dados['valor_foto'])}). Após a carga de {dados['data_carga_tardia']}, "
            f"foram processadas {dados['qtd_saidas_tardias_ate_corte']} saídas anteriores a {dados['data_corte']}, "
            f"mostrando que a realidade no corte era {dados['qtd_realidade_corte']} vidas "
            f"(e {dados['qtd_sistema_fim_mes']} vidas no fim do mês). "
            f"A diferença líquida em reais é de {formatar_brl(dados['diferenca_reais'])}."
        )

    if cenario == "estrela_minimo_credito":
        return (
            f"Cliente {dados['cliente']} ({dados['competencia']}): "
            f"a nota foi emitida sobre {dados['qtd_emitida']} vidas ({formatar_brl(dados['valor_emitido'])}). "
            f"Com os desligamentos informados após o corte, a base real no dia {dados['dia_corte']} "
            f"caiu para {dados['qtd_real']} vidas, acionando o mínimo contratual de {dados['minimo_vidas']} vidas "
            f"({formatar_brl(dados['valor_devido'])}). Isso gera um crédito de {formatar_brl(dados['credito_reais'])} na próxima nota."
        )

    if cenario == "bravo_unidade_errada":
        return (
            f"Cliente {dados['cliente']} ({dados['competencia']}): "
            f"o contrato cobra apenas por titulares ({formatar_brl(dados['valor_unitario'])}/titular), "
            f"mas a nota cobrou {dados['qtd_cobrada']} unidades ({formatar_brl(dados['valor_cobrado'])}), "
            f"equivalente ao total de vidas com dependentes. "
            f"Na foto da data de corte havia {dados['qtd_titulares_foto']} titulares ({formatar_brl(dados['valor_foto'])}), "
            f"evitando um erro de {formatar_brl(dados['erro_foto_reais'])} se travado antes da emissão."
        )

    return (
        f"Cliente {dados.get('cliente', '-')}, competência {dados.get('competencia', '-')}: "
        f"valor apurado {formatar_brl(dados.get('valor_total', 0.0))} "
        f"(corte de conhecimento: {dados.get('conhecido_ate', '-')})."
    )


def _chamar_openai_opcional(dados: dict[str, Any]) -> str | None:
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        return None
    prompt = (
        "Você é um analista de faturamento da Medipreço. Explique em português claro, "
        "em no máximo 3 frases, o resumo abaixo usando EXCLUSIVAMENTE os números fornecidos. "
        "Não faça contas novas nem invente datas ou valores.\n\n"
        f"Dados: {json.dumps(dados, ensure_ascii=False)}"
    )
    body = json.dumps(
        {
            "model": os.environ.get("OPENAI_MODEL", "gpt-4o-mini"),
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.0,
        }
    ).encode("utf-8")
    req = urllib.request.Request(
        "https://api.openai.com/v1/chat/completions",
        data=body,
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
        return payload["choices"][0]["message"]["content"].strip()
    except Exception:
        return None


def explicar_extrato(
    dados_estruturados: dict[str, Any],
    gerador_ia: Callable[[dict[str, Any]], str | None] | None = None,
) -> ResultadoExplicacao:
    """Gera explicação em português com guardrail anti-alucinação e fallback fixo."""
    fn_ia = gerador_ia if gerador_ia is not None else _chamar_openai_opcional
    texto_ia = fn_ia(dados_estruturados)

    if texto_ia:
        if validar_cifras_no_texto(texto_ia, dados_estruturados):
            return ResultadoExplicacao(
                texto=texto_ia, usou_ia=True, descartado_por_alucinacao=False
            )
        return ResultadoExplicacao(
            texto=gerar_texto_fixo(dados_estruturados),
            usou_ia=False,
            descartado_por_alucinacao=True,
        )

    return ResultadoExplicacao(
        texto=gerar_texto_fixo(dados_estruturados),
        usou_ia=False,
        descartado_por_alucinacao=False,
    )
