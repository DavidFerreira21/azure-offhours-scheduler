# Contributing

Obrigado por considerar contribuir com o Azure OffHours Scheduler.

Este projeto foi estruturado para ser facil de operar e de evoluir. Para manter isso verdadeiro, use este guia antes de abrir PRs ou propor mudancas maiores.

## Antes de Comecar

Leia nesta ordem:

1. `README.md`
2. `docs/architecture.md`
3. `docs/developer-guide.md`
4. `docs/repository-map.md`
5. `docs/code-components.md`

Se a mudanca tocar deploy ou operacao, leia tambem:

- `infra/bicep/main.bicep`
- `scripts/deploy_scheduler.sh`

## Fonte da Verdade

Regra principal:

- codigo da aplicacao vive em `src/`
- host da Azure Function vive em `function/`

Nao trate o conteudo copiado para publish dentro de `function/` como fonte principal da aplicacao.

Fluxo esperado:

1. alterar codigo em `src/`
2. atualizar testes
3. rodar `pytest -q`
4. rodar `./scripts/prepare_function_app_publish.sh` se a mudanca impactar publish

## Tipos de Contribuicao Bem-vindos

- correcao de bugs
- melhoria de legibilidade e organizacao interna
- novos handlers para outros tipos de recursos Azure
- melhorias no discovery e no modelo de escopo
- melhorias de deploy e experiencia operacional
- documentacao
- testes

## Como Propor Mudancas

### Mudancas pequenas

Exemplos:

- bugfix pontual
- melhoria de log
- ajuste de doc
- refatoracao localizada

Pode abrir PR direto.

### Mudancas maiores

Exemplos:

- novo tipo de recurso
- mudanca de schema das tabelas
- mudanca de modelo de escopo
- alteracoes grandes na infra

Recomendado:

1. abrir uma issue
2. explicar problema, impacto e abordagem
3. alinhar a direcao antes de codificar

## Padrao Esperado de Pull Request

Um PR bom deve deixar claro:

- qual problema resolve
- qual foi a abordagem tecnica
- quais riscos existem
- como validar
- se houve mudanca em schema, deploy ou documentacao

Checklist recomendado no PR:

- [ ] codigo atualizado em `src/` quando aplicavel
- [ ] testes atualizados
- [ ] `pytest -q` executado
- [ ] docs atualizadas quando necessario
- [ ] `prepare_function_app_publish.sh` validado se a mudanca impacta publish
- [ ] Bicep recompilado se houve mudanca em `infra/bicep/main.bicep`

## Testes

Rodar suite unitária:

```bash
pytest -q
```

Validar bundle da Function:

```bash
./scripts/prepare_function_app_publish.sh
```

Se houver mudanca no Bicep:

```bash
az bicep build --file infra/bicep/main.bicep
```

## Estilo de Mudanca

Preferencias do projeto:

- nomes claros e previsiveis
- funcoes pequenas quando melhoram legibilidade
- regra de negocio explicita
- pouco acoplamento entre camadas
- comentarios curtos apenas quando agregam contexto real

Evite:

- misturar mudancas de doc, infra e regra de negocio sem necessidade
- renomeacoes grandes junto com mudanca funcional complexa
- introduzir “magia” dificil de depurar

## Regras de Documentacao

Atualize docs quando a mudanca afetar:

- fluxo de deploy
- runtime settings
- schema das tabelas
- escopo tecnico ou operacional
- estrutura do repositorio
- onboarding de quem vai manter o projeto

Arquivos mais comuns:

- `README.md`
- `docs/architecture.md`
- `docs/developer-guide.md`
- `docs/repository-map.md`
- `docs/code-components.md`
- `docs/examples.md`

## Novos Handlers

Se voce adicionar suporte a um novo tipo de recurso:

1. crie um novo handler em `src/handlers/`
2. registre no bootstrap em `function/OffHoursTimer/__init__.py`
3. ajuste `src/discovery/resource_graph.py` se a query precisar suportar o novo tipo
4. adicione testes
5. atualize documentacao

## Novas Configuracoes

Se a configuracao for tecnica:

- `src/config/settings.py`
- `function/local.settings.json.example`
- `infra/bicep/modules/functionApp.bicep`

Se a configuracao for operacional:

- Azure Table Storage
- `src/persistence/config_store.py`
- documentacao do schema

## Duvidas de Design

Se estiver em duvida sobre onde colocar algo, use esta regra:

- muda sem redeploy e faz parte da operacao do scheduler:
  tabela
- descreve ambiente tecnico ou deploy:
  `settings` / Bicep
- e regra de decisao:
  `src/scheduler/`
- executa acao no Azure:
  `src/handlers/`

## Licenca e Responsabilidade

Ao contribuir, assuma que seu codigo podera ser distribuido sob a licenca do projeto e revisado publicamente.

Licenca atual do projeto:

- Apache License 2.0
