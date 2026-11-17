# Proposta: O Fechamento do Mês — Medipreço

**De "foto" manual em planilha para um motor determinístico, configurável e auditável. O protótipo reconcilia a base, analisa notas e prepara validações e relatórios; emissão fiscal e acompanhamento do pagamento ficam fora do escopo atual.**

---

## 1. O Problema: por que "718 vs. 737" acontece todo mês

Em outubro de 2026, o RH da Aurora Logística baixou sua base no dia 31 e encontrou **718 vidas**, mas recebeu uma nota fiscal cobrando **737 vidas**. Hoje ninguém consegue explicar essa conta rápido porque o fechamento olha apenas uma **foto** do sistema (`contagem_em`) perto do dia 26:

* Na foto de `26/10 às 09:00`, havia **737 vidas** (`548` Base + `189` Plus).
* Em `27/10 às 11:57`, o RH enviou uma carga com **19 saídas** — sendo **16 delas com data de desligamento até `26/10`**. A realidade no dia 26 já era **721 vidas** (e caiu para **718** em `31/10`).
* Como a planilha do financeiro não enxerga o histórico de eventos ("o vídeo") e não separa **quando aconteceu** (`data_informada`) de **quando o sistema soube** (`data_processamento`), o cliente vê uma cobrança inexplicável, o CS não tem extrato para defender e o financeiro gasta dois dias fechando regras diferentes na mão.

---

## 2. Tese Central

> **A nota fiscal é o resultado de uma conta que qualquer pessoa consegue refazer.**
> * O cálculo é **100% determinístico**, executado sobre o histórico de `eventos` (nunca sobre a foto de `vinculos`).
> * As regras de cada contrato vivem em **configuração declarativa** ([config/contratos.json](../config/contratos.json)), sem `if` por cliente no código.
> * **IA nunca calcula valor**: ela atua apenas na ponta de explicação em português sobre o extrato já calculado, protegida por guardrail que descarta qualquer resposta com números inventados.

---

## 3. Fluxo-alvo e escopo do protótipo

```text
[1. Contrato Assinado]
   │  Parametrização em JSON (unidade, método, corte, planos/faixas, mínimo, rateio, pré/pós)
   ▼
[2. Linha do Tempo de Eventos ("O Vídeo")]
   │  Dois eixos: data_informada (realidade) × data_processamento (conhecimento)
   │  Filtra cargas anuladas operacionalmente
   ▼
[3. Motor de Apuração + Extrato Auditável]
   │  Gera itens da nota + extrato pessoa a pessoa fechando no centavo
   ▼
[4. Validações Pré-Emissão (7 Travas)]
   │  Classifica bloqueios (unidade, carga em quarentena, soma do extrato) e avisos (faixa, mínimo, SLA)
   ▼
[5. Relatório de fechamento + Explicador para CS/RH]
   │  Gera o espelho CSV, alertas e resumo em português sem PII sensível
   ▼
[6. Emissão da NF e acompanhamento do pagamento (fora do protótipo)]
   │  Integração futura com o ERP/emissor fiscal e conciliação financeira
   ▼
[7. Informação Tardia / Compensação Pré-Pago]
   └─ O protótipo sinaliza diferenças; aplicar crédito/débito na nota seguinte é processo externo
```

**Implementado:** apuração determinística, extrato auditável, validações e relatórios CSV. O protótipo não emite NF, não registra pagamento e não envia ajustes ao ERP.

---

## 4. Resultados no conjunto de dados do case (Ago–Out/2026)

Ao rodar o motor sobre a base do case (com conhecimento até `12/11/2026`) e comparar contra as **28 linhas de `notas_emitidas`**, quatro achados ilustram fontes de divergência, perda de margem e atrito com clientes:

1. **Bravo Tecnologia — Erro de unidade em Set/2026 (-R\$ 2.505,00 na foto / -33,07%):**
   * O contrato cobra R\$ 15,00 **por titular ativo** (`332` na foto de `26/08 09h`, `333` na emissão de `27/08`, `334` em `12/11`).
   * A nota `NF-01187` cobrou **499** (R\$ 7.485,00) — exatamente o total de **vidas** (titulares + 167 dependentes). O protótipo classifica a divergência como bloqueio; impedir a emissão efetivamente exige integração com o fluxo fiscal, que está fora do escopo atual. Além disso, a compensação da Cláusula 4.4 (`336 - 333 = +3` titulares = +R\$ 45,00) nunca era feita.
2. **Delta Benefícios — Efeito degrau + lote mensal atrasado (-R\$ 3.456,00 em Set; -R\$ 3.488,00 em Out):**
   * A Delta envia o movimento do mês sempre nos dias `3–5` do mês seguinte (lag médio de `110,3` dias).
   * Ao tirar foto no dia 26 sem aplicar a Cláusula 7.2 ("ativo por ≥ 1 dia no mês"), a base caiu de `5.000` (`4.941` em Set; `4.892` em Out) e **pulou da faixa de R\$ 9,00 para R\$ 10,00** — gerando um efeito degrau de **-R\$ 5.106,00** (Set) e **-R\$ 5.048,00** (Out) no preço unitário! Pela regra contratual (`5.106` e `5.048` vidas), permanece na faixa de R\$ 9,00.
   * Em `07/10`, subiram `600` entradas erradas (desfeitas pelo suporte em `09/10`). A validação identifica e classifica a carga para quarentena; o bloqueio operacional depende de integração. A anulação evita considerar ~R\$ 5.400/mês indevidos na apuração.
