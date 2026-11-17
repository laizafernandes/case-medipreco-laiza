# Proposta: O Fechamento do Mês — Medipreço

**De "foto" manual em planilha para um motor determinístico, configurável e auditável. O protótipo reconcilia a base, analisa notas e prepara validações e relatórios; emissão fiscal e acompanhamento do pagamento ficam fora do escopo atual.**

*Os nomes e números apresentados a seguir pertencem ao conjunto fictício do case.*

---

## 1. O Problema: a divergência "718 vs. 737"

No cenário do case, em outubro de 2026 o RH da Aurora Logística baixou sua base no dia 31 e encontrou **718 vidas**, mas recebeu uma nota fiscal cobrando **737 vidas**. A equipe não consegue explicar rapidamente a conta porque o fechamento olha apenas uma **foto** do sistema (`contagem_em`) perto do dia 26:

* Na foto de `26/10 às 09:00`, havia **737 vidas** (`548` Base + `189` Plus).
* Em `27/10 às 11:57`, o RH enviou uma carga com **19 saídas** — sendo **16 delas com data de desligamento até `26/10`**. A realidade no dia 26 já era **721 vidas** (e caiu para **718** em `31/10`).
* Como a planilha do financeiro não enxerga o histórico de eventos ("o vídeo") e não separa **quando aconteceu** (`data_informada`) de **quando o sistema soube** (`data_processamento`), o cliente vê uma cobrança inexplicável e o CS não tem extrato para defendê-la. Os "dois dias" gastos pelo financeiro são uma premissa do cenário, não uma redução de tempo medida pelo protótipo.

---

## 2. Tese Central

> **A nota fiscal é o resultado de uma conta que qualquer pessoa consegue refazer.**
> * O cálculo é **100% determinístico**, executado sobre o histórico de `eventos` (nunca sobre a foto de `vinculos`).
> * As regras de cada contrato vivem em **configuração declarativa** ([config/contratos.json](../config/contratos.json)), sem `if` por cliente no código.
> * **IA nunca calcula valor**: ela atua apenas na explicação em português sobre o extrato já calculado; um filtro rejeita cifras que não constam nos dados fornecidos, mas não substitui a revisão humana da explicação.

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
[4. Validações para Revisão Pré-Emissão (7 Regras)]
   │  Classifica potenciais bloqueios e avisos; exige revisão humana e não aciona o emissor fiscal
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
   * Nos lotes de entradas de jul–set/2026, o processamento ocorreu nos dias `3` dos meses seguintes. Já o lote atípico de `07/10` trouxe `600` entradas retroativas, com atraso de até `1.010` dias.
   * Ao tirar foto no dia 26 sem aplicar a Cláusula 7.2 ("ativo por ≥ 1 dia no mês"), a base caiu de `5.000` (`4.941` em Set; `4.892` em Out) e **pulou da faixa de R\$ 9,00 para R\$ 10,00**. O impacto isolado do degrau no valor foi de **-R\$ 5.106,00** em Set e **-R\$ 5.048,00** em Out. Esses valores são componentes informativos de `ΔTard`/`ΔRelEm` e não devem ser somados novamente às diferenças líquidas de **-R\$ 3.456,00** e **-R\$ 3.488,00**. Pela regra contratual (`5.106` e `5.048` vidas), permanece na faixa de R\$ 9,00.
   * Em `07/10`, subiram `600` entradas erradas (desfeitas pelo suporte em `09/10`). A validação identifica e classifica a carga para quarentena; o bloqueio operacional depende de integração. A anulação evita considerar ~R\$ 5.400/mês indevidos na apuração.
3. **Estrela Indústria — Desligamentos fora do SLA e mínimo garantido (-R\$ 95,00 em Out):**
   * O RH tem lag médio de `16,5` dias (contrato prevê 5 dias úteis). Em Out/2026, na emissão (`03/11`) havia `510` vidas (R\$ 4.845,00); após a carga tardia de `05/11`, a realidade de `26/10` caiu para **478 vidas**, acionando o mínimo garantido de **500 vidas** (R\$ 4.750,00) → diferença de **R\$ 95,00** indicada para análise como crédito na nota seguinte; o protótipo não aplica esse ajuste.
4. **Grupo Cedro e Faro Serviços — Regras contratuais não operacionalizadas:**
   * **Cedro:** foto do dia 26 deixou de faturar o pico simultâneo do mês (`997` vs `968` em Ago = +R\$ 232; `963` vs `961` em Set = +R\$ 16; `961` vs `946` em Out = +R\$ 120).
   * **Faro:** pró-rata dia reduz pequenas diferenças a favor do cliente (`-R$ 13,13` em Ago, `-R$ 2,93` em Set, `-R$ 1,42` em Out).

