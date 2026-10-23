# SIGA — estrutura das telas usadas pelo AutoSIGA

Leia sob demanda, quando a tarefa mexer na automação do SIGA (`bot/`). Levantado em 19/10/2026, SIGA versão 6.71.0, navegando só em modo leitura. Nenhum dado financeiro ou pessoal foi registrado aqui.

## Visão geral

- **Nome**: Sistema Integrado de Gerenciamento Administrativo (CCB). URL: `https://siga.congregacao.org.br/`.
- **Login**: e-mail/usuário + senha + **reCAPTCHA**. O bot reaproveita a sessão do perfil persistente (`siga_browser_data/`); um login novo exige interação humana.
- **Duas gerações de tela**:
  - **Legado ASP.NET**: `/<MÓDULO>/<PROGRAMA>.aspx` (ex.: `/TES/TES01701.aspx`), com jQuery, Bootstrap e Select2. É onde o bot trabalha hoje.
  - **Front novo**: `/SIS/Programa.aspx?programa=<COD>` carrega um iframe **cross-origin** de `https://siga-front.congregacao.org.br/login/token/...`. Do contexto da página principal não dá para ler o DOM do iframe; com Playwright é preciso usar `page.frame_locator(...)`. Usam o front novo: Importação Extrato, Cartão de Débito e Transferências, Boletos e Repartição Ofertas.
- **Executar rotina**: o campo `#f_executar_programa` (cabeçalho, placeholder "Executar") + botão `#btn_executar_programa` abre qualquer programa pelo código. Também é possível navegar direto pela URL `.aspx`.
- **Contexto de trabalho (cabeçalho)**: o **Mês de Trabalho** (competência) e a **Localidade/Unidade Fiscal** ativas valem para todos os lançamentos. Trocam pelo modal "Mês de Trabalho" (campos Usuário, Unidade Fiscal, Localidade e Mês de Trabalho; `select#f_competencia_webmaster`, confirmar em `#btn-adicionar-competencia`).
- **Avisos fixos**: um banner vermelho "O(s) mês(es) de MM/AAAA ainda não foram fechados!" e um de LGPD. Um mês **fechado** recusa lançamentos com um aviso bootbox ("Fechamento de competência já realizado", "fora da Competência" ou "Fechamento mensal"). O fechamento é **por localidade** (normalmente, ADM fechada implica as demais fechadas). O bot guarda em memória, só durante a execução, o par localidade + mês recusado e pula os outros lançamentos dele.
- **Carregamento**: overlay "Aguarde..." após cada navegação (`esperar_loading`).
- **Rodapé**: cada tela mostra seu código (ex.: `TES01703 - Versão 6.71.0`), útil para confirmar em que tela se está.
- **Selects**: a maioria é `<select>` nativo envolvido por Select2 (inputs `s2id_autogen*`); alguns são AJAX (fornecedor). As opções seguem o formato `"<código> - <descrição>"`.

## Menu Tesouraria (códigos)

| Item | Programa |
|---|---|
| Caixas e Bancos | TES01701 |
| Contas a Pagar | TES01501 |
| Transf. Numerários | TES01301 |
| Doações | TES03501 |
| Retenções | TES03701 |
| Fech. Administração | TES02301 |
| Importação Extrato | TES05601 (front novo) |
| Cartão de Débito e Transferências, Boletos, Repartição Ofertas | front novo (`Programa.aspx`) |
| Relatórios | Dashboard TES00201, Extrato TES01201, Contas a Pagar TES01801, Adiantamento TES03801, Fluxo de Caixa TES01901, Mapa Coletas TES00501, Despesas TES00901, Depósitos TES00701, Razão Gerencial TES03101, Balancete Financ. TES02901, Receitas/Despesas TES03601 |
| Cadastros | Operadora Estabelecimento Coleta TES04301 |

## TES01701 — Caixas e Bancos (consulta)

