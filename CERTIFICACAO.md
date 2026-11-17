# Auditoria Interna — Case Medipreço

**Data da auditoria:** `2026-11-17`
**Veredito Final:** **APTO COM RESSALVA (integração fiscal fora do protótipo)**
*(O repositório Git foi publicado na branch `main`. O código, os exemplos e uma fixture de teste com identificadores sintéticos estão versionados; a base completa e os PDFs dos contratos permanecem fora do Git.)*

---

## 1. Matriz de Auditoria (Blocos A–F)

| Bloco | Critério | Status | Evidência |
|---|---|---|---|
| **A** | 3 entregas presentes (proposta, protótipo + instrução, relato de IA) | **OK** | `docs/PROPOSTA.md`, `medipreco/` + `README.md`, `docs/RELATO_IA.md` |
| **A** | Proposta responde às 4 áreas e separa o fluxo-alvo do escopo do protótipo | **OK** | `docs/PROPOSTA.md` seções 3 e 5 |
| **A** | Solução simples, escalável e auditável (limitações declaradas) | **OK** | `medipreco/timeline.py:38-66` (anulação heurística documentada no roadmap) |
| **B** | Cálculo usa `eventos` e nunca `vinculos` como fonte | **OK** | `medipreco/timeline.py` consulta só `eventos`; `vinculos` só em `tests/test_timeline.py:29` |
| **B** | Zero chamadas de IA no cálculo | **OK** | IA isolada em `medipreco/explicador.py` |
| **B** | Zero `if`/`elif` por nome de cliente ou CNPJ fora de `config/` e `tests/` | **OK** | Busca completa em `medipreco/` retorna apenas docstring/comentário e atributos de modelo (`l.cliente`, `ex.cliente`) |
| **B** | Contratos em `config/contratos.json` e separação dos dois eixos | **OK** | `config/contratos.json` + `medipreco/timeline.py:114-169` |
| **C** | `vinculos` ativos = `7.793`, 0 divergências | **OK** | SQL independente: `7793`; `test_reconciliacao_com_vinculos` OK |
| **C** | 27/28 itens reproduzidos (exceção Bravo set/2026: 499 vs 332) | **OK** | `test_reproduz_27_de_28_itens_notas_emitidas` OK |
| **C** | Aurora out: 737 / 718 / 721; 16 de 19 saídas em `27/10` | **OK** | SQL independente: `737`, `718`, `721`, `(19, 16)` |
| **C** | Bravo set: 332 foto / 333 emissão / 334 em 12/11; R\$ 2.505 / 2.490 / 2.475 | **OK** | SQL independente + `test_tabela_referencia...` OK |
| **C** | Delta: `5.051` / `4.950` / `5.048` emissão; `5.280` / `5.106` / `5.048` em 12/11; lote 600 | **OK** | SQL independente com `LEAD()` |
| **C** | Estrela out: `510` (03/11), `478` (12/11), mínimo `500`, crédito R\$ `95,00` | **OK** | SQL independente + `test_estrela_outubro...` OK |
| **C** | Cedro out: `961` pico, `984` distintas, `1.080` soma picos, `946` nota | **OK** | SQL independente com `LEAD()` |
| **C** | Números de `README.md` e `docs/PROPOSTA.md` consistentes | **OK** | `docs/PROPOSTA.md:71` alinhado com `exemplos/matriz_alertas_28_notas.csv` |
| **D** | `python3 -m unittest discover -s tests -v`: 27 testes + comportamento | **OK** | `Ran 27 tests — OK` usando `tests/fixtures/base.sqlite` |
| **D** | Comandos `fechar` e `tudo` rodam sem a base local completa | **OK** | Ambos executados com a fixture sintética; `tudo` reproduz os 27 CSVs de `exemplos/` |
| **E** | Sem chaves/segredos nem caminhos absolutos locais ou dados pessoais | **OK** | `grep` em todo o repositório retornou zero ocorrências |
| **E** | Extrato e IA sem nomes de pessoas (só IDs) | **OK** | `PRAGMA table_info(pessoas)` sem coluna de nome |
| **E** | Arquivos locais do case fora do Git (`git ls-files`) | **OK** | `data/base.sqlite`, `contratos/`, `saida/`, `scratch/` e `.env` são ignorados; `data/README.md` é versionado |
| **E** | Guardrail descarta número inventado | **OK** | `test_aurora_outubro_718_vs_737_sem_ia_e_guardrail` OK |
| **F** | `docs/RELATO_IA.md` atualizado com as duas IAs e erros reais | **OK** | `docs/RELATO_IA.md` |

---

## 2. Riscos Remanescentes
1. **Dados completos não são publicados:** testes e demonstração rodam com a fixture sintética; reproduzir a base completa original requer o arquivo local `data/base.sqlite`, descrito em `data/README.md`.
2. **Heurística de anulação em `medipreco/timeline.py:38-66`:** depende de `suporte_medipreco`; em produção exige coluna `anulado_por_evento_id`.
