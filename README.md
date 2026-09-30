# AutoSIGA v1.6.2 🚀

**AutoSIGA** é um motor avançado de RPA (Robotic Process Automation) construído em Python, voltado para a automatização e conciliação de tesourarias baseadas nas regras IT.TES.05. Ele cruza digitalmente extratos bancários brutos (`.OFX`) com o painel contábil administrativo SIGA (Sistema de Informação e Gestão), injetando dados, poupando centenas de horas humanas e reduzindo a taxa de erros a zero.

## 🎯 Por que o AutoSIGA existe?
A conciliação bancária entre múltiplas jurisdições (como a de Administração/Conta Corrente e de Ponto de Pregação/Fundo de Aplicação) no SIGA era uma tarefa manual, exaustiva e suscetível à desorganização humana. O AutoSIGA atua como um robô que enxerga o sistema exatamente como você.

## ✨ Próxima Versão

- **Faturas de Energia Nunca Se Perdem**: Uma fatura de UC ainda não mapeada é gravada como pendente assim que chega. Fechar a pergunta de UC nova ou escolher "Deixar Pendente" não a descarta mais: ela aparece na seção **Faturas pendentes** da aba Energia (com atalho para abrir o PDF) e volta a ser perguntada a cada importação. Mapeando a UC (pela pergunta ou em "Mapear UCs"), ela é lançada na próxima importação. O descarte definitivo passa a exigir confirmação.
- **Anexo com Nome do Lançamento**: O PDF da fatura é anexado no SIGA com a conta de despesa e o centro de custo no nome (ex: `3006 - ENERGIA ELETRICA - BR 10-0516 - ADM DOURADOS.pdf`). O arquivo original em `faturas_energisa/` não é alterado.

## ✨ Destaques da Versão v1.6.2

- **Dados Preservados Entre Versões**: No executável, faturas de energia, logs e o `.env` passam a ficar ao lado do `AutoSiga.exe` (como o `config.json`), e não mais dentro da pasta interna `_internal`, que é substituída a cada atualização.

## ✨ Destaques da Versão v1.6.1

- **Suporte a Extratos OFX do Sicoob**: O leitor de OFX passa a aproveitar a tag `NAME`, onde bancos como o Sicoob (756) enviam o nome do pagador enquanto o `MEMO` traz apenas o tipo genérico da operação (ex: `PIX RECEBIDO - OUTRA IF`). O histórico exibido na conferência e exportado no TXT de ofertas agora segue o formato `MEMO - NAME`, enquanto os filtros de palavras-chave continuam avaliando somente o `MEMO`, evitando que nomes de pessoas sejam confundidos com aplicações ou resgates. Extratos sem `NAME` (como os do Sicredi) permanecem inalterados.
- **Proteção do `config.json`**: A gravação passa a ser atômica (arquivo temporário + substituição) e um arquivo ilegível é preservado como `config.json.corrompido-<data>` em vez de ser sobrescrito, evitando a perda dos mapeamentos de contas.
- **Release Corrigida e Dependências Fixadas**: O pipeline empacota a pasta completa do executável (`AutoSiga.exe` + `_internal`) e as versões das dependências foram fixadas no `requirements.txt` para builds reprodutíveis.

## ✨ Destaques da Versão v1.6.0

- **Verificação Preventiva de Credenciais**: O robô agora valida previamente se o usuário possui credenciais (usuário e senha) cadastradas no Windows Keyring ou no arquivo `.env` antes de abrir a janela do SIGA, solicitando o cadastro automático por meio de uma modal caso não estejam presentes.
- **Precisão no Volume Financeiro de Energia**: Correção do cálculo do volume financeiro total processado no lote de faturas de energia, que agora computa dinamicamente a soma dos valores reais apenas das faturas confirmadas e auditadas com sucesso, em vez de realizar um fatiamento sequencial estático do lote.

## ✨ Destaques da Versão v1.5.1

- **Visualização Amigável de Localidades**: Substituição completa dos códigos de banco de dados numéricos internos (como `435` ou `5588`) pelos códigos legíveis e familiares aos usuários (`BR 10-XXXX`) na primeira coluna das listagens.
- **Edição Direta de Registros**: Inclusão de botões **"Editar"** nos modais de Localidades e UCs, permitindo carregar registros de volta aos campos de entrada para alteração rápida.
- **Comboboxes Inteligentes e Ampliados**: Aumento de largura dos modais e dropdowns para exibição completa de descrições longas, além de formatação dinâmica exibindo `[Código] - [Nome]`.
- **Limpeza Automatizada de Configurações**: Script de migração nativo que converteu de forma transparente todos os registros e relacionamentos do cache `config.json` legados para os novos padrões de código.

## ✨ Destaques da Versão v1.5.0

- **Módulo de Lançamento de Faturas de Energia**: Automação ponta a ponta na leitura (via IMAP ou PDFs locais) de faturas de energia elétrica (Energisa/Sanepar), extração inteligente de dados (Código UC, Vencimento, Valor) por leitura do texto do PDF (`pypdf` + expressões regulares) e injeção massiva de contas a pagar (`TES01502`) no SIGA.
- **Auditoria Inteligente Final (Double Check)**: O robô executa uma validação rigorosa de segurança (auditoria) lendo a grade de dados do SIGA via `TES01501` após o encerramento do lote, atestando o sucesso das importações e alertando se alguma fatura falhou mesmo após a tela de sucesso.
- **Fail-fast de Mês Fechado e Duplicidades**: Trava de segurança inteligente em cache de memória que previne falhas consecutivas de faturas pertencentes ao mesmo mês bloqueado, e checagem preventiva cruzada para notas duplicadas.
- **Resiliência e Retries no Select2**: Mecanismo de até 3 tentativas automáticas e validação de estado pós-seleção nos campos Select2 do SIGA, minimizando falhas causadas por atrasos de renderização ou rede lenta.
- **Correção de Busca de Credenciais (Gmail)**: Correção do cálculo do diretório base no modo executável empacotado pelo PyInstaller, permitindo que o `credentials.json` seja localizado corretamente na pasta de execução.
- **Correção de Layout e Alinhamento**: Correção de bug visual que ocultava ou cortava o botão "Excluir" nas telas de gerenciamento de localidades e mapeamento de UCs devido à ordem incorreta de empacotamento (pack order).

