# Relato de Uso de IA

## 1. Por que o cálculo nunca passa por IA
Faturamento é uma obrigação contratual e fiscal: precisa ser **100% determinístico, reproduzível e auditável** até o último centavo. Uma LLM pode arredondar diferente, confundir `data_informada` com `data_processamento` ou alucinar uma contagem quando há milhares de linhas.

Por isso, a arquitetura separa estritamente:
* **Motor determinístico (Python + SQLite):** lê a configuração JSON dos contratos, reconstrói a linha do tempo em `eventos`, gera o extrato pessoa a pessoa e roda as 7 validações pré-emissão.
* **Peça única de IA (`medipreco/explicador.py`):** atua apenas na ponta final para transformar o resumo numérico já calculado pelo motor em uma explicação em português claro para CS/RH — com **guardrail determinístico** (`validar_cifras_no_texto`) que descarta a resposta da IA e aciona um modelo fixo caso qualquer cifra numérica inventada apareça no texto.

---

## 2. As duas IAs usadas no processo
Durante a construção do case, trabalhei com **duas IAs** em papéis distintos:
1. **Gemini 4 Hydrogen (Medium) — via Antigravity (IA de implementação):** usada para explorar o `base.sqlite`, ler os 6 PDFs, estruturar o pacote `medipreco/`, escrever os testes e gerar os CSVs.
2. **Copilot (assistente de IA usando Copilot SDK no VS Code; IA de planejamento e revisão crítica):** usado para questionar premissas, definir critérios de aceite de cada etapa, cobrar checagens independentes e auditar o repositório antes da entrega.

### Decisões adotadas a partir da revisão crítica
As **3 decisões centrais** de modelagem (posição no dia 26 pela `data_informada` com ajuste na nota seguinte; anulação do lote de `07/10` da Delta; e leitura do Grupo Cedro por pico simultâneo com rateio no dia do pico) foram **sugeridas pela IA de planejamento/revisão e adotadas por mim** após validar os números e trade-offs.

---

## 3. Onde a IA errou e foi corrigida (registro real)

1. **16/11/2026 — Estrela Out/2026 (`510` vs. `478`):** na primeira versão do teste, a IA assumiu que as saídas tardias já estariam no sistema em `03/11`. Ao rodar no banco, falhou porque em `03/11` ainda havia `510` vidas; as `39` saídas tardias só entraram em `05/11` (compensadas por `7` entradas = saldo `-32`, caindo para `478`). Corrigido para validar os dois cortes (`03/11 = 510` e `12/11 = 478`).
2. **16/11/2026 — Bravo Set/2026 (`332` foto vs. `333` emissão):** o teste inicial esperava `332` na data de emissão (`27/08`), mas `332` era a foto de `26/08 09:00`; até `27/08 23:59` entrou `+1` titular (`333`), e até `12/11` chegou a `334`. Separamos explicitamente os três valores no código e nos testes.
3. **16/11/2026 — Regex do guardrail (`_extrair_cifras`):** a regex `\d+(?:\.\d{3})*(?:,\d+)?|\d+(?:\.\d+)?` dividiu `160.50` em `160` e `50`, fazendo o guardrail rejeitar um texto válido. Ajustamos a ordem das alternativas na regex.
4. **16/11/2026 — Chave de variação `> 10%` na matriz:** a primeira versão comparava `cliente|item` sem `cnpj_tomador`, misturando CNPJs diferentes do Grupo Cedro. Corrigido para `cliente|cnpj_tomador|item`.
5. **16/11/2026 — `ΔDegrau` na tabela de resultados:** a coluna `ΔDegrau` aparecia ao lado das colunas aditivas sem aviso de que era um subcomponente de `ΔTard`/`ΔRelEm`, podendo induzir dupla contagem. Adicionamos a legenda explícita no `README.md`.
6. **17/11/2026 — Lista de verificação incompleta ("tudo conferido"):** a verificação afirmou que tudo estava conferido quando consultas SQL independentes de Cedro (`1.080`) e Delta (`4.950`/`5.106`) haviam sido canceladas no background; reexecutamos com `LEAD()` em janela para comprovar todos os números.
7. **17/11/2026 — `24` em vez de `25` extratos:** o laço de `cmd_tudo` iterava apenas `2026-08` a `2026-10`, omitindo `2026-11` da Bravo. Corrigido para consultar `DISTINCT cliente, competencia` direto de `notas_emitidas`.
8. **17/11/2026 — Mistura de bases na matriz (`PROXIMO_LIMITE_FAIXA`):** a matriz rodava o alerta tanto em `qtd_nota` (`4.892`) quanto no cálculo do motor (`5.048`), fazendo Outubro disparar com `5.048` na linha de `4.892`. Unificamos a coluna como `qtd_avaliada` sobre a nota emitida.
9. **17/11/2026 — `.gitignore` ocultando `data/README.md`:** a regra `data/` ignorava toda a pasta; alteramos para `data/*` e `!data/README.md`.
10. **17/11/2026 — `grep` parcial e `if cliente ==` residual:** o `grep` inicial olhou apenas `contratos.py` e `extrato.py`; ao varrer todo o pacote `medipreco/`, encontramos `if cliente ==` residual em `medipreco/comparacao.py` (para rótulos de observação/causa) e links absolutos locais em `docs/PROPOSTA.md`; ambos foram removidos.
