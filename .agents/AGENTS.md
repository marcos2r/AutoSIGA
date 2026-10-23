# AutoSIGA — regras do projeto

Fonte única de instruções para qualquer IA (Antigravity lê direto; o `CLAUDE.md` da raiz só importa este arquivo). Mantenha-o curto: detalhe longo vai para `docs/` e é lido sob demanda.

RPA desktop para Windows (CustomTkinter + Playwright/Edge) que concilia extratos bancários (`.ofx`, `.xls` Sicredi) e faturas de energia (PDF via Gmail ou pasta local) com o sistema web SIGA, lançando o que falta.

## Comandos

```powershell
venv\Scripts\pip install -r requirements-dev.txt                 # app + pytest, ruff e mypy
venv\Scripts\python main.py                                    # roda o app
venv\Scripts\python -m pytest -q tests/                        # suíte completa (mesma do CI)
venv\Scripts\python -m pytest -q tests/test_conciliador.py::nome_do_teste   # teste único
venv\Scripts\ruff check .                                     # lint (--fix corrige o seguro)
venv\Scripts\mypy                                             # tipos (arquivos em pyproject.toml)
pyinstaller --noconfirm AutoSIGA.spec                          # build onedir em dist/AutoSiga/
```

A `venv` usa **Python 3.11**, igual ao CI e ao build (`uv python install 3.11`). Configuração de pytest, ruff e mypy no `pyproject.toml`; o mypy confere tudo em `controllers/` e `models/` (`check_untyped_defs`); em `bot/` e `ui/` ainda só as funções anotadas.

CI (`.github/workflows/ci_cd.yml`, Windows, Python 3.11): ruff, mypy e pytest em push/PR para `master`; tag `v*` gera o build e publica `AutoSiga_Windows.zip` (pasta inteira, com `_internal`) na Release.

## Arquitetura (MVC adaptado — detalhes em `docs/arquitetura.md`)

- `main.py`: ajusta `sys.path`, fixa o backend do `keyring` no Windows Credential Manager, carrega `.env` legado, configura log diário em `logs/` e abre `ui.main_window.MainWindow`.
- `models/`: só I/O, sem UI. `config_manager.py` é a persistência central em `config.json` (mapeamentos conta→SIGA, localidades, UCs, geometria da janela), com gravação atômica e backup de arquivo corrompido. As chaves de energia ficam no mixin `config_energia.py`. `faturas_pendentes.py` guarda faturas de UC não mapeada no mesmo `config.json`. Leitores: `ofx_reader`, `xls_reader`, `pdf_extractor` (pypdf + regex), `email_reader` (API do Gmail via `credentials.json`/`token.json`).
- `controllers/`: regras de negócio puras e testáveis — `conciliador` (OFX × grade do SIGA, tolerância de 1 centavo), `prova_real` (saldo do banco × SIGA e lançamentos do SIGA sem par; só lê), `baixa_energia` (qual provisão de energia cada débito do extrato quita), `exportador` (TXT de ofertas com blacklist de palavras-chave, Excel do lote), `fatura_energia_controller` (baixa/extrai/organiza faturas em `faturas_energisa/`), `anexo_fatura` (nome do PDF anexado no SIGA).
- `bot/siga_bot.py`: `SigaBot.fluxo_automacao()` roda numa thread separada (disparada em `ui/acoes_siga.py`) com `launch_persistent_context(channel="msedge")` em `siga_browser_data/`. Ramifica por `tipo_lote` (`"extrato"`, `"energia"` ou `"ofertas"`) e navega pelas rotinas do SIGA preenchendo `#f_executar_programa` (TES01701/01703/01704 extratos e rendimentos; TES01502 lançamento e TES01501 consulta/auditoria de faturas). Select2 tem helper com retries (`selecionar_select2`). Falhas geram screenshot em `logs/screenshots/`. `SigaBot` é composto por mixins: `siga_helpers` (Select2, loading, sessão, screenshot), `sessao` (Edge e login), `fluxo_extratos` (laço do lote de extratos, prévia opcional e prova real), `extratos` (lançamento de um extrato), `energia_auditoria` (TES01501), `energia` (TES01502), `baixa_provisoes` (aprova na TES01508 e baixa na TES01506 as faturas de energia debitadas, antes da conciliação), `ofertas` (importação do TXT de ofertas na TES05602, front novo em iframe via `frame_locator`) e `descoberta_contas` (`tipo_lote="descoberta"`, só leitura: catálogo de contas pela CTB00301 ou TES01701, devolvido pelo callback `on_catalogo`).
- **Telas do SIGA** (campos `#f_*`, códigos de rotina, menus, front novo em iframe): leia `docs/regras/siga.md` antes de mexer em `bot/`.
- Bot ↔ UI só por dicionário de **callbacks** (`update_status`, `show_message`, `update_progress`, `show_dashboard`, `on_finish`). Na UI, todo callback vindo da thread do bot passa por `self.after(0, ...)`; nunca tocar widgets direto da thread do bot.
- `ui/`: `main_window.py` (janela e layout, composta por mixins: `credenciais`, `lote_extratos`, `acoes_siga`, `catalogo_siga`, `dashboard`), `card_conta_extrato.py` (card guiado; sugestão e validação ficam em `controllers/sugestao_contas.py` e `estado_card.py`), `panel_energia.py` + `modais_energia.py` (aba Energia). Cores: use os tokens de `ui/tema.py` (tema Ace do SIGA), não hex soltos.

## Convenções

- **Versão**: definida só em `version.py` (`VERSION`); nunca hardcoded em UI, modais, logs ou spec. Ao subir a versão: nova seção no topo de `docs/CHANGELOG.md`, e no `README.md` trocar o título e a seção "Destaques da Versão" (o README mostra só a versão atual).
- **Caminhos de dados**: usar `caminhos.diretorio_base()` para tudo que o usuário mantém entre versões (`config.json`, `.env`, `credentials.json`, `token.json`, `logs/`, `faturas_energisa/`). No executável aponta para a pasta do `AutoSiga.exe`, não para `_internal` (substituída a cada atualização); calcular a partir de `__file__` quebra isso.
- **Credenciais do SIGA**: Windows Keyring (serviço `"AutoSIGA"`) com fallback para `SIGA_USUARIO`/`SIGA_SENHA` do `.env`.
- Teto de 500 linhas por `.py`, auditado por `tests/test_tamanho_arquivos.py`. Ao adicionar funcionalidade ao bot ou à janela, crie ou estenda o mixin da responsabilidade em vez de crescer `siga_bot.py`/`main_window.py`.
- Testes em `tests/` (fixtures em `tests/fixtures/`), sem `conftest.py`; o bot é testado com páginas falsas (classes que imitam `page`), sem navegador. `*.ofx` está no `.gitignore`: fixture nova de OFX precisa de `git add -f`.

## Handoff entre ferramentas (Claude Code ↔ Antigravity)

O estado da tarefa em andamento fica em `.agents/handoff.md` (fora do git).
- Usuário diz **"handoff"** (ou os tokens estão acabando): reescreva o arquivo, curto, com: tarefa e objetivo, o que já foi feito, decisões tomadas, arquivos alterados, como verificar e próximo passo exato. Substitua o conteúdo anterior, não acumule histórico.
- Usuário diz **"continuar"**: leia `.agents/handoff.md` antes de qualquer outra coisa e retome do próximo passo, sem reexplorar o que já está registrado.
- Concluída a tarefa (commit feito), esvazie o arquivo.
