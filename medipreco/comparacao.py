"""Comparação Emitido × Contrato, decomposição por causa e diagnóstico pessoa a pessoa (Etapa 4).

Separa:
- (a) O que deveria ter saído na data de emissão (`data_emissao`)
- (b) O que a realidade até `2026-11-12` mostra (o ajuste que viria na nota seguinte)
Decompõe a diferença em: emitido -> unidade -> método -> relógio -> emissão -> info tardia -> final.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from typing import Any

from medipreco.contratos import apurar_competencia, carregar_contratos
from medipreco.timeline import estado_na_foto_sistema, linha_do_tempo_diaria

CONHECIDO_FINAL = "2026-11-12 23:59:59"


@dataclass(frozen=True)
class LinhaComparacao:
    cliente: str
    competencia: str
    data_emissao: str
    valor_emitido: float
    delta_unidade: float
    delta_metodo: float
    delta_relogio_emissao: float
    valor_na_emissao: float
    delta_info_tardia: float
    delta_faixa_degrau: float
    valor_conhecido_final: float
    diff_emissao: float
    diff_final: float
    erro_pct: float
    causas: tuple[str, ...]
    observacao: str


@dataclass(frozen=True)
class DiferencaPessoa:
    pessoa_id: str
    cnpj: str
    tipo_pessoa: str
    plano: str
    data_informada_saida: str
    data_processamento_saida: str


def _classificar_causas(
    cfg: dict[str, Any],
    delta_unidade: float,
    valor_emitido: float,
    valor_na_emissao: float,
    valor_final: float,
    minimo_aplicado: bool,
) -> tuple[str, ...]:
    causas: list[str] = []
    if delta_unidade != 0:
        causas.append("unidade_errada")
    if cfg["metodo_contagem"] in ("qualquer_dia_ativo", "pico", "pro_rata"):
        causas.append("metodo_contagem")
    if minimo_aplicado:
        causas.append("minimo_contratual")
    if round(valor_final - valor_na_emissao, 2) != 0 or (
        cfg["metodo_contagem"] == "foto_dia"
        and round(valor_na_emissao - valor_emitido, 2) != 0
        and "unidade_errada" not in causas
    ):
        causas.append("relogio")
    return tuple(dict.fromkeys(causas))


def comparar_emitido_vs_contrato(
    conn: sqlite3.Connection,
    contratos: dict[str, dict[str, Any]] | None = None,
    conhecido_final: str = CONHECIDO_FINAL,
) -> list[LinhaComparacao]:
    """Gera a tabela Emitido × Contrato com decomposição em reais por causa."""
    cfg_mapa = contratos if contratos is not None else carregar_contratos()

    emitidos = conn.execute(
        """
        SELECT cliente, competencia, MIN(data_emissao) AS data_emissao,
               MIN(contagem_em) AS contagem_em,
               ROUND(SUM(valor_item), 2) AS valor_emitido,
               MIN(valor_unitario) AS valor_unitario_emitido
        FROM notas_emitidas
        GROUP BY cliente, competencia
        ORDER BY competencia, cliente
        """
    ).fetchall()

    linhas: list[LinhaComparacao] = []
    for cliente, comp, data_emissao, contagem_em, valor_emitido, unit_emitido in emitidos:
        cfg = cfg_mapa[cliente]
        corte_emissao = f"{data_emissao} 23:59:59"

        # 1) Valor com unidade correta na foto de contagem_em
        foto_contagem = estado_na_foto_sistema(conn, contagem_em, cliente=cliente)
        if cfg["unidade"] == "titular":
            titulares_foto = sum(1 for e in foto_contagem if e.tipo_pessoa == "titular")
            preco_unit = float(cfg["planos_precos"]["*"])
            valor_unidade_correta_foto = round(titulares_foto * preco_unit, 2)
        else:
            valor_unidade_correta_foto = valor_emitido
        delta_unidade = round(valor_unidade_correta_foto - valor_emitido, 2)

        # 2) Valor pela regra do contrato usando conhecimento até a emissão
        itens_emissao = apurar_competencia(conn, cliente, comp, corte_emissao, cfg_mapa)
        val_emissao = round(sum(i.valor_total for i in itens_emissao), 2)

        if cfg["metodo_contagem"] != "foto_dia":
            itens_metodo_em_contagem = apurar_competencia(
                conn, cliente, comp, contagem_em, cfg_mapa
            )
            val_metodo_em_contagem = round(
                sum(i.valor_total for i in itens_metodo_em_contagem), 2
            )
            delta_metodo = round(val_metodo_em_contagem - valor_unidade_correta_foto, 2)
            delta_relogio_emissao = round(val_emissao - val_metodo_em_contagem, 2)
        else:
            delta_metodo = 0.0
            delta_relogio_emissao = round(val_emissao - valor_unidade_correta_foto, 2)

        # 3) Valor com conhecimento completo até 12/11
        itens_final = apurar_competencia(conn, cliente, comp, conhecido_final, cfg_mapa)
        val_final = round(sum(i.valor_total for i in itens_final), 2)
        delta_info_tardia = round(val_final - val_emissao, 2)

        # Efeito degrau de faixa (quando há tabela escalonada e mudou o preço unitário)
        if cfg.get("faixas") is not None and itens_final:
            unit_final = itens_final[0].valor_unitario
            qtd_final = itens_final[0].quantidade
            delta_faixa_degrau = round((unit_final - unit_emitido) * qtd_final, 2)
        else:
            delta_faixa_degrau = 0.0

        minimo_aplicado = any(i.detalhe.get("minimo_aplicado") for i in itens_final)
        causas = _classificar_causas(
            cfg, delta_unidade, valor_emitido, val_emissao, val_final, minimo_aplicado
        )

        diff_emissao = round(val_emissao - valor_emitido, 2)
        diff_final = round(val_final - valor_emitido, 2)
        erro_pct = round((diff_final / valor_emitido) * 100, 2) if valor_emitido else 0.0

        partes_obs: list[str] = []
        if delta_unidade != 0:
            partes_obs.append("Unidade cobrada na nota divergiu da unidade contratual.")
        if delta_faixa_degrau != 0:
            partes_obs.append("Mudança de faixa por efeito degrau.")
        if minimo_aplicado:
            partes_obs.append("Mínimo contratual acionado após eventos tardios.")
        obs = " ".join(partes_obs)

        linhas.append(
            LinhaComparacao(
                cliente=cliente,
                competencia=comp,
                data_emissao=data_emissao,
                valor_emitido=valor_emitido,
                delta_unidade=delta_unidade,
                delta_metodo=delta_metodo,
                delta_relogio_emissao=delta_relogio_emissao,
                valor_na_emissao=val_emissao,
                delta_info_tardia=delta_info_tardia,
                delta_faixa_degrau=delta_faixa_degrau,
                valor_conhecido_final=val_final,
                diff_emissao=diff_emissao,
                diff_final=diff_final,
                erro_pct=erro_pct,
                causas=causas,
                observacao=obs,
            )
        )
    return linhas


def listar_diferencas_corte_dia_26(
    conn: sqlite3.Connection,
    cliente: str,
    competencia: str,
    conhecido_ate: str = CONHECIDO_FINAL,
) -> list[DiferencaPessoa]:
    """Lista pessoas cobradas na foto de `contagem_em` que já haviam saído até o dia 26 pela `data_informada`."""
    row = conn.execute(
        "SELECT MIN(contagem_em) FROM notas_emitidas WHERE cliente = ? AND competencia = ?",
        (cliente, competencia),
    ).fetchone()
    if not row or not row[0]:
        return []
    contagem_em = row[0]
    dia_26 = f"{competencia}-26"

    foto = {
        (e.pessoa_id, e.cnpj): e
        for e in estado_na_foto_sistema(conn, contagem_em, cliente=cliente)
    }
    realidade = {
        (e.pessoa_id, e.cnpj): e
        for e in linha_do_tempo_diaria(conn, cliente, [dia_26], conhecido_ate)[dia_26]
    }

    extras_na_foto = set(foto.keys()) - set(realidade.keys())
    diffs: list[DiferencaPessoa] = []
    for pid, cnpj in sorted(extras_na_foto):
        e = foto[(pid, cnpj)]
        saida = conn.execute(
            """
            SELECT data_informada, data_processamento
            FROM eventos
            WHERE pessoa_id = ? AND cnpj = ?
              AND tipo_evento = 'saida'
              AND data_informada <= ?
              AND data_processamento <= ?
            ORDER BY data_processamento DESC
            LIMIT 1
            """,
            (pid, cnpj, dia_26, conhecido_ate),
        ).fetchone()
        diffs.append(
            DiferencaPessoa(
                pessoa_id=pid,
                cnpj=cnpj,
                tipo_pessoa=e.tipo_pessoa,
                plano=e.plano,
                data_informada_saida=saida[0] if saida else "-",
                data_processamento_saida=saida[1] if saida else "-",
            )
        )
    return diffs