### Matriz de Alertas nas 28 Notas Emitidas
Ao passar as 28 notas já emitidas pelas 7 validações (`saida/matriz_alertas_28_notas.csv`), o protótipo faz um **retroteste**:
* **2 bloqueios graves** teriam sido sinalizados antes da emissão em um fluxo preventivo: `UNIDADE_VIDAS_EM_CONTRATO_TITULAR` na Bravo Set/2026 (`NF-01187`) e `CARGA_ATIPICA_QUARENTENA` na Delta Out/2026 (`NF-01313`). A matriz não altera nem bloqueia notas no sistema fiscal.
* **Avisos acionáveis** apareceram em Delta (`PROXIMO_LIMITE_FAIXA` em Ago com `5.051` e Set com `4.941`; em Out não dispara na nota emitida de `4.892` a `2,16%`, pois a matriz é um retroteste, mas dispararia em produção sobre os `5.048` calculados pelo motor a `0,96%` do limite; e `DESLIGAMENTO_FORA_SLA` como alerta operacional), Estrela (`MINIMO_GARANTIDO_ACIONADO` em Out e `DESLIGAMENTO_FORA_SLA` em Ago/Set/Out) e nas variações `> 10%` de Bravo/Aurora.

---

## 5. O que a proposta responde para cada área

* **Financeiro:** `python -m medipreco fechar` apura um cliente e uma competência até o corte informado e apresenta o extrato e os alertas para revisão humana. `python -m medipreco tudo` gera a comparação histórica e a matriz de retroteste; não é uma trava de emissão. A emissão continua no sistema fiscal existente.
* **RH do cliente:** pode receber, por um fluxo operacional externo, o extrato CSV pessoa a pessoa com dias ativos, plano, regra aplicada e data de corte — respondendo dúvidas como "718 vs 737". O protótipo gera o arquivo, mas não o envia.
* **Comercial:** o catálogo de primitivas em JSON ajuda a verificar se uma regra proposta cabe no que o motor suporta; não aprova automaticamente contratos nem substitui revisão comercial/jurídica.
* **Customer Success (CS):** hoje o comando `fechar` gera um resumo genérico com cliente, competência, valor total e corte. A explicação causal de cada variação, conectada às decomposições e alertas, é uma evolução proposta — não uma capacidade integrada no fluxo atual.

**Uso de IA externa:** quando `OPENAI_API_KEY` está configurada, o CLI envia ao provedor o nome do cliente, competência, valor total e corte de conhecimento. Não envia identificadores individuais de pessoas nesse fluxo, mas esses dados financeiros e comerciais ainda podem ser confidenciais. Antes de uso em produção, são necessários aprovação, minimização de dados e avaliação contratual do provedor. O filtro numérico rejeita cifras ausentes dos dados, mas não verifica se a explicação está semanticamente correta; a revisão humana continua necessária.

---

## 6. Decisões, Premissas e Alinhamentos Necessários com Negócio/Jurídico
* **Lote anulado da Delta (`07/10`):** hoje tratado por pareamento operacional (impacto de ~R\$ 5.400/mês). Recomenda-se incluir cláusula explícita prevendo janela de contestação/anulação sem cobrança.
* **Redação do Grupo Cedro ("máximo alcançado no mês"):** padronizar em aditivo como **pico simultâneo diário**. Em Out/2026, as bases são distintas: `984` pessoas únicas no mês, `1.110` vínculos pessoa–CNPJ observados no mês e `1.080` como soma dos picos diários individuais por CNPJ; o pico simultâneo do grupo foi `961` vidas (R\$ 7.688). Esses números não são medidas intercambiáveis.
* **Compensação da Bravo (Cláusula 4.4):** fixar "titulares efetivamente ativos" como os ativos no **dia 26 do mês de referência** (ex.: Set/2026 = `336` vs `333` cobrados = +R\$ 45,00).
* **Convenção de data de saída:** inativo a partir da `data_informada` (declarada em contrato).

---

## 7. O que ficou de fora e Roadmap
1. **Curto prazo (produção):** adicionar coluna `anulado_por_evento_id` na tabela `eventos` (eliminando heurística por origem `suporte_medipreco`) e usar centavos inteiros ou `Decimal` nos cálculos monetários.
2. **Médio prazo:** integrar explicações por causa a dados determinísticos, com revisão humana; definir controles de privacidade, retenção e auditoria antes de enviar dados a um provedor externo; criar extrator assistido por LLM para sugerir `config/contratos.json` a partir de PDFs (com aprovação humana) e integrar ao emissor de NF-e.
3. **Longo prazo:** acompanhamento de pagamento e conciliação de créditos/débitos com o ERP; copiloto conversacional no portal do CS/RH conectado exclusivamente aos extratos pré-calculados pelo motor determinístico.
