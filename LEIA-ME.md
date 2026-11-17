# O que tem neste kit

Todos os dados são fictícios: clientes, CNPJs, pessoas e valores. A base foi extraída em 13/11/2026 e vai até 12/11/2026.

| Arquivo | O que é |
|---|---|
| `contratos/` | Os contratos dos seis clientes, em PDF, do jeito que foram assinados. A cobrança está na cláusula de remuneração |
| `base.sqlite` | A base de vidas e as notas emitidas, num banco SQLite |
| `csv/` | As mesmas tabelas do banco, em CSV, para quem preferir planilha ou outra ferramenta |

Os CSVs usam vírgula como separador de colunas, ponto como separador decimal e codificação UTF-8. No Google Sheets abrem direto; no Excel, importe por Dados > Obter Dados > De Texto/CSV.

## As tabelas

**`empresas`**: cada CNPJ e o cliente a que pertence. Um cliente pode ter mais de um CNPJ: empresas diferentes do mesmo grupo, ou matriz e filial (`/0001` é a matriz, `/0002` a filial).

| Coluna | O que é |
|---|---|
| `cnpj` | CNPJ da empresa |
| `razao_social` | Nome da empresa |
| `cliente` | Nome do cliente (o contrato) |

**`pessoas`**: cada pessoa que já teve cadastro em algum dos clientes.

| Coluna | O que é |
|---|---|
| `pessoa_id` | Identificador da pessoa. É o mesmo em qualquer CNPJ |
| `tipo` | `titular` (o colaborador) ou `dependente` |
| `titular_id` | Para dependente, o `pessoa_id` do titular |

**`vinculos`**: a situação de hoje, do jeito que o sistema mostra. Uma linha por pessoa e CNPJ.

| Coluna | O que é |
|---|---|
| `pessoa_id`, `cnpj` | A pessoa e a empresa |
| `ativo` | `1` se a pessoa está ativa hoje nesse CNPJ, `0` se não está |
| `plano` | O plano da pessoa hoje. Quem tem um plano só aparece como `Padrão` |

Ninguém é apagado: quem sai fica com `ativo = 0`, e quem volta é reativado na mesma linha.

**`eventos`**: o histórico de todas as mudanças. É daqui que dá para saber quem estava ativo, e em qual plano, em qualquer dia do passado.

O movimento completo começa em 01/06/2026. Os eventos processados antes dessa data são só as entradas de quem estava ativo em 01/06/2026: quem saiu antes não aparece.

| Coluna | O que é |
|---|---|
| `evento_id` | Número do evento |
| `pessoa_id`, `cnpj` | A pessoa e a empresa |
| `tipo_evento` | `entrada`, `saida` ou `troca_plano` (a pessoa continua ativa e muda de plano) |
| `plano` | O plano da pessoa depois do evento. Na `saida`, o plano que ela tinha |
| `data_processamento` | Quando a mudança entrou no sistema (data e hora) |
| `data_informada` | A data que o RH informou: de admissão, de desligamento ou da troca de plano |
| `origem` | Quem fez a mudança: `carga_rh` (arquivo enviado pelo RH), `portal_rh` (RH pelo portal) ou `suporte_medipreco` (nosso time de suporte) |

**`notas_emitidas`**: as notas fiscais de mensalidade das competências de agosto a outubro de 2026 (na Bravo, que é pré-paga, até novembro), emitidas entre julho e novembro. Uma linha por item: uma nota com dois planos tem duas linhas com o mesmo `nota_id`.

| Coluna | O que é |
|---|---|
| `nota_id` | Número da nota |
| `cliente`, `tomador`, `cnpj_tomador` | Para quem a nota foi emitida |
| `competencia` | O mês de referência que a nota cobra (`AAAA-MM`) |
| `data_emissao` | Quando a nota foi emitida |
| `contagem_em` | Quando o financeiro consultou a base para contar as vidas ou titulares da nota |
| `item` | O que o item cobra |
| `base_calculo` | O que foi contado: `vidas` ou `titulares` |
| `quantidade` | Quantas vidas ou titulares foram cobrados no item |
| `valor_unitario`, `valor_item` | Em reais |
| `observacao` | Anotação do financeiro, quando houver |
