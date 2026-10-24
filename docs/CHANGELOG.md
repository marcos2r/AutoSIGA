# Changelog do AutoSIGA

Histórico das versões, da mais recente para a mais antiga. A versão atual é definida em `version.py`.

## v1.10.0

- **Faturas de Energia Baixadas pelo Extrato**: Em cada extrato de conta corrente, o robô reconhece os débitos automáticos da Energisa e, antes de conciliar, aprova e baixa a fatura certa na Contas a Pagar: data do débito, forma Débito Automático, conta do extrato e histórico 021. Com isso, a conciliação e a prova real passam a encontrar a saída no SIGA. A opção **Baixar as faturas de energia debitadas no extrato** vem ligada.
- **Três Chaves antes de Baixar**: O débito traz o código de débito automático da UC, o mesmo impresso no PDF da fatura. O robô só baixa quando o código, o valor e o número da fatura apontam para uma única fatura em aberto no SIGA. Empate, valor diferente (possível multa ou juros), débito estornado, fatura sem PDF ou não lançada viram pendência explicada, sem gravar nada. Fatura já paga não é baixada de novo.
- **Prévia das Baixas**: Com **Revisar as baixas de energia antes de gravar** (ligada por padrão), o robô mostra as faturas que vai aprovar e baixar e só grava com **Aprovar e baixar N fatura(s)**.
- **Cada Passo Conferido**: Antes de gravar, o robô confere na tela o número da fatura, o valor, a grade de pagamentos e o saldo restante. Depois de gravar, relê a Contas a Pagar para confirmar que a fatura ficou "Pago".
- **Rastro no SIGA**: A aprovação grava no Motivo quem aprovou e a prova (valor, data, conta e código de débito do extrato), e a baixa leva o complemento "Débito automático".
- **Painel e Excel**: O painel mostra, por extrato, quantas faturas foram baixadas e cada pendência com o motivo. O Excel ganha a aba **Baixas de Energia**.
- **Prova Real com Tolerância de Data**: Um lançamento manual com até 3 dias de diferença do banco (fim de semana, feriado) deixa de aparecer como "sem par no banco".
- **Extrato de Conta Corrente em XLS**: O XLS de conta corrente do Sicredi passa a ser lido como o OFX, com os mesmos movimentos, saldo e período. Se o OFX e o XLS da mesma conta e mês vierem juntos, o lote fica só com o OFX. O XLS corta a descrição do banco e, com ela, o código de débito automático da energia: nesse caso a fatura não é baixada e aparece como pendência pedindo o OFX.
- **Busca Completa no E-mail**: A importação de faturas da aba Energia passa a ler todas as páginas de resultados do Gmail. Antes, ela parava nas primeiras 100 mensagens.

## v1.9.0

- **Prova Real do Saldo**: Ao terminar cada extrato, o robô lê o saldo final da conta na Caixas e Bancos (TES01701) e o compara com o saldo do banco (OFX da conta corrente ou XLS da aplicação). O painel do lote ganha a seção **Prova real**, com uma linha por extrato: "✔ Saldo confere", "⚠ Diferença de R$ X" ou "— Não conferido" com o motivo. A prova real só lê: nada é lançado, apagado ou corrigido no SIGA.
- **Lançamentos do SIGA sem Par no Banco**: Além do que falta no SIGA, o robô passa a apontar o que sobra nele (lançamento duplicado, valor digitado errado, estorno esquecido), comparando data e valor um a um com o extrato. A lista aparece no painel e na nova aba **Prova Real** do Excel do lote.
- **Extratos sem Lançamento Novo também São Conferidos**: Um extrato sem nada a lançar (ex: aplicação sem rendimento no mês) entra no lote só para a prova real do saldo. Com o filtro manual de datas, o saldo não é conferido, porque um período parcial não fecha com o saldo do mês.
- **Nunca Lançar na Conta Errada**: Se a conta do card não aparece na lista da Caixas e Bancos da localidade, o extrato é pulado sem consulta e sem lançamento, e os itens ficam pendentes. Antes, o robô seguia e lançava na conta que já estava selecionada. A conta também passa a ser escolhida pelo código exato (`10130` não casa mais com `110130`), ignorando as inativas.
- **Rendimento do Dia 31 sem Duplicidade**: No extrato XLS de aplicação, a consulta ia só até o dia 30, e o rendimento do dia 31 era lançado de novo; em fevereiro a data nem existia. Agora vale o último dia real do mês.
- **Prévia Opcional dos Lançamentos**: Com a caixa **Revisar os lançamentos antes de gravar no SIGA** marcada (desligada por padrão), o robô mostra o que vai lançar em cada extrato, com a conta e a localidade, e só grava com **Lançar N itens**. **Pular este extrato** não grava nada.
- **Extrato de Capital Social Identificado**: O extrato de Capital Social é recusado com a mensagem "ainda não é suportado", em vez de um erro confuso sobre colunas.

