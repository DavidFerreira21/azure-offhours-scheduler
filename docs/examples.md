# Exemplos

Este documento traz exemplos prontos para uso em testes, operacao inicial e entendimento do modelo de tabelas.

Observacao importante:

- campos booleanos devem ser gravados como boolean quando possivel
- use `true` / `false` para `DRY_RUN`, `RETAIN_RUNNING`, `RETAIN_STOPPED` e `Enabled`
- evite texto livre em campos booleanos para nao quebrar a validacao operacional
- para schedules, `Periods` e o formato preferido/oficial
- `Start` e `Stop` continuam suportados como atalho para janelas simples e operacao manual no Portal
- `RETAIN_RUNNING` e temporario no comportamento atual
- `RETAIN_STOPPED` continua persistente no comportamento atual

## 1. Exemplo Minimo de Config Global

Tabela:

- `OffHoursSchedulerConfig`

Entidade:

```json
{
  "PartitionKey": "GLOBAL",
  "RowKey": "runtime",
  "DRY_RUN": true,
  "DEFAULT_TIMEZONE": "America/Sao_Paulo",
  "SCHEDULE_TAG_KEY": "schedule",
  "RETAIN_RUNNING": false,
  "RETAIN_STOPPED": false,
  "Version": "1",
  "UpdatedAtUtc": "2026-03-17T12:00:00Z",
  "UpdatedBy": "ops@example.com"
}
```

## 2. Exemplo Minimo de Schedule Simples

Tabela:

- `OffHoursSchedulerSchedules`

Entidade:

```json
{
  "PartitionKey": "SCHEDULE",
  "RowKey": "business-hours",
  "Start": "08:00",
  "Stop": "18:00",
  "SkipDays": "saturday,sunday",
  "Enabled": true,
  "Version": "1",
  "UpdatedAtUtc": "2026-03-17T12:05:00Z",
  "UpdatedBy": "ops@example.com"
}
```

Tag no recurso:

```text
schedule=business-hours
```

## 3. Exemplo de Schedule com Multiplas Janelas

Entidade:

```json
{
  "PartitionKey": "SCHEDULE",
  "RowKey": "office-hours",
  "Periods": "[{\"start\":\"08:00\",\"stop\":\"12:00\"},{\"start\":\"13:00\",\"stop\":\"18:00\"}]",
  "SkipDays": "saturday,sunday",
  "Enabled": true,
  "Version": "2",
  "UpdatedAtUtc": "2026-03-17T12:10:00Z",
  "UpdatedBy": "ops@example.com"
}
```

## 4. Exemplo de Escopo por Subscription

Entidade:

```json
{
  "PartitionKey": "SCHEDULE",
  "RowKey": "prod-office-hours",
  "Start": "07:00",
  "Stop": "19:00",
  "IncludeSubscriptions": "sub-a,sub-b",
  "ExcludeSubscriptions": "sub-b",
  "Enabled": true,
  "Version": "3",
  "UpdatedAtUtc": "2026-03-17T12:15:00Z",
  "UpdatedBy": "ops@example.com"
}
```

Leitura pratica:

- `sub-a`: entra
- `sub-b`: fica fora porque `exclude` vence

## 5. Exemplo de Escopo por Management Group

Entidade:

```json
{
  "PartitionKey": "SCHEDULE",
  "RowKey": "shared-services",
  "Start": "08:00",
  "Stop": "20:00",
  "IncludeManagementGroups": "mg-shared,mg-platform",
  "ExcludeManagementGroups": "mg-blocked",
  "Enabled": true,
  "Version": "1",
  "UpdatedAtUtc": "2026-03-17T12:20:00Z",
  "UpdatedBy": "ops@example.com"
}
```

## 6. Exemplo de VM com Timezone Local

Tags:

```text
schedule=office-hours
timezone=America/Mexico_City
```

Nesse caso:

- o schedule continua vindo da tabela
- o timezone da avaliacao vem da tag do recurso
- se a tag faltar, o fallback e `DEFAULT_TIMEZONE`

## 7. Exemplo de Escopo Tecnico por Subscriptions

Trecho de `infra/bicep/main.parameters.json`:

```json
{
  "parameters": {
    "subscriptionIds": {
      "value": [
        "00000000-0000-0000-0000-000000000000",
        "11111111-1111-1111-1111-111111111111"
      ]
    },
    "managementGroupIds": {
      "value": []
    },
    "excludeSubscriptionIds": {
      "value": []
    }
  }
}
```

## 8. Exemplo de Escopo Tecnico por Management Groups

Trecho de `infra/bicep/main.parameters.json`:

```json
{
  "parameters": {
    "subscriptionIds": {
      "value": []
    },
    "managementGroupIds": {
      "value": [
        "mg-platform-prod",
        "mg-shared-services"
      ]
    },
    "excludeSubscriptionIds": {
      "value": [
        "22222222-2222-2222-2222-222222222222"
      ]
    }
  }
}
```

## 9. Exemplo de Filtro Regional

Trecho de `infra/bicep/main.parameters.json`:

```json
{
  "parameters": {
    "targetResourceLocations": {
      "value": [
        "brazilsouth",
        "eastus2"
      ]
    }
  }
}
```

Com isso:

- a Function continua enxergando apenas o escopo tecnico efetivo
- dentro desse escopo, o discovery considera apenas recursos nessas regioes

Se quiser todas as regioes:

```json
{
  "parameters": {
    "targetResourceLocations": {
      "value": []
    }
  }
}
```

## 10. Exemplo de Teste Seguro Inicial

Passo a passo recomendado:

1. subir a infra
2. ajustar `DRY_RUN=true` se quiser uma validacao inicial sem acao real
3. criar `business-hours`
4. marcar uma VM com:

```text
schedule=business-hours
```

5. acompanhar logs da Function
6. validar se a decisao calculada esta correta
7. so depois mudar `DRY_RUN` para `false`

## 11. Exemplo de Bootstrap Default

O bootstrap default cria:

Config:

```json
{
  "PartitionKey": "GLOBAL",
  "RowKey": "runtime",
  "DRY_RUN": false,
  "DEFAULT_TIMEZONE": "America/Sao_Paulo",
  "SCHEDULE_TAG_KEY": "schedule",
  "RETAIN_RUNNING": false,
  "RETAIN_STOPPED": false,
  "Version": "1",
  "UpdatedAtUtc": "<utc-now>",
  "UpdatedBy": "<operator>"
}
```

Schedule:

```json
{
  "PartitionKey": "SCHEDULE",
  "RowKey": "business-hours",
  "Start": "08:00",
  "Stop": "18:00",
  "SkipDays": "saturday,sunday",
  "Enabled": true,
  "Version": "1",
  "UpdatedAtUtc": "<utc-now>",
  "UpdatedBy": "<operator>"
}
```
