"""Smoke real: pesos enviados + imagens locais, sem substituir os modelos."""
from pathlib import Path
import cv2
import numpy as np
import pytest
from facial_recognition.core.biometrics import FaceModels,ROOT,BiometricError,decode_frame

# O fixture HTTP substitui load durante o lifespan; este smoke precisa dos pesos reais.
REAL_MODEL_LOAD = FaceModels.load


def test_real_models_and_notebook_embedding():
    """Executa YuNet, SFace e MiniFASNet com os pesos reais e uma imagem local.

    Pode ser skipped se os arquivos locais necessários estiverem ausentes. Uma foto pode ser
    reprovada por PAD; este smoke valida execução e formatos, não mede eficácia ou FAR/FRR.

    Returns:
        None: O caso termina quando todas as asserções são satisfeitas.

    Raises:
        AssertionError: Quando o comportamento observado difere do contrato descrito pelo
            caso.
    """
    required=[ROOT/'models/face_detection_yunet_2023mar.onnx',ROOT/'models/face_recognition_sface_2021dec.onnx']
    if not all(p.exists() for p in required):pytest.fail('Restaure os quatro pesos versionados em models/ para testar inferência real.')
    images=list((ROOT/'dataset').glob('*/*/*.jpg'))
    if not images:pytest.skip('Sem imagens locais para smoke real; não baixa rostos de terceiros.')
    models=FaceModels();models.load()
    found=None
    for image in images[:30]:
        frame=cv2.imread(str(image))
        if frame is None:continue
        models.detector.setInputSize((frame.shape[1],frame.shape[0]))
        _,faces=models.detector.detect(frame)
        if faces is not None and len(faces)==1:
            aligned=models.recognizer.alignCrop(frame,faces[0])
            embedding=models.recognizer.feature(aligned).flatten()
            assert embedding.shape==(128,) and np.isfinite(embedding).all()
            normalized=embedding/np.linalg.norm(embedding)
            assert float(np.dot(normalized,normalized))>0.99
            found=image
            break
    assert found is not None,'Nenhum rosto detectado nas amostras locais.'
    try:
        template=models.evaluate([found.read_bytes()]*5)
        assert template.shape==(128,) and np.isclose(np.linalg.norm(template),1)
    except BiometricError as error:
        assert error.kind=='rejected',str(error)
    # PAD pode reprovar a foto; isso é resultado do modelo, não uma falha de integração.


def test_real_models_through_biometric_endpoint(client):
    """Exercita a rota biométrica com inferência real sem liberar sessão antes da senha.

    Pode ser skipped se os arquivos locais necessários estiverem ausentes. Uma foto pode ser
    reprovada por PAD; este smoke valida execução e formatos, não mede eficácia ou FAR/FRR.
    Aceita decisão ou erro de qualidade (200/401/422), mas recusa erro interno e emissão de
    access nesta etapa.

    Args:
        client: Cliente HTTP com dados isolados pela transação do fixture.

    Returns:
        None: O caso termina quando todas as asserções são satisfeitas.

    Raises:
        AssertionError: Quando o comportamento observado difere do contrato descrito pelo
            caso.
    """
    from conftest import activate_admin,mutate
    from facial_recognition.app import Inference
    paths=list((ROOT/'dataset').glob('*/*/*.jpg'))
    if not paths or not (ROOT/'models/face_recognition_sface_2021dec.onnx').exists():
        pytest.skip('Pesos ou dataset local ausentes.')
    activate_admin(client)
    team=client.get('/api/v1/teams').json()['data']['items'][0]['id']
    body=dict(name='Smoke real',email='smoke@example.com',role_code='N1',team_id=team,temporary_password='Smoke!Temporary2026')
    assert mutate(client,'/access-requests',body).status_code==201
    mutate(client,'/auth/logout')
    assert mutate(client,'/auth/login',{'email':body['email'],'password':body['temporary_password']}).status_code==200
    models = FaceModels()
    REAL_MODEL_LOAD(models)
    client.app.state.inference=Inference(models)
    response=mutate(client,'/auth/biometric/enroll',files=[('frames',('capture.jpg',paths[0].read_bytes(),'image/jpeg')) for _ in range(5)])
    assert response.status_code in {200,401,422},response.text
    assert 'lab_access' not in client.cookies
    if response.status_code==200:assert response.json()['data']['next_step']=='CHANGE_PASSWORD'
    # Uma entrada real deve produzir decisão ou qualidade, nunca erro 500 ou bypass.
