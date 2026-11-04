"""Coordena captura, detecção e reconhecimento facial com verificação antifraude."""

import io
import threading
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, UnidentifiedImageError

from facial_recognition.core.minifasnet import MiniFASNet
from facial_recognition.exceptions.biometrics import BiometricError

ROOT = Path(__file__).resolve().parents[2]
MODEL_VERSION = 'sface-2021dec-yunet-2023mar-v1'
# shortcut: limiar do notebook; recalibrar com capturas reais e FAR/FRR antes de uso além da bancada.
SIMILARITY_THRESHOLD = 0.2332
CAPTURE_FRAMES = 5


def decode_frame(content: bytes) -> np.ndarray:
    """Valida o arquivo e decodifica uma imagem JPEG ou PNG em BGR.

    Confere formato e dimensões com Pillow antes da decodificação integral. Aceita ao menos
    80 pixels por eixo e no máximo 1920 por 1080; não persiste a imagem.

    Args:
        content: Bytes de uma imagem de até 1 MiB recebida pela rota.

    Returns:
        numpy.ndarray: Imagem BGR com três canais, pronta para o OpenCV.

    Raises:
        BiometricError: Categoria quality para arquivo inválido, dimensões não permitidas ou
            falha de decodificação.
    """
    if not content or len(content) > 1024 * 1024:
        raise BiometricError('Cada imagem deve ter até 1 MiB.')
    try:
        with Image.open(io.BytesIO(content)) as image:
            w, h = image.size
            if image.format not in {'JPEG', 'PNG'} or w > 1920 or h > 1080 or min(w, h) < 80:
                raise BiometricError('Use JPEG/PNG entre 80 pixels e 1920 × 1080.')
            image.verify()
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError):
        raise BiometricError('Imagem inválida ou corrompida.') from None
    frame = cv2.imdecode(np.frombuffer(content, np.uint8), cv2.IMREAD_COLOR)
    if frame is None:
        raise BiometricError('Não foi possível decodificar a imagem.')
    return frame


class FaceModels:
    """Coordena detecção, reconhecimento e antifraude da captura facial.

    Carrega os modelos no primeiro uso e mantém um bloqueio durante a captura
    para impedir acesso simultâneo às instâncias mutáveis. Delega a decisão
    antifraude a MiniFASNet e gera o template somente após aprovar os frames.

    Attributes:
        lock: Bloqueio que serializa a avaliação da captura.
        loaded: Indica que os modelos foram carregados com sucesso.
        anti_spoof: Integração MiniFASNet responsável pela antifraude.
        detector: Detector YuNet inicializado por load.
        recognizer: Reconhecedor SFace inicializado por load.
    """

    def __init__(self):
        """Prepara o bloqueio e o adaptador antifraude sem carregar os pesos.

        O lifespan chama load antes de liberar a API. Fora desse fluxo, evaluate carrega
        os pesos no primeiro uso. A instância pode ser compartilhada pela aplicação,
        com acesso serializado por evaluate.
        """
        self.lock = threading.Lock()
        self.loaded = False
        self.anti_spoof = MiniFASNet()

    def load(self):
        """Carrega YuNet, SFace e os dois modelos MiniFASNet de arquivos locais.

        Não baixa modelos pela rede. loaded só é marcado como True depois que todo o
        carregamento termina.

        Returns:
            None: Atualiza detector, recognizer, anti_spoof e loaded na instância.

        Raises:
            OSError: Quando um peso local não está disponível.
            RuntimeError: Quando os pesos PyTorch são incompatíveis com as redes.
            cv2.error: Quando o OpenCV não consegue carregar os arquivos ONNX.
        """
        model_dir = ROOT / 'models'
        self.detector = cv2.FaceDetectorYN.create(str(model_dir / 'face_detection_yunet_2023mar.onnx'), '', (320, 320), 0.9)
        self.recognizer = cv2.FaceRecognizerSF.create(str(model_dir / 'face_recognition_sface_2021dec.onnx'), '')
        self.anti_spoof.load()
        self.loaded = True

    def evaluate(self, contents: list[bytes], reference: np.ndarray | None = None) -> np.ndarray:
        """Avalia os cinco frames e produz um template facial normalizado.

        Exige exatamente um rosto inteiro em cada frame e aprova todos no MiniFASNet antes
        de gerar o template. Se houver referência, aplica o limiar cosseno configurado. O
        bloqueio é liberado mesmo quando ocorre erro.

        Args:
            contents: Lista com exatamente cinco imagens codificadas.
            reference: Template da conta esperada ou None durante o cadastro autorizado.

        Returns:
            numpy.ndarray: Vetor float32 obtido pela média normalizada dos embeddings SFace.

        Raises:
            BiometricError: quality para captura inadequada; rejected para PAD ou identidade
                reprovados; busy para concorrência; unavailable para falha de
                carregamento/processamento.
        """
        if len(contents) != CAPTURE_FRAMES:
            raise BiometricError(f'Capture exatamente {CAPTURE_FRAMES} imagens.')
        if not self.lock.acquire(blocking=False):
            raise BiometricError('Outra captura está em processamento. Tente novamente.', 'busy')
        try:
            if not self.loaded:
                try:
                    self.load()
                except (OSError, RuntimeError, cv2.error, ImportError):
                    raise BiometricError('Modelos indisponíveis. Execute a preparação descrita no README.', 'unavailable') from None
            embeddings = []
            for content in contents:
                frame = decode_frame(content)
                self.detector.setInputSize((frame.shape[1], frame.shape[0]))
                _, faces = self.detector.detect(frame)
                if faces is None or len(faces) != 1:
                    raise BiometricError('Mantenha somente um rosto visível, com boa iluminação.')
                face = faces[0]
                x, y, w, h = face[:4]
                if min(w, h) < 60 or x < 0 or y < 0 or x+w > frame.shape[1] or y+h > frame.shape[0]:
                    raise BiometricError('Centralize o rosto inteiro e aproxime-se da câmera.')
                if not self.anti_spoof.is_live(frame, [int(x), int(y), int(w), int(h)]):
                    raise BiometricError('A verificação de presença real foi reprovada. Use a câmera ao vivo.', 'rejected')
                aligned = self.recognizer.alignCrop(frame, face)
                embedding = self.recognizer.feature(aligned).flatten().astype(np.float32)
                embedding /= np.linalg.norm(embedding)
                embeddings.append(embedding)
            template = np.mean(embeddings, axis=0)
            template /= np.linalg.norm(template)
            if reference is not None and float(np.dot(template, reference)) < SIMILARITY_THRESHOLD:
                raise BiometricError('O rosto não corresponde à conta informada.', 'rejected')
            return template.astype(np.float32)
        except cv2.error:
            raise BiometricError('Falha ao processar a captura. Tente novamente.', 'unavailable') from None
        finally:
            self.lock.release()
