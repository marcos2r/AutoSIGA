# Diretrizes de Desenvolvimento Local - AutoSIGA

Este arquivo define as regras locais específicas para o projeto AutoSIGA.

---

## 1. Controle de Versão e Exibição de Versão
* **Centralização da Versão**: O número de versão da aplicação deve ser definido única e exclusivamente no arquivo `version.py` através da variável `VERSION`.
* **Proibição de Hardcoding**: É terminantemente proibido declarar a string de versão de forma manual (hardcoded) em qualquer componente da interface de usuário, modais, logs ou metadados de empacotamento. Todos os arquivos devem importar e utilizar `VERSION` de `version.py`.
* **Sincronização ao Atualizar**: Sempre que a versão em `version.py` for atualizada, certifique-se de que a documentação como o `README.md` também seja atualizada em sua seção de destaques para refletir o novo ciclo de lançamento.
