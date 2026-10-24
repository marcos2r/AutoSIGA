# AutoSIGA v1.10.0 🚀

**AutoSIGA** é um motor avançado de RPA (Robotic Process Automation) construído em Python, voltado para a automatização e conciliação de tesourarias baseadas nas regras IT.TES.05. Ele cruza digitalmente extratos bancários brutos (`.OFX`) com o painel contábil administrativo SIGA (Sistema de Informação e Gestão), injetando dados, poupando centenas de horas humanas e reduzindo a taxa de erros a zero.

## 🎯 Por que o AutoSIGA existe?
A conciliação bancária entre múltiplas jurisdições (como a de Administração/Conta Corrente e de Ponto de Pregação/Fundo de Aplicação) no SIGA era uma tarefa manual, exaustiva e suscetível à desorganização humana. O AutoSIGA atua como um robô que enxerga o sistema exatamente como você.

## ✨ Destaques da Versão v1.10.0

- **Faturas de Energia Baixadas pelo Extrato**: Em cada extrato de conta corrente, o robô reconhece os débitos automáticos da Energisa e, antes de conciliar, aprova e baixa a fatura certa na Contas a Pagar: data do débito, forma Débito Automático, conta do extrato e histórico 021. Com isso, a conciliação e a prova real passam a encontrar a saída no SIGA. A opção **Baixar as faturas de energia debitadas no extrato** vem ligada.
- **Três Chaves antes de Baixar**: O débito traz o código de débito automático da UC, o mesmo impresso no PDF da fatura. O robô só baixa quando o código, o valor e o número da fatura apontam para uma única fatura em aberto no SIGA. Empate, valor diferente (possível multa ou juros), débito estornado, fatura sem PDF ou não lançada viram pendência explicada, sem gravar nada. Fatura já paga não é baixada de novo.
- **Prévia das Baixas**: Com **Revisar as provisões e baixas de energia antes de gravar** (ligada por padrão), o robô mostra as faturas que vai aprovar e baixar e só grava com **Aprovar e baixar N fatura(s)**.
- **Cada Passo Conferido**: Antes de gravar, o robô confere na tela o número da fatura, o valor, a grade de pagamentos e o saldo restante. Depois de gravar, relê a Contas a Pagar para confirmar que a fatura ficou "Pago".
- **Rastro no SIGA**: A aprovação grava no Motivo quem aprovou e a prova (valor, data, conta e código de débito do extrato), e a baixa leva o complemento "Débito automático".
- **Painel e Excel**: O painel mostra, por extrato, quantas faturas foram baixadas e cada pendência com o motivo. O Excel ganha a aba **Baixas de Energia**.
- **Prova Real com Tolerância de Data**: Um lançamento manual com até 3 dias de diferença do banco (fim de semana, feriado) deixa de aparecer como "sem par no banco".
- **Provisões de Energia pelo E-mail**: Com o e-mail conectado, o robô começa o lote de extratos buscando no Gmail todas as faturas de energia emitidas nos meses dos extratos (e no mês anterior), lidas ou não. As que ainda não estão na Contas a Pagar são provisionadas na competência da emissão, debitadas ou não. Pelo regime de competência, a provisão nasce no mês da fatura e a baixa vem com o débito. Sem e-mail conectado, a etapa é pulada com aviso.
- **Nunca Provisionar Duas Vezes**: O AutoSIGA roda em várias máquinas da mesma administração, então o SIGA é a única referência. Antes de gravar cada fatura, o robô confere a Contas a Pagar e reconhece tanto a provisão lançada por ele (mesmo número da fatura) quanto a lançada à mão (código de débito da UC no Nº Doc. e mesmo valor). Se não conseguir conferir, não lança. A grade da Contas a Pagar passa a ser lida inteira, e não só as 100 primeiras linhas.
- **Prévia e Painel das Provisões**: A caixa **Revisar as provisões e baixas de energia antes de gravar** também mostra as faturas a provisionar antes de gravar. O painel final ganha a seção **Provisões de energia**, com o número de faturas lançadas e das que já estavam no SIGA, e cada pendência com o motivo (UC sem localidade, competência fechada, fatura lançada duas vezes no SIGA).
- **De Onde Vem a Diferença**: Na prova real, cada extrato mostra conta, localidade, tipo e período. Quando o saldo não fecha, o painel separa a diferença pela origem: lançamentos do SIGA sem par no banco (um a um), débitos de energia ainda sem baixa, outros movimentos do banco sem lançamento no SIGA e o que os movimentos do período não explicam (saldo inicial diferente ou lançamento fora do período). A aba **Prova Real** do Excel ganha as colunas Tipo e Período e lista cada item com a origem e o efeito na diferença. O painel final abre maximizado, com as métricas à esquerda e as provisões e a prova real à direita, um cartão por extrato e borda vermelha no que pede atenção.
- **Extrato de Conta Corrente em XLS**: O XLS de conta corrente do Sicredi passa a ser lido como o OFX, com os mesmos movimentos, saldo e período. Se o OFX e o XLS da mesma conta e mês vierem juntos, o lote fica só com o OFX. O XLS corta a descrição do banco e, com ela, o código de débito automático da energia: nesse caso a fatura não é baixada e aparece como pendência pedindo o OFX.
- **Prévia dos Lançamentos Sempre Ligada**: A caixa **Revisar os lançamentos antes de gravar no SIGA** sai da tela. O robô sempre mostra o que vai lançar em cada extrato e só grava com **Lançar N itens**, para ninguém gravar em duplicidade sem ver.
- **UC sem Localidade Perguntada no Começo do Lote**: Fatura de UC sem localidade é perguntada logo depois do download do e-mail, antes de abrir o SIGA, com a opção de pular.
- **SIGA Continua Aberto Depois do Robô**: O Edge do AutoSIGA passa a ser um programa à parte. Ao terminar o lote, ou ao fechar o AutoSIGA, ele continua aberto e logado para consultar os lançamentos ou seguir trabalhando no SIGA. Na execução seguinte, o robô reaproveita essa mesma janela, sem novo login.

Histórico completo das versões em [docs/CHANGELOG.md](docs/CHANGELOG.md). Arquitetura em [docs/arquitetura.md](docs/arquitetura.md).

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
# Instalar dependências do app + pytest, ruff e mypy
venv\Scripts\pip install -r requirements-dev.txt

# Executar a suíte de testes
venv\Scripts\python -m pytest tests/
```

## 📜 Licença e Origem
Desenvolvido incansavelmente pela equipe técnica autônoma da **CCB Dourados/MS**, garantindo o sigilo, fidelidade de roteamento IP interno e segurança máxima.
Uso interno estabelecido sob licença GNU GPL v3.0 mod.
