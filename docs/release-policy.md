# Política de Release e Compatibilidade

Este documento define a política de compatibilidade e release do projeto.

## Alvos de Compatibilidade Atuais

O projeto atualmente considera como baseline:

- Python `3.12`
- Azure Functions runtime `v4`
- Azure Table Storage para configuração operacional e estado
- Azure Resource Graph para discovery

Suporte atual para ação real:

- `Microsoft.Compute/virtualMachines`

## Direção de Versionamento

A baseline atual do projeto é `1.0.0`.

A partir de `1.0.0`:

- breaking changes devem ser excepcionais e claramente anunciadas
- mudanças de schema ou comportamento devem incluir orientação de migração
- exemplos e documentação operacional devem ser atualizados na mesma mudança
- app settings, schema das tabelas e semântica de retain não devem mudar silenciosamente

Expectativa dos maintainers:

- documentar breaking changes com clareza
- atualizar exemplos e documentação técnica junto com a mudança
- evitar mudanças silenciosas de comportamento

## Compatibilidade do Schema das Tabelas

O scheduler depende de 3 tabelas:

- `OffHoursSchedulerConfig`
- `OffHoursSchedulerSchedules`
- `OffHoursSchedulerState`

Se uma mudança afetar formato de entidade, campos obrigatórios ou regra de interpretação:

- a mudança deve ser documentada
- os exemplos devem ser atualizados
- o changelog ou release notes devem indicar o impacto operacional

Campos mínimos de auditoria esperados hoje:

- `Version`
- `UpdatedAtUtc`
- `UpdatedBy`

## Compatibilidade de Deploy

O caminho recomendado de deploy é:

```bash
./scripts/deploy_scheduler.sh
```

Isso é especialmente importante quando o escopo usa:

- `managementGroupIds`
- `excludeSubscriptionIds`

Porque o wrapper resolve o escopo efetivo antes do deploy.
Ele tambem preenche `resourceGroupName` automaticamente quando o arquivo de parametros deixa esse valor vazio.

## Política de Dependências

Regra atual:

- `requirements.txt` da raiz é a fonte da verdade para dependências de runtime
- `function/requirements.txt` é gerado por `scripts/prepare_function_app_publish.sh`

Contribuidores devem atualizar dependências no arquivo da raiz e validar:

- testes
- preparação do bundle da Function

## Expectativas de CI

Mudanças não devem quebrar:

- `ruff check .`
- `bandit -q -r src function -c pyproject.toml`
- `pip-audit --local --progress-spinner off`
- `pytest -q`
- validação sintática dos scripts shell
- compilação do Bicep
- preparação do bundle da Function

A CI do repositório deve validar esse baseline.

## Orientação de Compatibilidade Retroativa

O projeto busca preservar:

- app settings documentadas
- nomes documentados das tabelas
- o significado operacional de `DRY_RUN`
- a semântica atual de retain:
  - `RETAIN_RUNNING` como override manual temporário
  - `RETAIN_STOPPED` como override manual persistente

Se alguma mudança precisar quebrar compatibilidade:

- documente de forma explícita
- forneça orientação de migração sempre que possível

## Orientação para Release Notes

Ao publicar uma release relevante ou marco importante, inclua:

- novas capacidades
- breaking changes
- passos de migração
- mudanças de deploy
- mudanças de schema
- notas de compatibilidade