## v1.8.0

- **Contas do SIGA Descobertas Sozinhas**: O botão **Buscar no SIGA** lê as contas bancárias direto do SIGA, só para leitura: pelo Plano de Contas da Contabilidade e, para quem não tem esse acesso, pela Caixas e Bancos de cada localidade (ADM, DR e PIA). No fim o SIGA volta à localidade e ao mês em que o usuário estava, sem alterar a localidade padrão dele. Cada card de extrato já vem com a localidade, a C. Corrente e a C. Aplicação sugeridas.
- **Card Guiado, sem Digitação**: As contas são escolhidas em listas que mostram o código e a finalidade (ex: `10396 · APLICACAO`). A C. Corrente só aceita contas 101 e a C. Aplicação só contas 103, então inverter os campos fica impossível. Um selo com ícone e texto mostra o estado do card (Confirmado, Sugerido pelo SIGA, Escolha necessária, Revisar, Não encontrado), com o motivo da sugestão logo abaixo. Quando há empate (ex: aplicação e poupança da mesma conta), o AutoSIGA não escolhe e pede a escolha ao usuário. O botão **Confirmar sugestões** confirma o lote de uma vez.
- **Conciliação Protegida**: A conciliação só é liberada com todos os cards confirmados. Um mapeamento antigo com conta inativa ou de outra localidade fica como **Revisar** até ser corrigido.
- **Troca de Localidade Corrigida**: O robô passa a usar o formulário do modal "Outros Meses" que contém a localidade e envia os valores ao SIGA como dados, sem montá-los dentro do código JavaScript. Deixa também de marcar "lembrar a escolha": a troca vale só para aquela sessão e não muda a localidade padrão do usuário.
- **Mês Fechado Pulado na Mesma Execução**: Quando o SIGA recusa um lançamento de extrato ou rendimento por competência fechada, o robô para de tentar aquele extrato e pula os outros da mesma localidade e mês, sem as 3 re-tentativas. O fechamento é por localidade: um mês fechado na PIA não impede a DR. A memória vale só para aquela execução; na próxima, o robô tenta de novo, porque o mês pode ter sido reaberto.
- **Janela Maximizada**: O AutoSIGA abre maximizado e lembra se o usuário preferiu a janela normal. Redimensionada, a janela não fica menor que 1000×680, para o card nunca esconder campos e botões. O tamanho passa a ser gravado só ao fechar, não a cada movimento da janela.
- **Tirar Extrato do Lote**: Cada card tem o botão "✕ Tirar do lote", para retirar um extrato (ex: conta que não existe no SIGA) e seguir com a conciliação dos demais, sem apagar mapeamentos.

## v1.7.0

- **Faturas de Energia Nunca Se Perdem**: Uma fatura de UC ainda não mapeada é gravada como pendente assim que chega. Fechar a pergunta de UC nova ou escolher "Deixar Pendente" não a descarta mais: ela aparece na seção **Faturas pendentes** da aba Energia (com atalho para abrir o PDF) e volta a ser perguntada a cada importação. Mapeando a UC (pela pergunta ou em "Mapear UCs"), ela é lançada na próxima importação. O descarte definitivo passa a exigir confirmação.
- **Anexo com Nome do Lançamento**: O PDF da fatura é anexado no SIGA com a conta de despesa e o centro de custo no nome (ex: `3006 - ENERGIA ELETRICA - BR 10-0516 - ADM DOURADOS.pdf`). O arquivo original em `faturas_energisa/` não é alterado.

