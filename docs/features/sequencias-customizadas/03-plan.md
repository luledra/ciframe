# Plano — Sequências de Acordes Customizadas

## Contexto e decisões

**Situação atual**
- O backend reconhece apenas 6 sequências hardcoded (`main.py:40-45`) e busca pela tag pré-computada `SEQ_FAMOSA`; o frontend mostra 4 sequências hardcoded em `sequencia.js:2-37`.
- Não existe catálogo dinâmico, cadastro de sequência nem matching em tempo real.
- Músicas e gêneros continuam vindo do CSV em memória; somente o catálogo de sequências passa a ser persistido.

**Escopo desta fase**
- Implementar o que está em `02-proposal.md` e na ADR `0002-persist-custom-sequences.md`.
- Matching em runtime pela regra D (bloco contíguo ordenado + vocabulário da música contido no da sequência) sobre `musica.cifra`, para todas as sequências.
- Catálogo de sequências em SQLite (`sqlite3` da stdlib), com seed idempotente das 6 originais.
- Endpoints `GET /sequencias`, `POST /sequencias` e evolução de `GET /similares?sequencia=...`.
- Frontend `#/porsequencia` lendo o catálogo do backend e permitindo cadastro.
- Gêneros do frontend unificados em `GET /generos`, com normalização de `R&B;` para `R&B` no carregamento do CSV.

**Restrições fixas**
- Não migrar `musicas`/`generos` para o banco; o CSV continua carregado em memória.
- Manter o container único e local-only da ADR 0001, sem serviço externo.
- Manter `json.dumps(...)` como resposta, nunca `jsonify`.
- Manter os mesmos resultados das 6 sequências atuais (0 faltantes, 0 extras).
- Fora do escopo: login, moderação, edição/remoção de sequências, normalização avançada de acordes, rate limiting e deploy em nuvem.
- Não há prazo externo definido; executar os passos na ordem abaixo e verificar cada um antes de avançar.

## Passos

### Preparação e baseline

1. [x] Antes de alterar o backend, rodar o app atual via `app.test_client()` e salvar em `tests/fixtures/regressao_sequencias.json` os `id_unico_musica` de todas as páginas das 6 sequências.
2. [x] Registrar a contagem atual de gêneros e os ids das músicas com `R&B;`, para comparar depois da normalização.

### Backend — persistência

3. [x] Em `main.py`, definir `CAMINHO_DB` com default `instance/sequencias.db` e override por `SEQUENCIAS_DB`; criar o diretório com `os.makedirs(..., exist_ok=True)`; abrir conexões curtas por operação e ativar `PRAGMA journal_mode=WAL` na inicialização.
4. [x] Criar a tabela `sequencias` de forma idempotente (`CREATE TABLE IF NOT EXISTS`) com `id`, `acordes_json`, `chave_canonica TEXT NOT NULL UNIQUE`, `origem` e `criado_em`.
5. [x] Definir `SEQUENCIAS_SEED` com as 6 listas na ordem original e inserir com `INSERT OR IGNORE`, `origem='seed'` e `criado_em` em UTC; não sobrescrever sequências customizadas.
6. [x] Implementar `normalizar_acordes` (aceita lista ou string, faz `strip`, descarta vazios, preserva a grafia original e gera a chave em minúsculas separada por vírgula) e a validação: 1 a 16 acordes, cada acorde não vazio.
7. [x] Implementar helpers de leitura/escrita e a serialização `acordes_json` ↔ lista; logar no startup o caminho do banco e a quantidade de seeds.

### Backend — API e matching

8. [x] Implementar `GET /sequencias`: selecionar por `id`, desserializar `acordes_json` e retornar `json.dumps([...])` com `id`, `acordes`, `origem` e `criado_em`.
9. [x] Implementar `POST /sequencias`: ler `request.get_json(silent=True)`, validar, inserir e responder com `json.dumps(...)`; criação nova → 201; chave já existente → 200 com o registro existente e `"duplicada": true`; payload inválido → 400 com `{"erro": "..."}`.
10. [x] Remover o dicionário `sequencias` hardcoded e o caminho de `/similares` que consulta `musica.seqs_famosas`.
11. [x] Implementar `sequencia_aparece_na_musica(cifra_musica, acordes_sequencia)`: normalizar tokens para minúsculas, verificar bloco contíguo na ordem e verificar `set(musica.cifra) ⊆ set(sequencia.acordes)`; varrer `musica.cifra`, nunca `musica.acordes`.
12. [x] Refatorar `GET /similares?sequencia=...`: canonicalizar a entrada por vírgulas (`strip` + minúsculas), resolver somente por `chave_canonica`; sequência inexistente → `[]`; não remover vírgulas nem aceitar o formato antigo `CGAmF`; reutilizar `apply_filtro`, `get_pagina` e o formato de objeto atual, sem `diferenca`/`intersecao`.
13. [x] Normalizar o gênero no carregamento do CSV: `musica[GENERO] = musica[GENERO].rstrip(';')` antes de `generos.add` e da criação de `Musica`, para que `R&B;` vire `R&B` também nas músicas.

