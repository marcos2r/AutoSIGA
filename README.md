# AutoSIGA v1.14.0 🚀

**AutoSIGA** é um motor avançado de RPA (Robotic Process Automation) construído em Python, voltado para a automatização e conciliação de tesourarias baseadas nas regras IT.TES.05. Ele cruza digitalmente extratos bancários brutos (`.OFX`) com o painel contábil administrativo SIGA (Sistema de Informação e Gestão), injetando dados, poupando centenas de horas humanas e reduzindo a taxa de erros a zero.

## 🎯 Por que o AutoSIGA existe?
A conciliação bancária entre múltiplas jurisdições (como a de Administração/Conta Corrente e de Ponto de Pregação/Fundo de Aplicação) no SIGA era uma tarefa manual, exaustiva e suscetível à desorganização humana. O AutoSIGA atua como um robô que enxerga o sistema exatamente como você.

## ✨ Destaques da Versão v1.14.0

- **Tarifas Bancárias Lançadas pelo Robô**: Cada tarifa do extrato sem lançamento no SIGA (ex.: `CESTA DE RELACIONAMENTO`) vira uma despesa na `TES01702` com despesa `3030 - DESPESAS BANCARIAS`, histórico `012 - DESP.BANCÁRIAS`, aviso de débito, débito automático e centro de custo ADM. O fornecedor é pesquisado pelo banco da conta (código do extrato) e, entre os resultados, fica o da cidade da administração; banco sem fornecedor fica pendente. Depois o robô relê o extrato do SIGA e refaz a prova real.
- **Transferências entre Contas como Movimentação Interna**: As duas pontas de cada `TRANSF ENTRE CONTAS` do lote são juntadas pelo código da operação (`SI…`), pela data e pelo valor, e a transferência é gravada uma vez só, pela conta de origem, na `TES01704` (histórico `032 - TRANSF.VLR`). Ponta sem par no lote ou de outra localidade vira aviso no painel com o motivo.
- **Recebimentos de Outras Administrações Confirmados**: Crédito de outra administração no extrato é casado com o `Pendente Recebimento` da `TES01301` (mesmo valor, data perto da emissão), e o robô confirma na `TES01313` com a data do extrato, o código da operação e a conta onde o dinheiro entrou. Remessas enviadas continuam com a tesouraria.
- **Conciliação no Modelo do FOR.TES.02**: Nova aba `Conciliação FOR.TES.02` no Excel do painel final, com as 10 linhas do formulário por conta (saldo do extrato, depósitos e débitos não contabilizados, saldo do SIGA e o que ficou sem explicação).
- **Avisos no Painel Final**: Aplicação com saldo e sem rendimento no mês, e tarifa do banco sem lançamento no SIGA, aparecem como aviso no cartão da conta. O cabeçalho de cada conta passa a mostrar o nome dela no SIGA e banco, agência e conta (`10123 · MANUTENCAO · SICREDI ag. 0903 c/c 58414-1`).
- **Classificador Único das Linhas do Extrato**: Um só módulo decide o que cada linha é (oferta, aplicação, tarifa, boleto, guia, cota capital, transferência…), com as regras em `regras_extrato.json`. Comparado em 1.318 linhas de extratos reais, o TXT de ofertas saiu idêntico ao anterior.
- **Interface Mais Simples e Acessível**: Um único botão principal (`Conciliar no SIGA`), confirmação antes de apagar (tecla Esc e `Limpar`), contraste WCAG AA em todas as cores (com teste automático), avisos de sucesso na barra de status em vez de janelas com OK, cards confirmados recolhidos numa linha, etapas 1-2-3 numa linha só e atalhos visíveis nos botões. Tudo cabe na janela mínima de 880x520.
- **Correções**: O Select2 espera a tela de "Aguarde" do SIGA sumir antes de cada tentativa (uma fatura de energia da ADM falhava por isso), e a gravação recusada pelo SIGA ("Formulário Incompleto") passa a parar com print e mensagem, em vez de contar como gravada.

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