## v1.6.2

- **Dados Preservados Entre Versões**: No executável, faturas de energia, logs e o `.env` passam a ficar ao lado do `AutoSiga.exe` (como o `config.json`), e não mais dentro da pasta interna `_internal`, que é substituída a cada atualização.

## v1.6.1

- **Suporte a Extratos OFX do Sicoob**: O leitor de OFX passa a aproveitar a tag `NAME`, onde bancos como o Sicoob (756) enviam o nome do pagador enquanto o `MEMO` traz apenas o tipo genérico da operação (ex: `PIX RECEBIDO - OUTRA IF`). O histórico exibido na conferência e exportado no TXT de ofertas agora segue o formato `MEMO - NAME`, enquanto os filtros de palavras-chave continuam avaliando somente o `MEMO`, evitando que nomes de pessoas sejam confundidos com aplicações ou resgates. Extratos sem `NAME` (como os do Sicredi) permanecem inalterados.
- **Proteção do `config.json`**: A gravação passa a ser atômica (arquivo temporário + substituição) e um arquivo ilegível é preservado como `config.json.corrompido-<data>` em vez de ser sobrescrito, evitando a perda dos mapeamentos de contas.
- **Release Corrigida e Dependências Fixadas**: O pipeline empacota a pasta completa do executável (`AutoSiga.exe` + `_internal`) e as versões das dependências foram fixadas no `requirements.txt` para builds reprodutíveis.

## v1.6.0

- **Verificação Preventiva de Credenciais**: O robô agora valida previamente se o usuário possui credenciais (usuário e senha) cadastradas no Windows Keyring ou no arquivo `.env` antes de abrir a janela do SIGA, solicitando o cadastro automático por meio de uma modal caso não estejam presentes.
- **Precisão no Volume Financeiro de Energia**: Correção do cálculo do volume financeiro total processado no lote de faturas de energia, que agora computa dinamicamente a soma dos valores reais apenas das faturas confirmadas e auditadas com sucesso, em vez de realizar um fatiamento sequencial estático do lote.

## v1.5.1

- **Visualização Amigável de Localidades**: Substituição completa dos códigos de banco de dados numéricos internos (como `435` ou `5588`) pelos códigos legíveis e familiares aos usuários (`BR 10-XXXX`) na primeira coluna das listagens.
- **Edição Direta de Registros**: Inclusão de botões **"Editar"** nos modais de Localidades e UCs, permitindo carregar registros de volta aos campos de entrada para alteração rápida.
- **Comboboxes Inteligentes e Ampliados**: Aumento de largura dos modais e dropdowns para exibição completa de descrições longas, além de formatação dinâmica exibindo `[Código] - [Nome]`.
- **Limpeza Automatizada de Configurações**: Script de migração nativo que converteu de forma transparente todos os registros e relacionamentos do cache `config.json` legados para os novos padrões de código.

## v1.5.0

- **Módulo de Lançamento de Faturas de Energia**: Automação ponta a ponta na leitura (via IMAP ou PDFs locais) de faturas de energia elétrica (Energisa/Sanepar), extração inteligente de dados (Código UC, Vencimento, Valor) por leitura do texto do PDF (`pypdf` + expressões regulares) e injeção massiva de contas a pagar (`TES01502`) no SIGA.
- **Auditoria Inteligente Final (Double Check)**: O robô executa uma validação rigorosa de segurança (auditoria) lendo a grade de dados do SIGA via `TES01501` após o encerramento do lote, atestando o sucesso das importações e alertando se alguma fatura falhou mesmo após a tela de sucesso.
- **Fail-fast de Mês Fechado e Duplicidades**: Trava de segurança inteligente em cache de memória que previne falhas consecutivas de faturas pertencentes ao mesmo mês bloqueado, e checagem preventiva cruzada para notas duplicadas.
- **Resiliência e Retries no Select2**: Mecanismo de até 3 tentativas automáticas e validação de estado pós-seleção nos campos Select2 do SIGA, minimizando falhas causadas por atrasos de renderização ou rede lenta.
- **Correção de Busca de Credenciais (Gmail)**: Correção do cálculo do diretório base no modo executável empacotado pelo PyInstaller, permitindo que o `credentials.json` seja localizado corretamente na pasta de execução.
- **Correção de Layout e Alinhamento**: Correção de bug visual que ocultava ou cortava o botão "Excluir" nas telas de gerenciamento de localidades e mapeamento de UCs devido à ordem incorreta de empacotamento (pack order).