### Infraestrutura e persistência do arquivo

14. [x] Atualizar o `Dockerfile` com `RUN mkdir -p /app/instance` e `VOLUME /app/instance`; manter `/app/data` intocado para não sombrear o CSV.
15. [x] Adicionar `instance/` ao `.gitignore` e ao `.dockerignore` para não versionar nem copiar o banco local para a imagem.
16. [x] Atualizar o `README.md` com o uso de volume nomeado (`docker run -v ciframe-instance:/app/instance -p 8080:8080 ciframe`) e nota de que o catálogo de músicas continua no CSV em memória.

### Frontend — gêneros

17. [x] Em `app.js`, remover a constante `GENEROS` e criar a factory `GenerosService`, que faz `GET /generos` uma única vez, compartilha a promise e expõe falha para a tela.
18. [x] Em `sequencia.js`, `acordes.js` e `musica.js`, injetar `GenerosService`, inicializar `vm.generos = []` e preencher no `.then`; remover a injeção de `GENEROS`.

### Frontend — catálogo e cadastro

19. [x] Em `sequencia.js`, remover as 4 sequências hardcoded e carregar `GET /sequencias` na inicialização, mapeando cada linha para `{index, acordes: [{acorde, cor: '#2E1C74'}]}`; manter `createChordsString` e `pesquisarPorSequencia`.
20. [x] Em `sequencia.js`, adicionar `vm.novaSequencia = {acordes: ''}`, `vm.cadastrando`, `vm.mensagem`, `vm.erro` e `vm.cadastrarSequencia()`: enviar `POST /sequencias`; em 201/200 limpar o formulário, exibir mensagem (200 = já existia) e recarregar o catálogo; em 400 exibir `data.erro`; em falha de rede exibir mensagem genérica.
21. [x] Em `sequencia.html`, adicionar formulário com acordes separados por vírgula, botão de cadastro e áreas de sucesso/erro; deixar o texto digitado em preto no campo; manter a lista `ng-repeat`, o clique para buscar e os cards de resultado sem alteração.

### Testes e verificação

22. [x] Criar `tests/test_sequencias.py` com `unittest` e `app.test_client()`, usando `SEQUENCIAS_DB` apontando para arquivo temporário; cobrir `GET /sequencias`, `POST` válido, duplicata, payload inválido, busca de sequência customizada, busca case-insensitive e formato antigo retornando `[]`.
23. [x] Adicionar o teste de regressão: para cada uma das 6 sequências, agregar todas as páginas de `/similares?sequencia=...` e comparar com a fixture do passo 1, falhando em qualquer faltante ou extra.
24. [x] Testar persistência: cadastrar uma sequência, abrir nova conexão/processo com o mesmo arquivo e confirmar que o registro continua disponível.
25. [x] Verificar manualmente no browser: `#/porsequencia` lista as 6 seeds, cadastro funciona, busca funciona, o select de gêneros vem de `/generos` e `R&B` filtra corretamente.
26. [x] Atualizar `04-test-report.md` com cobertura, resultado da regressão e o comando `python -m unittest discover -s tests -v`.

## Arquivos afetados

| Arquivo | Mudança |
|---|---|
| `main.py` | Inicialização e seed do SQLite, `GET/POST /sequencias`, matching em runtime, canonicalização de `/similares`, remoção do dicionário hardcoded e normalização de gênero. |
| `musica.py` | Sem mudança prevista; `cifra` já preserva ordem e repetições. |
| `Dockerfile` | Criação de `/app/instance` e `VOLUME /app/instance`. |
| `.gitignore` / `.dockerignore` | Exclusão do diretório `instance/` e do arquivo do banco local. |
| `README.md` | Instrução de volume nomeado e nota sobre a persistência do catálogo. |
| `static/assets/js/app.js` | Remoção da constante `GENEROS` e criação da factory `GenerosService`. |
| `static/assets/js/controllers/sequencia.js` | Catálogo vindo do backend, remoção das sequências hardcoded, formulário e `cadastrarSequencia()`. |
| `static/assets/js/controllers/acordes.js` | Uso de `GenerosService` no lugar da constante `GENEROS`. |
| `static/assets/js/controllers/musica.js` | Uso de `GenerosService` no lugar da constante `GENEROS`. |
| `static/templates/sequencia.html` | Formulário de cadastro e mensagens de sucesso/erro, mantendo lista e cards. |
| `tests/test_sequencias.py` | (novo) Testes de API, matching, validação e persistência. |
| `tests/fixtures/regressao_sequencias.json` | (novo) Baseline dos resultados das 6 sequências antes da mudança. |
| `docs/features/sequencias-customizadas/04-test-report.md` | Relatório da fase 5. |

## Riscos e mitigação

