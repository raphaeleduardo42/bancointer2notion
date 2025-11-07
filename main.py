import os
import datetime
import re

from authlib.integrations.requests_client import OAuth2Session
from dotenv import load_dotenv
from notion_client import Client
from notion_client.helpers import iterate_paginated_api, collect_paginated_api

from models import Transacao, ContainsRichText, Contains, NotionProperties

load_dotenv()

client_id = os.getenv("CLIENT_ID")
client_secret = os.getenv("CLIENT_SECRET")
token_endpoint = "https://cdpj.partners.bancointer.com.br/oauth/v2/token"
extrair_enriquecido_endpoint = "https://cdpj.partners.bancointer.com.br/banking/v2/extrato/completo"
scope = "extrato.read" # multiplos scopes devem ser separados por espaços simples

database_id = os.getenv("NOTION_DATABASE") # Série Histórica

cert_path = os.getenv("INTER_CERT_PATH")
key_path = os.getenv("INTER_KEY_PATH")

if not cert_path or not key_path:
    raise ValueError("Os caminhos para o certificado (INTER_CERT_PATH) e chave (INTER_KEY_PATH) não foram definidos no .env")

cert_files = (cert_path, key_path)

entity_map = {
    "OBRA": (os.getenv("CONTROLE_FINANCEIRO", ""), "Controle Financeiro", "Identificador"),
    "ELEVARE": (os.getenv("PAGAR_E_RECEBER", ""), "Pagar e Receber", "Identificador")
}

session = OAuth2Session(
    client_id=client_id,
    client_secret=client_secret,
    scope=scope
)

session.cert = cert_files

notion = Client(auth=os.getenv("NOTION_TOKEN"))

def extrato(
    data_inicio: datetime.date | None = None,
    data_fim: datetime.date | None = None,
) -> list[Transacao] | None:
    if data_fim is None:
        data_fim = datetime.date.today()
    if data_inicio is None:
        data_inicio = max(data_fim - datetime.timedelta(days=89), datetime.date(2025, 8, 1))

    params = {
        "dataInicio": data_inicio.strftime("%Y-%m-%d"),
        "dataFim": data_fim.strftime("%Y-%m-%d"),
        "pagina": 0
    }

    transacoes = []
    while True:
        response = session.get(extrair_enriquecido_endpoint, params=params)
        response.raise_for_status()

        data: dict = response.json()
        data_transacoes: list = data.get('transacoes') #type: ignore
        transacoes.extend(data_transacoes) 

        if data.get('ultimaPagina', True):
            break

        params['pagina'] += 1

    if transacoes:
        return [Transacao.model_validate(transacao) for transacao in transacoes]

    return

def transacoes_existentes(id_transacoes: dict[str, Transacao]) -> list[str]:
    id_filter = [
        ContainsRichText(
            property="idTransacao",
            rich_text=Contains(contains=_id)
        ).model_dump()
        for _id in id_transacoes.keys()
    ]

    _filter = {
        "and": [
            {"property": "Data", "date": {"on_or_after": "2025-08-01"}}
        ]
    }

    if len(id_filter) == 1:
        _filter['and'].append(id_filter[0])
    else:
        or_filter = {"or": id_filter}
        _filter['and'].append(or_filter)

    transacoes_existentes = []
    for transacao_existente in iterate_paginated_api(
        notion.databases.query ,database_id=database_id, filter=_filter
    ):
        existent_idTransacao = transacao_existente['properties']['idTransacao']['rich_text'][0]['plain_text']
        transacoes_existentes.append(existent_idTransacao)
    
    return transacoes_existentes

