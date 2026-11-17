"""CLI em 1 comando para o motor de fechamento Medipreço.

Exemplos:
  python -m medipreco fechar --cliente "Grupo Cedro" --competencia 2026-10 --conhecido-ate 2026-11-03
  python -m medipreco tudo
"""

from __future__ import annotations

import argparse
import csv
import re
import sqlite3
from pathlib import Path

from medipreco.comparacao import CONHECIDO_FINAL, comparar_emitido_vs_contrato
from medipreco.contratos import carregar_contratos
from medipreco.explicador import explicar_extrato
from medipreco.extrato import ExtratoNota, gerar_extratos_cliente
from medipreco.formatacao import formatar_brl
from medipreco.validacoes import (
    AlertaValidacao,
    validar_cargas_atipicas_quarentena,
    validar_desligamentos_fora_sla,
    validar_minimo_acionado,
    validar_proximidade_limite_faixa,
    validar_soma_extrato_independente,
    validar_unidade_titular_vs_vidas,
    validar_variacao_vs_mes_anterior,
)


def _normalizar_corte(data_ou_ts: str) -> str:
    return data_ou_ts if len(data_ou_ts) > 10 else f"{data_ou_ts} 23:59:59"


def _slug(texto: str) -> str:
    limpo = re.sub(r"[^a-zA-Z0-9]+", "_", texto).strip("_").lower()
    return limpo


def _salvar_extrato_csv(extrato: ExtratoNota, pasta_extratos: Path) -> Path:
    pasta_extratos.mkdir(parents=True, exist_ok=True)
    cnpj_limpo = re.sub(r"\D", "", extrato.cnpj_tomador)
    arquivo = pasta_extratos / f"{_slug(extrato.cliente)}_{extrato.competencia}_{cnpj_limpo}.csv"
    with arquivo.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(
            [
                "cliente",
                "competencia",
                "cnpj_tomador",
                "pessoa_id",
                "cnpj_vinculo",
                "tipo_pessoa",
                "dias_ativos",
                "plano",
                "valor",
                "regra_contrato",
                "conhecido_ate",
            ]
        )
        for l in extrato.linhas:
            w.writerow(
                [
                    extrato.cliente,
                    extrato.competencia,
                    extrato.cnpj_tomador,
                    l.pessoa_id,
                    l.cnpj,
                    l.tipo_pessoa,
                    l.dias_ativos,
                    l.plano,
                    f"{l.valor:.2f}",
                    l.regra_contrato,
                    l.conhecido_ate,
                ]
            )
    return arquivo


def _rodar_alertas_cliente(
    conn: sqlite3.Connection,
    cliente: str,
    competencia: str,
    extratos: list[ExtratoNota],
    valor_anterior: float | None,
    corte_ts: str,
    contratos: dict,
) -> list[AlertaValidacao]:
    alertas: list[AlertaValidacao] = []
    valor_total = round(sum(ex.valor_total_nota for ex in extratos), 2)
    qtd_total = sum(sum(it.quantidade for it in ex.itens) for ex in extratos)

    a1 = validar_unidade_titular_vs_vidas(
        conn, cliente, competencia, qtd_total, corte_ts, contratos
    )
    if a1:
        alertas.append(a1)
    a2 = validar_variacao_vs_mes_anterior(cliente, competencia, valor_total, valor_anterior)
    if a2:
        alertas.append(a2)
    a3 = validar_proximidade_limite_faixa(cliente, competencia, qtd_total, contratos)
    if a3:
        alertas.append(a3)
    for ex in extratos:
        a4 = validar_minimo_acionado(cliente, competencia, ex)
        if a4:
            alertas.append(a4)
        a7 = validar_soma_extrato_independente(ex)
        if a7:
            alertas.append(a7)
    alertas.extend(validar_cargas_atipicas_quarentena(conn, cliente, competencia))
    a6 = validar_desligamentos_fora_sla(conn, cliente, competencia)
    if a6:
        alertas.append(a6)
    return alertas


def _abrir_db(caminho: str) -> sqlite3.Connection | None:
    db_path = Path(caminho)
    if not db_path.exists():
        print(
            f"Erro: banco de dados não encontrado em '{db_path}'. "
            "Coloque o arquivo base.sqlite em data/base.sqlite ou informe --db <caminho>."
        )
        return None
    return sqlite3.connect(db_path)