| Risco | Como perceber | Mitigação |
|---|---|---|
| Divergência entre a regra D implementada e a tag `SEQ_FAMOSA` | Teste de regressão com faltantes ou extras | Comparar todas as páginas das 6 sequências com a fixture; investigar caixa, tokens vazios e repetições antes de ajustar. |
| Perda do catálogo ao recriar o container | Cadastro some após `docker rm` + container novo | Declarar `VOLUME /app/instance` e documentar volume nomeado; validar `docker restart` e recriação com volume. |
| Concorrência de escrita no SQLite | Erro `database is locked` | Usar WAL, transações curtas e conexões por operação; manter um worker gunicorn por default. |
| Lentidão por varrer todas as músicas a cada busca | Aumento de latência em `/similares` | Medir o tempo com o dataset atual; aceitar o custo nesta fase e registrar cache/pré-cálculo como evolução futura. |
| Payload inválido ou abusivo no catálogo aberto | Respostas 500 ou linhas inconsistentes | Validar tipos, quantidade de acordes e acorde vazio; responder 400. Rate limiting fica fora do escopo. |
| Clientes antigos usando `sequencia=CGAmF` | Busca passa a retornar `[]` | Mudança de contrato explícita na proposta/ADR; o frontend já envia vírgulas. |
| Normalização de `R&B;` aplicada só no conjunto de gêneros | Contagem divergente e filtro por `R&B` sem resultados | Normalizar antes de `generos.add` e da criação de `Musica`; testar a contagem e o filtro. |
| Catálogo vazio no frontend se `GET /sequencias` falhar | Lista em branco ou sem mensagem | Estado de carregamento e mensagem de erro no controller/template; não remover a busca existente. |

## Pendências

Itens em aberto, identificados após a revisão de código, que ficaram como melhorias:

- [ ] Definir com o cliente a lista de acordes válidos e validar os acordes
  informados no cadastro (hoje qualquer texto não vazio é aceito).
- [ ] Validar formato e tamanho dos acordes em `main.py:65-85` (ex.: `"C G Am F"`
  sem vírgulas é aceito como um único acorde) e limitar o tamanho do payload
  (considerar `MAX_CONTENT_LENGTH`).
- [ ] Definir com o cliente a semântica da busca por sequência: apenas músicas
  que usam só a sequência (regra D atual) ou qualquer música em que a sequência
  aparece, mesmo com outros acordes. A decisão pode alterar o matching e o
  baseline de regressão.
- [ ] Otimizar o matching em `main.py:362-395`: pré-computar a cifra em
  minúsculas no carregamento e evitar recalcular `set(sequencia)` e a varredura
  completa a cada página; avaliar cache por chave canônica.
- [ ] Exibir falha de carregamento de gêneros: `vm.erroGeneros` é definido em
  `acordes.js`, `musica.js` e `sequencia.js`, mas nenhum template o mostra.
- [ ] Limitar/paginar `GET /sequencias` (`main.py:264-273`) e definir um teto de
  crescimento do catálogo, já que o `POST` é aberto e sem autenticação.
- [ ] Validar e limitar `pagina` em `get_pagina` (`main.py:399-401`): valores
  não numéricos geram 500 e páginas `0`/negativas retornam slices inesperados.
- [ ] Melhorar o isolamento dos testes (`tests/test_sequencias.py:8-12`): usar
  um arquivo de banco por teste e restaurar `SEQUENCIAS_DB` ao final.
- [ ] Melhorias no formulário de `sequencia.html:7-14`: usar `<form ng-submit>`,
  `<label>` acessível e `maxlength`; remover `ng-hide="music.diferenca.length"`
  de `sequencia.html:64`, irrelevante para resultados de sequência.

## Definição de pronto

- [x] `GET /sequencias` retorna as 6 sequências seed e qualquer sequência customizada persistida, ordenadas por `id`.
- [x] `POST /sequencias` cria uma sequência nova (201), deduplica chaves existentes (200 com `duplicada: true`) e rejeita payload inválido (400).
- [x] As 6 sequências originais continuam retornando exatamente os mesmos conjuntos de músicas de antes (0 faltantes, 0 extras).
- [x] Uma sequência cadastrada pode ser buscada por `GET /similares?sequencia=...` usando a regra D.
- [x] A busca é case-insensitive e o formato antigo sem vírgulas (`CGAmF`) retorna `[]`.
- [x] O banco sobrevive a `docker restart` e à recriação do container quando usado o volume nomeado.
- [x] `#/porsequencia` lista o catálogo real, permite cadastrar sequência e buscar por qualquer sequência listada.
- [x] O select de gêneros usa `GET /generos` e o filtro por `R&B` funciona.
- [x] A suíte de testes passa com `python -m unittest discover -s tests -v`.
- [x] Todas as respostas continuam usando `json.dumps(...)` e o catálogo de músicas/gêneros continua vindo do CSV em memória.