3. **Estrela Indústria — Desligamentos fora do SLA e mínimo garantido (-R\$ 95,00 em Out):**
   * O RH tem lag médio de `16,5` dias (contrato prevê 5 dias úteis). Em Out/2026, na emissão (`03/11`) havia `510` vidas (R\$ 4.845,00); após a carga tardia de `05/11`, a realidade de `26/10` caiu para **478 vidas**, acionando o mínimo garantido de **500 vidas** (R\$ 4.750,00) → crédito de **R\$ 95,00** na nota seguinte.
4. **Grupo Cedro e Faro Serviços — Regras contratuais não operacionalizadas:**
   * **Cedro:** foto do dia 26 deixou de faturar o pico simultâneo do mês (`997` vs `968` em Ago = +R\$ 232; `963` vs `961` em Set = +R\$ 16; `961` vs `946` em Out = +R\$ 120).
   * **Faro:** pró-rata dia reduz pequenas diferenças a favor do cliente (`-R$ 13,13` em Ago, `-R$ 2,93` em Set, `-R$ 1,42` em Out).

### Matriz de Alertas nas 28 Notas Emitidas
Ao passar as 28 notas já emitidas pelas 7 validações (`saida/matriz_alertas_28_notas.csv`), o protótipo faz um **retroteste**:
* **2 bloqueios graves** teriam sido sinalizados antes da emissão em um fluxo preventivo: `UNIDADE_VIDAS_EM_CONTRATO_TITULAR` na Bravo Set/2026 (`NF-01187`) e `CARGA_ATIPICA_QUARENTENA` na Delta Out/2026 (`NF-01313`). A matriz não altera nem bloqueia notas no sistema fiscal.
* **Avisos acionáveis** apareceram em Delta (`PROXIMO_LIMITE_FAIXA` em Ago com `5.051` e Set com `4.941`; em Out não dispara na nota emitida de `4.892` a `2,16%`, pois a matriz é um retroteste, mas dispararia em produção sobre os `5.048` calculados pelo motor a `0,96%` do limite; e `DESLIGAMENTO_FORA_SLA` como alerta operacional), Estrela (`MINIMO_GARANTIDO_ACIONADO` em Out e `DESLIGAMENTO_FORA_SLA` em Ago/Set/Out) e nas variações `> 10%` de Bravo/Aurora.

---

## 5. O que a proposta responde para cada área

* **Financeiro:** gera relatórios com um comando (`python -m medipreco tudo`) e apresenta bloqueios e avisos para revisão antes da emissão; a emissão continua no sistema fiscal existente.
* **RH do cliente:** pode receber, por um fluxo operacional, o extrato CSV pessoa a pessoa com dias ativos, plano, regra aplicada e data de corte — respondendo dúvidas como "718 vs 737".
* **Comercial:** passa a vender sobre um **catálogo de primitivas parametrizáveis** em JSON. Se o cliente pedir uma regra que não cabe no catálogo, o Comercial já sabe antes de assinar o contrato.
* **Customer Success (CS):** tem uma explicação pronta em português claro (com guardrail que impede números inventados) para compartilhar e contextualizar cada variação.

---

## 6. Decisões, Premissas e Alinhamentos Necessários com Negócio/Jurídico
* **Lote anulado da Delta (`07/10`):** hoje tratado por pareamento operacional (impacto de ~R\$ 5.400/mês). Recomenda-se incluir cláusula explícita prevendo janela de contestação/anulação sem cobrança.
* **Redação do Grupo Cedro ("máximo alcançado no mês"):** padronizar em aditivo como **pico simultâneo diário** (em Out/2026: `961` vidas = R\$ 7.688, contra `984` distintas = R\$ 7.872 ou `1.110` vínculos).
* **Compensação da Bravo (Cláusula 4.4):** fixar "titulares efetivamente ativos" como os ativos no **dia 26 do mês de referência** (ex.: Set/2026 = `336` vs `333` cobrados = +R\$ 45,00).
* **Convenção de data de saída:** inativo a partir da `data_informada` (declarada em contrato).

---

## 7. O que ficou de fora e Roadmap
1. **Curto prazo (produção):** adicionar coluna `anulado_por_evento_id` na tabela `eventos` (eliminando heurística por origem `suporte_medipreco`).
2. **Médio prazo:** extrator assistido por LLM para sugerir o JSON de `config/contratos.json` a partir de novos PDFs (com aprovação humana obrigatória) e integração com emissor de NF-e.
3. **Longo prazo:** acompanhamento de pagamento e conciliação de créditos/débitos com o ERP; copiloto conversacional no portal do CS/RH conectado exclusivamente aos extratos pré-calculados pelo motor determinístico.