def cmd_fechar(args: argparse.Namespace) -> int:
    conn = _abrir_db(args.db)
    if conn is None:
        return 1
    contratos = carregar_contratos()
    if args.cliente not in contratos:
        print(f"Cliente desconhecido: {args.cliente}. Opções: {list(contratos.keys())}")
        conn.close()
        return 1

    corte = _normalizar_corte(args.conhecido_ate)
    extratos = gerar_extratos_cliente(conn, args.cliente, args.competencia, corte, contratos)
    pasta_saida = Path(args.saida)
    pasta_extratos = pasta_saida / "extratos"

    print(f"=== Fechamento: {args.cliente} | {args.competencia} | conhecido até {corte} ===")
    total_geral = 0.0
    for ex in extratos:
        arq = _salvar_extrato_csv(ex, pasta_extratos)
        total_geral = round(total_geral + ex.valor_total_nota, 2)
        print(f"- Tomador {ex.cnpj_tomador}: {formatar_brl(ex.valor_total_nota)} ({len(ex.linhas)} linhas) -> {arq}")
        for it in ex.itens:
            print(f"  * {it.descricao}: {it.quantidade} × {formatar_brl(it.valor_unitario)} = {formatar_brl(it.valor_total)}")

    alertas = _rodar_alertas_cliente(conn, args.cliente, args.competencia, extratos, None, corte, contratos)
    if alertas:
        print("\nAlertas pré-emissão:")
        for al in alertas:
            print(f"  [{al.severidade.upper()}] {al.codigo}: {al.mensagem}")
    else:
        print("\nAlertas pré-emissão: nenhum.")

    explicacao = explicar_extrato(
        {
            "cliente": args.cliente,
            "competencia": args.competencia,
            "valor_total": total_geral,
            "conhecido_ate": corte,
        }
    )
    print(f"\nResumo: {explicacao.texto}")
    conn.close()
    return 0


