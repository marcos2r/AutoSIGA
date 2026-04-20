# AutoSIGA v1.1.0 🚀

**AutoSIGA** é um motor avançado de RPA (Robotic Process Automation) construído em Python, voltado para a automatização e conciliação de tesourarias baseadas nas regras IT.TES.05. Ele cruza digitalmente extratos bancários brutos (`.OFX`) com o painel contábil administrativo SIGA (Sistema de Informação e Gestão), injetando dados, poupando centenas de horas humanas e reduzindo a taxa de erros a zero.

## 🎯 Por que o AutoSIGA existe?
A conciliação bancária entre múltiplas jurisdições (como a de Administração/Conta Corrente e de Ponto de Pregação/Fundo de Aplicação) no SIGA era uma tarefa manual, exaustiva e suscetível à desorganização humana. O AutoSIGA atua como um robô que enxerga o sistema exatamente como você.

## ✨ Destaques da Versão v1.1.0
- **Unificação Dinâmica de Telas Web**: O Bot abstrai atrasos do SIGA acessando portas nativas Javascript do sistema e fundindo escolhas de localidade e competência de uma vez só!
- **Mapeamento Cérebro Reverso**: Detecta qual Administração possui a conta bancária do seu arquivo OFX e **corrige a interface gráfica automática pra você** caso esbarre nos botões.
- **Leitura Extrema de Invisibilidade**: Tolerância absurda contra renderização corrompida de HTML do portal (ex: lançamentos manuais passados onde "Saídas" e "Entradas" viram fantasmas nulos na tela). Tudo mapeado, módulo matematicamente convertido e fechado.
- **Prevenção Interceptiva Contra Timeouts**: Se os clusters de banco de dados do SIGA demorarem a engolir "Salvar e Novo", o robô perfura bloqueios de transparência preta do backend usando força de evaluate.
- **Drenagem Órfã Chromium**: Trata o tráfego Playwright Edge para que nunca suba instâncias espelhadas e quebre os cookies se você clicar o botão múltiplas vezes num mesmo ciclo.

## 🛠️ Tecnologias Principais
* **`customtkinter` & `tkinter`**: Para proporcionar a face amigável (User Interface - Ui) do seu cockpit.
* **`playwright` (`sync_api`)**: Os olhos, pernas e braços que disparam gatilhos simulados do browser (No nosso caso `msedge`, via persistent context!).
* **`ofxparse`**: Canivete suíço de conversão estruturada de movimentações bancárias puras direto da agência.
* **`pyinstaller`**: Motor que compacta, emoldura e transforma o algoritmo python numa execução standalone executável pra levar em qualquer Windows.

## 🚀 Como gerar um novo executável (PyInstaller)?
Se você realizar edições, gerar a compilação local (.exe) exige certificar-se que os módulos de interface rodem lisos:
```powershell
# Usar o ambiente virtual ativo (venv)
pyinstaller --noconfirm --onedir --windowed --add-data "venv/Lib/site-packages/customtkinter;customtkinter/" app.py
```
> O executável será salvo dentro de `dist/app/app.exe`.

## 📜 Licença e Origem
Desenvolvido incansavelmente pela equipe técnica autônoma da **CCB Dourados/MS**, garantindo o sigilo, fidelidade de roteamento IP interno e segurança máxima.
Uso interno estabelecido sob licença GNU GPL v3.0 mod.
