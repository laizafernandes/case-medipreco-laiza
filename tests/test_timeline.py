"""Testes obrigatórios da Etapa 1: reconciliação com `vinculos`,
reprodução de 27/28 itens de `notas_emitidas` e checagem dos fatos do histórico.
"""

from __future__ import annotations

import sqlite3
import unittest
from pathlib import Path

from medipreco.timeline import (
    estado_na_foto_sistema,
    linha_do_tempo_diaria,
    listar_dias_mes,
    obter_eventos_anulados,
)

DB_PATH = Path(__file__).resolve().parent.parent / "data/base.sqlite"


class TestTimelineEtapa1(unittest.TestCase):
    def setUp(self) -> None:
        self.conn = sqlite3.connect(DB_PATH)

    def tearDown(self) -> None:
        self.conn.close()

    def test_reconciliacao_com_vinculos(self) -> None:
        """A foto reconstruída de `eventos` até o fim da base deve bater 100% com `vinculos`."""
        ativos_vinculos = {
            (r[0], r[1]): r[2]
            for r in self.conn.execute(
                "SELECT pessoa_id, cnpj, plano FROM vinculos WHERE ativo = 1"
            ).fetchall()
        }
        self.assertEqual(len(ativos_vinculos), 7793)

        ativos_eventos = {
            (e.pessoa_id, e.cnpj): e.plano
            for e in estado_na_foto_sistema(self.conn, "2026-11-12 23:59:59")
        }
        self.assertEqual(ativos_eventos, ativos_vinculos)

    def test_reproduz_27_de_28_itens_notas_emitidas(self) -> None:
        """A foto do sistema em `contagem_em` reproduz 27/28 itens; única exceção é Bravo set/2026."""
        notas = self.conn.execute(
            """
            SELECT nota_id, cliente, cnpj_tomador, competencia, contagem_em,
                   item, base_calculo, quantidade
            FROM notas_emitidas
            ORDER BY nota_id, item
            """
        ).fetchall()
        self.assertEqual(len(notas), 28)

        divergencias = []
        for nota_id, cliente, cnpj_tom, comp, contagem_em, item, base_calc, qtd in notas:
            if cliente == "Grupo Cedro":
                estados = estado_na_foto_sistema(
                    self.conn, contagem_em, cnpj=cnpj_tom
                )
            else:
                estados = estado_na_foto_sistema(
                    self.conn, contagem_em, cliente=cliente
                )

            if base_calc == "titulares":
                calc = sum(1 for e in estados if e.tipo_pessoa == "titular")
            elif "Base" in item:
                calc = sum(1 for e in estados if e.plano == "Base")
            elif "Plus" in item:
                calc = sum(1 for e in estados if e.plano == "Plus")
            else:
                calc = len(estados)

            if calc != qtd:
                divergencias.append((nota_id, cliente, comp, qtd, calc))

        self.assertEqual(
            divergencias,
            [("NF-01187", "Bravo Tecnologia", "2026-09", 499, 332)],
        )

    def test_aurora_737_vs_718_e_realidade_721(self) -> None:
        """Confirma o caso Aurora out/2026: foto 26/10=737, sistema 31/10=718, realidade 26/10=721."""
        foto_26 = estado_na_foto_sistema(
            self.conn, "2026-10-26 09:00:00", cliente="Aurora Logística"
        )
        self.assertEqual(len(foto_26), 737)

        foto_31 = estado_na_foto_sistema(
            self.conn, "2026-10-31 23:59:59", cliente="Aurora Logística"
        )
        self.assertEqual(len(foto_31), 718)

        tl = linha_do_tempo_diaria(
            self.conn,
            "Aurora Logística",
            ["2026-10-26"],
            conhecido_ate="2026-11-03 23:59:59",
        )
        self.assertEqual(len(tl["2026-10-26"]), 721)

    def test_delta_lote_anulado_600_eventos(self) -> None:
        """Confirma que o lote errado de 07/10 + suporte 09/10 soma 1.200 eventos anulados."""
        anulados = obter_eventos_anulados(self.conn)
        self.assertEqual(len(anulados), 1200)

    def test_estrela_realidade_outubro_abaixo_minimo(self) -> None:
        """Na emissão de 03/11 ainda havia 510; com os atrasos até 12/11, realidade de 26/10 cai para 478 (< 500)."""
        tl_emissao = linha_do_tempo_diaria(
            self.conn,
            "Estrela Indústria",
            ["2026-10-26"],
            conhecido_ate="2026-11-03 23:59:59",
        )
        self.assertEqual(len(tl_emissao["2026-10-26"]), 510)

        tl_pos = linha_do_tempo_diaria(
            self.conn,
            "Estrela Indústria",
            ["2026-10-26"],
            conhecido_ate="2026-11-12 23:59:59",
        )
        self.assertEqual(len(tl_pos["2026-10-26"]), 478)

    def test_cedro_pico_outubro_961(self) -> None:
        """Confirma que o pico simultâneo de pessoas distintas no Grupo Cedro em out/2026 foi 961."""
        dias = listar_dias_mes("2026-10")
        tl = linha_do_tempo_diaria(
            self.conn,
            "Grupo Cedro",
            dias,
            conhecido_ate="2026-11-03 23:59:59",
        )
        pico = max(len({e.pessoa_id for e in estados}) for estados in tl.values())
        self.assertEqual(pico, 961)

    def test_sensibilidade_premissa_saida_aurora(self) -> None:
        """Mede o impacto da convenção 'inativo a partir da data_informada': 721 vs 723 se valesse no dia seguinte."""
        # Na regra adotada (inativo no próprio dia da saída): 721
        tl = linha_do_tempo_diaria(
            self.conn,
            "Aurora Logística",
            ["2026-10-26"],
            conhecido_ate="2026-11-03 23:59:59",
        )
        self.assertEqual(len(tl["2026-10-26"]), 721)

        # Quantas saídas tinham data_informada == '2026-10-26' (diferença exata de 2 vidas)
        saidas_no_dia = self.conn.execute(
            """
            SELECT COUNT(*) FROM eventos ev
            JOIN empresas e ON ev.cnpj = e.cnpj
            WHERE e.cliente = 'Aurora Logística'
              AND ev.tipo_evento = 'saida'
              AND ev.data_informada = '2026-10-26'
              AND ev.data_processamento <= '2026-11-03 23:59:59'
            """
        ).fetchone()[0]
        self.assertEqual(saidas_no_dia, 2)


