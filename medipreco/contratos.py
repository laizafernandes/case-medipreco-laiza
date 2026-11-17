"""Motor genérico de apuração contratual orientado a configuração (JSON).

Nenhuma regra de cliente é codificada via `if cliente == ...`; todo o cálculo
deriva dos parâmetros em `config/contratos.json` e da linha do tempo de eventos.
"""

from __future__ import annotations

import json
import sqlite3
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from medipreco.timeline import EstadoDia, linha_do_tempo_diaria, listar_dias_mes

CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "contratos.json"


@dataclass(frozen=True)
class ItemApurado:
    """Um item faturável gerado pelo motor para um CNPJ tomador."""

    cnpj_tomador: str
    descricao: str
    unidade: str
    quantidade: float
    valor_unitario: float
    valor_total: float
    conhecido_ate: str
    regra_contrato: str
    detalhe: dict[str, Any]


def carregar_contratos(path: Path = CONFIG_PATH) -> dict[str, dict[str, Any]]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _filtrar_unidade(estados: list[EstadoDia], unidade: str) -> list[EstadoDia]:
    if unidade == "titular":
        return [e for e in estados if e.tipo_pessoa == "titular"]
    return estados


def _competencia_anterior(competencia: str) -> str:
    ano, mes = map(int, competencia.split("-"))
    if mes == 1:
        return f"{ano - 1}-12"
    return f"{ano}-{mes - 1:02d}"


def _preco_por_faixa(faixas_cfg: dict[str, Any], quantidade: float) -> float:
    for nivel in faixas_cfg["niveis"]:
        ate = nivel["ate"]
        if ate is None or quantidade <= ate:
            return float(nivel["valor"])
    raise ValueError(f"Nenhuma faixa encontrada para quantidade={quantidade}")


def _ratear_centavos(valor_total: float, pesos_por_cnpj: dict[str, int]) -> dict[str, float]:
    """Rateia `valor_total` proporcionalmente aos pesos, dando centavos de resto ao maior resto."""
    total_centavos = round(valor_total * 100)
    soma_pesos = sum(pesos_por_cnpj.values())
    if soma_pesos == 0:
        return {cnpj: 0.0 for cnpj in pesos_por_cnpj}

    cotas_exatas = {
        cnpj: (total_centavos * peso) / soma_pesos
        for cnpj, peso in pesos_por_cnpj.items()
    }
    centavos_base = {cnpj: int(val) for cnpj, val in cotas_exatas.items()}
    resto = total_centavos - sum(centavos_base.values())

    ordem = sorted(
        pesos_por_cnpj.keys(),
        key=lambda c: (-(cotas_exatas[c] - centavos_base[c]), c),
    )
    for cnpj in ordem[:resto]:
        centavos_base[cnpj] += 1

    return {cnpj: round(cent / 100, 2) for cnpj, cent in centavos_base.items()}


def _rotulo_regra(cfg: dict[str, Any]) -> str:
    return (
        f"{cfg['contrato_id']} | {cfg['modalidade']['tipo']} | "
        f"{cfg['metodo_contagem']} | unidade={cfg['unidade']}"
    )