## v1.4.0

- **Segurança de Credenciais (Windows Keyring)**: Armazenamento local de credenciais em repouso do SIGA de forma criptografada usando a API nativa do Windows (biblioteca `keyring`).
- **Interface Gráfica de Credenciais**: Nova modal interna no app para cadastrar/alterar usuário e senha do SIGA, removendo a necessidade de manipular arquivos de texto `.env`.

## v1.3.0

- **Suíte de Testes Automatizados**: Cobertura de testes unitários robusta com `pytest` para os módulos de negócio e leitores contábeis (`Conciliador`, `Exportador`, `OfxReader`, `XlsReader`).
- **Resiliência e Auditoria**: Registro de fotos da tela em caso de falha na pasta `logs/screenshots/`, detecção ativa de sessão expirada no SIGA e fail-fast robusto com Select2.

## v1.2.2

- **Bloqueio de Transferências**: Adicionada a palavra-chave `"TRANSFERENCIA"` à blacklist do exportador de ofertas no arquivo `.txt`, impedindo que movimentações identificadas como transferências sejam indevidamente processadas como ofertas puras de igreja no SIGA.

## v1.2.1

- **Refatoração do Mapeamento**: Migração completa do armazenamento de mapeamentos no `config.json` para uma lista de objetos JSON estruturada, eliminando bugs de parse em contas que contêm caracteres especiais como hífens (ex: `58308-2`). Inclui migração automatizada e transparente do banco de dados legado.
- **Otimização de UI Responsiva para Lotes**: Melhoria de layout na interface gráfica que resume a exibição de lotes com mais de 3 arquivos (exibindo `... + X outros` em uma única linha), impedindo a quebra de proporções da janela e o estrangulamento do scroll de cards.
- **Posicionamento e Geometria Persistentes**: O aplicativo agora detecta a resolução do monitor do usuário para se centralizar e dimensionar proporcionalmente no primeiro uso, além de salvar e restaurar automaticamente a última posição e tamanho utilizados ao ser fechado e reaberto.
- **Prevenção de Gravação Prematura**: Correção de bug no ciclo de vida do Tkinter no qual a inicialização de componentes dropdown disparava gravações parciais incorretas com localidade vazia no banco.

## v1.2.0

- **Arquitetura MVC:** Refatoração completa do código-fonte para o padrão Model-View-Controller, separando lógica de negócio, automação e interface.
- **Módulo de Automação Independente:** Robô Playwright agora isolado em `siga_bot.py`.
- **Melhoria na Manutenibilidade:** Código modularizado e documentado para facilitar futuras updates.
- **Suporte a Rendimentos de Aplicação (XLS Sicredi):** Detecção inteligente e processamento automatizado de planilhas XLS de aplicação (Poupança e CDB/RDC), conciliando e injetando rendimentos em lote na rotina de Receitas (`TES01703`) de forma robusta e transparente.
- **Isolamento de Contas por Produto de Investimento:** Segmentação inteligente no armazenamento local para que a mesma conta bancária possa ter mapeamentos de contas do SIGA totalmente independente para diferentes produtos (ex: CDB vs. Poupança).
- **Dashboard de Produtividade Avançado (ROI de Automação):** Apresentação interativa do tempo real economizado em conciliação.

