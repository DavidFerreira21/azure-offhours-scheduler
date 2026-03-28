# Guia de Desenvolvimento

Este documento e voltado para quem vai manter, evoluir ou depurar o projeto.

O objetivo aqui nao e apenas explicar o que existe, mas mostrar como fazer alteracoes sem quebrar o fluxo de deploy, publish e execucao do scheduler.

## 1. Objetivo do Projeto

O Azure OffHours Scheduler automatiza `start` e `stop` de recursos Azure com base em:

- tag de schedule no recurso
- janelas definidas em Azure Table Storage
- regras de escopo por subscription e management group
- regras de retencao para respeitar override manual

No estado atual, o runtime executa acoes reais para:

- `Microsoft.Compute/virtualMachines`

## 2. Mapa Mental da Solucao

Pense na solucao em 5 camadas:

1. `function/`
   Host da Azure Function.
2. `src/`
   Codigo da aplicacao.
3. `infra/bicep/`
   Infraestrutura e app settings.
4. `scripts/`
   Automacao de deploy e publish.

Para operacao repo-local, existe tambem:

5. `offhours_cli/`
   Wrapper para `./offhours`.

Fluxo de runtime:

```text
Timer Trigger
  -> carrega settings tecnicos
  -> le Config e Schedules nas tabelas
  -> consulta Resource Graph
  -> avalia cada recurso no engine
  -> chama o handler correto
  -> grava state quando necessario
  -> monta relatorio estruturado
```

## 3. Estrutura do Repositorio

Este guia assume que `repository-map.md` e a referencia curta para estrutura do repo.
Aqui, o foco e manutencao e evolucao do comportamento da solucao.

### `function/`

Responsavel apenas pelo host da Azure Function.

Arquivos principais:

- `function/OffHoursTimer/__init__.py`
- `function/OffHoursTimer/function.json`
  Timer trigger com cron vindo de `TIMER_SCHEDULE`.
- `function/host.json`
- `function/local.settings.json.example`

Importante:

- `function/` nao e a fonte principal da regra de negocio
- durante o publish, os modulos de `src/` sao copiados para dentro de `function/`
- `function/requirements.txt` e gerado pelo script de prepare a partir do `requirements.txt` da raiz

### `src/`

Codigo fonte principal.

Subpastas:

- `src/config/`
  Configuracao tecnica do runtime.
- `src/discovery/`
  Busca recursos no Azure.
- `src/handlers/`
  Executa acoes por tipo de recurso.
- `src/persistence/`
  Le e grava dados nas tabelas.
- `src/reporting/`
  Monta o relatorio estruturado final do ciclo.
- `src/scheduler/`
  Modelos, engine e service.
- `src/offhours_cli/`
  CLI repo-local para operacao de `config`, `schedule` e `state`.

### `infra/bicep/`, `scripts/` e `tests/`

Essas areas sustentam deploy, publish e validacao automatizada.
Use `repository-map.md` quando a duvida for "onde editar".

## 4. Fonte da Verdade

Esta e a regra mais importante do projeto:

- alteracoes de regra de negocio e integracao devem ser feitas em `src/`
- alteracoes de host devem ser feitas em `function/`

Nao trate os modulos copiados para publish como fonte da verdade.

Fluxo correto:

1. editar em `src/`
2. rodar testes
3. montar bundle com `scripts/prepare_function_app_publish.sh`
4. gerar o zip com `scripts/build_function_app_package.sh`
5. publicar a Function com `az functionapp deployment source config-zip --build-remote false`
6. sincronizar os triggers
7. confirmar que `OffHoursTimer` foi registrado

Observacao:

- o bundle de publish agora leva `.python_packages` com as dependencias de runtime
- o wrapper atual garante registro da funcao antes de concluir
- isso nao significa necessariamente host totalmente aquecido no mesmo instante

## 5. Como o Runtime Sobe

Arquivo principal:

- `function/OffHoursTimer/__init__.py`

Quando o timer dispara:

1. a Function monta o `sys.path`
2. chama `Settings.from_env()`
3. carrega configuracao global na tabela `Config`
4. carrega schedules ativos na tabela `Schedules`
5. cria `ScheduleEngine`
6. cria `ResourceGraphDiscovery`
7. registra handlers
8. cria `StateStore`
9. roda `SchedulerService`
10. monta o relatorio final do ciclo
11. escreve o resumo final e o JSON estruturado em log

Se voce precisar depurar o startup do runtime, este e o melhor ponto de entrada.

## 6. O Que Cada Modulo Faz

Use `code-components.md` se voce quiser uma visao mais modular e mais focada nas camadas do runtime.

### `src/config/settings.py`

Le apenas configuracao tecnica:

- subscriptions efetivas
- regioes alvo
- `SCHEDULER_TABLE_SERVICE_URI` no ambiente Azure
- connection string das tabelas apenas como fallback para desenvolvimento local
- nomes das tabelas
- concorrencia maxima

Nao coloque regra operacional aqui.

Regra pratica:

- se a configuracao muda sem redeploy, ela deve ir para tabela
- se a configuracao descreve o ambiente tecnico da app, ela pode ficar aqui

Observacao:

- o cron tecnico do timer vem da app setting `TIMER_SCHEDULE`, resolvida pelo host da Function
- os logs estruturados por recurso sao controlados pela app setting `RESOURCE_RESULT_LOG_MODE`
- os logs verbosos do SDK Azure sao controlados pela app setting `ENABLE_VERBOSE_AZURE_SDK_LOGS`

### `src/persistence/config_store.py`

Converte entidades do Azure Table Storage em modelos Python.

Responsabilidades:

- validar audit trail
- interpretar listas e booleans
- interpretar `Start/Stop` ou `Periods`
- montar `ScheduleDefinition`
- montar `GlobalSchedulerConfig`

Se mudar o schema das tabelas, este arquivo quase sempre sera impactado.

### `src/persistence/table_entities.py`

Camada compartilhada de parse, validacao e serializacao das entidades de tabela.

Responsabilidades:

- validar booleans, datas ISO-8601 e timezones
- interpretar `Start/Stop`, `Periods` e listas de escopo
- montar payload normalizado para CLI e runtime
- evitar divergencia entre o que a CLI valida e o que o runtime consome

Se a mudanca envolver schema, formato declarativo da CLI ou normalizacao de entidades, este arquivo deve ser o primeiro ponto de edicao.

### `src/persistence/state_store.py`

Persistencia operacional do scheduler.

Responsabilidades:

- descobrir se o recurso ja foi iniciado/parado pelo scheduler
- registrar a ultima observacao
- permitir regras `retain_running` e `retain_stopped`

Detalhe importante:

- `retain_running` e temporario no comportamento atual
- `retain_stopped` continua persistente no comportamento atual

Se o comportamento de retencao mudar, comece por aqui e pelo `SchedulerService`.

### `src/discovery/resource_graph.py`

Camada que fala com Azure Resource Graph.

Responsabilidades:

- montar a query
- restringir tipos suportados
- exigir a tag de schedule
- trazer subscription, resource group, location e management groups
- aplicar filtro tecnico de regiao

Se entrar um novo tipo de recurso, normalmente este arquivo precisa ser revisto.

### `src/scheduler/models.py`

Modelos de dominio.

Classes principais:

- `SchedulePeriod`
- `ScheduleScope`
- `ScheduleDefinition`
- `GlobalSchedulerConfig`

`ScheduleScope` e especialmente importante porque encapsula a regra include/exclude.

### `src/scheduler/engine.py`

Regra pura de decisao.

Responsabilidades:

- localizar schedule pela tag
- validar escopo do recurso
- resolver timezone
- aplicar `skip_days`
- decidir `START`, `STOP` ou `SKIP`

Se a mudanca for de regra de negocio, comece por aqui.

### `src/scheduler/service.py`

Orquestrador do ciclo.

Responsabilidades:

- iterar recursos descobertos
- aplicar engine
- chamar handler
- lidar com `dry_run`
- aplicar retencao
- salvar state
- propagar `run_id`
- medir tempo do ciclo e tempo por recurso
- consolidar resumo e resultados estruturados
- respeitar a politica de logs por recurso definida em `RESOURCE_RESULT_LOG_MODE`

Se o engine responde "o que deveria acontecer", o service responde "como isso acontece no runtime".

### `src/reporting/report_builder.py`

Responsabilidades:

- transformar o resultado final do scheduler em um payload JSON simples
- manter o formato do relatorio desacoplado da orquestracao principal

### `src/handlers/`

Executa a acao real em cada tipo de recurso.

Arquivos:

- `base_handler.py`
- `registry.py`
- `vm_handler.py`

Se entrar novo recurso, voce provavelmente vai:

1. criar um handler novo
2. registrar esse handler no bootstrap da Function
3. ajustar discovery
4. adicionar testes

### `src/offhours_cli/`

Implementa a CLI repo-local.

Arquivos principais:

- `src/offhours_cli/main.py`
  Parser `argparse` e dispatch dos comandos operacionais.
- `src/offhours_cli/storage.py`
  Resolucao de `DefaultAzureCredential`, Table Service e nomes das tabelas.
- `src/offhours_cli/files.py`
  Leitura declarativa de YAML/JSON.
- `src/offhours_cli/formatting.py`
  Renderizacao em `table`, `json` e `yaml`.
- `offhours`
  Wrapper shell curto que carrega `.offhours.env` automaticamente antes de chamar `python3 -m offhours_cli`.

Regra importante:

- a CLI nao deve duplicar validacao de entidade em paralelo ao runtime
- sempre que possivel, reaproveite `src/persistence/table_entities.py`
- o escopo da CLI deve continuar simples: `config`, `schedule` e `state`

Fluxo esperado:

- o deploy recomendado grava `.offhours.env` na raiz do repositorio
- o wrapper `./offhours` carrega esse arquivo automaticamente
- o operador normalmente so precisa fazer `az login` antes de usar a CLI

## 7. Como Fazer Alteracoes Comuns