def cmd_tudo(args: argparse.Namespace) -> int:
    conn = _abrir_db(args.db)
    if conn is None:
        return 1
    contratos = carregar_contratos()
    corte = _normalizar_corte(args.conhecido_ate)
    pasta_saida = Path(args.saida)
    pasta_saida.mkdir(parents=True, exist_ok=True)
    pasta_extratos = pasta_saida / "extratos"

    # 1) Comparação Emitido × Contrato + Decomposição
    linhas_comp = comparar_emitido_vs_contrato(conn, contratos, corte)
    arq_comp = pasta_saida / "comparacao_emitido_x_contrato.csv"
    with arq_comp.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(
            [
                "cliente",
                "competencia",
                "data_emissao",
                "valor_emitido",
                "delta_unidade",
                "delta_metodo",
                "delta_relogio_emissao",
                "valor_na_emissao",
                "delta_info_tardia",
                "delta_faixa_degrau",
                "valor_conhecido_final",
                "diff_emissao",
                "diff_final",
                "erro_pct",
                "causas",
                "observacao",
            ]
        )
        for l in linhas_comp:
            w.writerow(
                [
                    l.cliente,
                    l.competencia,
                    l.data_emissao,
                    f"{l.valor_emitido:.2f}",
                    f"{l.delta_unidade:.2f}",
                    f"{l.delta_metodo:.2f}",
                    f"{l.delta_relogio_emissao:.2f}",
                    f"{l.valor_na_emissao:.2f}",
                    f"{l.delta_info_tardia:.2f}",
                    f"{l.delta_faixa_degrau:.2f}",
                    f"{l.valor_conhecido_final:.2f}",
                    f"{l.diff_emissao:.2f}",
                    f"{l.diff_final:.2f}",
                    f"{l.erro_pct:.2f}",
                    ";".join(l.causas),
                    l.observacao,
                ]
            )

    # 2) Extratos CSV para todas as competências emitidas (guiado por notas_emitidas + config)
    qtd_extratos = 0
    valor_anterior_por_cliente: dict[str, float] = {}
    pares_emitidos = conn.execute(
        """
        SELECT DISTINCT cliente, competencia
        FROM notas_emitidas
        ORDER BY competencia, cliente
        """
    ).fetchall()
    for cliente, comp in pares_emitidos:
        if cliente not in contratos:
            continue
        extratos = gerar_extratos_cliente(conn, cliente, comp, corte, contratos)
        for ex in extratos:
            _salvar_extrato_csv(ex, pasta_extratos)
            qtd_extratos += 1

    # 3) Matriz de alertas das 28 linhas de notas_emitidas
    notas_28 = conn.execute(
        """
        SELECT nota_id, cliente, cnpj_tomador, competencia, contagem_em,
               item, quantidade, valor_item
        FROM notas_emitidas
        ORDER BY competencia, nota_id, item
        """
    ).fetchall()

    arq_matriz = pasta_saida / "matriz_alertas_28_notas.csv"
    with arq_matriz.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(
            [
                "nota_id",
                "cliente",
                "competencia",
                "item",
                "qtd_avaliada",
                "valor_nota",
                "alertas_bloqueio",
                "alertas_aviso",
                "detalhe",
            ]
        )
        for nota_id, cliente, cnpj_tom, comp, contagem_em, item, qtd_nota, val_nota in notas_28:
            extratos = gerar_extratos_cliente(conn, cliente, comp, corte, contratos)
            chave_ant = f"{cliente}|{cnpj_tom}|{item}"
            valor_ant = valor_anterior_por_cliente.get(chave_ant)
            alertas: list[AlertaValidacao] = []
            al_un = validar_unidade_titular_vs_vidas(
                conn, cliente, comp, qtd_nota, contagem_em, contratos
            )
            if al_un:
                alertas.append(al_un)
            al_var = validar_variacao_vs_mes_anterior(cliente, comp, val_nota, valor_ant)
            if al_var:
                alertas.append(al_var)
            al_fx = validar_proximidade_limite_faixa(cliente, comp, qtd_nota, contratos)
            if al_fx:
                alertas.append(al_fx)
            for ex in extratos:
                al_min = validar_minimo_acionado(cliente, comp, ex)
                if al_min:
                    alertas.append(al_min)
                al_sum = validar_soma_extrato_independente(ex)
                if al_sum:
                    alertas.append(al_sum)
            alertas.extend(validar_cargas_atipicas_quarentena(conn, cliente, comp))
            al_sla = validar_desligamentos_fora_sla(conn, cliente, comp)
            if al_sla:
                alertas.append(al_sla)

            valor_anterior_por_cliente[chave_ant] = val_nota

            bloqueios = [a.codigo for a in alertas if a.severidade == "bloqueio"]
            avisos = [a.codigo for a in alertas if a.severidade == "aviso"]
            detalhe = " | ".join(a.mensagem for a in alertas)
            w.writerow(
                [
                    nota_id,
                    cliente,
                    comp,
                    item,
                    qtd_nota,
                    f"{val_nota:.2f}",
                    ";".join(dict.fromkeys(bloqueios)),
                    ";".join(dict.fromkeys(avisos)),
                    detalhe,
                ]
            )

    print(f"Concluído! Arquivos gerados em '{pasta_saida}/':")
    print(f"- {arq_comp} ({len(linhas_comp)} competências)")
    print(f"- {arq_matriz} ({len(notas_28)} itens de nota)")
    print(f"- {pasta_extratos}/ ({qtd_extratos} extratos CSV)")
    conn.close()
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(prog="medipreco", description="Motor de fechamento Medipreço")
    sub = parser.add_subparsers(dest="comando", required=True)

    p_fechar = sub.add_parser("fechar", help="Fecha um cliente e competência")
    p_fechar.add_argument("--cliente", required=True)
    p_fechar.add_argument("--competencia", required=True)
    p_fechar.add_argument("--conhecido-ate", default=CONHECIDO_FINAL)
    p_fechar.add_argument("--db", default="data/base.sqlite")
    p_fechar.add_argument("--saida", default="saida")
    p_fechar.set_defaults(func=cmd_fechar)

    p_tudo = sub.add_parser("tudo", help="Gera comparação, matriz de alertas das 28 notas e extratos")
    p_tudo.add_argument("--conhecido-ate", default=CONHECIDO_FINAL)
    p_tudo.add_argument("--db", default="data/base.sqlite")
    p_tudo.add_argument("--saida", default="saida")
    p_tudo.set_defaults(func=cmd_tudo)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
