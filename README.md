# Sincronizador de Extrato Banco Inter para Notion

Este script automatiza a importação de transações da conta PJ do Banco Inter para uma base de dados no Notion. Ele busca novas transações, evita duplicatas e cria relações com outras bases de dados (como controle de obras ou contas a pagar/receber) com base em um identificador no `txId` do PIX.

## Funcionalidades

- Autenticação segura na API do Banco Inter usando OAuth2.
- Busca de transações do extrato em um período de datas configurável.
- Verificação de transações já existentes no Notion para evitar duplicidade.
- Criação de novas páginas no Notion para cada nova transação.
- Mapeamento e criação de relações com outras bases de dados do Notion através de um identificador (ex: `OBRA0001`).
- Logs detalhados no terminal para acompanhar o processo de sincronização.

## Pré-requisitos

- Python 3.9+
- Uma conta PJ no Banco Inter com acesso à API.
- Um espaço de trabalho no Notion com as bases de dados configuradas.
- Certificado e chave da API do Inter (arquivos `.crt` e `.key`).

## Configuração

1. **Clone o repositório:**

    ```bash
    git clone <url-do-seu-repositorio>
    cd <nome-do-repositorio>
    ```

2. **Crie um ambiente virtual e instale as dependências:**

    ```bash
    python -m venv .venv
    source .venv/bin/activate  # No Windows: .venv\Scripts\activate
    pip install -r requirements.txt
    ```

3. **Configure as variáveis de ambiente:**
    - Renomeie o arquivo `.env.example` para `.env`.
    - Preencha as variáveis no arquivo `.env` com suas credenciais, IDs do Notion e os caminhos para os arquivos de certificado e chave.

        ```ini
        # .env
        CLIENT_ID="seu-client-id-do-inter"
        CLIENT_SECRET="seu-client-secret-do-inter"

        NOTION_TOKEN="seu-token-de-integracao-do-notion"

        NOTION_DATABASE="id-da-sua-base-principal"
        CONTROLE_FINANCEIRO="id-da-base-de-obras"
        PAGAR_E_RECEBER="id-da-base-de-contas-a-pagar"

        INTER_CERT_PATH="C:\caminho\completo\para\seu\certificado.crt"
        INTER_KEY_PATH="C:\caminho\completo\para\sua\chave.key"
        ```

## Como Usar

Para executar o script, basta rodar o arquivo `main.py`.

```bash
python main.py
```

Por padrão, o script buscará as transações a partir da data definida na variável `lancamentos_desde` no final do arquivo `main.py`. Você pode alterar essa data conforme necessário.

## Como Funciona

1. **Autenticação:** O script obtém um token de acesso da API do Inter.
2. **Busca no Extrato:** Consulta o endpoint de extrato do Inter para obter as transações a partir da data especificada.
3. **Verificação de Duplicatas:** Faz uma consulta na base de dados do Notion para encontrar quais transações (pelo `idTransacao`) já foram importadas.
4. **Análise de Relações:** Para as novas transações, o script verifica o campo `txId` do PIX em busca de padrões como `OBRAXXXX` ou `ELEVAREXXXX` para identificar a qual item de outra base de dados a transação deve ser relacionada.
5. **Criação de Páginas:** Por fim, o script cria uma nova página no Notion para cada transação nova, preenchendo as propriedades (Descrição, Data, Valor, etc.) e adicionando a relação, se encontrada.
