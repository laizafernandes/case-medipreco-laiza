"""Validações determinísticas pré-emissão (Etapa 5).

Cada regra retorna um AlertaValidacao explícito com severidade ('bloqueio' ou 'aviso'),
código da regra e detalhes numéricos para revisão do financeiro antes de emitir a NF.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from typing import Any

from medipreco.contratos import carregar_contratos
from medipreco.extrato import ExtratoNota
from medipreco.timeline import estado_na_foto_sistema


@dataclass(frozen=True)
class AlertaValidacao:
    codigo: str
    severidade: str  # 'bloqueio' | 'aviso'
    cliente: str
    competencia: str
    mensagem: str
    detalhes: dict[str, Any]


def validar_unidade_titular_vs_vidas(
    conn: sqlite3.Connection,
    cliente: str,
    competencia: str,
    quantidade_candidata: float,
    corte_ts: str,
    contratos: dict[str, dict[str, Any]] | None = None,
) -> AlertaValidacao | None:
    """Regra 1: bloqueia se contrato cobra por titular e a quantidade candidata equivale ao total de vidas."""
    cfg = (contratos or carregar_contratos())[cliente]
    if cfg["unidade"] != "titular":
        return None
    estados = estado_na_foto_sistema(conn, corte_ts, cliente=cliente)
    total_vidas = len(estados)
    total_titulares = sum(1 for e in estados if e.tipo_pessoa == "titular")
    if total_vidas > total_titulares and round(quantidade_candidata) == total_vidas:
        return AlertaValidacao(
            codigo="UNIDADE_VIDAS_EM_CONTRATO_TITULAR",
            severidade="bloqueio",
            cliente=cliente,
            competencia=competencia,
            mensagem=(
                f"Quantidade informada ({int(quantidade_candidata)}) coincide com total de vidas "
                f"({total_vidas}), mas o contrato cobra apenas titulares ({total_titulares})."
            ),
            detalhes={"candidata": quantidade_candidata, "total_vidas": total_vidas, "titulares": total_titulares},
        )
    return None


def validar_variacao_vs_mes_anterior(
    cliente: str,
    competencia: str,
    valor_atual: float,
    valor_anterior: float | None,
    limite_pct: float = 10.0,
) -> AlertaValidacao | None:
    """Regra 2: alerta quando a variação absoluta frente ao mês anterior passa de 10%."""
    if not valor_anterior:
        return None
    var_pct = ((valor_atual - valor_anterior) / valor_anterior) * 100
    if abs(var_pct) > limite_pct:
        return AlertaValidacao(
            codigo="VARIACAO_MAIOR_10_PCT",
            severidade="aviso",
            cliente=cliente,
            competencia=competencia,
            mensagem=f"Variação de {var_pct:+.1f}% vs mês anterior (R$ {valor_anterior:,.2f} -> R$ {valor_atual:,.2f}).",
            detalhes={"valor_anterior": valor_anterior, "valor_atual": valor_atual, "variacao_pct": round(var_pct, 2)},
        )
    return None


def validar_proximidade_limite_faixa(
    cliente: str,
    competencia: str,
    quantidade: float,
    contratos: dict[str, dict[str, Any]] | None = None,
    margem_pct: float = 2.0,
) -> AlertaValidacao | None:
    """Regra 3: alerta quando a base está a menos de 2% de um degrau da tabela escalonada."""
    cfg = (contratos or carregar_contratos())[cliente]
    if not cfg.get("faixas"):
        return None
    for nivel in cfg["faixas"]["niveis"]:
        ate = nivel["ate"]
        if ate is None:
            continue
        dist_pct = abs(quantidade - ate) / ate * 100
        if dist_pct < margem_pct:
            return AlertaValidacao(
                codigo="PROXIMO_LIMITE_FAIXA",
                severidade="aviso",
                cliente=cliente,
                competencia=competencia,
                mensagem=f"Base ({int(quantidade)}) a {dist_pct:.2f}% do limite de faixa ({ate} vidas).",
                detalhes={"quantidade": quantidade, "limite": ate, "distancia_pct": round(dist_pct, 2)},
            )
    return None


def validar_minimo_acionado(
    cliente: str,
    competencia: str,
    extrato: ExtratoNota,
) -> AlertaValidacao | None:
    """Regra 4: alerta quando o mínimo garantido foi acionado no faturamento."""
    for item in extrato.itens:
        if item.detalhe.get("minimo_aplicado"):
            return AlertaValidacao(
                codigo="MINIMO_GARANTIDO_ACIONADO",
                severidade="aviso",
                cliente=cliente,
                competencia=competencia,
                mensagem=(
                    f"Mínimo contratual acionado: base real de {item.detalhe['quantidade_real']} "
                    f"vidas ficou abaixo do mínimo de {int(item.quantidade)}."
                ),
                detalhes={"real": item.detalhe["quantidade_real"], "faturado": int(item.quantidade)},
            )
    return None


def validar_cargas_atipicas_quarentena(
    conn: sqlite3.Connection,
    cliente: str,
    competencia: str,
    limite_lote_entradas: int = 300,
    limite_retroativo_dias: int = 90,
) -> list[AlertaValidacao]:
    """Regra 5: coloca em quarentena lotes com muitas entradas de uma vez ou data_informada > 90 dias retroativa."""
    rows = conn.execute(
        """
        SELECT date(ev.data_processamento) AS dia_proc,
               COUNT(*) AS qtd_entradas,
               MAX(julianday(date(ev.data_processamento)) - julianday(ev.data_informada)) AS max_lag_dias
        FROM eventos ev
        JOIN empresas e ON ev.cnpj = e.cnpj
        WHERE e.cliente = ?
          AND ev.tipo_evento = 'entrada'
          AND substr(ev.data_processamento, 1, 7) = ?
        GROUP BY dia_proc
        HAVING qtd_entradas >= ? OR max_lag_dias > ?
        ORDER BY dia_proc
        """,
        (cliente, competencia, limite_lote_entradas, limite_retroativo_dias),
    ).fetchall()

    alertas: list[AlertaValidacao] = []
    for dia_proc, qtd, max_lag in rows:
        alertas.append(
            AlertaValidacao(
                codigo="CARGA_ATIPICA_QUARENTENA",
                severidade="bloqueio",
                cliente=cliente,
                competencia=competencia,
                mensagem=(
                    f"Quarentena: carga de {dia_proc} trouxe {qtd} entradas "
                    f"com retroatividade de até {int(max_lag)} dias."
                ),
                detalhes={"dia_processamento": dia_proc, "qtd_entradas": qtd, "max_lag_dias": int(max_lag)},
            )
        )
    return alertas


def validar_desligamentos_fora_sla(
    conn: sqlite3.Connection,
    cliente: str,
    competencia: str,
    sla_dias_corridos: int = 7,
) -> AlertaValidacao | None:
    """Regra 6: alerta quando há desligamentos informados após o SLA contratual."""
    row = conn.execute(
        """
        SELECT COUNT(*) AS fora_sla,
               ROUND(AVG(julianday(date(ev.data_processamento)) - julianday(ev.data_informada)), 1) AS media_lag
        FROM eventos ev
        JOIN empresas e ON ev.cnpj = e.cnpj
        WHERE e.cliente = ?
          AND ev.tipo_evento = 'saida'
          AND substr(ev.data_informada, 1, 7) = ?
          AND (julianday(date(ev.data_processamento)) - julianday(ev.data_informada)) > ?
        """,
        (cliente, competencia, sla_dias_corridos),
    ).fetchone()
    if row and row[0] > 0:
        return AlertaValidacao(
            codigo="DESLIGAMENTO_FORA_SLA",
            severidade="aviso",
            cliente=cliente,
            competencia=competencia,
            mensagem=f"{row[0]} desligamentos de {competencia} informados fora do SLA (lag médio {row[1]} dias).",
            detalhes={"fora_sla": row[0], "media_lag_dias": row[1], "sla_dias": sla_dias_corridos},
        )
    return None


def validar_soma_extrato_independente(
    extrato: ExtratoNota,
) -> AlertaValidacao | None:
    """Regra 7: bloqueia se a soma das linhas do extrato divergir do total da nota."""
    soma_linhas = round(sum(l.valor for l in extrato.linhas), 2)
    if soma_linhas != extrato.valor_total_nota:
        return AlertaValidacao(
            codigo="DIVERGENCIA_EXTRATO_NOTA",
            severidade="bloqueio",
            cliente=extrato.cliente,
            competencia=extrato.competencia,
            mensagem=f"Soma do extrato ({soma_linhas}) difere do total da nota ({extrato.valor_total_nota}).",
            detalhes={"soma_linhas": soma_linhas, "valor_total_nota": extrato.valor_total_nota},
        )
    return None
