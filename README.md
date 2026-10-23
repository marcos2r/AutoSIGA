# AutoSIGA v1.9.0 🚀

**AutoSIGA** é um motor avançado de RPA (Robotic Process Automation) construído em Python, voltado para a automatização e conciliação de tesourarias baseadas nas regras IT.TES.05. Ele cruza digitalmente extratos bancários brutos (`.OFX`) com o painel contábil administrativo SIGA (Sistema de Informação e Gestão), injetando dados, poupando centenas de horas humanas e reduzindo a taxa de erros a zero.

## 🎯 Por que o AutoSIGA existe?
A conciliação bancária entre múltiplas jurisdições (como a de Administração/Conta Corrente e de Ponto de Pregação/Fundo de Aplicação) no SIGA era uma tarefa manual, exaustiva e suscetível à desorganização humana. O AutoSIGA atua como um robô que enxerga o sistema exatamente como você.

## ✨ Destaques da Versão v1.9.0

- **Prova Real do Saldo**: Ao terminar cada extrato, o robô lê o saldo final da conta na Caixas e Bancos (TES01701) e o compara com o saldo do banco (OFX da conta corrente ou XLS da aplicação). O painel do lote ganha a seção **Prova real**, com uma linha por extrato: "✔ Saldo confere", "⚠ Diferença de R$ X" ou "— Não conferido" com o motivo. A prova real só lê: nada é lançado, apagado ou corrigido no SIGA.
- **Lançamentos do SIGA sem Par no Banco**: Além do que falta no SIGA, o robô passa a apontar o que sobra nele (lançamento duplicado, valor digitado errado, estorno esquecido), comparando data e valor um a um com o extrato. A lista aparece no painel e na nova aba **Prova Real** do Excel do lote.
- **Extratos sem Lançamento Novo também São Conferidos**: Um extrato sem nada a lançar (ex: aplicação sem rendimento no mês) entra no lote só para a prova real do saldo. Com o filtro manual de datas, o saldo não é conferido, porque um período parcial não fecha com o saldo do mês.
- **Nunca Lançar na Conta Errada**: Se a conta do card não aparece na lista da Caixas e Bancos da localidade, o extrato é pulado sem consulta e sem lançamento, e os itens ficam pendentes. Antes, o robô seguia e lançava na conta que já estava selecionada. A conta também passa a ser escolhida pelo código exato (`10130` não casa mais com `110130`), ignorando as inativas.
- **Rendimento do Dia 31 sem Duplicidade**: No extrato XLS de aplicação, a consulta ia só até o dia 30, e o rendimento do dia 31 era lançado de novo; em fevereiro a data nem existia. Agora vale o último dia real do mês.
- **Prévia Opcional dos Lançamentos**: Com a caixa **Revisar os lançamentos antes de gravar no SIGA** marcada (desligada por padrão), o robô mostra o que vai lançar em cada extrato, com a conta e a localidade, e só grava com **Lançar N itens**. **Pular este extrato** não grava nada.
- **Extrato de Capital Social Identificado**: O extrato de Capital Social é recusado com a mensagem "ainda não é suportado", em vez de um erro confuso sobre colunas.

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
