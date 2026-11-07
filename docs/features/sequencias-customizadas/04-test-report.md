# Relatório de testes — Sequências de Acordes Customizadas

## Cobertura

Suíte automatizada em `tests/test_sequencias.py`, usando `unittest` e
`app.test_client()` com `SEQUENCIAS_DB` apontando para um arquivo temporário:

- `GET /sequencias` — retorna as 6 seeds ordenadas por `id`, com `acordes`,
  `origem='seed'` e `criado_em`.
- `POST /sequencias` — criação nova (201), aceite de `acordes` como string,
  deduplicação por chave canônica (200 + `duplicada: true`) inclusive com
  variação de caixa/espaços, e rejeição de payload inválido (400) para corpo
  não-objeto, lista vazia, acordes vazios, mais de 16 acordes e tipos errados.
- Busca por sequência customizada criada via `POST`, agregando todas as
  páginas de `/similares?sequencia=...`.
- Busca case-insensitive: a mesma sequência em minúsculas e maiúsculas
  devolve o mesmo conjunto.
- Formato antigo sem vírgulas (`CGAmF`, `BmGDA`) e sequência inexistente
  retornam `[]`.
- Persistência: após o `POST`, uma nova conexão SQLite ao mesmo arquivo lê o
  registro criado.
- Normalização de gênero: `R&B;` não existe mais, `R&B` está em `GET /generos`,
  nenhum gênero termina em `;` e o filtro `generos=R&B` devolve apenas músicas
  desse gênero.
- Regressão das 6 sequências contra a fixture gerada antes da mudança.

## Teste de regressão obrigatório

A fixture `tests/fixtures/regressao_sequencias.json` foi gerada com o app ainda
no estado antigo (`app.test_client()`), agregando todas as páginas de
`/similares?sequencia=...`. Contagens do baseline:

| Sequência | Músicas |
|---|---:|
| Bm,G,D,A | 199 |
| C,G,Am,F | 296 |
| Em,G | 4 |
| C,A7,Dm,G7 | 5 |
| Gm,F | 7 |
| C,C7,F,Fm | 3 |

Depois da migração para a regra D em runtime, o teste
`test_regressao_das_seis_sequencias` compara os conjuntos e o resultado foi
**0 faltantes e 0 extras em todas as 6 sequências**. O baseline de gêneros
registrou 52 gêneros e 303 músicas com `R&B;`; após `rstrip(';')`, o gênero
`R&B` (303 músicas) passa a ser encontrável pelo filtro.

Smoke test manual com servidor local: `/` responde 200, `GET /sequencias`
lista as 6 seeds, `POST /sequencias` cria (201) e deduplica (200), a busca pela
sequência criada funciona, o formato antigo retorna `[]` e o filtro `R&B`
retorna somente músicas de `R&B`.

## Como rodar

```
python -m unittest discover -s tests -v
```

## O que ficou de fora

- Não foi executado um teste E2E de navegador (AngularJS); o frontend foi
  verificado por checagem de sintaxe com `node --check`, pela ausência de
  referências à antiga constante `GENEROS` e pelo contrato dos endpoints
  exercitado via `app.test_client()`. A verificação visual de `#/porsequencia`
  fica pendente de uma execução manual no browser.
- A sobrevivência do banco a `docker restart`/recriação de container com volume
  nomeado não foi automatizada (exigiria Docker); a configuração
  `VOLUME /app/instance` e o uso de volume nomeado estão documentados no
  README.
- Desempenho do matching em runtime não foi medido com benchmark; a suíte de
  regressão completa (6 sequências, todas as páginas) roda em cerca de 6
  segundos no ambiente de teste.
- Concorrência de escrita, rate limiting e normalização avançada de acordes
  estão fora do escopo conforme a proposta.
