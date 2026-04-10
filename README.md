# 🚀 AutoSIGA - Motor de Automação de Tesouraria e Extratos

O **AutoSIGA** é uma interface de automação local (Desktop GUI), construída em Python, focada em mitigar drasticamente o trabalho manual do setor de Tesouraria na importação de extratos bancários, conciliação e geração de arquivos obrigatórios segundo a norma técnica **IT.TES.05**.

## 📖 Visão Geral

Essa ferramenta foi projetada para cruzar dados de extratos no formato `.OFX` com os registros online do portal SIGA. Ela se divide em duas potências interligadas:
1. **Verificador e Injetor Web (Playwright):** Um robô em navegador que bate linha a linha de um arquivo OFX contra a página online de Lançamentos de Resgaste e Aplicação. Onde não existe um registro, ele intercepta a interface via injeção JavaScript, auto-preenche o formulário e salva usando AJAX invisível ("Salvar e Novo").
2. **Exportador Formato Puro (Gerador TXT):** Capaz de escrutinar dezenas de transações PIX, boletos e transações diversas e exportar **somente** ofertas de depósitos válidas (limpando o extrato de transferências, rendimentos e tarifas).

---

## 🔥 Funcionalidades Principais

### 1. Injeção e Conciliação Super-Rápida
O robô extrai todas as informações de Data, Histórico, Valor e Complemento (descrição) de um `.OFX`. Ele faz login persistente, bypassa os Banners Informativos Ocultos do SIGA (pop-ups flutuantes interativos) e processa tudo diretamente do navegador:
- Navega para a aba de Lançamentos automaticamente.
- Seleciona as comboboxes de conta bancária complexas (onde há pesquisa AJAX) através de scripts manipulados com `playwright`.
- **Prova Real:** Finalizado o processo de injeção, ele re-analisa a tela da tabela pela segunda vez para certificar que 100% dos dados bateram, mostrando até `centavos` de divergências deixados para trás na conferência humana.

### 2. O Dólar do Tempo (Dashboard de Rendimento)
A cada execução finalizada ou relatório verificado sem alterações na malha, o sistema exibe um relatório visual elegante na tela focado em ganhos corporativos.
- **Transações Injetadas:** Número absoluto do lote processado no Banco de Dados.
- **Tempo Ocioso Removido da Máquina Humana:** Adotamos métricas justas (120s por preenchimento de modal e click online, mais 12s de checagem mental humana base a cada linha que o olho cruzaria PDF vs Tela). O robô emite estimativas precisas de Tempo Poupado (*Ex: 30 Lançamentos evitam 1h 12m na cadeira*).
- **Exportação do Gráfico:** Com a integração local usando *Pillow*, o robô recorta a precisão da tela visual desse resumo e exporta um arquivo `.JPG`, `.PNG` ou `.PDF` apresentável para a auditoria ou o WhatsApp rápido da coordenação.

### 3. Regras de Negócio e Conformidade Inflexíveis
Este robô reflete obrigações contábeis severas. Não basta copiar ou jogar na Web. 
- **O Fator do Histórico "002" e "031":** Em linhas negativas do Banco o robô escolhe nativamente a regra `002 - APLICAÇÃO FINANCEIRA`. Nas entradas positivas, a etiqueta é fixa e imutável para `031 - RESGATE DE APLICAÇÃO`.
- **Filtros Lexográficos Ofensivos (IT.TES.05):** Ao exportar os recebimentos (botão: `"Exportar TXT OFX"`), o aplicativo recusa de forma absoluta qualquer lançamento bancário que inicie ou contenha os radicais de expurgo:
  - `" DEP "` (Ex: Depósito Caixa Eletrônico ou Envolope físico).
  - `"TRANSF"` (Transferências inter-contas).
  - `"RESG."` ou `"RESGATE"` (Rendimentos da liquidez devolvidos).
  - `"APLICA"` (Aplicações noturnas automáticas).

---

## 🛠 Entendimento Técnico & Dependências

A infraestrutura foi montada sob Python 3 e encapsulada num `.venv` clássico local. Modificações são perfeitamente possíveis, mas instabilidades na plataforma central do SIGA (como mudanças no `ID` dos botões ou novas `<div>` modais) podem requerer calibração dos refletores DOM usados na rotina Playwright (`app.py` → `inserir_lancamentos_siga`).

**Principais bibliotecas instaladas recomendadas:**
```bash
pip install customtkinter playwright ofxparse Pillow
playwright install chromium
```

> **Aviso UX (Atenção Modais):** O AutoSIGA possui alertas (`CTkToplevel` e `messagebox`) que invocam nativamente argumentos orientados ao OS local (ex: `.attributes('-topmost', True)`). Devido a arquitetura imperativa web do Playwright que puxa foco ao carregar as strings da web, se esse parâmetro for removido em futuras formatações, os alertas críticos podem desaparecer nos bastidores atrás da aba maximizada do navegador.

## 🤝 Histórico de Lançamento
O sistema evoluiu partindo de um layout monolítico do *Tkinter* feio p/ o *CustomTkinter* limpo com temas harmoniosos.
Nenhuma mudança arquitetônica de conta foi feita fora do `.OFX`. E a regra de mapeamento de CC p/ SIGA se concentra totalmente no arquivo simples legível por fora `"config.json"`.

**Maintainer(s):** Marcos Ricardo Rodrigues

---

## ⚖️ Licenciamento e Isenção de Garantia

Este projeto está devidamente protegido sob a poderosa **GNU GPL v3.0**. Ele pode ser compartilhado gratuitamente, evoluído localmente ou estudado pela irmandade cooperativa. É expressamente **VEDADA** a sua comercialização de código fechado ("Closed Source Proprietary") ou derivações visando lucro.

> [!WARNING]
> **Aviso de Isenção de Garantia (As-Is):** 
> O *AutoSIGA* é entregue na configuração *"no estado em que se encontra"* (As-Is), sem garantias implicadas de adequação total às instabilidades ou futuras atualizações visuais do portal governante/institucional web. O desenvolvedor originário (`Marcos Ricardo Rodrigues`) fica permanentemente **isento de qualquer responsabilidade fiscal, contábil ou penal** advinda do intermédio dos processamentos, cruzamentos de dados ou importações. Cabe ao operador (Usuário Final) possuir prerrogativa administrativa e atestar pela Prova Real ou relatórios manuais se a automação espelhou fielmente os saldos da Tesouraria Local.