def apurar_competencia(
    conn: sqlite3.Connection,
    cliente: str,
    competencia: str,
    conhecido_ate: str,
    contratos: dict[str, dict[str, Any]] | None = None,
) -> list[ItemApurado]:
    """Calcula os itens faturáveis de um cliente para uma competência."""
    cfg_mapa = contratos if contratos is not None else carregar_contratos()
    cfg = cfg_mapa[cliente]

    unidade = cfg["unidade"]
    metodo = cfg["metodo_contagem"]
    modalidade = cfg["modalidade"]["tipo"]
    rateio_cfg = cfg["rateio_cnpj"]
    regra_str = _rotulo_regra(cfg)

    comp_base = _competencia_anterior(competencia) if modalidade == "pre_pago" else competencia
    dias_mes = listar_dias_mes(comp_base)

    if metodo == "foto_dia":
        dia_alvo = f"{comp_base}-{cfg['dia_corte']:02d}"
        tl = linha_do_tempo_diaria(conn, cliente, [dia_alvo], conhecido_ate)
        estados = _filtrar_unidade(tl[dia_alvo], unidade)
        return _montar_itens_planos_ou_faixa(
            cfg, estados, conhecido_ate=conhecido_ate, regra_str=regra_str, dia_referencia=dia_alvo
        )

    tl = linha_do_tempo_diaria(conn, cliente, dias_mes, conhecido_ate)

    if metodo == "qualquer_dia_ativo":
        vistos: dict[tuple[str, str], EstadoDia] = {}
        for dia in dias_mes:
            for e in _filtrar_unidade(tl[dia], unidade):
                vistos[(e.pessoa_id, e.cnpj)] = e
        estados_unicos = list(vistos.values())
        return _montar_itens_planos_ou_faixa(
            cfg, estados_unicos, conhecido_ate=conhecido_ate, regra_str=regra_str, dia_referencia=None
        )

    if metodo == "pro_rata":
        n_dias = len(dias_mes)
        dias_ativos_total = sum(len(_filtrar_unidade(tl[d], unidade)) for d in dias_mes)
        qtd_equiv = dias_ativos_total / n_dias
        preco = float(cfg["planos_precos"]["*"])
        valor = round(qtd_equiv * preco, 2)
        return [
            ItemApurado(
                cnpj_tomador=rateio_cfg["cnpj_unico"],
                descricao="Mensalidade (pró-rata dia)",
                unidade=unidade,
                quantidade=round(qtd_equiv, 4),
                valor_unitario=preco,
                valor_total=valor,
                conhecido_ate=conhecido_ate,
                regra_contrato=regra_str,
                detalhe={"dias_mes": n_dias, "dias_ativos_total": dias_ativos_total},
            )
        ]

    if metodo == "pico":
        melhor_dia = dias_mes[0]
        melhor_pessoas: set[str] = set()
        for dia in dias_mes:
            pessoas_dia = {e.pessoa_id for e in _filtrar_unidade(tl[dia], unidade)}
            if len(pessoas_dia) > len(melhor_pessoas):
                melhor_pessoas = pessoas_dia
                melhor_dia = dia

        qtd_pico = len(melhor_pessoas)
        preco = float(cfg["planos_precos"]["*"])
        valor_grupo = round(qtd_pico * preco, 2)

        if not rateio_cfg["nota_por_cnpj"]:
            return [
                ItemApurado(
                    cnpj_tomador=rateio_cfg["cnpj_unico"],
                    descricao="Mensalidade (pico simultâneo)",
                    unidade=unidade,
                    quantidade=qtd_pico,
                    valor_unitario=preco,
                    valor_total=valor_grupo,
                    conhecido_ate=conhecido_ate,
                    regra_contrato=regra_str,
                    detalhe={"dia_pico": melhor_dia},
                )
            ]

        pesos: dict[str, int] = defaultdict(int)
        for e in _filtrar_unidade(tl[melhor_dia], unidade):
            pesos[e.cnpj] += 1
        valores_rateados = _ratear_centavos(valor_grupo, dict(pesos))
        itens: list[ItemApurado] = []
        for cnpj in sorted(pesos.keys()):
            itens.append(
                ItemApurado(
                    cnpj_tomador=cnpj,
                    descricao="Mensalidade (rateio pico)",
                    unidade=unidade,
                    quantidade=pesos[cnpj],
                    valor_unitario=preco,
                    valor_total=valores_rateados[cnpj],
                    conhecido_ate=conhecido_ate,
                    regra_contrato=regra_str,
                    detalhe={"dia_pico": melhor_dia, "pico_grupo": qtd_pico},
                )
            )
        return itens

    raise ValueError(f"Método de contagem desconhecido: {metodo}")


