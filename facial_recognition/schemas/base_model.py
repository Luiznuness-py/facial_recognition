from uuid import UUID
from datetime import datetime
from typing import Any, Generic, TypeVar, Annotated

from pydantic import (
    BaseModel, 
    ConfigDict, 
    Field, 
    StringConstraints,
    EmailStr, 
    BeforeValidator,
)

# O `T` é um espaço reservado para um tipo que você escolhe ao usar a classe
# um exemplo disso é ApiResponse[ListResponse[UserResponse]].
# Nesse caso, o campo `data` contém uma listagem cujos itens seguem UserResponse.
# Assim, reutilizamos ApiResponse em diferentes rotas, definindo em cada
# uma o tipo e a estrutura esperados para o retorno.
T = TypeVar("T")

Reason = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1500)]
NormalizedEmail = Annotated[
    EmailStr,
    BeforeValidator(lambda value: value.strip().lower() if isinstance(value, str) else value),
]

class BaseSchema(BaseModel):
    """Compartilha a configuração de validação dos schemas da aplicação.

    Rejeita campos não declarados ao criar ou validar um modelo, em vez de
    ignorá-los silenciosamente. Os schemas específicos devem declarar seus
    campos, tipos, limites e regras de obrigatoriedade.

    Não remove espaços das strings nem impõe limites globais aos números.
    Normalização de nomes e emails deve ser definida nos campos apropriados;
    senhas e outros valores sensíveis devem preservar o conteúdo recebido.

    Esta classe não executa SQL nem protege consultas por inspeção de texto.
    Os valores externos devem ser enviados ao banco como parâmetros separados
    do comando SQL. Registros asyncpg podem ser convertidos com dict(record)
    antes da validação, selecionando somente os campos previstos na resposta.
    """

    model_config = ConfigDict(extra="forbid")


class AuditSchema(BaseSchema):
    """Agrupa os campos comuns de auditoria para respostas da API.

    Deve ser herdada apenas por respostas de tabelas que possuem todos estes
    campos. Não deve servir de base para requisições de criação ou atualização:
    autoria, datas e exclusão lógica são preenchidas pelo backend. Tabelas com
    campos diferentes, como audit_events, precisam de respostas específicas.

    Attributes:
        created_at: Data e hora de criação do registro. Campo obrigatório,
            sem geração automática de uma data durante a montagem da resposta.
        created_by: UUID do usuário que criou o registro. Pode ser nulo quando
            não houver autoria cadastrada, como nos dados iniciais do sistema.
        updated_at: Data e hora da última alteração, ou None se não registrada.
        updated_by: UUID do autor da última alteração, ou None se não registrado.
        soft_delete: Indica exclusão lógica. O padrão é False; True representa
            um registro excluído sem remoção física dos dados.
    """

    created_at: datetime
    created_by: UUID | None = None
    updated_at: datetime | None = None
    updated_by: UUID | None = None
    soft_delete: bool = False


class PaginationParams(BaseSchema):
    """Valida os parâmetros de uma consulta paginada por número de página.

    Define apenas os limites recebidos pela API. A consulta ao banco deve
    aplicar os filtros e a autorização, calcular o deslocamento e limitar a
    quantidade de registros. Esta classe não executa consultas.

    Attributes:
        page: Página solicitada, iniciando em 1. O padrão é a primeira página.
        per_page: Quantidade máxima de itens por página, entre 1 e 100.
            O padrão é 20 itens.
    """

    page: int = Field(default=1, ge=1)
    per_page: int = Field(default=20, ge=1, le=100)


class ListResponse(BaseSchema, Generic[T]):
    """Representa uma lista de itens de um tipo definido pelo schema concreto.

    O parâmetro genérico T determina o tipo dos elementos de items. Por exemplo,
    ListResponse[UserResponse] valida cada item como uma resposta de usuário.
    A classe não busca dados nem calcula o total; ambos vêm da camada de consulta.

    Attributes:
        items: Itens retornados na página atual. Uma lista vazia representa uma
            consulta sem itens naquela página.
        total: Quantidade total de registros que atendem aos filtros e às
            permissões da consulta, antes da paginação. Deve ser zero ou maior.
    """

    items: list[T]
    total: int = Field(ge=0)


class ApiError(BaseSchema):
    """Descreve um erro que pode ser apresentado ao consumidor da API.

    Deve conter uma explicação compreensível e somente os detalhes necessários
    para orientar a correção ou recuperação. A camada que trata o erro deve
    selecionar essas informações, sem expor senhas, tokens, dados biométricos,
    comandos SQL ou detalhes internos de exceções.

    Attributes:
        message: Mensagem principal do erro, obrigatória como campo textual.
        details: Informações complementares permitidas, como os nomes de campos
            inválidos. É opcional e tem None como padrão.
    """

    message: str
    details: dict[str, Any] | None = None


class ApiResponse(BaseSchema, Generic[T]):
    """Define o envelope comum para respostas de sucesso ou erro da API.

    O parâmetro genérico T define o tipo de data. Em uma resposta de sucesso,
    o backend preenche data conforme a operação e deixa error como None. Em uma
    resposta de falha, informa success=False, preenche error e deixa data como
    None. Operações sem conteúdo podem manter data como None.

    Esta classe define o formato, mas não valida a coerência entre success,
    data e error. A camada HTTP deve montar a combinação correta e definir o
    código de resposta; alterar success não muda automaticamente o status HTTP.

    Attributes:
        success: Indica se a operação foi bem-sucedida. O padrão é True.
        data: Resultado da operação, validado pelo tipo T, ou None quando ausente.
        error: Erro apresentado ao consumidor, no formato ApiError, ou None.
    """

    success: bool = True
    data: T | None = None
    error: ApiError | None = None
