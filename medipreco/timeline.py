"""Motor de linha do tempo diária sobre o histórico de eventos.

Reconstrói quem estava ativo (e em qual plano) em qualquer dia ou instante,
sem depender da tabela `vinculos` (que é apenas a foto atual).
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Iterable


@dataclass(frozen=True)
class EstadoDia:
    """Estado de um vínculo (pessoa_id, cnpj) em um determinado dia."""

    pessoa_id: str
    cnpj: str
    tipo_pessoa: str  # 'titular' | 'dependente'
    plano: str


def listar_dias_mes(competencia: str) -> list[str]:
    """Retorna todas as datas YYYY-MM-DD de uma competência YYYY-MM."""
    ano, mes = map(int, competencia.split("-"))
    inicio = date(ano, mes, 1)
    proximo_mes = date(ano + 1, 1, 1) if mes == 12 else date(ano, mes + 1, 1)
    dias: list[str] = []
    atual = inicio
    while atual < proximo_mes:
        dias.append(atual.isoformat())
        atual += timedelta(days=1)
    return dias


def obter_eventos_anulados(conn: sqlite3.Connection) -> set[int]:
    """Identifica pares (entrada, saida) anulados operacionalmente.

    Regra atual: toda `saida` com `origem = 'suporte_medipreco'` cuja
    `data_informada` coincide com a data de processamento de uma `entrada`
    do mesmo vínculo `(pessoa_id, cnpj)` anula tanto a `saida` quanto essa
    `entrada` (sem fixar cliente ou data).
    Limitação conhecida: a solução definitiva de produto é um campo explícito
    `anulado_por_evento_id` no schema de `eventos`.
    """
    rows = conn.execute(
        """
        SELECT ent.evento_id, sai.evento_id
        FROM eventos sai
        JOIN eventos ent
          ON ent.pessoa_id = sai.pessoa_id
         AND ent.cnpj = sai.cnpj
         AND ent.tipo_evento = 'entrada'
         AND date(ent.data_processamento) = sai.data_informada
         AND ent.data_processamento < sai.data_processamento
        WHERE sai.tipo_evento = 'saida'
          AND sai.origem = 'suporte_medipreco'
        """
    ).fetchall()
    anulados: set[int] = set()
    for ent_id, sai_id in rows:
        anulados.add(ent_id)
        anulados.add(sai_id)
    return anulados


def estado_na_foto_sistema(
    conn: sqlite3.Connection,
    corte_ts: str,
    cliente: str | None = None,
    cnpj: str | None = None,
) -> list[EstadoDia]:
    """Reconstrói a 'foto' do sistema no instante `corte_ts` (eixo `data_processamento`).

    Equivale a perguntar: 'o que o sistema mostrava como ativo exatamente em corte_ts?'
    """
    filtros = ["ev.data_processamento <= ?"]
    params: list[str] = [corte_ts]
    if cliente:
        filtros.append("e.cliente = ?")
        params.append(cliente)
    if cnpj:
        filtros.append("ev.cnpj = ?")
        params.append(cnpj)

    where_sql = " AND ".join(filtros)
    rows = conn.execute(
        f"""
        WITH ultimo AS (
            SELECT ev.pessoa_id,
                   ev.cnpj,
                   ev.tipo_evento,
                   ev.plano,
                   ROW_NUMBER() OVER (
                       PARTITION BY ev.pessoa_id, ev.cnpj
                       ORDER BY ev.data_processamento DESC, ev.evento_id DESC
                   ) AS rn
            FROM eventos ev
            JOIN empresas e ON ev.cnpj = e.cnpj
            WHERE {where_sql}
        )
        SELECT u.pessoa_id, u.cnpj, p.tipo, u.plano
        FROM ultimo u
        JOIN pessoas p ON u.pessoa_id = p.pessoa_id
        WHERE u.rn = 1 AND u.tipo_evento != 'saida'
        """,
        params,
    ).fetchall()
    return [EstadoDia(*r) for r in rows]


def linha_do_tempo_diaria(
    conn: sqlite3.Connection,
    cliente: str,
    dias: Iterable[str],
    conhecido_ate: str,
    ignorar_anulados: bool = True,
) -> dict[str, list[EstadoDia]]:
    """Reconstrói os ativos dia a dia pela `data_informada` (eixo realidade).

    Premissas:
    - Considera apenas eventos já conhecidos pelo sistema até `conhecido_ate`.
    - Saída vale a partir da `data_informada` (no dia da saída, a pessoa já está inativa).
    """
    dias_lista = sorted(dias)
    if not dias_lista:
        return {}

    anulados = obter_eventos_anulados(conn) if ignorar_anulados else set()

    rows = conn.execute(
        """
        SELECT ev.evento_id, ev.pessoa_id, ev.cnpj, ev.tipo_evento, ev.plano,
               ev.data_processamento, ev.data_informada, p.tipo
        FROM eventos ev
        JOIN empresas e ON ev.cnpj = e.cnpj
        JOIN pessoas p ON ev.pessoa_id = p.pessoa_id
        WHERE e.cliente = ?
          AND ev.data_processamento <= ?
        ORDER BY ev.data_informada ASC, ev.data_processamento ASC, ev.evento_id ASC
        """,
        (cliente, conhecido_ate),
    ).fetchall()

    por_vinculo: dict[tuple[str, str], list[tuple]] = {}
    for ev in rows:
        if ev[0] in anulados:
            continue
        chave = (ev[1], ev[2])
        por_vinculo.setdefault(chave, []).append(ev)

    resultado: dict[str, list[EstadoDia]] = {d: [] for d in dias_lista}

    for (pessoa_id, cnpj), evs in por_vinculo.items():
        tipo_pessoa = evs[0][7]
        idx = 0
        n = len(evs)
        ativo = False
        plano = ""

        for dia in dias_lista:
            while idx < n and evs[idx][6] <= dia:
                tipo_ev = evs[idx][3]
                if tipo_ev == "saida":
                    ativo = False
                else:
                    ativo = True
                    plano = evs[idx][4]
                idx += 1

            if ativo:
                resultado[dia].append(
                    EstadoDia(
                        pessoa_id=pessoa_id,
                        cnpj=cnpj,
                        tipo_pessoa=tipo_pessoa,
                        plano=plano,
                    )
                )

    return resultado
