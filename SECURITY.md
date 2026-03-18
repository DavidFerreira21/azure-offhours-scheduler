# Security Policy

## Escopo

Este projeto automatiza operacoes de `start` e `stop` em recursos Azure. Por isso, problemas de seguranca ou falhas de desenho operacional podem ter impacto real em ambientes de nuvem.

Use divulgacao responsavel.

## Como Reportar Vulnerabilidades

Se voce identificar uma vulnerabilidade ou um problema de seguranca, nao abra uma issue publica com detalhes exploraveis.

Em vez disso:

1. descreva o problema
2. explique o impacto
3. forneca passos de reproducao
4. informe versao, contexto e area afetada

Envie o relato ao mantenedor do projeto pelo canal definido pela comunidade ou pelo repositório.

Se ainda nao houver um canal formal publicado, abra uma issue publica apenas pedindo um canal de contato privado, sem divulgar detalhes tecnicos da vulnerabilidade.

## O Que Consideramos Problema de Seguranca

Exemplos:

- bypass de escopo que permita operar recursos fora do alvo esperado
- exposicao indevida de credenciais ou connection strings
- elevacao indevida de permissao no deploy
- falhas que permitam alterar comportamento do scheduler sem auditoria adequada
- problemas que permitam operacoes destrutivas fora da logica esperada

## O Que Nao e Vulnerabilidade por Si So

Exemplos:

- configuracao insegura feita pelo proprio operador
- uso deliberado de permissao ampla no ambiente sem mitigacao externa
- limite funcional conhecido e documentado

## Boas Praticas Operacionais

Para reduzir risco:

- prefira `DRY_RUN=true` em validacoes iniciais
- valide escopo tecnico e operacional antes de ativar execucao real
- revise role assignments no deploy
- use grupo dedicado para operacao das tabelas
- mantenha auditoria em `Version`, `UpdatedAtUtc` e `UpdatedBy`
- teste novas configuracoes em ambiente nao produtivo primeiro

## Credenciais e Dados Sensiveis

Nunca publique em issues ou PRs:

- connection strings
- chaves de Storage
- object IDs sensiveis sem necessidade
- nomes de subscriptions/clientes que nao devam ser publicos
- dumps de tabelas com dados reais de operacao

## Expectativa de Correcao

O projeto e mantido em base best effort.

Relatos de seguranca bem documentados ajudam muito a reduzir tempo de analise e correcao.