def buscar_ids_filtrados(database_id: str, numeros: list[int], unique_field: str, column: str) -> dict[str, tuple[str, str]]:
    """
    Retorna um dict {numero: page_id} para registros cujo unique_field está em numeros
    """
    # Monta filtros or
    or_filters = [
        {"property": unique_field, "number": {"equals": n}}
        for n in numeros
    ]

    # Coleta paginando
    all_pages = collect_paginated_api(notion.databases.query, database_id=database_id, filter={"or": or_filters})

    result = {}
    for page in all_pages:
        unique_id = page["properties"].get(unique_field, {}).get('unique_id', None)
        if unique_id:
            tx_id = "".join([unique_id.get('prefix', ""), str(unique_id.get('number', ""))])
            result[tx_id] = (column, page['id'])
    return result

def main(lancamentos_desde: datetime.date | None):
    print("🚀 Iniciando a sincronização de transações do Banco Inter para o Notion...")
    print(f"Buscando transações a partir de: {lancamentos_desde}")

    # Conecta no endpoint do Banco Inter conseguindo o Token
    print("🔑 Obtendo token de acesso do Banco Inter...")
    session.fetch_token(
        url=token_endpoint,
        grant_type='client_credentials',
    )
    print("✅ Token obtido com sucesso.")

    # Recupera os lançamentos no extrato até o valor definido. data mínima 2025-08-01
    print("📄 Buscando extrato no Banco Inter...")
    resposta_extrato = extrato(data_inicio = lancamentos_desde)
    if resposta_extrato == None:
        print("✅ Nenhuma transação encontrada no extrato para o período definido.")
        return
    
    print(f"📊 Encontradas {len(resposta_extrato)} transações no extrato.")
    id_transacoes = {transacao.idTransacao: transacao for transacao in resposta_extrato}

    # Remove os lançamentos já existentes no Notion com base no `idTransacao``
    print("🔍 Verificando transações já existentes no Notion...")
    ids_existentes = transacoes_existentes(id_transacoes)
    print(f"📖 Encontradas {len(ids_existentes)} transações já existentes no Notion.")
    for id in ids_existentes:
        id_transacoes.pop(id, None)

    if not id_transacoes:
        print("✅ Nenhuma transação nova para adicionar. Tudo em dia!")
        return
    
    print(f"✨ {len(id_transacoes)} novas transações para adicionar.")

    relations = {key: [] for key in entity_map}
    
    # Recupera informações sobre transações linkadas ao txId no extrato
    print("🔗 Verificando relações com outras bases de dados do Notion...")
    for id, transacao in id_transacoes.items():
        if transacao.detalhes and transacao.detalhes.txId:
            match = re.match(r"(OBRA|ELEVARE)(\d{3,4})", transacao.detalhes.txId)
            if match:
                type = match.group(1)
                number = match.group(2)
                relations[type].append(int(number))
                transacao.identificador = match.group(0)
    
    relations_notion: dict[str, tuple[str, str]] = {}
    for type, values in relations.items():
        if not values:
            continue
        db = entity_map[type][0]
        field = entity_map[type][2]
        column = entity_map[type][1]
        if db and field:
            print(f"   -> Buscando {len(values)} relações para '{type}' na base '{column}'...")
            results = buscar_ids_filtrados(db, values, field, column)
            relations_notion.update(results)
            print(f"   -> Encontradas {len(results)} páginas relacionadas.")

    # Monta a lista de páginas a ser enviadas para o Notion
    to_notion: list[NotionProperties] = []
    for transacao in id_transacoes.values():
        if transacao.identificador:
            transacao.relation = relations_notion.get(transacao.identificador, None)
        
        to_notion.append(
            NotionProperties.model_validate(transacao.model_dump())
        )

    print(f"➕ Adicionando {len(to_notion)} novas transações ao Notion...")
    for page in to_notion:
        notion.pages.create(parent={"database_id": database_id}, **page.model_dump())
    print(f"🎉 Sucesso! {len(to_notion)} transações foram adicionadas ao Notion.")

if __name__ == "__main__":
    #Define até quando deve buscar os lançamentos no banco, mas não antes de 2025-08-01 (critério pessoal)
    lancamentos_desde = max(
        datetime.date.fromisoformat("2025-08-01"),
        datetime.date.today() - datetime.timedelta(days=89)
    )

    main(lancamentos_desde)