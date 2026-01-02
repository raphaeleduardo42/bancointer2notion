import os
import datetime
import re
import asyncio

from itertools import batched

from authlib.integrations.httpx_client import AsyncOAuth2Client
from dotenv import load_dotenv

import notion_client
from notion_client.helpers import async_iterate_paginated_api

from models import Transacao, ContainsRichText, Contains, NotionProperties

load_dotenv()

client_id = os.getenv("CLIENT_ID")
client_secret = os.getenv("CLIENT_SECRET")
token_endpoint = "https://cdpj.partners.bancointer.com.br/oauth/v2/token"
extrair_enriquecido_endpoint = "https://cdpj.partners.bancointer.com.br/banking/v2/extrato/completo"
scope = "extrato.read" # multiplos scopes devem ser separados por espaços simples

data_source_id = os.getenv("NOTION_DATA_SOURCE") # Série Histórica

cert_path = os.getenv("INTER_CERT_PATH")
key_path = os.getenv("INTER_KEY_PATH")

if not cert_path or not key_path:
    raise ValueError("Os caminhos para o certificado (INTER_CERT_PATH) e chave (INTER_KEY_PATH) não foram definidos no .env")

cert_files = (cert_path, key_path)

entity_map = {
    "OBRA": (os.getenv("CONTROLE_FINANCEIRO", ""), "Controle Financeiro", "Identificador"),
    "ELEVARE": (os.getenv("PAGAR_E_RECEBER", ""), "Pagar e Receber", "Identificador")
}

notion = notion_client.AsyncClient(auth=os.getenv("NOTION_TOKEN"))

async def extrato(
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

    
    async with AsyncOAuth2Client(
        client_id=client_id,
        client_secret=client_secret,
        scope=scope,
        cert=(cert_path, key_path)
    ) as client:
        
        # Conecta no endpoint do Banco Inter conseguindo o Token
        print("🔑 Obtendo token de acesso do Banco Inter...")
        await client.fetch_token(
            url=token_endpoint,
            grant_type='client_credentials',
        )
        print("✅ Token obtido com sucesso.")

        transacoes = []
        while True:
            response = await client.get(extrair_enriquecido_endpoint, params=params)
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

async def transacoes_existentes(id_transacoes: dict[str, Transacao]) -> set[str]:
    transacoes_existentes = set()

    for lote in batched(id_transacoes.keys(), 50):
        id_filter = [
            ContainsRichText(
                property="idTransacao",
                rich_text=Contains(contains=_id)
            ).model_dump()
            for _id in lote
        ]

        if len(id_filter) == 1:
            _filter = id_filter[0]
        else:
            _filter = {"or": id_filter}

        async for transacao_existente in async_iterate_paginated_api(
            notion.data_sources.query, data_source_id=data_source_id, filter=_filter
        ):
            existent_idTransacao = transacao_existente['properties']['idTransacao']['rich_text'][0]['plain_text']
            transacoes_existentes.add(existent_idTransacao)
        
    return transacoes_existentes

async def buscar_ids_filtrados(data_source_id: str, numeros: list[int], unique_field: str, column: str) -> dict[str, tuple[str, str]]:
    """
    Retorna um dict {numero: page_id} para registros cujo unique_field está em numeros
    """

    result: dict[str, tuple[str, str]] = {}

    for batch_numeros in batched(numeros, 50):
        # Monta filtros or
        or_filters = [
            {"property": unique_field, "number": {"equals": n}}
            for n in batch_numeros
        ]

        # Monta o dicionário ID -> UUID
        async for page in async_iterate_paginated_api(
            notion.data_sources.query,
            data_source_id=data_source_id,
            filter={"or": or_filters}
        ):
            unique_id = page["properties"].get(unique_field, {}).get('unique_id', None)
            if unique_id:
                tx_id = "".join([unique_id.get('prefix', ""), str(unique_id.get('number', ""))])
                result[tx_id] = (column, page['id'])

    return result

async def main(lancamentos_desde: datetime.date | None):
    print("🚀 Iniciando a sincronização de transações do Banco Inter para o Notion...")
    print(f"Buscando transações a partir de: {lancamentos_desde}")

    # Recupera os lançamentos no extrato até o valor definido. data mínima 2025-08-01
    print("📄 Buscando extrato no Banco Inter...")
    resposta_extrato = await extrato(data_inicio = lancamentos_desde)
    if resposta_extrato == None:
        print("✅ Nenhuma transação encontrada no extrato para o período definido.")
        return
    
    print(f"📊 Encontradas {len(resposta_extrato)} transações no extrato.")
    id_transacoes = {transacao.idTransacao: transacao for transacao in resposta_extrato}

    # Remove os lançamentos já existentes no Notion com base no `idTransacao``
    print("🔍 Verificando transações já existentes no Notion...")
    ids_existentes = await transacoes_existentes(id_transacoes)
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
            results = await buscar_ids_filtrados(db, values, field, column)
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
    tasks = [
        notion.pages.create(parent={"data_source_id": data_source_id}, **page.model_dump())
        for page in to_notion
    ]

    await asyncio.gather(*tasks)
        
    print(f"🎉 Sucesso! {len(to_notion)} transações foram adicionadas ao Notion.")

if __name__ == "__main__":
    #Define até quando deve buscar os lançamentos no banco, mas não antes de 2025-08-01 (critério pessoal)
    lancamentos_desde = max(
        datetime.date.fromisoformat("2025-08-01"),
        datetime.date.today() - datetime.timedelta(days=89)
    )

    # Executa o script de maneira assincrona
    asyncio.run(
        main(lancamentos_desde)
    )
    