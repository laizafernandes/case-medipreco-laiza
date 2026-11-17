"""Testes da Etapa 4: tabela Emitido x Contrato e diferenças pessoa a pessoa."""

from __future__ import annotations

import sqlite3
import unittest
from pathlib import Path

from medipreco.comparacao import (
    comparar_emitido_vs_contrato,
    listar_diferencas_corte_dia_26,
)

DB_PATH = Path(__file__).resolve().parent / "fixtures/base.sqlite"


class TestComparacaoEtapa4(unittest.TestCase):
    def setUp(self) -> None:
        self.conn = sqlite3.connect(DB_PATH)

    def tearDown(self) -> None:
        self.conn.close()

    def test_tabela_referencia_calculado_menos_emitido_12_11(self) -> None:
        """Valida todas as diferenças calculado(12/11) - emitido contra a tabela de referência."""
        linhas = comparar_emitido_vs_contrato(self.conn)
        mapa = {(l.cliente, l.competencia): l for l in linhas}

        esperado_final = {
            ("Aurora Logística", "2026-08"): -7.50,
            ("Aurora Logística", "2026-09"): 15.00,
            ("Aurora Logística", "2026-10"): -160.50,
            ("Bravo Tecnologia", "2026-08"): 0.00,
            ("Bravo Tecnologia", "2026-09"): -2475.00,
            ("Bravo Tecnologia", "2026-10"): -15.00,
            ("Delta Benefícios", "2026-08"): 2061.00,
            ("Delta Benefícios", "2026-09"): -3456.00,
            ("Delta Benefícios", "2026-10"): -3488.00,
            ("Estrela Indústria", "2026-08"): -9.50,
            ("Estrela Indústria", "2026-09"): 38.00,
            ("Estrela Indústria", "2026-10"): -95.00,
            ("Faro Serviços", "2026-08"): -13.13,
            ("Faro Serviços", "2026-09"): -2.93,
            ("Faro Serviços", "2026-10"): -1.42,
            ("Grupo Cedro", "2026-08"): 232.00,
            ("Grupo Cedro", "2026-09"): 16.00,
            ("Grupo Cedro", "2026-10"): 120.00,
        }
        for chave, diff_esp in esperado_final.items():
            self.assertAlmostEqual(mapa[chave].diff_final, diff_esp, places=2, msg=chave)

        # Bravo set/2026 na emissão (333 titulares = 4995) vs 499 cobrados (7485) -> -2490
        self.assertAlmostEqual(mapa[("Bravo Tecnologia", "2026-09")].diff_emissao, -2490.00, places=2)
        self.assertIn("unidade_errada", mapa[("Bravo Tecnologia", "2026-09")].causas)

        # Decomposição aditiva fecha no centavo para todas as 19 linhas
        for l in linhas:
            calc_emissao = round(
                l.valor_emitido + l.delta_unidade + l.delta_metodo + l.delta_relogio_emissao, 2
            )
            self.assertEqual(calc_emissao, l.valor_na_emissao, (l.cliente, l.competencia))
            calc_final = round(l.valor_na_emissao + l.delta_info_tardia, 2)
            self.assertEqual(calc_final, l.valor_conhecido_final, (l.cliente, l.competencia))

    def test_diferencas_pessoa_a_pessoa_aurora_e_estrela_outubro(self) -> None:
        """Aurora out/2026: 16 pessoas saíram até 26/10 e só chegaram em 27/10; Estrela: 32 saídas tardias."""
        diffs_aurora = listar_diferencas_corte_dia_26(
            self.conn, "Aurora Logística", "2026-10", "2026-11-03 23:59:59"
        )
        self.assertEqual(len(diffs_aurora), 16)
        self.assertTrue(all(d.data_processamento_saida.startswith("2026-10-27") for d in diffs_aurora))

        diffs_estrela = listar_diferencas_corte_dia_26(
            self.conn, "Estrela Indústria", "2026-10", "2026-11-12 23:59:59"
        )
        # 39 saídas tardias (carga 05/11) compensadas por 7 entradas tardias -> saldo líquido -32 (510 -> 478)
        self.assertEqual(len(diffs_estrela), 39)
        self.assertTrue(any(d.data_processamento_saida.startswith("2026-11-05") for d in diffs_estrela))


if __name__ == "__main__":
    unittest.main()
