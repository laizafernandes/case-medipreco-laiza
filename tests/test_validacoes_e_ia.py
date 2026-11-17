"""Testes da Etapa 5: validações pré-emissão e peça única de IA com guardrail."""

from __future__ import annotations

from argparse import Namespace
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from medipreco.__main__ import cmd_fechar
from medipreco.contratos import carregar_contratos
from medipreco.explicador import explicar_extrato, validar_cifras_no_texto
from medipreco.extrato import gerar_extratos_cliente
from medipreco.validacoes import (
    validar_cargas_atipicas_quarentena,
    validar_desligamentos_fora_sla,
    validar_minimo_acionado,
    validar_proximidade_limite_faixa,
    validar_soma_extrato_independente,
    validar_unidade_titular_vs_vidas,
    validar_variacao_vs_mes_anterior,
)

DB_PATH = Path(__file__).resolve().parent / "fixtures/base.sqlite"
CONHECIDO_FINAL = "2026-11-12 23:59:59"


class TestValidacoesEtapa5(unittest.TestCase):
    def setUp(self) -> None:
        self.conn = sqlite3.connect(DB_PATH)
        self.contratos = carregar_contratos()

    def tearDown(self) -> None:
        self.conn.close()

    def test_bravo_setembro_bloqueado_por_unidade_e_variacao(self) -> None:
        alerta_un = validar_unidade_titular_vs_vidas(
            self.conn, "Bravo Tecnologia", "2026-09", 499, "2026-08-26 09:00:00", self.contratos
        )
        self.assertIsNotNone(alerta_un)
        self.assertEqual(alerta_un.severidade, "bloqueio")

        alerta_var = validar_variacao_vs_mes_anterior("Bravo Tecnologia", "2026-09", 7485.0, 4815.0)
        self.assertIsNotNone(alerta_var)
        self.assertEqual(alerta_var.codigo, "VARIACAO_MAIOR_10_PCT")

    def test_delta_quarentena_07_10_e_proximidade_faixa(self) -> None:
        quarentena = validar_cargas_atipicas_quarentena(self.conn, "Delta Benefícios", "2026-10")
        self.assertTrue(any(a.detalhes["dia_processamento"] == "2026-10-07" for a in quarentena))

        antes_da_carga = validar_cargas_atipicas_quarentena(
            self.conn,
            "Delta Benefícios",
            "2026-10",
            conhecido_ate="2026-10-06 23:59:59",
        )
        self.assertFalse(any(a.detalhes["dia_processamento"] == "2026-10-07" for a in antes_da_carga))

        alerta_fx = validar_proximidade_limite_faixa("Delta Benefícios", "2026-10", 5048, self.contratos)
        self.assertIsNotNone(alerta_fx)
        self.assertEqual(alerta_fx.detalhes["limite"], 5000)

    def test_estrela_minimo_acionado_e_desligamentos_fora_sla(self) -> None:
        extratos = gerar_extratos_cliente(
            self.conn, "Estrela Indústria", "2026-10", CONHECIDO_FINAL, self.contratos
        )
        alerta_min = validar_minimo_acionado("Estrela Indústria", "2026-10", extratos[0])
        self.assertIsNotNone(alerta_min)
        self.assertEqual(alerta_min.detalhes["real"], 478)

        alerta_sla = validar_desligamentos_fora_sla(
            self.conn,
            "Estrela Indústria",
            "2026-10",
            conhecido_ate="2026-11-05 23:59:59",
        )
        self.assertIsNotNone(alerta_sla)
        self.assertGreater(alerta_sla.detalhes["fora_sla"], 0)

        alerta_sla_na_emissao = validar_desligamentos_fora_sla(
            self.conn,
            "Estrela Indústria",
            "2026-10",
            conhecido_ate="2026-11-03 23:59:59",
        )
        self.assertIsNone(alerta_sla_na_emissao)

        self.assertIsNone(validar_soma_extrato_independente(extratos[0]))

    def test_fechar_usa_corte_de_conhecimento_e_nota_anterior(self) -> None:
        with TemporaryDirectory() as saida:
            args = Namespace(
                cliente="Bravo Tecnologia",
                competencia="2026-10",
                conhecido_ate="2026-11-12",
                db=str(DB_PATH),
                saida=saida,
            )
            texto = StringIO()
            with patch(
                "medipreco.__main__.explicar_extrato",
                return_value=SimpleNamespace(texto="ok"),
            ), redirect_stdout(texto):
                self.assertEqual(cmd_fechar(args), 0)
            self.assertIn("VARIACAO_MAIOR_10_PCT", texto.getvalue())

        with TemporaryDirectory() as saida:
            args = Namespace(
                cliente="Estrela Indústria",
                competencia="2026-10",
                conhecido_ate="2026-11-03",
                db=str(DB_PATH),
                saida=saida,
            )
            texto = StringIO()
            with patch(
                "medipreco.__main__.explicar_extrato",
                return_value=SimpleNamespace(texto="ok"),
            ), redirect_stdout(texto):
                self.assertEqual(cmd_fechar(args), 0)
            self.assertNotIn("DESLIGAMENTO_FORA_SLA", texto.getvalue())