class TestTimelineComportamento(unittest.TestCase):
    """Testes unitários em banco em memória para casos de borda da linha do tempo."""

    def _criar_db(self, eventos: list[tuple]) -> sqlite3.Connection:
        conn = sqlite3.connect(":memory:")
        conn.executescript(
            """
            CREATE TABLE empresas (cnpj TEXT, razao_social TEXT, cliente TEXT);
            CREATE TABLE pessoas (pessoa_id TEXT, tipo TEXT, titular_id TEXT);
            CREATE TABLE eventos (
                evento_id INTEGER, pessoa_id TEXT, cnpj TEXT,
                tipo_evento TEXT, plano TEXT,
                data_processamento TEXT, data_informada TEXT, origem TEXT
            );
            INSERT INTO empresas VALUES ('11', 'Teste Ltda', 'Cliente Teste');
            INSERT INTO pessoas VALUES ('P1', 'titular', NULL);
            """
        )
        conn.executemany(
            "INSERT INTO eventos VALUES (?, ?, ?, ?, ?, ?, ?, ?)", eventos
        )
        return conn

    def test_entrada_e_saida_mesmo_dia_fica_inativo(self) -> None:
        conn = self._criar_db([
            (1, "P1", "11", "entrada", "Padrão", "2026-10-05 09:00:00", "2026-10-05", "portal_rh"),
            (2, "P1", "11", "saida", "Padrão", "2026-10-05 15:00:00", "2026-10-05", "portal_rh"),
        ])
        tl = linha_do_tempo_diaria(conn, "Cliente Teste", ["2026-10-04", "2026-10-05", "2026-10-06"], "2026-10-31 23:59:59")
        self.assertEqual(len(tl["2026-10-04"]), 0)
        self.assertEqual(len(tl["2026-10-05"]), 0)
        self.assertEqual(len(tl["2026-10-06"]), 0)

    def test_reativacao_sai_e_volta(self) -> None:
        conn = self._criar_db([
            (1, "P1", "11", "entrada", "Base", "2026-10-01 09:00:00", "2026-10-01", "carga_rh"),
            (2, "P1", "11", "saida", "Base", "2026-10-10 09:00:00", "2026-10-10", "carga_rh"),
            (3, "P1", "11", "entrada", "Plus", "2026-10-20 09:00:00", "2026-10-20", "carga_rh"),
        ])
        tl = linha_do_tempo_diaria(conn, "Cliente Teste", ["2026-10-05", "2026-10-10", "2026-10-15", "2026-10-20"], "2026-10-31 23:59:59")
        self.assertEqual(tl["2026-10-05"][0].plano, "Base")
        self.assertEqual(len(tl["2026-10-10"]), 0)
        self.assertEqual(len(tl["2026-10-15"]), 0)
        self.assertEqual(tl["2026-10-20"][0].plano, "Plus")

    def test_saida_informada_antes_da_entrada_nao_ativa_antes(self) -> None:
        conn = self._criar_db([
            (1, "P1", "11", "saida", "Padrão", "2026-10-10 09:00:00", "2026-10-05", "carga_rh"),
            (2, "P1", "11", "entrada", "Padrão", "2026-10-02 09:00:00", "2026-10-10", "carga_rh"),
        ])
        tl = linha_do_tempo_diaria(conn, "Cliente Teste", ["2026-10-05", "2026-10-09", "2026-10-10"], "2026-10-31 23:59:59")
        self.assertEqual(len(tl["2026-10-05"]), 0)
        self.assertEqual(len(tl["2026-10-09"]), 0)
        self.assertEqual(len(tl["2026-10-10"]), 1)

    def test_conhecido_ate_anterior_ao_evento_ignora_evento(self) -> None:
        conn = self._criar_db([
            (1, "P1", "11", "entrada", "Padrão", "2026-10-01 09:00:00", "2026-10-01", "carga_rh"),
            (2, "P1", "11", "saida", "Padrão", "2026-11-05 10:00:00", "2026-10-20", "carga_rh"),
        ])
        tl_antes = linha_do_tempo_diaria(conn, "Cliente Teste", ["2026-10-26"], "2026-11-03 23:59:59")
        tl_depois = linha_do_tempo_diaria(conn, "Cliente Teste", ["2026-10-26"], "2026-11-06 23:59:59")
        self.assertEqual(len(tl_antes["2026-10-26"]), 1)
        self.assertEqual(len(tl_depois["2026-10-26"]), 0)


if __name__ == "__main__":
    unittest.main()
