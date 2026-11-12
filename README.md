# Nosso Apê 3.0 — PostgreSQL + FastAPI + Dashboard

Esta versão adiciona **Cotado / Aprovado / Recusado**, compara **preço à vista e total a prazo**, agrupa propostas por **nome do item**, permite selecionar a forma de pagamento da proposta aprovada e controla **parcelas com vencimento e baixa individual**. Mantém os dados do banco da versão 2.

## IMPORTANTE — antes de atualizar

1. **Não substitua o `.env`** nem a pasta `.git`. Não envie senhas, backups nem orçamentos reais ao GitHub.
2. Pare a API antiga no terminal (`Ctrl+C`) ou o serviço que a executa. Deixe o PostgreSQL ativo.
3. Faça um **backup do PostgreSQL**, de preferência pelo pgAdmin: selecione o banco `nosso_ape` → **Backup...** → formato **Custom** → salve um `.backup` fora da pasta do repositório. Confirme que o arquivo foi criado. A migração muda tabelas reais.
4. Extraia os arquivos do pacote na raiz de `C:\Users\otavi\OneDrive\003 - Repos\nosso_ape_app`, fazendo cópia dos arquivos substituídos antes. O pacote foi criado para ser mesclado à raiz do repositório.
5. Abra PowerShell nessa pasta e execute:

```powershell
cd "C:\Users\otavi\OneDrive\003 - Repos\nosso_ape_app"
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m scripts.migrate_v3
.\.venv\Scripts\python.exe -m scripts.init_db
.\.venv\Scripts\python.exe -m pytest -q
```

`migrate_v3` é um script de migração **aditiva e idempotente**: adiciona colunas em `orcamentos` e a tabela `parcelas`, sem apagar orçamentos. Itens antigos `Pago` são convertidos em uma parcela já quitada; `Aprovado`, em parcela pendente. **Não é Alembic nesta entrega**; a migração é executada explicitamente pelo comando acima. Não use `drop_all` nem recrie o banco.

## Iniciar a API e o painel local

Terminal 1:

```powershell
.\.venv\Scripts\python.exe -m uvicorn api.main:app --host 127.0.0.1 --port 8000
```

Terminal 2:

```powershell
.\.venv\Scripts\python.exe -m http.server 8080 --bind 127.0.0.1 -d frontend
```

Abra `http://127.0.0.1:8080`, clique **Conectar PostgreSQL**, use `http://127.0.0.1:8000` e seu usuário existente. **Não abra o arquivo HTML com `file://`**.

## Como usar a versão 3

1. Em **Lançamentos**, crie até três propostas para a compra usando o **mesmo nome em “Agrupar propostas do mesmo item”** e a mesma categoria. Fornecedores diferentes podem ter preços diferentes.
2. Cadastre ambos: **valor à vista** e **valor total a prazo**. O painel mostra o acréscimo em reais e percentual relativo ao valor à vista (não taxa mensal efetiva).
3. Marque uma proposta como **Aprovado** e as demais como **Recusado**. A API bloqueia duas aprovações do mesmo item na mesma categoria.
4. Ao aprovar, selecione **À vista** (1 pagamento) ou **Parcelado**, indique a quantidade e o primeiro vencimento. A API gera parcelas mensais, arredondadas em centavos.
5. Na aba **Parcelas**, marque o pagamento de cada parcela. Os valores **Comprometido**, **Pago** e **A pagar** são calculados sem duplicar os pagamentos.

### Regras de negócio

- **Cotado** e **Recusado** não comprometem a meta. Recusado permanece no histórico. Para a projeção, o painel considera apenas a menor cotação à vista por item ainda não aprovado, não a soma de três propostas.
- **Aprovado** compromete valor à vista ou valor total a prazo, conforme modalidade selecionada.
- **Pago** é um status legado preservado para compatibilidade; novos pagamentos devem ser baixados na aba **Parcelas**.
- Depois que uma parcela é paga, a API impede alteração de valor, número de parcelas e datas de vencimento, ou exclusão do orçamento, para preservar o histórico. É possível desfazer a baixa se necessário.
- O cálculo do percentual de acréscimo é `(total_a_prazo - valor_a_vista) / valor_a_vista`. Não representa taxa efetiva de juros ao mês (CET).
- Pagamento parcial de uma única parcela, entrada + cartão, upload persistente de PDF e conciliação bancária **não** estão implementados nesta versão.

## Endpoints novos/atualizados

- `GET /api/parcelas` — lista parcelas
- `PATCH /api/parcelas/{id}` com `{"paid":true,"paid_at":"2026-11-12"}` — registra pagamento; `{"paid":false}` desfaz
- `POST /api/orcamentos`, `PATCH /api/orcamentos/{id}` e `PUT /api/estado` aceitam `item_name`, `cash_price`, `installment_total`, `payment_method`, `installments_count`, `first_due_date`, além dos campos existentes
- `GET /api/dashboard` apresenta `comprometido`, `pago`, `a_pagar`, `cotado`, `saldo` e demais métricas
- `/docs` apresenta os esquemas completos, apenas para uso controlado

## Segurança e Cloudflare (NÃO PULAR)

O túnel Cloudflare já encaminha `https://api.otavioaraujo.com.br` ao seu computador. **O retorno de `/health` sozinho não comprova que o Cloudflare Access está protegendo os demais endpoints.** Antes de cadastrar dados reais no servidor acessível pela internet:

1. Confirme que Cloudflare Zero Trust Access possui aplicação **Self-hosted** abrangendo `api.otavioaraujo.com.br/*`, com política **Allow → Emails** restrita a vocês dois.
2. Faça o teste em navegador anônimo **sem sessão Cloudflare** e verifique que acesso aos endpoints protegidos exige autenticação (e que outras contas são bloqueadas). Se a API estiver pública, **desative a rota temporariamente** até corrigir.
3. O frontend no GitHub Pages (`https://otavioaraujo.com.br`) e a API em subdomínio são origens diferentes. Em `.env`, ajuste `CORS_ORIGINS` para incluir também `https://otavioaraujo.com.br` (sem a parte `/nosso_ape_app/`) e reinicie a API.
4. O Cloudflare Access pode bloquear o preflight `OPTIONS`/redirecionar chamadas `fetch` em navegadores. **A integração de login remoto não está garantida por esta atualização**. Será preciso configurar e testar corretamente Access/cookies/CORS; não desabilite a proteção apenas para fazer o login funcionar.
5. Limite tentativas de login, mantenha credenciais secretas e implemente backups automáticos antes de produção. A API usa JWT e não deve ficar aberta publicamente sem essas camadas.

## Publicar frontend no GitHub Pages

Somente depois dos testes locais e da segurança remota confirmados:

```powershell
git status
git add api frontend scripts tests README.md
git diff --cached --name-only
git commit -m "Nosso Ape 3.0: propostas e parcelas"
git push
```

Se já possuir o workflow `.github/workflows/deploy-pages.yml`, ele publicará somente a pasta `frontend` conforme a configuração anterior. **Nunca execute `git add .` sem antes conferir arquivos sensíveis.**

## Testes desta entrega

Os testes automatizados rodam com SQLite isolado, não com seu PostgreSQL de produção, e cobrem: login, cotações, revisão, regra de aprovação única, parcelas mensais e baixa. O script de migração PostgreSQL precisa ser validado no seu Windows usando o backup e o banco reais. A interface foi validada sintaticamente, mas não houve teste de navegador end-to-end nesta entrega.
