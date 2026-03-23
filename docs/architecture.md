# Arquitetura

## Objetivo

O Azure OffHours Scheduler automatiza `start` e `stop` de recursos Azure com base em tags e janelas operacionais definidas em Azure Table Storage.

O objetivo do desenho atual e permitir:

- configuracao operacional sem redeploy
- escopo dinamico por subscription e management group
- retencao de override manual
- auditoria minima de mudancas

## Visao Geral

Fluxo fim a fim:

```text
Bicep deploya infraestrutura
    ->
Function App recebe configuracao tecnica de runtime
    ->
Timer Trigger dispara o ciclo
    ->
App le configuracao global na tabela Config
    ->
App le schedules ativos na tabela Schedules
    ->
Discovery consulta Resource Graph nas subscriptions tecnicas
    ->
Scheduler avalia cada recurso contra schedule + timezone + escopo
    ->
Service decide START / STOP / SKIP
    ->
Handler executa acao real no recurso
    ->
Tabela State registra o historico operacional
    ->
Logs consolidam o resultado do ciclo
```

## Componentes

### 1. Infraestrutura

Provisionada por Bicep:

- Storage Account
- 3 tabelas Azure Table Storage
- Function App com Managed Identity
- App Service Plan
- Log Analytics
- Application Insights
- Role assignments nas subscriptions monitoradas

Arquivos principais:

- `infra/bicep/main.bicep`
- `infra/bicep/modules/functionApp.bicep`
- `infra/bicep/modules/subscriptionRoles.bicep`

### 2. Runtime Settings

O ambiente da Function guarda apenas configuracao tecnica:

- `AZURE_SUBSCRIPTION_IDS`
- `TARGET_RESOURCE_LOCATIONS`
- `DECLARED_MANAGEMENT_GROUP_IDS`
- `DECLARED_EXCLUDE_SUBSCRIPTION_IDS`
- `AzureWebJobsStorage__accountName`
- `SCHEDULER_TABLE_SERVICE_URI`
- `CONFIG_STORAGE_TABLE_NAME`
- `SCHEDULE_STORAGE_TABLE_NAME`
- `STATE_STORAGE_TABLE_NAME`
- `MAX_WORKERS`
- `ENABLE_VERBOSE_AZURE_SDK_LOGS`
- `RESOURCE_RESULT_LOG_MODE`
- `TIMER_SCHEDULE`

Esses valores dizem onde executar e onde buscar a configuracao operacional. Eles nao definem regras de negocio.

Leitura pratica:

- `AZURE_SUBSCRIPTION_IDS`: escopo tecnico efetivo ja resolvido pelo wrapper de deploy
- `DECLARED_MANAGEMENT_GROUP_IDS` e `DECLARED_EXCLUDE_SUBSCRIPTION_IDS`: metadados do escopo originalmente informado no `main.parameters.json`
- `ENABLE_VERBOSE_AZURE_SDK_LOGS`: deve permanecer `false` no uso normal para evitar custo e volume excessivo de logs
- `RESOURCE_RESULT_LOG_MODE`: use `executed-and-errors` no uso normal e `all` apenas para troubleshooting

### 3. Tabelas Operacionais

O comportamento do scheduler vem de 3 tabelas:

- `OffHoursSchedulerConfig`
- `OffHoursSchedulerSchedules`
- `OffHoursSchedulerState`

## Fluxo Completo

### Etapa 1. Deploy

O Bicep cria a storage account, as tabelas e a Function App.

No fluxo padrao de deploy, os inputs principais sao:

- `resourceGroupName`
- `location`
- `namePrefix`
- `subscriptionIds`
- `managementGroupIds`
- `excludeSubscriptionIds`
- `targetResourceLocations`

Input opcional recomendado para operacao do time:

- `tableOperatorsGroupObjectId`

Com isso, o template gera automaticamente os nomes de:

- Function App
- Storage Account
- Log Analytics
- Application Insights
- App Service Plan

As tabelas usam os nomes default do template, sem necessidade de informar no `parameters`.

Quando `tableOperatorsGroupObjectId` e informado, o template tambem atribui `Storage Table Data Contributor` na Storage Account para esse grupo Microsoft Entra.

Uso de `targetResourceLocations`:

- vazio: o scheduler considera todas as regioes das subscriptions monitoradas
- preenchido: o scheduler filtra os recursos do discovery para as regioes informadas

