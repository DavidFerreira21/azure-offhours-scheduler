# Azure OffHours Scheduler

![CI](https://github.com/<OWNER>/<REPO>/actions/workflows/ci.yml/badge.svg)
![License](https://img.shields.io/badge/license-Apache%202.0-blue.svg)
![Python](https://img.shields.io/badge/python-3.12-blue.svg)

English version: [README.en.md](README.en.md)

**Desligue automaticamente recursos não produtivos fora do horário, de forma centralizada, auditável e segura.**

Azure OffHours Scheduler é uma automação open source pronta para produção que reduz custo no Azure com schedules orientados por tabela, escopo controlado e execução segura.

## Por Que Este Projeto?

- Reduz custo de compute sem exigir automações diferentes para cada time
- Permite operação segura com schedules editáveis após o deploy
- Suporta ambientes enterprise com múltiplas subscriptions e governança centralizada
- Respeita intervenções manuais com regras de retenção
- Mantém a solução enxuta, previsível e simples de operar

## O Problema

Grande parte das soluções de off-hours falha nos mesmos pontos:

- schedules ficam hardcoded em arquivos ou app settings
- alterar janelas operacionais exige código ou redeploy
- controlar escopo entre subscriptions vira operação manual e frágil
- overrides manuais são desfeitos rápido demais
- os logs mostram que algo rodou, mas não deixam claro o resultado

## A Solução

Azure OffHours Scheduler centraliza a configuração operacional do scheduler sem misturar regra de negócio com configuração técnica de runtime:

- runtime fica em app settings da Function e no Bicep
- schedules e comportamento global ficam em Azure Table Storage
- os recursos entram no ciclo por tag, por exemplo `schedule=business-hours`
- o escopo pode ser controlado por subscription, management group e exclusões
- cada execução gera um relatório estruturado com resultado por recurso

## Arquitetura Simplificada

```text
Timer Trigger
  ↓
Config + Schedules no Table Storage
  ↓
Discovery via Azure Resource Graph
  ↓
Avaliação de regras e escopo
  ↓
Ação: START | STOP | SKIP
  ↓
Persistência de estado
  ↓
Relatório estruturado da execução
```

Tabelas principais:

- `OffHoursSchedulerConfig`
- `OffHoursSchedulerSchedules`
- `OffHoursSchedulerState`

## Quick Start

Setup:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp infra/bicep/main.parameters.example.json infra/bicep/main.parameters.json
az login
```

Deploy:

```bash
make deploy
```

Ou:

```bash
./scripts/deploy_scheduler.sh --parameters-file infra/bicep/main.parameters.json
```

Parâmetros mínimos:

- `resourceGroupName`
- `location`
- `namePrefix`
- `subscriptionIds` ou `managementGroupIds`
- `tableOperatorsGroupObjectId`

## Exemplo de Uso

Tag em uma VM:

```text
schedule=business-hours
```

Exemplo simples de schedule:

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

Formato preferido para janelas mais ricas:

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

## Casos de Uso

- Ambientes de desenvolvimento e sandbox com horários previsíveis
- Ambientes enterprise com múltiplas subscriptions e governança centralizada
- Iniciativas de FinOps focadas em reduzir custo de compute ocioso

## Funcionalidades

- Schedules e configuração global orientados por tabela
- Suporte a múltiplas subscriptions com escopo opcional por management group
- Regras de include/exclude com precedência explícita de exclude
- Retenção para respeitar override manual do operador
- Filtro regional com `targetResourceLocations`
- Timer técnico configurável com `TIMER_SCHEDULE`
- Bootstrap padrão no primeiro deploy
- Fluxo de deploy limpo com Bicep

## Observabilidade

A solução já entrega visibilidade operacional por execução, sem exigir ferramentas adicionais para começar:

- Correlation ID por execução via `run_id`
- Tempo total do ciclo e tempo por recurso com `duration_sec`
- Relatório final emitido como uma única linha JSON em todo ciclo
- Resultado estruturado por recurso com ação, status e motivo
- Em produção, o padrão recomendado é `RESOURCE_RESULT_LOG_MODE=executed-and-errors`
- Logs verbosos de request/response do SDK Azure ficam desabilitados por padrão

Exemplo de formato do relatório:

```json
{
  "run_id": "...",
  "timestamp": "...",
  "dry_run": true,
  "summary": {
    "total": 2,
    "started": 1,
    "stopped": 0,
    "skipped": 1
  },
  "duration_sec": 1.234,
  "resources": []
}
```

## Objetivos de Design

- Permitir mudanças operacionais sem depender de redeploy
- Automatizar com segurança antes de automatizar com agressividade
- Separar configuração técnica de runtime das regras do scheduler
- Manter escopo explícito, auditável e governável
- Entregar observabilidade útil sem adicionar infraestrutura extra

## Documentação

- Índice da documentação: [docs/README.md](docs/README.md)
- Arquitetura: [docs/architecture.md](docs/architecture.md)
- Exemplos: [docs/examples.md](docs/examples.md)
- Guia operacional: [docs/operator-guide.md](docs/operator-guide.md)
- Guia de desenvolvimento: [docs/developer-guide.md](docs/developer-guide.md)
- Estrutura do repositório: [docs/repository-map.md](docs/repository-map.md)
- Componentes de código: [docs/code-components.md](docs/code-components.md)
- Troubleshooting: [docs/troubleshooting.md](docs/troubleshooting.md)
- Política de release: [docs/release-policy.md](docs/release-policy.md)

## Recursos Suportados

Hoje:

- `Microsoft.Compute/virtualMachines`

Roadmap:

- `VirtualMachineScaleSets`
- `App Services`
- outros recursos elegíveis para estratégia off-hours

## Princípios de Design

- Dados operacionais ficam em tabelas, não no código
- Configuração técnica de runtime fica separada das regras de negócio
- Defaults operacionais devem ser explícitos
- Escopo deve ser explícito e auditável
- A solução deve continuar simples de operar
- Observabilidade deve crescer sem introduzir complexidade desnecessária

## Contribuição

- Guia de contribuição: [CONTRIBUTING.md](CONTRIBUTING.md)
- Código de conduta: [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md)
- Política de segurança: [SECURITY.md](SECURITY.md)
- Licença: [LICENSE](LICENSE)
- A CI valida lint, SAST, audit de dependências, testes, scripts shell e compilação do Bicep

Versão atual:

- `1.0.0`
