"""Execução biométrica em thread com vaga única e timeout de resposta."""
import asyncio


from facial_recognition.core.biometrics import BiometricError

class Inference:
    """Executa a avaliação biométrica em uma única tarefa de trabalho por vez.

    Retira o processamento pesado do loop assíncrono. Um timeout de resposta não interrompe
    a thread e não libera a vaga enquanto a inferência continua executando.

    Attributes:
        models: Instância com o método evaluate que processa a captura.
        task: Tarefa atual ou None antes da primeira avaliação.
    """

    def __init__(self, models):
        """Associa os modelos à instância responsável pela execução assíncrona.

        Args:
            models: Objeto com evaluate(contents, reference), chamado em uma thread.
        """
        self.models = models
        self.task = None

    async def __call__(self, contents, reference):
        """Processa uma captura fora do loop assíncrono, com prazo de resposta.

        Usa shield para preservar a tarefa quando a espera expira ou a requisição é
        cancelada. A próxima chamada só começa quando o trabalho anterior termina.

        Args:
            contents: Imagens codificadas que serão repassadas aos modelos.
            reference: Template esperado ou None para cadastro.

        Returns:
            numpy.ndarray: Template devolvido por models.evaluate.

        Raises:
            BiometricError: busy se uma tarefa ainda executa ou unavailable se o prazo de 30
                segundos é excedido; falhas biométricas dos modelos também são propagadas.
        """
        if self.task is not None and not self.task.done():
            raise BiometricError('Outra captura está em processamento. Aguarde.', 'busy')
        self.task = asyncio.create_task(asyncio.to_thread(self.models.evaluate, contents, reference))
        self.task.add_done_callback(lambda task: task.exception() if not task.cancelled() else None)
        try:
            return await asyncio.wait_for(asyncio.shield(self.task), timeout=30)
        except TimeoutError:
            raise BiometricError('O processamento excedeu 30 segundos. Aguarde antes de repetir.', 'unavailable') from None