Uso do escopo tecnico da solucao:

- `subscriptionIds`: subscriptions explicitamente monitoradas
- `managementGroupIds`: management groups usados para descobrir subscriptions adicionais
- `excludeSubscriptionIds`: subscriptions removidas do escopo final

O wrapper de deploy resolve o escopo efetivo assim:

- `subscriptionIds` + subscriptions descendentes de `managementGroupIds` - `excludeSubscriptionIds`

Modelos de uso:

- explicito: apenas `subscriptionIds`
- enterprise: `managementGroupIds` com exclusoes pontuais em `excludeSubscriptionIds`
- misto: uniao de subscriptions explicitas com subscriptions herdadas dos management groups

Para primeira carga operacional, o repositorio tambem disponibiliza um bootstrap padrao via:

```bash
./scripts/bootstrap_scheduler_tables.sh --resource-group <rg> --storage-account <account>
```

O bootstrap cria uma configuracao global com `DRY_RUN=false` e um schedule `business-hours` (`08:00-18:00`, segunda a sexta) apenas se essas entidades ainda nao existirem.

No desenho atual, esse bootstrap usa Microsoft Entra ID com `az storage entity ... --auth-mode login`, nao shared key.
Por isso, quem executa o bootstrap precisa ter `Storage Table Data Contributor` na Storage Account do scheduler.

Na operacao recomendada do repositorio, esse bootstrap e chamado automaticamente por:

```bash
./scripts/deploy_scheduler.sh --parameters-file infra/bicep/main.parameters.json
```

Esse wrapper executa um preflight antes do deploy:

- valida ferramentas locais obrigatorias
- confirma autenticacao ativa no Azure CLI
- resolve o escopo final da solucao a partir de subscriptions e management groups
- valida acesso as subscriptions efetivas do escopo resolvido
- executa `az deployment sub validate` antes do create

Depois disso, ele executa o deploy da infra, aplica o bootstrap das tabelas e publica a Function App no final.
No estado atual, esse publish usa `func azure functionapp publish --python --build remote`.

Observacao importante:

- quando o escopo usa `managementGroupIds` ou `excludeSubscriptionIds`, o caminho recomendado e o wrapper `scripts/deploy_scheduler.sh`
- um `az deployment sub create` direto nao resolve automaticamente subscriptions descendentes de management groups

A identidade gerenciada da Function recebe:

- `Reader`
- `Virtual Machine Contributor`

Esses papeis sao atribuidos em cada subscription do escopo tecnico efetivo resolvido pelo deploy.

### Etapa 2. Disparo do timer

A Function `OffHoursTimer` executa no cron configurado em `function/OffHoursTimer/function.json`, resolvido pela app setting tecnica `TIMER_SCHEDULE`.

Por padrao, o deploy define `TIMER_SCHEDULE=0 */15 * * * *`, ou seja, uma execucao a cada 15 minutos.

Cada disparo representa um ciclo completo de avaliacao.

### Etapa 3. Bootstrap do runtime

No inicio do ciclo:

1. `Settings.from_env()` carrega a configuracao tecnica.
2. O app conecta na tabela global.
3. O app conecta na tabela de schedules.
4. Se retencao estiver habilitada, o app prepara a tabela de state.

Nesse ponto o runtime ainda nao consultou nenhum recurso Azure. Ele apenas montou o contexto operacional.

### Etapa 4. Leitura da configuracao global

A tabela `Config` define o comportamento do ciclo atual.

Entidade esperada:

```text
PartitionKey=GLOBAL
RowKey=runtime
```

Campos obrigatorios:

- `DRY_RUN`
- `DEFAULT_TIMEZONE`
- `SCHEDULE_TAG_KEY`
- `RETAIN_RUNNING`
- `RETAIN_STOPPED`
- `Version`
- `UpdatedAtUtc`
- `UpdatedBy`

Significado:

- `DRY_RUN`: calcula e loga, sem executar `start/stop`
- `DEFAULT_TIMEZONE`: fallback quando o recurso nao tem tag `timezone`
- `SCHEDULE_TAG_KEY`: nome da tag que aponta para o schedule
- `RETAIN_RUNNING`: preserva recurso ligado manualmente fora da janela de forma temporaria, ate atravessar a proxima janela valida
- `RETAIN_STOPPED`: preserva recurso parado manualmente dentro da janela e permanece persistente ate nova intervencao ou mudanca de estado
- `Version`, `UpdatedAtUtc`, `UpdatedBy`: trilha minima de auditoria

