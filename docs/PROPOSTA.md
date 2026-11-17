# Proposta: O Fechamento do Mês — Medipreço

**De "foto" manual em planilha para um motor determinístico, configurável e auditável — do contrato assinado até a nota paga.**

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

## 3. Fluxo Ponta a Ponta (Contrato → Nota Paga)

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
   │  Bloqueios (unidade errada, carga em quarentena, soma do extrato) e Avisos (faixa, mínimo, SLA)
   ▼
[5. Emissão da NF + Explicador para CS/RH]
   │  Nota sai acompanhada do espelho CSV e resumo em português sem PII sensível
   ▼
[6. Informação Tardia / Compensação Pré-Pago]
   └─ Diferenças que chegarem após a emissão viram crédito/débito na nota seguinte (sem reabrir NF)
```

---

## 4. Resultados nos Dados Reais (Ago–Out/2026)

Ao rodar o motor sobre `base.sqlite` (com conhecimento até `12/11/2026`) e comparar contra as **28 linhas de `notas_emitidas`**, quatro achados explicam praticamente toda a perda de margem e atrito com clientes:

1. **Bravo Tecnologia — Erro de unidade em Set/2026 (-R\$ 2.505,00 na foto / -33,07%):**
   * O contrato cobra R\$ 15,00 **por titular ativo** (`332` na foto de `26/08 09h`, `333` na emissão de `27/08`, `334` em `12/11`).
   * A nota `NF-01187` cobrou **499** (R\$ 7.485,00) — exatamente o total de **vidas** (titulares + 167 dependentes). A trava pré-emissão `UNIDADE_VIDAS_EM_CONTRATO_TITULAR` bloqueia esse erro automaticamente antes da emissão. Além disso, a compensação da Cláusula 4.4 (`336 - 333 = +3` titulares = +R\$ 45,00) nunca era feita.
2. **Delta Benefícios — Efeito degrau + lote mensal atrasado (-R\$ 3.456,00 em Set; -R\$ 3.488,00 em Out):**
   * A Delta envia o movimento do mês sempre nos dias `3–5` do mês seguinte (lag médio de `110,3` dias).
   * Ao tirar foto no dia 26 sem aplicar a Cláusula 7.2 ("ativo por ≥ 1 dia no mês"), a base caiu de `5.000` (`4.941` em Set; `4.892` em Out) e **pulou da faixa de R\$ 9,00 para R\$ 10,00** — gerando um efeito degrau de **-R\$ 5.106,00** (Set) e **-R\$ 5.048,00** (Out) no preço unitário! Pela regra contratual (`5.106` e `5.048` vidas), permanece na faixa de R\$ 9,00.
   * Em `07/10`, subiram `600` entradas erradas (desfeitas pelo suporte em `09/10`). A regra de quarentena bloqueia a carga na entrada e a anulação evita cobrar ~R\$ 5.400/mês indevidos.
3. **Estrela Indústria — Desligamentos fora do SLA e mínimo garantido (-R\$ 95,00 em Out):**
   * O RH tem lag médio de `16,5` dias (contrato prevê 5 dias úteis). Em Out/2026, na emissão (`03/11`) havia `510` vidas (R\$ 4.845,00); após a carga tardia de `05/11`, a realidade de `26/10` caiu para **478 vidas**, acionando o mínimo garantido de **500 vidas** (R\$ 4.750,00) → crédito de **R\$ 95,00** na nota seguinte.
4. **Grupo Cedro e Faro Serviços — Regras contratuais não operacionalizadas:**
   * **Cedro:** foto do dia 26 deixou de faturar o pico simultâneo do mês (`997` vs `968` em Ago = +R\$ 232; `963` vs `961` em Set = +R\$ 16; `961` vs `946` em Out = +R\$ 120).
   * **Faro:** pró-rata dia reduz pequenas diferenças a favor do cliente (`-R$ 13,13` em Ago, `-R$ 2,93` em Set, `-R$ 1,42` em Out).

### Matriz de Alertas nas 28 Notas Emitidas
Ao passar as 28 linhas emitidas pelas 7 travas pré-emissão (`saida/matriz_alertas_28_notas.csv`):
* **2 bloqueios graves** teriam impedido erros antes da emissão: `UNIDADE_VIDAS_EM_CONTRATO_TITULAR` na Bravo Set/2026 (`NF-01187`) e `CARGA_ATIPICA_QUARENTENA` na Delta Out/2026 (`NF-01313`).
* **Avisos acionáveis** apareceram em Delta (`PROXIMO_LIMITE_FAIXA` em Ago com `5.051` e Set com `4.941`; em Out não dispara na nota emitida de `4.892` a `2,16%`, pois a matriz é um retroteste, mas dispararia em produção sobre os `5.048` calculados pelo motor a `0,96%` do limite; e `DESLIGAMENTO_FORA_SLA` como alerta operacional), Estrela (`MINIMO_GARANTIDO_ACIONADO` em Out e `DESLIGAMENTO_FORA_SLA` em Ago/Set/Out) e nas variações `> 10%` de Bravo/Aurora.

---

## 5. O que a proposta responde para cada área

* **Financeiro:** fecha o mês em minutos com um comando (`python -m medipreco tudo`), com checklist automático de travas antes da emissão e sem risco de cobrar vidas no lugar de titulares.
* **RH do cliente:** recebe junto da nota o extrato CSV pessoa a pessoa com dias ativos, plano, regra aplicada e data de corte — eliminando dúvidas como "718 vs 737".
* **Comercial:** passa a vender sobre um **catálogo de primitivas parametrizáveis** em JSON. Se o cliente pedir uma regra que não cabe no catálogo, o Comercial já sabe antes de assinar o contrato.
* **Customer Success (CS):** recebe uma explicação pronta em português claro (com guardrail que impede números inventados) e sabe exatamente o porquê de cada variação.

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
3. **Longo prazo:** copiloto conversacional no portal do CS/RH conectado exclusivamente aos extratos pré-calculados pelo motor determinístico.