## ✨ Destaques da Versão v1.4.0

- **Segurança de Credenciais (Windows Keyring)**: Armazenamento local de credenciais em repouso do SIGA de forma criptografada usando a API nativa do Windows (biblioteca `keyring`).
- **Interface Gráfica de Credenciais**: Nova modal interna no app para cadastrar/alterar usuário e senha do SIGA, removendo a necessidade de manipular arquivos de texto `.env`.

## ✨ Destaques da Versão v1.3.0

- **Suíte de Testes Automatizados**: Cobertura de testes unitários robusta com `pytest` para os módulos de negócio e leitores contábeis (`Conciliador`, `Exportador`, `OfxReader`, `XlsReader`).
- **Resiliência e Auditoria**: Registro de fotos da tela em caso de falha na pasta `logs/screenshots/`, detecção ativa de sessão expirada no SIGA e fail-fast robusto com Select2.

## ✨ Destaques da Versão v1.2.2

- **Bloqueio de Transferências**: Adicionada a palavra-chave `"TRANSFERENCIA"` à blacklist do exportador de ofertas no arquivo `.txt`, impedindo que movimentações identificadas como transferências sejam indevidamente processadas como ofertas puras de igreja no SIGA.

## ✨ Destaques da Versão v1.2.1

- **Refatoração do Mapeamento**: Migração completa do armazenamento de mapeamentos no `config.json` para uma lista de objetos JSON estruturada, eliminando bugs de parse em contas que contêm caracteres especiais como hífens (ex: `58308-2`). Inclui migração automatizada e transparente do banco de dados legado.
- **Otimização de UI Responsiva para Lotes**: Melhoria de layout na interface gráfica que resume a exibição de lotes com mais de 3 arquivos (exibindo `... + X outros` em uma única linha), impedindo a quebra de proporções da janela e o estrangulamento do scroll de cards.
- **Posicionamento e Geometria Persistentes**: O aplicativo agora detecta a resolução do monitor do usuário para se centralizar e dimensionar proporcionalmente no primeiro uso, além de salvar e restaurar automaticamente a última posição e tamanho utilizados ao ser fechado e reaberto.
- **Prevenção de Gravação Prematura**: Correção de bug no ciclo de vida do Tkinter no qual a inicialização de componentes dropdown disparava gravações parciais incorretas com localidade vazia no banco.

## ✨ Destaques da Versão v1.2.0

- **Arquitetura MVC:** Refatoração completa do código-fonte para o padrão Model-View-Controller, separando lógica de negócio, automação e interface.
- **Módulo de Automação Independente:** Robô Playwright agora isolado em `siga_bot.py`.
- **Melhoria na Manutenibilidade:** Código modularizado e documentado para facilitar futuras updates.
- **Suporte a Rendimentos de Aplicação (XLS Sicredi):** Detecção inteligente e processamento automatizado de planilhas XLS de aplicação (Poupança e CDB/RDC), conciliando e injetando rendimentos em lote na rotina de Receitas (`TES01703`) de forma robusta e transparente.
- **Isolamento de Contas por Produto de Investimento:** Segmentação inteligente no armazenamento local para que a mesma conta bancária possa ter mapeamentos de contas do SIGA totalmente independente para diferentes produtos (ex: CDB vs. Poupança).
- **Dashboard de Produtividade Avançado (ROI de Automação):** Apresentação interativa do tempo real economizado em conciliação.

## 🛠️ Tecnologias Principais
* **`customtkinter` & `tkinter`**: Para proporcionar a face amigável (User Interface - Ui) do seu cockpit.
* **`playwright` (`sync_api`)**: Os olhos, pernas e braços que disparam gatilhos simulados do browser (No nosso caso `msedge`, via persistent context!).
* **`ofxparse`**: Canivete suíço de conversão estruturada de movimentações bancárias puras direto da agência.
* **`xlrd`**: Módulo especialista em decodificar arquivos binários antigos (BIFF8) de planilhas do Excel.
* **`pyinstaller`**: Motor que compacta, emoldura e transforma o algoritmo python numa execução standalone executável pra levar em qualquer Windows.

## 🚀 Como gerar um novo executável (PyInstaller)?
Se você realizar edições, gerar a compilação local (.exe) exige certificar-se que os módulos de interface rodem lisos:
```powershell
# Usar o ambiente virtual ativo (venv)
pyinstaller --noconfirm AutoSIGA.spec
```
> O executável será salvo dentro de `dist/AutoSiga/AutoSiga.exe`.

## 🧪 Como rodar os testes automatizados (Pytest)?
Para rodar a suíte de testes unitários locais, utilize o pytest sob o ambiente virtual:
```powershell
# Instalar dependências
venv\Scripts\pip install -r requirements.txt

# Executar a suíte de testes
venv\Scripts\python -m pytest tests/
```

## 📜 Licença e Origem
Desenvolvido incansavelmente pela equipe técnica autônoma da **CCB Dourados/MS**, garantindo o sigilo, fidelidade de roteamento IP interno e segurança máxima.
Uso interno estabelecido sob licença GNU GPL v3.0 mod.
