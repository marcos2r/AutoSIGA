# AutoSIGA v1.15.0 🚀

**AutoSIGA** é um motor avançado de RPA (Robotic Process Automation) construído em Python, voltado para a automatização e conciliação de tesourarias baseadas nas regras IT.TES.05. Ele cruza digitalmente extratos bancários brutos (`.OFX`) com o painel contábil administrativo SIGA (Sistema de Informação e Gestão), injetando dados, poupando centenas de horas humanas e reduzindo a taxa de erros a zero.

## 🎯 Por que o AutoSIGA existe?
A conciliação bancária entre múltiplas jurisdições (como a de Administração/Conta Corrente e de Ponto de Pregação/Fundo de Aplicação) no SIGA era uma tarefa manual, exaustiva e suscetível à desorganização humana. O AutoSIGA atua como um robô que enxerga o sistema exatamente como você.

## ✨ Destaques da Versão v1.15.0

- **Extrato do SIGA Lido Uma Vez por Conta**: A grade da `TES01701` é lida no começo de cada extrato e vira uma matriz em memória. Cada aplicação, resgate, recebimento, transferência e tarifa gravada entra nessa matriz, e as etapas seguintes decidem por ela, sem reconsultar o SIGA entre uma e outra. No fim, uma única releitura confere tudo e faz a prova real; só ela pode pedir nova tentativa do que faltou, com a mesma trava contra lançamento em dobro. Eram de 2 a 7 consultas por extrato de conta corrente; agora são no máximo 2 (uma só quando não há nada a gravar).
- **Prováveis Duplicidades com Pedido de Exclusão**: Na prova real, lançamento do SIGA sem par no banco que repete outro já pareado (mesmo valor, data até 3 dias e histórico igual) aparece como "Excluir no SIGA" no cartão da conta, com o número do lançamento (`Lançto`) a excluir e o que fica, e na nova aba `Excluir no SIGA` do Excel. Valores iguais que também se repetem no banco (duas tarifas no mesmo dia) não são apontados. O robô só aponta: a exclusão fica com o usuário.
- **Tempo por Etapa**: O lote mede quanto tempo gasta em cada etapa (consulta da TES01701, lançamentos, baixas, troca de localidade, tarifas...) e grava o total e a média no log e na nova aba `Tempos por Etapa` do Excel, para mostrar onde ainda vale otimizar.
- **Menos Espera Fixa**: A abertura da `TES01701` e do filtro passa a esperar a tela de fato (página nova carregada, modal aberto com as contas) em vez de pausas fixas, que só voltam se a condição não vier. Saíram também a pausa de 2 s entre extratos e a de 2,5 s antes da conferência.
- **Correção**: O total de lançamentos gravados passa a ser contado a cada gravação confirmada; antes, uma falha no meio contava zero e o navegador fechado no meio contava todos.

Histórico das versões anteriores em [`docs/CHANGELOG.md`](docs/CHANGELOG.md).

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