- Grade de movimentos: Data, Lançto, Nº Documento, Histórico, Origem, Entrada, Saída, Saldo. Filtro por conta (`select#f_conta`) e período (`#f_data1`, `#f_data2`). É a fonte da conciliação OFX × SIGA.
- **Saldo na grade** (levantado em 23/10/2026, só consulta):
  - A 1ª linha do `tbody` é "Saldo Anterior", feita de `th` (sem `td`), com o saldo antes do período na coluna Saldo. Os leitores que exigem 8 `td` a ignoram.
  - As linhas seguem a ordem de data; a coluna Saldo é acumulada a partir do saldo anterior.
  - O `tfoot` tem uma linha "Total": Entrada e Saída somam só o período, e a coluna Saldo é o **saldo final** (anterior + entradas − saídas). Ele bateu com o `LEDGERBAL` do OFX e com o "Saldo Atual" do XLS de aplicação.
  - Período sem movimento: a grade traz só o "Saldo Anterior", e o `tfoot` continua com o saldo, então ele é sempre legível.
  - Valores no formato brasileiro (`10.977,40`), negativo com `-` na frente (`-27,50`); `-` sozinho significa zero.
- No `select#f_conta`, os grupos aparecem como opções de 3 dígitos (`100 - CAIXA`, `101 - BANCOS CONTA MOVIMENTO`, `103 - APLICAÇÕES FINANCEIRAS`), não como `optgroup`; o único `optgroup` é o INATIVO.
- Blocos de saldo por grupo de conta: **Caixas** (1000 Caixa Geral, 1001 Numerários a Depositar, 1002 Numerários Coletas, 1009 Caixa de Manutenção), **Bancos Conta Movimento** (101xx, um por conta corrente, rótulo `"<cód> - <BANCO> - AG: <ag> CC: <conta> <finalidade>"`) e **Aplicações Financeiras**.
- Botão **Novo**: Receita (TES01703), Despesa (TES01702), Despesa em Lote (TES01705), Movimentação Interna (TES01704). **Imprimir**: PDF/Excel.

## TES01703 — Receita (novo)

| Campo | Elemento | Obs. |
|---|---|---|
| Origem | `#f_pessoa` | opcional |
| Receita * | `select#f_receita` | conta de receita (~42) |
| Histórico * (crédito) | `select#f_historico_credito` | ~112 históricos |
| Centro Custo * | — | bloqueado = localidade ativa |
| Data Recebimento * | `#f_data` | |
| Forma Recebimento | `select#f_formapagamento` | Dinheiro, Cheque, Transf. Bancária, TED, DOC, Crédito em Conta, PIX |
| Nº Documento * | `#f_documento` | |
| Valor * | `#f_valor` | máscara `R$` |
| Conta * | `select#f_conta` | carrega após escolher a receita |
| Histórico * (débito) | `select#f_historico_debito` | |
| Complemento | `#f_complemento` | |
| Anexos | `#f_anexos` (file) | |

Botões: Salvar, Salvar e Novo, Cancelar. O bot usa esta tela para rendimentos de aplicação (XLS Sicredi).

## TES01704 — Movimentação Interna (novo)

Transferência entre contas (aplicações e resgates do extrato).
- Cabeçalho: Data * `#f_data`, Forma Transferência `select#f_formapagamento` (inclui SAQUE), Nº Documento `#f_documento`, Valor * `#f_valor`, Favorecido * `#f_nomefavorecido`.
- **Origem**: Conta * `select#f_contaorigem`, Histórico * `select#f_historicoorigem`, Complemento `#f_complementoorigem`.
- **Destino**: Conta * `select#f_conta`, Histórico `select#f_historico` (**bloqueado**, fixo em "032 - TRANSFER..."), Complemento `#f_complemento`.

## TES01502 — Contas a Pagar › Provisão (novo)