### Mudar a regra de horario

Arquivos provaveis:

- `src/scheduler/engine.py`
- `src/scheduler/models.py`
- `tests/test_engine.py`

### Mudar o schema da tabela de schedules

Arquivos provaveis:

- `src/persistence/table_entities.py`
- `src/persistence/config_store.py`
- `src/offhours_cli/main.py`
- `docs/architecture.md`
- `README.md`
- `tests/test_config_store.py`
- `tests/test_offhours_cli.py`

### Mudar o comportamento de retencao

Arquivos provaveis:

- `src/persistence/state_store.py`
- `src/scheduler/service.py`
- `tests/test_scheduler_service.py`

### Adicionar um novo tipo de recurso

Passos tipicos:

1. criar um handler em `src/handlers/`
2. registrar o handler em `function/OffHoursTimer/__init__.py`
3. atualizar `src/discovery/resource_graph.py` se a query precisar mudar
4. criar testes
5. atualizar documentacao

### Adicionar uma nova configuracao tecnica

Arquivos provaveis:

- `src/config/settings.py`
- `function/local.settings.json.example`
- `infra/bicep/modules/functionApp.bicep`
- `tests/test_settings.py`

### Mudar o deploy

Arquivos provaveis:

- `infra/bicep/main.bicep`
- `infra/bicep/modules/functionApp.bicep`
- `infra/bicep/modules/subscriptionRoles.bicep`
- `scripts/deploy_scheduler.sh`

## 8. Fluxo de Desenvolvimento Recomendado

### Rodar testes

```bash
pytest -q
```

### Rodar lint e checagens de seguranca

```bash
ruff check .
bandit -q -r src function -c pyproject.toml
pip-audit --local --progress-spinner off
```

### Preparar bundle da Function

```bash
./scripts/prepare_function_app_publish.sh
```

### Gerar zip de publish

```bash
./scripts/build_function_app_package.sh /tmp/offhours-function.zip
```

### Rodar localmente

```bash
cd function
cp local.settings.json.example local.settings.json
func start
```

### Fazer deploy completo

```bash
./scripts/deploy_scheduler.sh
```

## 9. Armadilhas Comuns

### 1. Editar o lugar errado

Erro comum:

- editar codigo copiado dentro de `function/`

Regra:

- edite em `src/`
- use `prepare_function_app_publish.sh` para sincronizar
- use `build_function_app_package.sh` quando quiser inspecionar o pacote final que sera publicado

### 2. Mudar Bicep sem alinhar o runtime

Se voce adicionar uma app setting nova no deploy, normalmente tambem precisa ajustar:

- `src/config/settings.py`
- `function/local.settings.json.example`
- testes

### 3. Mudar tabelas sem atualizar parser

Se o schema mudar, mas `config_store.py` nao for atualizado, o runtime falha cedo.

Isso e bom do ponto de vista operacional, mas exige disciplina de manutencao.

### 4. Usar `az deployment sub create` direto com management groups

Quando o escopo usa:

- `managementGroupIds`
- `excludeSubscriptionIds`

prefira:

```bash
./scripts/deploy_scheduler.sh
```

Porque o wrapper resolve o escopo efetivo antes do deploy.

### 5. Esquecer de atualizar docs

Este projeto tem bastante comportamento operacional. Sempre que mexer em:

- schema de tabela
- regras de escopo
- runtime settings
- fluxo de deploy

atualize tambem:

- `README.md`
- `docs/architecture.md`
- `docs/operator-guide.md` se a mudanca afetar a operacao no Portal
- `docs/repository-map.md` se a mudanca afetar a estrutura do repo
- `docs/code-components.md` se a mudanca afetar responsabilidades de camadas
- este `docs/developer-guide.md`

## 10. Como Ler o Projeto Pela Primeira Vez

Ordem recomendada:

1. `README.md`
2. `docs/architecture.md`
3. `docs/repository-map.md`
4. `docs/code-components.md`
5. `function/OffHoursTimer/__init__.py`
6. `src/scheduler/engine.py`
7. `src/scheduler/service.py`
8. `src/persistence/config_store.py`
9. `src/discovery/resource_graph.py`

Essa ordem ajuda a entender primeiro o fluxo, depois a estrutura, depois a implementacao.

## 11. Checklist Antes de Subir Mudancas

- o codigo foi alterado em `src/` quando aplicavel
- os testes relevantes foram atualizados
- `ruff check .` passou
- `pytest -q` passou
- `bandit -q -r src function -c pyproject.toml` passou
- `pip-audit --local --progress-spinner off` passou
- `prepare_function_app_publish.sh` continua funcionando
- a documentacao foi revisada
- se houve mudanca de deploy, o Bicep foi recompilado

## 12. Regra de Ouro

Se a alteracao tocar comportamento de producao, pense sempre nestes 3 niveis:

1. escopo tecnico da solucao
2. regra operacional do scheduler
3. impacto no deploy e na documentacao

Esse projeto fica facil de manter quando essas 3 coisas continuam alinhadas.
