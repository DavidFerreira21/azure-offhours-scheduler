# Guia Operacional

Este documento e voltado para quem vai operar o scheduler depois do deploy, principalmente pelo Azure Portal.

O foco aqui nao e explicar a implementacao interna, e sim o que editar, onde editar e como validar o resultado.

## 1. O Que Normalmente Muda Depois do Deploy

No dia a dia, a operacao costuma mexer em 3 coisas:

- configuracao global do scheduler
- schedules na tabela operacional
- tags nos recursos Azure

Na maioria dos casos, nao e necessario redeploy para isso.

## 2. Onde Operar

Recursos principais no Azure:

- Function App
  Executa o timer do scheduler.
- Storage Account
  Hospeda as tabelas operacionais.
- Azure Table Storage
  Guarda config global, schedules e state.

Configuracao tecnica importante na Function App:

- `ENABLE_VERBOSE_AZURE_SDK_LOGS`
  Deve permanecer `false` no uso normal. Ative apenas para troubleshooting temporario.
- `RESOURCE_RESULT_LOG_MODE`
  O valor recomendado e `executed-and-errors`. Use `all` apenas quando precisar investigar recurso por recurso.

Tabelas principais:

- `OffHoursSchedulerConfig`
- `OffHoursSchedulerSchedules`
- `OffHoursSchedulerState`

## 3. Config Global

Entidade principal:

- `PartitionKey=GLOBAL`
- `RowKey=runtime`

Campos mais importantes:

- `DRY_RUN`
  Quando `true`, o scheduler avalia e registra, mas nao executa `start` ou `stop`.
- `DEFAULT_TIMEZONE`
  Timezone padrao usada quando o recurso nao informa override proprio.
- `SCHEDULE_TAG_KEY`
  Nome da tag que aponta para o schedule. O padrao e `schedule`.
- `RETAIN_RUNNING`
  Respeita uma ligacao manual fora da janela. No comportamento atual, esse retain e temporario.
- `RETAIN_STOPPED`
  Respeita um desligamento manual dentro da janela. No comportamento atual, esse retain e persistente.

Recomendacao pratica:

- prefira boolean real (`true` e `false`) para campos booleanos
- mantenha `Version`, `UpdatedAtUtc` e `UpdatedBy` preenchidos

## 4. Criar ou Editar um Schedule

Cada schedule fica em uma entidade da tabela `OffHoursSchedulerSchedules`.

Campos minimos:

- `PartitionKey=SCHEDULE`
- `RowKey=<nome-do-schedule>`
- `Enabled=true`
- `Version`
- `UpdatedAtUtc`
- `UpdatedBy`

Para janela simples, voce pode usar:

- `Start`
- `Stop`

Para janelas mais ricas, o formato preferido e:

- `Periods`

Exemplo simples:

```json
{
  "PartitionKey": "SCHEDULE",
  "RowKey": "business-hours",
  "Start": "08:00",
  "Stop": "18:00",
  "SkipDays": "saturday,sunday",
  "Enabled": true,
  "Version": "1",
  "UpdatedAtUtc": "2026-03-19T12:00:00Z",
  "UpdatedBy": "ops@example.com"
}
```

Exemplo com multiplas janelas:

```json
{
  "PartitionKey": "SCHEDULE",
  "RowKey": "office-hours-split",
  "Periods": "[{\"start\":\"08:00\",\"stop\":\"12:00\"},{\"start\":\"13:00\",\"stop\":\"18:00\"}]",
  "Enabled": true,
  "Version": "1",
  "UpdatedAtUtc": "2026-03-19T12:00:00Z",
  "UpdatedBy": "ops@example.com"
}
```

## 5. Aplicar o Schedule em um Recurso

O recurso entra no ciclo por tag.

Exemplo:

```text
schedule=business-hours
```

Tambem e possivel usar timezone por recurso, por exemplo:

```text
timezone=America/Sao_Paulo
```

## 6. Como Funciona o Retain na Pratica

Sem retain:

- fora da janela, o scheduler tende a desligar
- dentro da janela, o scheduler tende a ligar

Com `RETAIN_RUNNING=true`:

- se alguem ligar manualmente um recurso fora da janela, o scheduler respeita isso temporariamente
- depois que o recurso atravessa uma janela valida, ele volta ao ciclo normal

Com `RETAIN_STOPPED=true`:

- se alguem desligar manualmente um recurso dentro da janela, o scheduler respeita isso
- no comportamento atual, esse override permanece ate outro evento operacional mudar o estado

## 7. Como Validar se Esta Funcionando

Sinais mais uteis:

- logs da Function
- relatorio estruturado do ciclo
- tabela `OffHoursSchedulerState`

O relatorio final de cada execucao traz:

- `run_id`
- `summary`
- `duration_sec`
- `resources`

Cada recurso processado pode informar:

- `resource_id`
- `name`
- `type`
- `action`
- `result`
- `reason`
- `duration_sec`

No modo recomendado de producao:

- o relatorio final do ciclo continua sempre
- o resumo textual do ciclo continua sempre
- logs por recurso aparecem apenas para `EXECUTED` e `FAILED`
- para troubleshooting detalhado, troque `RESOURCE_RESULT_LOG_MODE` para `all`

## 8. Validacao Segura Recomendada

Para primeira validacao:

1. deixe `DRY_RUN=true`
2. crie ou ajuste um schedule
3. aplique a tag em um recurso de teste
4. aguarde o ciclo do timer ou dispare a Function manualmente
5. confirme o resultado pelos logs e pelo relatorio estruturado
6. so depois troque `DRY_RUN` para `false`

## 9. Quando Voce Precisa de Ajuda Mais Tecnica

Use estes documentos:

- `architecture.md`
  Para entender o fluxo completo.
- `examples.md`
  Para copiar exemplos validos de entidades e escopo.
- `troubleshooting.md`
  Para erros comuns de deploy, runtime e edicao manual.
- `developer-guide.md`
  Para manutencao e alteracoes de codigo.