Usada para as faturas de energia.
- Data Lançamento * `#f_lancamento`, Data Documento * `#f_emissao`, Tipo Documento * `select#f_tipodocumento` (Aviso de Débito, Conhecimento de Transporte, Contrato, Cupom Fiscal, Declaração de Trânsito, Guia, Nota Fiscal, Nota Serviço, Pedido de Compra, Recibo), Nº Documento * `#f_documento`, Valor * `#f_valor`.
- **Rateio** (linha despesa × centro de custo): `select#f_despesa_rateio` (~163 contas de despesa, ex.: 3006 Energia Elétrica), `select#f_centrocusto_rateio` (ADM + localidades `BR 10-XXXX - <nome>`), `#f_percentual_rateio`, `#f_valor_rateio`.
- **Fornecedor**: Select2 AJAX (`f_fornecedor`), com link "Novo Fornecedor".
- **Parcelas**: `select#f_parcelas` (001–240). Cada parcela N tem `#f_parcela_N` (bloqueado), `#f_datavencimento_N`, `#f_valor_N` e `#f_observacao_N`; o bot usa só a parcela 1.
- **Provisionamento**: Conta de Provisão * `select#f_credito` (200 Fornecedores, 2000 Fornecedores Materiais Diversos...), Histórico * `select#f_historico`.
- Anexos `#f_anexos`; Salvar / Salvar e Novo.

## TES01501 — Contas a Pagar (consulta)

- Grade: Dt. Docto, Dt. Vcto, Parcela, Nº Doc., Fornecedor, Nº Pedido, Origem (Documento/Provisão), Vlr. Parcela, Vlr. Pago, Vlr. a Pagar, Status (ex.: Pago). Paginação de 10/25/50/100, busca livre, checkbox por linha (`f_lista`).
- Botões: **Novo** (Provisão TES01502, Adiantamento TES01512), **Filtros** (modal `form#f_main`: Tipo Período, Período, Fornecedor, Conta Provisão, Centro Custo, Valor Fatura, Agrupamento, Status da Fatura; botão Consultar), Imprimir, Pagos Rateio, **Manutenções** (Aprovar/Desaprovar em Lote, Baixar em Lote Agrupado/Individual).
- Opções por linha: Visualizar, Estornar (TES01507), Imprimir, Anexos.
- O bot usa esta tela para checar duplicidade e para a auditoria final das faturas.
- **Ciclo da provisão** (levantado em 23/10/2026, só consulta): status **Lançado** → **Aprovado** → **Pago** (ou Pago Parcialmente). As opções por linha mudam com o status:
  - Lançado: Visualizar, Editar (TES01505), Excluir (TES01504), **Aprovar (TES01508)**, Anexos;
  - Aprovado: Desaprovar (TES01509), **Baixar (TES01506)**;
  - Pago: Visualizar, Estornar (TES01507), Anexos.

  Os links levam `?codigo=<GUID da parcela>`. As faturas de energia lançadas pelo AutoSIGA ficam como **Lançado**, então só podem ser baixadas depois de aprovadas.

- Filtros (`form#f_main`): `f_tipodata` (Dt. Vcto, Dt. Emissão, Dt. Lcto, Dt. Pagamento), `f_data1`/`f_data2`, `f_fornecedor`, `f_contaprovisao`, `f_centrocusto`, `f_valorfatura1`/`f_valorfatura2`, `f_agrupamento`, `f_statusfatura` (Aprovado, Lançado, Pago, Pago Parcialmente).
- Visualizar (modal TES01503): rateio (despesa 3006 - ENERGIA ELÉTRICA e centro de custo), pagamentos parciais (data, valor pago, multa, juros, desconto, total) e anexos. Não mostra a forma nem a conta de pagamento.

## TES01508 — Aprovar provisão (formulário, testado em 23/10/2026)