class TestExplicadorIAEtapa5(unittest.TestCase):
    def test_aurora_outubro_718_vs_737_sem_ia_e_guardrail(self) -> None:
        dados = {
            "cenario": "aurora_corte_vs_rh",
            "cliente": "Aurora Logística",
            "competencia": "2026-10",
            "data_corte": "2026-10-26",
            "qtd_foto": 737,
            "valor_foto": 6378.00,
            "data_carga_tardia": "2026-10-27",
            "qtd_saidas_tardias_ate_corte": 16,
            "qtd_realidade_corte": 721,
            "qtd_sistema_fim_mes": 718,
            "diferenca_reais": -160.50,
        }
        res = explicar_extrato(dados, gerador_ia=lambda _: None)
        self.assertFalse(res.usou_ia)
        self.assertIn("737", res.texto)
        self.assertIn("718", res.texto)
        self.assertIn("721", res.texto)
        self.assertTrue(validar_cifras_no_texto(res.texto, dados))

        # Simula IA alucinando um número que não está nos dados (ex: 999)
        res_aluc = explicar_extrato(dados, gerador_ia=lambda _: "Foram cobradas 999 vidas extras.")
        self.assertTrue(res_aluc.descartado_por_alucinacao)
        self.assertFalse(res_aluc.usou_ia)
        self.assertNotIn("999", res_aluc.texto)

    def test_estrela_outubro_credito_95(self) -> None:
        dados = {
            "cenario": "estrela_minimo_credito",
            "cliente": "Estrela Indústria",
            "competencia": "2026-10",
            "dia_corte": 26,
            "qtd_emitida": 510,
            "valor_emitido": 4845.00,
            "qtd_real": 478,
            "minimo_vidas": 500,
            "valor_devido": 4750.00,
            "credito_reais": 95.00,
        }
        res = explicar_extrato(dados, gerador_ia=lambda _: None)
        self.assertIn("R$ 4.750,00", res.texto)
        self.assertIn("R$ 95,00", res.texto)
        self.assertIn("478", res.texto)
        self.assertIn("500", res.texto)

    def test_fallback_formata_valor_em_brl_com_separador_de_milhar(self) -> None:
        dados = {"cliente": "Grupo Cedro", "competencia": "2026-10", "valor_total": 7688.00}
        res = explicar_extrato(dados, gerador_ia=lambda _: None)
        self.assertIn("R$ 7.688,00", res.texto)

    def test_bravo_setembro_499_vs_332(self) -> None:
        dados = {
            "cenario": "bravo_unidade_errada",
            "cliente": "Bravo Tecnologia",
            "competencia": "2026-09",
            "valor_unitario": 15.00,
            "qtd_cobrada": 499,
            "valor_cobrado": 7485.00,
            "qtd_titulares_foto": 332,
            "valor_foto": 4980.00,
            "erro_foto_reais": 2505.00,
        }
        res = explicar_extrato(dados, gerador_ia=lambda _: None)
        self.assertIn("499", res.texto)
        self.assertIn("332", res.texto)
        self.assertIn("R$ 2.505,00", res.texto)


if __name__ == "__main__":
    unittest.main()
