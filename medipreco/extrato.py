"""Gerador de extrato auditável por nota (Etapa 3).

Cada linha do extrato representa uma pessoa (ou complemento de mínimo garantido)
com dias ativos, plano, valor, regra do contrato e corte de conhecimento.
A soma das linhas fecha exatamente no centavo com o total apurado pelo motor.
"""

from __future__ import annotations

import sqlite3
from collections import defaultdict
from dataclasses import dataclass
from typing import Any

from medipreco.contratos import (
    ItemApurado,
    _competencia_anterior,
    _filtrar_unidade,
    _preco_por_faixa,
    _ratear_centavos,
    _rotulo_regra,
    apurar_competencia,
    carregar_contratos,
)
from medipreco.timeline import EstadoDia, linha_do_tempo_diaria, listar_dias_mes


@dataclass(frozen=True)
class LinhaExtrato:
    """Uma linha auditável do extrato de faturamento."""

    pessoa_id: str
    cnpj: str
    tipo_pessoa: str
    dias_ativos: int
    plano: str
    valor: float
    regra_contrato: str
    conhecido_ate: str


@dataclass(frozen=True)
class ExtratoNota:
    """Extrato completo de um CNPJ tomador em uma competência."""

    cliente: str
    competencia: str
    cnpj_tomador: str
    conhecido_ate: str
    regra_contrato: str
    valor_total_nota: float
    itens: list[ItemApurado]
    linhas: list[LinhaExtrato]


