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

Pense na solucao em 4 camadas:

1. `function/`
   Host da Azure Function.
2. `src/`
   Codigo da aplicacao.
3. `infra/bicep/`
   Infraestrutura e app settings.
4. `scripts/`
   Automacao de deploy, bootstrap e publish.

Fluxo de runtime:

```text
Timer Trigger
  -> carrega settings tecnicos
  -> le Config e Schedules nas tabelas
  -> consulta Resource Graph
  -> avalia cada recurso no engine
  -> chama o handler correto
  -> grava state quando necessario
```

## 3. Estrutura do Repositorio

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
- `src/scheduler/`
  Modelos, engine e service.

### `infra/bicep/`

Infraestrutura da solucao.

### `scripts/`

Automacao operacional e de publish.

### `tests/`

Cobertura unitária do comportamento principal.

## 4. Fonte da Verdade

Esta e a regra mais importante do projeto:

- alteracoes de regra de negocio e integracao devem ser feitas em `src/`
- alteracoes de host devem ser feitas em `function/`

Nao trate os modulos copiados para publish como fonte da verdade.

Fluxo correto:

1. editar em `src/`
2. rodar testes
3. montar bundle com `scripts/prepare_function_app_publish.sh`
4. publicar a Function

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
10. escreve o resumo final em log

Se voce precisar depurar o bootstrap, este e o melhor ponto de entrada.

## 6. O Que Cada Modulo Faz

### `src/config/settings.py`

Le apenas configuracao tecnica:

- subscriptions efetivas
- regioes alvo
- connection string das tabelas
- nomes das tabelas
- concorrencia maxima

Nao coloque regra operacional aqui.

Regra pratica:

- se a configuracao muda sem redeploy, ela deve ir para tabela
- se a configuracao descreve o ambiente tecnico da app, ela pode ficar aqui

### `src/persistence/config_store.py`

Converte entidades do Azure Table Storage em modelos Python.

Responsabilidades:

- validar audit trail
- interpretar listas e booleans
- interpretar `Start/Stop` ou `Periods`
- montar `ScheduleDefinition`
- montar `GlobalSchedulerConfig`

Se mudar o schema das tabelas, este arquivo quase sempre sera impactado.

### `src/persistence/state_store.py`

Persistencia operacional do scheduler.

Responsabilidades:

- descobrir se o recurso ja foi iniciado/parado pelo scheduler
- registrar a ultima observacao
- permitir regras `retain_running` e `retain_stopped`

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
- consolidar resumo

Se o engine responde "o que deveria acontecer", o service responde "como isso acontece no runtime".

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

## 7. Como Fazer Alteracoes Comuns

### Mudar a regra de horario

Arquivos provaveis:

- `src/scheduler/engine.py`
- `src/scheduler/models.py`
- `tests/test_engine.py`

### Mudar o schema da tabela de schedules

Arquivos provaveis:

- `src/persistence/config_store.py`
- `docs/architecture.md`
- `README.md`
- `tests/test_config_store.py`

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

### Preparar bundle da Function

```bash
./scripts/prepare_function_app_publish.sh
```

### Rodar localmente

```bash
cd function
cp local.settings.json.example local.settings.json
func start
```

### Fazer deploy completo

```bash
./scripts/deploy_scheduler.sh \
  --parameters-file infra/bicep/main.parameters.json
```

## 9. Armadilhas Comuns

### 1. Editar o lugar errado

Erro comum:

- editar codigo copiado dentro de `function/`

Regra:

- edite em `src/`
- use `prepare_function_app_publish.sh` para sincronizar

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
- `docs/repository-map.md`
- `docs/code-components.md`
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
- `pytest -q` passou
- `prepare_function_app_publish.sh` continua funcionando
- a documentacao foi revisada
- se houve mudanca de deploy, o Bicep foi recompilado

## 12. Regra de Ouro

Se a alteracao tocar comportamento de producao, pense sempre nestes 3 niveis:

1. escopo tecnico da solucao
2. regra operacional do scheduler
3. impacto no deploy e na documentacao

Esse projeto fica facil de manter quando essas 3 coisas continuam alinhadas.