Exemplo:

```json
{
  "PartitionKey": "GLOBAL",
  "RowKey": "runtime",
  "DRY_RUN": true,
  "DEFAULT_TIMEZONE": "America/Sao_Paulo",
  "SCHEDULE_TAG_KEY": "schedule",
  "RETAIN_RUNNING": true,
  "RETAIN_STOPPED": false,
  "Version": "1",
  "UpdatedAtUtc": "2026-03-17T12:00:00Z",
  "UpdatedBy": "ops@example.com"
}
```

### Etapa 5. Leitura dos schedules

A tabela `Schedules` contem uma entidade por schedule.

O `RowKey` e o nome usado na tag do recurso, por exemplo:

```text
schedule=office-hours
```

Campos suportados:

- `Start`
- `Stop`
- `Periods`
- `SkipDays`
- `IncludeManagementGroups`
- `IncludeSubscriptions`
- `ExcludeManagementGroups`
- `ExcludeSubscriptions`
- `Enabled`
- `Version`
- `UpdatedAtUtc`
- `UpdatedBy`

Regras de interpretacao:

- `Periods` e o formato preferido/oficial para modelar janelas operacionais
- `Periods` permite multiplas janelas no mesmo schedule
- `Start/Stop` continua valendo para janelas simples e compatibilidade com edicao manual no Portal
- `Enabled=false` remove o schedule do ciclo sem apagar a entidade
- `SkipDays` ignora o schedule em dias especificos

Exemplo:

```json
{
  "PartitionKey": "SCHEDULE",
  "RowKey": "office-hours",
  "Periods": "[{\"start\":\"08:00\",\"stop\":\"12:00\"},{\"start\":\"13:00\",\"stop\":\"18:00\"}]",
  "SkipDays": "saturday,sunday",
  "IncludeSubscriptions": "sub-a,sub-b",
  "ExcludeManagementGroups": "[\"mg-sandbox-blocked\"]",
  "Enabled": true,
  "Version": "4",
  "UpdatedAtUtc": "2026-03-17T12:15:00Z",
  "UpdatedBy": "ops@example.com"
}
```

### Etapa 6. Discovery dos recursos

O discovery usa Azure Resource Graph para buscar recursos:

- dentro das subscriptions listadas em `AZURE_SUBSCRIPTION_IDS`
- opcionalmente filtrados por `TARGET_RESOURCE_LOCATIONS`
- do tipo atualmente suportado
- que possuam a tag definida por `SCHEDULE_TAG_KEY`

Para cada recurso, o scheduler coleta:

- `id`
- `name`
- `type`
- `location`
- `subscriptionId`
- `resourceGroup`
- `tags`
- `managementGroupAncestorsChain`

O filtro do Resource Graph e tecnico. A validacao de regra operacional acontece depois.

Em execucao local, o app usa `AZURE_SUBSCRIPTION_IDS` diretamente. A resolucao de `managementGroupIds` e `excludeSubscriptionIds` e uma responsabilidade do wrapper de deploy.

### Etapa 7. Avaliacao do recurso

Cada recurso passa pelo `ScheduleEngine`.

Ordem da avaliacao:

1. Ler o nome do schedule na tag do recurso.
2. Verificar se o schedule existe na tabela.
3. Verificar se o recurso esta dentro do escopo do schedule.
4. Resolver timezone do recurso:
   `tag timezone` -> `DEFAULT_TIMEZONE`.
5. Verificar se o dia atual esta em `SkipDays`.
6. Verificar se o horario atual cai em alguma janela.
7. Retornar `START`, `STOP` ou `SKIP`.

Saidas possiveis:

- `START`: recurso deveria estar ligado agora
- `STOP`: recurso deveria estar desligado agora
- `SKIP`: nao agir por falta de tag, schedule inexistente, escopo invalido, dia ignorado ou timezone invalido

### Etapa 8. Escopo dinamico

Cada schedule pode restringir alcance usando:

- `IncludeManagementGroups`
- `IncludeSubscriptions`
- `ExcludeManagementGroups`
- `ExcludeSubscriptions`

Regra de precedencia:

- `exclude` sempre vence `include`

Leitura pratica:

- sem `include`, o schedule vale para todo o universo tecnico efetivo carregado em `AZURE_SUBSCRIPTION_IDS`
- com `include`, o recurso so entra se bater em pelo menos um include
- se bater em qualquer `exclude`, o recurso sai mesmo que tambem esteja em `include`

Exemplo mental:

```text
IncludeSubscriptions = sub-a
ExcludeManagementGroups = mg-blocked
```

Resultado:

- recurso em `sub-a` e fora de `mg-blocked` -> entra
- recurso em `sub-a` e dentro de `mg-blocked` -> fica fora
- recurso fora de `sub-a` -> fica fora

### Etapa 9. Execucao da acao

Depois da decisao:

- se nao houver handler para o tipo, o recurso vira `SKIP`
- se `DRY_RUN=true`, a acao e apenas logada
- se `DRY_RUN=false`, o handler consulta o estado atual e executa `start/stop` quando necessario

No estado atual, o handler implementado e para:

- `Microsoft.Compute/virtualMachines`

### Etapa 10. Retencao e state

A tabela `State` protege overrides manuais.

Campos gravados por recurso:

- `ResourceId`
- `ResourceGroup`
- `ResourceName`
- `ResourceType`
- `StartedByScheduler`
- `StoppedByScheduler`
- `LastObservedState`
- `LastAction`
- `UpdatedAtUtc`

Comportamentos:

- se a decisao for `START` e a VM ja estiver `running`, o resultado e `SKIP_ALREADY_RUNNING`
- se a decisao for `STOP` e a VM ja estiver `stopped`, o resultado e `SKIP_ALREADY_STOPPED`
- se `RETAIN_RUNNING=true` e a VM estiver ligada fora da janela sem ter sido ligada pelo scheduler, o resultado e `SKIP_RETAIN_RUNNING`
- quando essa mesma VM atravessa uma janela valida ainda ligada, o override temporario e consumido e ela volta ao ciclo automatico para o proximo periodo fora da janela
- se `RETAIN_STOPPED=true` e a VM estiver parada dentro da janela sem ter sido parada pelo scheduler, o resultado e `SKIP_RETAIN_STOPPED`
- `RETAIN_STOPPED` permanece persistente no comportamento atual

Isso evita que o scheduler desfaça uma decisao manual indevidamente.

Cada ciclo tambem gera observabilidade estruturada:

- `run_id` unico por execucao
- `duration_sec` total do ciclo
- `duration_sec` por recurso processado
- relatorio final em uma unica linha JSON com `summary` e `resources`

### Etapa 11. Concorrencia

Os recursos encontrados sao processados em paralelo via `ThreadPoolExecutor`.

A concorrencia maxima e definida por:

- `MAX_WORKERS`

O limite aplicado em runtime e:

- `min(MAX_WORKERS, quantidade_de_recursos_encontrados)`

### Etapa 12. Log e consolidacao

Ao final do ciclo, a Function publica um resumo com:

- total de recursos avaliados
- quantos iniciaram
- quantos pararam
- quantos foram ignorados
- modo `dry_run`
- timezone padrao
- tag key usada
- flags de retencao
- `run_id`
- `duration_sec`
- configuracao de logs tecnicos do runtime

Em paralelo, a solucao publica:

- um relatorio final em JSON para todo ciclo
- logs estruturados por recurso quando o modo configurado permitir

Modo recomendado para uso normal:

- `ENABLE_VERBOSE_AZURE_SDK_LOGS=false`
- `RESOURCE_RESULT_LOG_MODE=executed-and-errors`

Efeito pratico desse modo:

- o relatorio final do ciclo continua sempre
- o resumo textual do ciclo continua sempre
- logs por recurso ficam restritos a `EXECUTED` e `FAILED`
- `SKIPPED` e `DRY_RUN` nao geram volume por recurso no modo padrao

## Modelo das Tabelas

### Config

Uso:

- 1 entidade global por ambiente

Chave:

```text
PartitionKey=GLOBAL
RowKey=runtime
```

### Schedules

Uso:

- 1 entidade por schedule

Chave recomendada:

```text
PartitionKey=SCHEDULE
RowKey=<nome-do-schedule>
```

### State

Uso:

- 1 entidade por recurso processado

Chave:

- `PartitionKey = subscription_id`
- `RowKey = sha1(resource.id)`

## Validacao e Auditoria

O app falha rapido ao carregar configuracao quando:

- a entidade global nao existe
- `Version` nao existe
- `UpdatedAtUtc` nao existe ou nao esta em ISO-8601
- `UpdatedBy` nao existe
- um schedule nao define `Start/Stop` nem `Periods`
- `Enabled`, `DRY_RUN` ou `RETAIN_*` nao sao booleans validos

Isso evita ciclo rodando com configuracao ambigua ou parcialmente corrompida.

## Permissoes

### Permissoes da identidade da Function

Hoje o deploy atribui:

- `Reader`
- `Virtual Machine Contributor`
- `Storage Blob Data Owner`
- `Storage Table Data Contributor`

Essas permissoes cobrem:

- leitura de recursos monitorados
- discovery via Resource Graph
- operacoes de `start/deallocate` em VMs
- operacao do host da Function sem shared key
- leitura e gravacao das tabelas operacionais via managed identity

### Permissoes para operadores humanos

Para evitar erro de acesso ao abrir entidades das tabelas pelo Portal com Microsoft Entra ID, o deploy aceita um grupo Entra opcional:

- `tableOperatorsGroupObjectId`

Se informado, o template cria na Storage Account a role:

- `Storage Table Data Contributor`

Escopo:

- Storage Account do scheduler

Uso recomendado:

- criar um grupo como `azure-offhours-operators`
- adicionar as pessoas do time nesse grupo
- informar o `objectId` do grupo no deploy

### Acesso as tabelas

No desenho atual em Azure, a Function acessa:

- o host storage por identidade usando `AzureWebJobsStorage__accountName`
- as tabelas operacionais por identidade usando `SCHEDULER_TABLE_SERVICE_URI`

Implicacao:

- o deploy nao precisa injetar `AccountKey` em app settings
- o acesso a Table Storage depende de RBAC de dados na Storage Account
- `SCHEDULER_STORAGE_CONNECTION_STRING` permanece apenas como fallback para desenvolvimento local

## Como a solucao muda sem redeploy

A vantagem principal do modelo table-driven e separar codigo de operacao.

Mudancas sem publicar novamente a Function:

- alterar `DRY_RUN`
- trocar `DEFAULT_TIMEZONE`
- trocar `SCHEDULE_TAG_KEY`
- habilitar ou desabilitar `RETAIN_RUNNING`
- habilitar ou desabilitar `RETAIN_STOPPED`
- criar um novo schedule
- alterar janelas de horario
- alterar escopo por subscriptions ou management groups
- desabilitar um schedule com `Enabled=false`

O proximo ciclo do timer ja passa a usar os novos valores.

## Exemplo Completo

Suponha:

- tabela global com `DRY_RUN=false`
- `DEFAULT_TIMEZONE=America/Sao_Paulo`
- `SCHEDULE_TAG_KEY=schedule`
- schedule `office-hours` ativo
- VM com tags:

```text
schedule=office-hours
timezone=America/Sao_Paulo
```

E schedule:

```text
08:00-12:00
13:00-18:00
```

Se o ciclo rodar as `09:30`:

1. discovery encontra a VM
2. engine identifica o schedule `office-hours`
3. engine valida escopo
4. engine converte horario para `America/Sao_Paulo`
5. engine conclui `START`
6. service verifica estado atual da VM
7. se estiver parada e nenhuma regra de retencao bloquear, o handler chama `start`
8. tabela `State` grava `LastAction=START`

Se o ciclo rodar as `20:00`:

1. engine conclui `STOP`
2. se a VM estiver ligada manualmente e `RETAIN_RUNNING=true`, o resultado vira `SKIP_RETAIN_RUNNING`
3. quando a VM atravessar a proxima janela valida ainda ligada, esse override temporario sera consumido
4. no proximo ciclo fora da janela, a VM volta a ser elegivel para `STOP`
5. caso contrario, o handler chama `deallocate`
6. tabela `State` grava `LastAction=STOP`

## Extensibilidade

Os pontos naturais de evolucao continuam claros:

- novos handlers em `src/handlers/`
- novos tipos de recurso no discovery
- novas regras de avaliacao no `src/scheduler/engine.py`
- novas colunas operacionais nas tabelas
- migracao futura para RBAC de Storage por managed identity