- Abrir `TES01508.aspx?codigo=<GUID>` **não aprova**: é um formulário de confirmação.
- Só leitura: `#f_lote`, `#f_documento` (Nº Doc., o número da fatura), `#f_valor`, rateio, `#f_credito` (conta provisão), `#f_historico`, fornecedor, `f_dataVencimento`, observação e anexos. O formulário `form#f_main` (POST para a própria página) leva os hidden `f_codigo=<GUID>` e `gravar=S`.
- Único campo editável: `#f_motivo` (textarea, opcional).
- O botão verde **Aprovar** (submit, sem id) grava. Em seguida aparece o bootbox "Informações armazenadas com sucesso!" (botão Ok, `data-bb-handler="botao"`); o Ok volta para a TES01501, onde a linha passa a **Aprovado**, com Desaprovar e Baixar.
## Como o extrato vira lançamento no SIGA (ADM, levantado em 23/10/2026)

Cruzamento do OFX de maio/2026 de uma conta corrente da ADM com a grade da TES01701 (data e valor, um a um): 328 de 331 movimentos tinham par exato. O que cada movimento do banco vira:

| Movimento no OFX (`MEMO`) | No SIGA (origem · histórico) | Quem lança hoje |
|---|---|---|
| `RECEBIMENTO PIX…` (ofertas) | OFERTA · DEPÓSITO/PIX - OFERTA | AutoSIGA (TXT na TES05602) |
| `APLICACAO FINANCEIRA` / `RESG.APLIC…` | CAIXAS · APLICAÇÃO / RESGATE | AutoSIGA |
| `LIQUIDACAO BOLETO…` (traz CNPJ e nome do beneficiário) | FATURA · NF … (baixa de provisão) | manual |
| `PAGAMENTO PIX…` a fornecedor (traz CNPJ/CPF e nome) | FATURA · NF … (baixa) ou LANÇAM · PGTO.RECIBO | manual |
| `DEB.CTA.FATURA-…` (fatura do cartão, 1 débito) | FATURA · PGTO FAT. CARTÃO, **uma baixa por compra** no mesmo dia, somando o débito | manual |
| `DEBITO CONVENIOS-ENERGI 70 ID <código> ENERGISA…` | até jun/2026: CAIXAS · PGTO.GUIA ENERGISA; desde jul/2026: FATURA · NF (baixa da provisão) | manual |
| `DEBITO ARRECADACAO-DARF…`, guias ISSQN/FGTS | LANÇAM · PGTO.GUIA | manual |
| PIX/TED a pessoas (salário, férias) | LANÇAM · PGTO.RECIBO SALARIO/FERIAS | manual |
| `TRANSF ENTRE CONTAS` / PIX de outra administração | TRANSF · TRANSF.VLR DOC | manual |

- O `<código>` do débito de energia é o **código de débito automático da UC**, impresso na fatura ("DÉBITO AUTOMÁTICO UTILIZANDO O CÓDIGO: 0000000000-0"; sem o traço, é o ID do OFX).
- Energia: as faturas das casas de oração são baixadas na conta corrente de **manutenção**, uma baixa por fatura, no dia do débito (dia 26); a da ADM, na conta regional, no vencimento (dia 22). De jul a set/2026, 80 faturas foram baixadas assim.
- Lançamentos manuais às vezes ficam com data diferente da do banco (1 a 2 dias, fim de semana): a comparação de "sem par" precisa de tolerância de data.

## TES01506 — Baixar provisão (formulário)

- Cabeçalho só para leitura (lote, datas, documento, valor, conta provisão, fornecedor, parcela, vencimento). Campos da baixa: `#f_datapagamento` (obrigatório), `#f_valorapagar` (obrigatório, vem com o saldo), `#f_multa`, `#f_juros`, `#f_desconto` e `#f_total` calculado.
- **Novo Pagamento** abre um modal: `#f_codigoFormaPgto` (11 Adiantamento, 2 Cheque, **9 Débito Automático**, 1 Dinheiro, 8 Pgto. Eletrônico, 14 PIX, 5 Transf. Bancária, 7 DOC, 6 TED), `#f_valorpagamento`, `#f_conta` (Conta de Pagamento: as 101 e 103 da localidade, carregadas depois de escolher a forma), `#f_historicobaixa` (ex.: 023 - PGTO.NF., 026 - PGTO.DUPL.), `#f_complementobaixa`; cheque, banco/agência/conta e nº do documento aparecem conforme a forma. **Inserir** põe o pagamento na grade (Forma, Conta, Valor) e **Confirmar** grava a baixa. Aceita anexo do comprovante (`#f_anexos`).
- Uma provisão aceita vários pagamentos (parciais). Abrir o formulário e sair sem Confirmar não grava nada.