def gerar_extratos_cliente(
    conn: sqlite3.Connection,
    cliente: str,
    competencia: str,
    conhecido_ate: str,
    contratos: dict[str, dict[str, Any]] | None = None,
) -> list[ExtratoNota]:
    """Gera um ExtratoNota por CNPJ tomador para o cliente e competência."""
    cfg_mapa = contratos if contratos is not None else carregar_contratos()
    cfg = cfg_mapa[cliente]
    itens = apurar_competencia(conn, cliente, competencia, conhecido_ate, cfg_mapa)

    unidade = cfg["unidade"]
    metodo = cfg["metodo_contagem"]
    modalidade = cfg["modalidade"]["tipo"]
    regra_str = _rotulo_regra(cfg)
    comp_base = _competencia_anterior(competencia) if modalidade == "pre_pago" else competencia
    dias_mes = listar_dias_mes(comp_base)
    tl_mes = linha_do_tempo_diaria(conn, cliente, dias_mes, conhecido_ate)

    # Conta quantos dias cada vínculo esteve ativo na competência base
    dias_por_vinculo: dict[tuple[str, str], int] = defaultdict(int)
    for d in dias_mes:
        for e in _filtrar_unidade(tl_mes[d], unidade):
            dias_por_vinculo[(e.pessoa_id, e.cnpj)] += 1

    linhas_por_tomador: dict[str, list[LinhaExtrato]] = defaultdict(list)

    if metodo == "foto_dia":
        dia_alvo = f"{comp_base}-{cfg['dia_corte']:02d}"
        estados = _filtrar_unidade(tl_mes[dia_alvo], unidade)
        planos_precos = cfg["planos_precos"]
        cnpj_tom = cfg["rateio_cnpj"]["cnpj_unico"]

        for e in sorted(estados, key=lambda x: (x.cnpj, x.pessoa_id)):
            preco = float(planos_precos["*"] if "*" in planos_precos else planos_precos[e.plano])
            linhas_por_tomador[cnpj_tom].append(
                LinhaExtrato(
                    pessoa_id=e.pessoa_id,
                    cnpj=e.cnpj,
                    tipo_pessoa=e.tipo_pessoa,
                    dias_ativos=dias_por_vinculo[(e.pessoa_id, e.cnpj)],
                    plano=e.plano,
                    valor=round(preco, 2),
                    regra_contrato=regra_str,
                    conhecido_ate=conhecido_ate,
                )
            )

        minimo = int(cfg["minimo_vidas"])
        if len(estados) < minimo:
            faltantes = minimo - len(estados)
            preco = float(planos_precos["*"])
            linhas_por_tomador[cnpj_tom].append(
                LinhaExtrato(
                    pessoa_id="COMPLEMENTO_MINIMO",
                    cnpj=cnpj_tom,
                    tipo_pessoa="ajuste_minimo",
                    dias_ativos=0,
                    plano="-",
                    valor=round(faltantes * preco, 2),
                    regra_contrato=regra_str,
                    conhecido_ate=conhecido_ate,
                )
            )

    elif metodo == "qualquer_dia_ativo":
        vistos: dict[tuple[str, str], EstadoDia] = {}
        for d in dias_mes:
            for e in _filtrar_unidade(tl_mes[d], unidade):
                vistos[(e.pessoa_id, e.cnpj)] = e
        preco = _preco_por_faixa(cfg["faixas"], len(vistos))
        cnpj_tom = cfg["rateio_cnpj"]["cnpj_unico"]
        for (pid, cnpj), e in sorted(vistos.items()):
            linhas_por_tomador[cnpj_tom].append(
                LinhaExtrato(
                    pessoa_id=pid,
                    cnpj=cnpj,
                    tipo_pessoa=e.tipo_pessoa,
                    dias_ativos=dias_por_vinculo[(pid, cnpj)],
                    plano=e.plano,
                    valor=round(preco, 2),
                    regra_contrato=regra_str,
                    conhecido_ate=conhecido_ate,
                )
            )

    elif metodo == "pro_rata":
        vistos_pr: dict[tuple[str, str], EstadoDia] = {}
        for d in dias_mes:
            for e in _filtrar_unidade(tl_mes[d], unidade):
                vistos_pr[(e.pessoa_id, e.cnpj)] = e

        cnpj_tom = cfg["rateio_cnpj"]["cnpj_unico"]
        total_nota = itens[0].valor_total
        pesos_dias = {
            f"{pid}|{cnpj}": dias_por_vinculo[(pid, cnpj)]
            for (pid, cnpj) in vistos_pr
        }
        valores_por_chave = _ratear_centavos(total_nota, pesos_dias)
        for (pid, cnpj), e in sorted(vistos_pr.items()):
            linhas_por_tomador[cnpj_tom].append(
                LinhaExtrato(
                    pessoa_id=pid,
                    cnpj=cnpj,
                    tipo_pessoa=e.tipo_pessoa,
                    dias_ativos=dias_por_vinculo[(pid, cnpj)],
                    plano=e.plano,
                    valor=valores_por_chave[f"{pid}|{cnpj}"],
                    regra_contrato=regra_str,
                    conhecido_ate=conhecido_ate,
                )
            )

    elif metodo == "pico":
        dia_pico = itens[0].detalhe["dia_pico"]
        estados_pico = _filtrar_unidade(tl_mes[dia_pico], unidade)
        por_tomador: dict[str, list[EstadoDia]] = defaultdict(list)
        if cfg["rateio_cnpj"]["nota_por_cnpj"]:
            for e in estados_pico:
                por_tomador[e.cnpj].append(e)
        else:
            por_tomador[cfg["rateio_cnpj"]["cnpj_unico"]] = estados_pico

        for item in itens:
            cnpj_tom = item.cnpj_tomador
            grupo_estados = sorted(por_tomador[cnpj_tom], key=lambda x: (x.cnpj, x.pessoa_id))
            pesos_pessoas = {f"{e.pessoa_id}|{e.cnpj}": 1 for e in grupo_estados}
            valores_pessoas = _ratear_centavos(item.valor_total, pesos_pessoas)
            for e in grupo_estados:
                linhas_por_tomador[cnpj_tom].append(
                    LinhaExtrato(
                        pessoa_id=e.pessoa_id,
                        cnpj=e.cnpj,
                        tipo_pessoa=e.tipo_pessoa,
                        dias_ativos=dias_por_vinculo[(e.pessoa_id, e.cnpj)],
                        plano=e.plano,
                        valor=valores_pessoas[f"{e.pessoa_id}|{e.cnpj}"],
                        regra_contrato=regra_str,
                        conhecido_ate=conhecido_ate,
                    )
                )

    itens_por_tomador: dict[str, list[ItemApurado]] = defaultdict(list)
    for it in itens:
        itens_por_tomador[it.cnpj_tomador].append(it)

    extratos: list[ExtratoNota] = []
    for cnpj_tom in sorted(itens_por_tomador.keys()):
        its = itens_por_tomador[cnpj_tom]
        total_nota = round(sum(i.valor_total for i in its), 2)
        extratos.append(
            ExtratoNota(
                cliente=cliente,
                competencia=competencia,
                cnpj_tomador=cnpj_tom,
                conhecido_ate=conhecido_ate,
                regra_contrato=regra_str,
                valor_total_nota=total_nota,
                itens=its,
                linhas=linhas_por_tomador[cnpj_tom],
            )
        )
    return extratos
