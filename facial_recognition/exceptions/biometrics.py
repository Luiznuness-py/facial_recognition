"""Exceção usada pelas operações biométricas."""


class BiometricError(Exception):
    """Representa uma falha biométrica com categoria para tratamento HTTP.

    Distingue captura ruim de reprovação de identidade/PAD e de indisponibilidade. A
    categoria orienta a resposta e define se a falha deve entrar no contador de reprovações.

    Attributes:
        kind: Categoria quality, rejected, busy ou unavailable.
    """

    def __init__(self, message: str, kind: str = 'quality'):
        """Inicializa a mensagem e a categoria da falha biométrica.

        Args:
            message: Mensagem permitida para orientar o usuário sem expor embeddings.
            kind: Categoria da falha; quality é o padrão.
        """
        super().__init__(message)
        self.kind = kind