## TES05601 / TES05602 — Importação Extrato (front novo)

- Consulta: Número, Data, Nome Arquivo (`AAAA/M - AAAAMMDD_HHMMSS`), Valor; botões Novo, Filtros e Exportar.
- **Novo** abre o modal "Importar Extrato" (TES05602): Data, Banco (select) e Histórico **fixo em "156 - DEPÓSITO/PIX - OFERTA PIEDADE/DIVERSOS"**, além do anexo do arquivo. Botões: Salvar e Novo, Salvar e Fechar, Fechar.
- O bot (`bot/ofertas.py`, botão "Importar Ofertas no SIGA") importa aqui um TXT por conta corrente: Data = último dia do mês do extrato, Banco = opção que contém o código mapeado no card (ex.: `10130`). Pula quando a grade já tem a mesma data e valor, e audita se surgiu uma linha nova com o valor total.
- O Banco lista só as contas que recebem ofertas da localidade ativa (hoje 10129, 10130 e 10315).

## CTB00301 — Plano de Contas (consulta)

Menu Contabilidade › Cadastros › Plano de Contas. Nem todo usuário tem acesso; quem tem vê o plano inteiro, de qualquer localidade ativa.
- Grade `#grid1` (DataTables **server-side**, ~491 registros, paginada): Cód. Reduzido (`"101 30"` = grupo + sufixo, equivale ao código `10130` da Tesouraria), Cód. Contábil (`1.1.1.02.55`), Nome, **Localidade** (`ADM - DOURADOS - MS`, `DR - DOURADOS`, `PIA - DOURADOS` ou lista de tipos `ADM, SET, PIA...` nas contas genéricas), Cust, TES, CTB, Status.
- A busca livre `CC:` (`jQuery('#grid1').dataTable().fnFilter('CC:')`) traz numa página só todas as contas bancárias ativas (101 corrente e 103 aplicação) **com a localidade dona**, inclusive as das localidades que o usuário não abriu. É a melhor fonte para descobrir conta → localidade.

## Contas por localidade (TES01701)

Levantado em 23/10/2026.
- O `select#f_conta` lista só as contas da **localidade ativa**: na DR aparecem só as contas da DR; na PIA, só as da PIA. Exceção: a ADM também lista a conta corrente da DR (10127), mas não a aplicação dela.
- Contas desativadas ficam num `<optgroup label="INATIVO">`; a Contabilidade não as mostra.
- Os rótulos são texto livre e variam (`AG:0101` / `AG: 0101`, CC com e sem hífen, `CC: CONTA CAPITAL`): compare só os dígitos.
- Uma conta corrente pode ter várias contas 103 (ex.: aplicação e poupança da mesma CC).
- **Troca de localidade**: no modal "Outros Meses" há dois `form.modal-form`; o certo é o que contém `select[name="f_estabelecimento"]` (o outro recusa com "Formulário incompleto"). Depois de Confirmar, o SIGA redireciona para `/SIS/SIS99908.aspx`; é preciso abrir a rotina de novo. O AutoSIGA sempre desmarca `#f-mudarpadrao` ("lembrar a escolha"): a troca vale só para a sessão e não altera a localidade padrão do usuário.
- O modal lista ADM, DR, PIA, SEC, setores e casas de oração. Ainda não foi visto o comportamento de um usuário sem acesso a uma localidade (o levantamento teve acesso a todas).

## Ainda não levantado

Despesa (TES01702), Despesa em Lote (TES01705), Repartição Ofertas, Boletos, Cartão de Débito e Transferências, Fech. Administração (TES02301) e os relatórios.
