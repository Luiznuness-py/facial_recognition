"""Limites ASGI de corpo e frequência antes da interpretação das entradas."""
import time
from collections import OrderedDict

from facial_recognition.utils.utils import failure

class RequestLimits:
    """Controla o volume de requisições e o tamanho do corpo recebido pela API.

    Atua antes do parser multipart em /api/v1. Os contadores usam janelas fixas de um minuto
    e existem apenas neste processo; não são um limite compartilhado entre vários
    servidores.

    Attributes:
        app: Aplicação ASGI seguinte na cadeia de middlewares.
        windows: Mapa ordenado de IP/rota ou IP/método para janela e contagem; guarda até
            10.000 entradas.
    """

    def __init__(self, app):
        """Prepara a aplicação seguinte e o armazenamento dos limites locais.

        Args:
            app: Aplicação ASGI que receberá as requisições permitidas.
        """
        self.app = app
        self.windows = OrderedDict()

    async def __call__(self, scope, receive, send):
        """Filtra a requisição ASGI antes de entregá-la ao FastAPI.

        Aplica limites por IP e tipo de rota. Acumula até 256 KiB em alterações comuns ou 16
        MiB nas biométricas e reapresenta o corpo uma vez ao parser. Caminhos fora de
        /api/v1 e conexões não HTTP seguem sem esse filtro.

        Args:
            scope: Metadados ASGI com tipo, caminho, método e endereço do cliente.
            receive: Canal assíncrono usado para ler os eventos e os bytes recebidos.
            send: Canal assíncrono usado para enviar a resposta HTTP.

        Returns:
            None: Envia 429/413, encerra ao desconectar ou repassa a requisição.
        """
        if scope['type'] != 'http' or not scope['path'].startswith('/api/v1'):
            return await self.app(scope,receive,send)
        method,path = scope['method'],scope['path']
        client = scope.get('client') or ('unknown',0)
        limit = 10 if path.endswith('/login') else 30 if path.endswith('/refresh') else 6 if '/biometric' in path else 120 if method=='GET' else 60
        key = (client[0],path if '/auth/' in path else method)
        current = int(time.monotonic()//60)
        window,count = self.windows.pop(key,(current,0))
        count = count+1 if window==current else 1
        self.windows[key]=(current,count)
        if len(self.windows)>10000:
            self.windows.popitem(last=False)
        if count>limit:
            return await failure(429,'Muitas requisições. Aguarde um minuto.',{'Retry-After':'60'}, request_id=scope['state']['request_id'])(scope,receive,send)
        if method in {'POST','PATCH','DELETE'}:
            maximum = 16*1024*1024 if '/biometric' in path else 256*1024
            content = bytearray()
            while True:
                message = await receive()
                if message['type']=='http.disconnect':
                    return
                content.extend(message.get('body',b''))
                if len(content)>maximum:
                    return await failure(413,'Requisição maior que o limite permitido.', request_id=scope['state']['request_id'])(scope,receive,send)
                if not message.get('more_body',False):break
            delivered = False
            original_receive = receive
            async def bounded_receive():
                """Entrega o corpo já limitado ao próximo componente ASGI.

                Captura delivered, content e original_receive do middleware. Não lê
                novamente o corpo que já foi consumido para aplicar o limite.

                Returns:
                    dict: Primeiro evento http.request com os bytes acumulados; nas chamadas
                        seguintes, evento vindo do canal original.
                """
                nonlocal delivered
                if delivered:return await original_receive()
                delivered=True
                return {'type':'http.request','body':bytes(content),'more_body':False}
            receive = bounded_receive
        await self.app(scope,receive,send)
