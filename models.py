## models.py
from pydantic import BaseModel, model_validator
from decimal import Decimal
from datetime import datetime, date
from typing import Optional

class PixDetalhes(BaseModel):
    txId: Optional[str] = None
    nomePagador: Optional[str] = None
    descricaoPix: Optional[str] = None
    cpfCnpjPagador: Optional[str] = None
    endToEndId: Optional[str] = None
    chavePixRecebedor: Optional[str] = None
    nomeRecebedor: Optional[str] = None
    cpfCnpjRecebedor: Optional[str] = None


class Transacao(BaseModel):
    idTransacao: str
    dataInclusao: datetime
    dataTransacao: date
    tipoTransacao: str
    tipoOperacao: str
    valor: Decimal
    titulo: str
    descricao: str
    numeroDocumento: Optional[str] = None
    detalhes: Optional[PixDetalhes] = None
    identificador: Optional[str] = None
    relation: Optional[tuple[str, str]] = None


class Contains(BaseModel):
    contains: str


class ContainsRichText(BaseModel):
    property: str
    rich_text: Contains


class NotionProperties(BaseModel):
    properties: dict

    @model_validator(mode="before")
    @classmethod
    def inter2notion(cls, raw: dict) -> dict:
        tipo = "Saída" if raw['tipoOperacao'] == "D" else "Entrada"
        valor = float(raw["valor"]) * (-1 if raw["tipoOperacao"] == "D" else 1)
        data = raw['dataTransacao'].isoformat()
        id_transacao = raw['idTransacao']

        titulo = [raw['titulo']]
        titulo.append(raw['descricao'])
        titulo.append(f"- {raw['numeroDocumento']}")

        detalhes = raw['detalhes']
        if detalhes and detalhes.get('descricaoPix'):
            titulo.insert(0, f"{detalhes['descricaoPix']} -")

        transacao = {
            "properties": {
                "Descrição": {
                    "title": [
                        {
                            "text": {
                                "content": ' '.join(str(item.strip()) for item in titulo if item is not None and item != '')
                            }
                        }
                    ]
                },
                "Data": {
                    "date": {
                        "start": data,
                        "end": None
                    }
                },
                "Banco": {
                    "select": {
                        "name": "Banco Intermedium S/A"
                    }
                },
                "Tipo": {
                    "select": {
                        "name": tipo
                    }
                },
                "Valor Extrato": {
                    "number": valor
                },
                "idTransacao": {
                    "rich_text": [
                        {
                            "text": {
                                "content": id_transacao
                            }
                        }
                    ]
                }
            }
        }

        relation = raw.get('relation')
        if relation:
            column, page_id = relation
            transacao["properties"][column] = {
                "relation": [{"id": page_id}]
            }

        return transacao