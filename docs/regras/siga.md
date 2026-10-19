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
- **Avisos fixos**: um banner vermelho "O(s) mês(es) de MM/AAAA ainda não foram fechados!" e um de LGPD. Um mês **fechado** recusa lançamentos (o bot guarda as competências fechadas em cache).
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

## TES05601 / TES05602 — Importação Extrato (front novo)

- Consulta: Número, Data, Nome Arquivo (`AAAA/M - AAAAMMDD_HHMMSS`), Valor; botões Novo, Filtros e Exportar.
- **Novo** abre o modal "Importar Extrato" (TES05602): Data, Banco (select) e Histórico **fixo em "156 - DEPÓSITO/PIX - OFERTA PIEDADE/DIVERSOS"**, além do anexo do arquivo. Botões: Salvar e Novo, Salvar e Fechar, Fechar.
- O bot (`bot/ofertas.py`, botão "Importar Ofertas no SIGA") importa aqui um TXT por conta corrente: Data = último dia do mês do extrato, Banco = opção que contém o código mapeado no card (ex.: `10130`). Pula quando a grade já tem a mesma data e valor, e audita se surgiu uma linha nova com o valor total.
- O Banco lista só as contas que recebem ofertas da localidade ativa (hoje 10129, 10130 e 10315).

## Ainda não levantado

Despesa (TES01702), Despesa em Lote (TES01705), Repartição Ofertas, Boletos, Cartão de Débito e Transferências, Fech. Administração (TES02301) e os relatórios.
