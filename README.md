# AutoSIGA v1.8.0 🚀

**AutoSIGA** é um motor avançado de RPA (Robotic Process Automation) construído em Python, voltado para a automatização e conciliação de tesourarias baseadas nas regras IT.TES.05. Ele cruza digitalmente extratos bancários brutos (`.OFX`) com o painel contábil administrativo SIGA (Sistema de Informação e Gestão), injetando dados, poupando centenas de horas humanas e reduzindo a taxa de erros a zero.

## 🎯 Por que o AutoSIGA existe?
A conciliação bancária entre múltiplas jurisdições (como a de Administração/Conta Corrente e de Ponto de Pregação/Fundo de Aplicação) no SIGA era uma tarefa manual, exaustiva e suscetível à desorganização humana. O AutoSIGA atua como um robô que enxerga o sistema exatamente como você.

## ✨ Destaques da Versão v1.8.0

- **Contas do SIGA Descobertas Sozinhas**: O botão **Buscar no SIGA** lê as contas bancárias direto do SIGA, só para leitura: pelo Plano de Contas da Contabilidade e, para quem não tem esse acesso, pela Caixas e Bancos de cada localidade (ADM, DR e PIA). No fim o SIGA volta à localidade e ao mês em que o usuário estava, sem alterar a localidade padrão dele. Cada card de extrato já vem com a localidade, a C. Corrente e a C. Aplicação sugeridas.
- **Card Guiado, sem Digitação**: As contas são escolhidas em listas que mostram o código e a finalidade (ex: `10396 · APLICACAO`). A C. Corrente só aceita contas 101 e a C. Aplicação só contas 103, então inverter os campos fica impossível. Um selo com ícone e texto mostra o estado do card (Confirmado, Sugerido pelo SIGA, Escolha necessária, Revisar, Não encontrado), com o motivo da sugestão logo abaixo. Quando há empate (ex: aplicação e poupança da mesma conta), o AutoSIGA não escolhe e pede a escolha ao usuário. O botão **Confirmar sugestões** confirma o lote de uma vez.
- **Conciliação Protegida**: A conciliação só é liberada com todos os cards confirmados. Um mapeamento antigo com conta inativa ou de outra localidade fica como **Revisar** até ser corrigido.
- **Troca de Localidade Corrigida**: O robô passa a usar o formulário do modal "Outros Meses" que contém a localidade e envia os valores ao SIGA como dados, sem montá-los dentro do código JavaScript.

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
