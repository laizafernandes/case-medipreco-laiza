"""Testes da Etapa 3: extrato auditável pessoa a pessoa fechando no centavo com a nota."""

from __future__ import annotations

import sqlite3
import unittest
from pathlib import Path

from medipreco.contratos import carregar_contratos
from medipreco.extrato import gerar_extratos_cliente

DB_PATH = Path(__file__).resolve().parent / "fixtures/base.sqlite"
CONHECIDO_FINAL = "2026-11-12 23:59:59"


class TestExtratoEtapa3(unittest.TestCase):
    def setUp(self) -> None:
        self.conn = sqlite3.connect(DB_PATH)
        self.contratos = carregar_contratos()

    def tearDown(self) -> None:
        self.conn.close()

    def test_soma_linhas_fecha_com_valor_da_nota_todos_clientes_e_meses(self) -> None:
        """Para os 6 clientes e 3 competências, soma(linha.valor) == valor_total_nota."""
        for cliente in self.contratos:
            for comp in ("2026-08", "2026-09", "2026-10"):
                extratos = gerar_extratos_cliente(
                    self.conn, cliente, comp, CONHECIDO_FINAL, self.contratos
                )
                self.assertGreaterEqual(len(extratos), 1)
                for ex in extratos:
                    soma_linhas = round(sum(l.valor for l in ex.linhas), 2)
                    self.assertEqual(
                        soma_linhas,
                        ex.valor_total_nota,
                        f"Divergência de centavos em {cliente} {comp} {ex.cnpj_tomador}",
                    )
                    self.assertEqual(ex.conhecido_ate, CONHECIDO_FINAL)
                    for l in ex.linhas:
                        self.assertTrue(l.pessoa_id)
                        self.assertTrue(l.regra_contrato)
                        self.assertEqual(l.conhecido_ate, CONHECIDO_FINAL)

    def test_estrela_outubro_inclui_linha_complemento_minimo(self) -> None:
        """Quando Estrela cai para 478 vidas (<500), extrato tem 478 pessoas + 1 linha de complemento."""
        extratos = gerar_extratos_cliente(
            self.conn, "Estrela Indústria", "2026-10", CONHECIDO_FINAL, self.contratos
        )
        ex = extratos[0]
        self.assertEqual(len(ex.linhas), 479)
        comp = ex.linhas[-1]
        self.assertEqual(comp.pessoa_id, "COMPLEMENTO_MINIMO")
        self.assertAlmostEqual(comp.valor, 22 * 9.50, places=2)
        self.assertEqual(round(sum(l.valor for l in ex.linhas), 2), 4750.0)

    def test_checagem_independente_sql_faro_outubro_e_isolamento_lgpd(self) -> None:
        """Recalcula Faro out/2026 por SQL recursiva independente e valida isolamento de cliente (LGPD)."""
        dias_ativos_sql = self.conn.execute(
            """
            WITH RECURSIVE datas(d) AS (
                SELECT date('2026-10-01')
                UNION ALL
                SELECT date(d, '+1 day') FROM datas WHERE d < '2026-10-31'
            ),
            ativos AS (
                SELECT d, ev.pessoa_id,
                       (SELECT ev2.tipo_evento FROM eventos ev2
                        WHERE ev2.pessoa_id = ev.pessoa_id AND ev2.cnpj = ev.cnpj
                          AND ev2.data_informada <= d AND ev2.data_processamento <= '2026-11-12 23:59:59'
                        ORDER BY ev2.data_informada DESC, ev2.data_processamento DESC, ev2.evento_id DESC
                        LIMIT 1) AS st
                FROM datas
                CROSS JOIN (
                    SELECT DISTINCT ev.pessoa_id, ev.cnpj
                    FROM eventos ev JOIN empresas e ON ev.cnpj = e.cnpj
                    WHERE e.cliente = 'Faro Serviços'
                ) ev
            )
            SELECT COUNT(*) FROM ativos WHERE st != 'saida'
            """
        ).fetchone()[0]
        total_sql = round((dias_ativos_sql / 31) * 11.0, 2)

        ex = gerar_extratos_cliente(
            self.conn, "Faro Serviços", "2026-10", CONHECIDO_FINAL, self.contratos
        )[0]
        self.assertEqual(ex.valor_total_nota, total_sql)
        self.assertEqual(round(sum(l.valor for l in ex.linhas), 2), total_sql)
        self.assertTrue(all(l.cnpj == "71.403.268/0001-22" for l in ex.linhas))


if __name__ == "__main__":
    unittest.main()
