"""Testes da Etapa 2: contratos, compensação pré-pago, todas as competências e casos de borda."""

from __future__ import annotations

import sqlite3
import unittest
from pathlib import Path

from medipreco.contratos import (
    _preco_por_faixa,
    apurar_compensacao_pre_pago,
    apurar_competencia,
    carregar_contratos,
)
from medipreco.timeline import estado_na_foto_sistema

DB_PATH = Path(__file__).resolve().parent.parent / "data/base.sqlite"
CONHECIDO_FINAL = "2026-11-12 23:59:59"


class TestContratosEtapa2(unittest.TestCase):
    def setUp(self) -> None:
        self.conn = sqlite3.connect(DB_PATH)

    def tearDown(self) -> None:
        self.conn.close()

    def test_bravo_setembro_foto_332_emissao_333_final_334_e_compensacao(self) -> None:
        """Bravo set/2026: foto 26/08=332 (vs 499 cobrado), regra nova na emissão 27/08=333, em 12/11=334 (+R$ 15)."""
        foto_332 = estado_na_foto_sistema(
            self.conn, "2026-08-26 09:00:00", cliente="Bravo Tecnologia"
        )
        self.assertEqual(sum(1 for e in foto_332 if e.tipo_pessoa == "titular"), 332)

        itens_emissao = apurar_competencia(
            self.conn, "Bravo Tecnologia", "2026-09", "2026-08-27 23:59:59"
        )
        self.assertEqual(itens_emissao[0].quantidade, 333)
        self.assertEqual(itens_emissao[0].valor_total, 4995.0)

        itens_final = apurar_competencia(
            self.conn, "Bravo Tecnologia", "2026-09", CONHECIDO_FINAL
        )
        self.assertEqual(itens_final[0].quantidade, 334)

        # Compensação da Cláusula 4.4 para set/2026 (cobrado na prévia=333; efetivo em 26/09)
        comp = apurar_compensacao_pre_pago(
            self.conn, "Bravo Tecnologia", "2026-09", 333, CONHECIDO_FINAL
        )
        self.assertEqual(comp.detalhe["efetivos_no_mes"], 336)
        self.assertEqual(comp.quantidade, 3)
        self.assertEqual(comp.valor_total, 45.0)

    def test_todas_competencias_ago_set_out_tabela_referencia(self) -> None:
        """Valida Ago, Set e Out/2026 para os 6 clientes com conhecimento até 12/11."""
        # Aurora (Base/Plus): 697/177, 703/177, 541/180
        esperado_aurora = {"2026-08": (697, 177), "2026-09": (703, 177), "2026-10": (541, 180)}
        for m, (base, plus) in esperado_aurora.items():
            its = apurar_competencia(self.conn, "Aurora Logística", m, CONHECIDO_FINAL)
            self.assertEqual((its[0].quantidade, its[1].quantidade), (base, plus), m)

        # Bravo (titulares em 26/mês anterior): 321, 334, 336
        esperado_bravo = {"2026-08": 321, "2026-09": 334, "2026-10": 336}
        for m, qtd in esperado_bravo.items():
            its = apurar_competencia(self.conn, "Bravo Tecnologia", m, CONHECIDO_FINAL)
            self.assertEqual(its[0].quantidade, qtd, m)

        # Delta (>= 1 dia; faixa R$ 9): 5280, 5106, 5048
        esperado_delta = {"2026-08": 5280, "2026-09": 5106, "2026-10": 5048}
        for m, qtd in esperado_delta.items():
            its = apurar_competencia(self.conn, "Delta Benefícios", m, CONHECIDO_FINAL)
            self.assertEqual(its[0].quantidade, qtd, m)
            self.assertEqual(its[0].valor_unitario, 9.0, m)

        # Estrela (vidas reais; mínimo 500): 502, 513, 478 (faturado 500)
        esperado_estrela = {"2026-08": (502, 502), "2026-09": (513, 513), "2026-10": (478, 500)}
        for m, (real, fat) in esperado_estrela.items():
            its = apurar_competencia(self.conn, "Estrela Indústria", m, CONHECIDO_FINAL)
            self.assertEqual(its[0].detalhe["quantidade_real"], real, m)
            self.assertEqual(its[0].quantidade, fat, m)

        # Faro (R$): 2912.87, 2835.07, 2869.58
        esperado_faro = {"2026-08": 2912.87, "2026-09": 2835.07, "2026-10": 2869.58}
        for m, val in esperado_faro.items():
            its = apurar_competencia(self.conn, "Faro Serviços", m, CONHECIDO_FINAL)
            self.assertAlmostEqual(its[0].valor_total, val, places=2, msg=m)

        # Grupo Cedro (pico + rateio exato em centavos): 997, 963, 961
        esperado_cedro = {"2026-08": 997, "2026-09": 963, "2026-10": 961}
        for m, pico in esperado_cedro.items():
            its = apurar_competencia(self.conn, "Grupo Cedro", m, CONHECIDO_FINAL)
            self.assertEqual(len(its), 3, m)
            self.assertEqual(sum(i.quantidade for i in its), pico, m)
            self.assertAlmostEqual(sum(i.valor_total for i in its), pico * 8.0, places=2, msg=m)

    def test_delta_limites_de_faixa(self) -> None:
        """Testa limites exatos da tabela escalonada (degrau total): 5000->10, 5001->9, 10000->9, 10001->8."""
        faixas = carregar_contratos()["Delta Benefícios"]["faixas"]
        self.assertEqual(_preco_por_faixa(faixas, 5000), 10.0)
        self.assertEqual(_preco_por_faixa(faixas, 5001), 9.0)
        self.assertEqual(_preco_por_faixa(faixas, 10000), 9.0)
        self.assertEqual(_preco_por_faixa(faixas, 10001), 8.0)

    def test_faro_divisor_28_e_30_dias(self) -> None:
        """Testa pró-rata da Faro com mês de 28 dias (fev/2026 sintético) e 30 dias (set/2026 real)."""
        its_30 = apurar_competencia(self.conn, "Faro Serviços", "2026-09", CONHECIDO_FINAL)
        self.assertEqual(its_30[0].detalhe["dias_mes"], 30)

        mem = sqlite3.connect(":memory:")
        mem.executescript(
            """
            CREATE TABLE empresas (cnpj TEXT, razao_social TEXT, cliente TEXT);
            CREATE TABLE pessoas (pessoa_id TEXT, tipo TEXT, titular_id TEXT);
            CREATE TABLE eventos (
                evento_id INTEGER, pessoa_id TEXT, cnpj TEXT,
                tipo_evento TEXT, plano TEXT,
                data_processamento TEXT, data_informada TEXT, origem TEXT
            );
            INSERT INTO empresas VALUES ('71.403.268/0001-22', 'Faro', 'Faro Serviços');
            INSERT INTO pessoas VALUES ('P1', 'titular', NULL);
            INSERT INTO eventos VALUES (1, 'P1', '71.403.268/0001-22', 'entrada', 'Padrão', '2026-02-01 09:00:00', '2026-02-01', 'portal_rh');
            INSERT INTO eventos VALUES (2, 'P1', '71.403.268/0001-22', 'saida', 'Padrão', '2026-02-15 09:00:00', '2026-02-15', 'portal_rh');
            """
        )
        its_28 = apurar_competencia(mem, "Faro Serviços", "2026-02", "2026-03-01 23:59:59")
        self.assertEqual(its_28[0].detalhe["dias_mes"], 28)
        self.assertEqual(its_28[0].detalhe["dias_ativos_total"], 14)
        self.assertAlmostEqual(its_28[0].valor_total, 5.50, places=2)
        mem.close()


if __name__ == "__main__":
    unittest.main()