def apurar_compensacao_pre_pago(
    conn: sqlite3.Connection,
    cliente: str,
    competencia_referencia: str,
    qtd_cobrada_antecipadamente: int,
    conhecido_ate: str,
    contratos: dict[str, dict[str, Any]] | None = None,
) -> ItemApurado:
    """Calcula a compensação (crédito/débito) de contratos pré-pagos na nota seguinte.

    Premissa declarada: 'efetivamente ativos no mês de referência' = ativos no
    dia 26 do próprio mês de referência (coerente com a régua de dia 26).
    """
    cfg_mapa = contratos if contratos is not None else carregar_contratos()
    cfg = cfg_mapa[cliente]
    if cfg["modalidade"]["tipo"] != "pre_pago":
        raise ValueError(f"{cliente} não é contrato pré-pago")

    dia_ref = f"{competencia_referencia}-{cfg['dia_corte']:02d}"
    tl = linha_do_tempo_diaria(conn, cliente, [dia_ref], conhecido_ate)
    efetivos = len(_filtrar_unidade(tl[dia_ref], cfg["unidade"]))
    diferenca = efetivos - qtd_cobrada_antecipadamente
    preco = float(cfg["planos_precos"]["*"])
    valor = round(diferenca * preco, 2)

    return ItemApurado(
        cnpj_tomador=cfg["rateio_cnpj"]["cnpj_unico"],
        descricao=f"Compensação pré-pago ({competencia_referencia})",
        unidade=cfg["unidade"],
        quantidade=diferenca,
        valor_unitario=preco,
        valor_total=valor,
        conhecido_ate=conhecido_ate,
        regra_contrato=f"{_rotulo_regra(cfg)} | compensacao={cfg['modalidade']['regra_compensacao']}",
        detalhe={
            "dia_referencia": dia_ref,
            "cobrado_antecipadamente": qtd_cobrada_antecipadamente,
            "efetivos_no_mes": efetivos,
        },
    )


def _montar_itens_planos_ou_faixa(
    cfg: dict[str, Any],
    estados: list[EstadoDia],
    conhecido_ate: str,
    regra_str: str,
    dia_referencia: str | None,
) -> list[ItemApurado]:
    cnpj_unico = cfg["rateio_cnpj"]["cnpj_unico"]
    unidade = cfg["unidade"]
    minimo = int(cfg["minimo_vidas"])

    if cfg["faixas"] is not None:
        qtd = len(estados)
        qtd_faturada = max(qtd, minimo)
        preco = _preco_por_faixa(cfg["faixas"], qtd_faturada)
        return [
            ItemApurado(
                cnpj_tomador=cnpj_unico,
                descricao="Mensalidade",
                unidade=unidade,
                quantidade=qtd_faturada,
                valor_unitario=preco,
                valor_total=round(qtd_faturada * preco, 2),
                conhecido_ate=conhecido_ate,
                regra_contrato=regra_str,
                detalhe={"quantidade_real": qtd, "dia_referencia": dia_referencia},
            )
        ]

    planos_precos: dict[str, float] = cfg["planos_precos"]
    if "*" in planos_precos:
        qtd = len(estados)
        qtd_faturada = max(qtd, minimo)
        preco = float(planos_precos["*"])
        return [
            ItemApurado(
                cnpj_tomador=cnpj_unico,
                descricao="Mensalidade",
                unidade=unidade,
                quantidade=qtd_faturada,
                valor_unitario=preco,
                valor_total=round(qtd_faturada * preco, 2),
                conhecido_ate=conhecido_ate,
                regra_contrato=regra_str,
                detalhe={
                    "quantidade_real": qtd,
                    "minimo_aplicado": qtd < minimo,
                    "dia_referencia": dia_referencia,
                },
            )
        ]

    por_plano: dict[str, int] = defaultdict(int)
    for e in estados:
        por_plano[e.plano] += 1

    itens: list[ItemApurado] = []
    for plano in sorted(planos_precos.keys()):
        preco = float(planos_precos[plano])
        qtd = por_plano[plano]
        itens.append(
            ItemApurado(
                cnpj_tomador=cnpj_unico,
                descricao=f"Mensalidade Plano {plano}",
                unidade=unidade,
                quantidade=qtd,
                valor_unitario=preco,
                valor_total=round(qtd * preco, 2),
                conhecido_ate=conhecido_ate,
                regra_contrato=regra_str,
                detalhe={"plano": plano, "dia_referencia": dia_referencia},
            )
        )
    return itens
