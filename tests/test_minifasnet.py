"""Verifica a integração antifraude sem depender da decisão de uma foto real."""
from types import SimpleNamespace
from unittest.mock import Mock

import numpy as np
import pytest
import torch

from facial_recognition.core.minifasnet import CropImage, MiniFASNet


@pytest.mark.parametrize('first,second,expected', [
    ([0.1, 0.8, 0.1], [0.1, 0.2, 0.7], True),
    ([0.8, 0.1, 0.1], [0.1, 0.6, 0.3], False),
])
def test_ensemble_preserves_preprocessing_and_combines_both_models(first, second, expected):
    """Confere a soma das duas redes e a preservação de BGR, escala e formato do tensor.

    Args:
        first: Probabilidades predefinidas da primeira rede simulada.
        second: Probabilidades predefinidas da segunda rede simulada.
        expected: Resultado ou coordenadas esperados para a entrada parametrizada.

    Returns:
        None: O caso termina quando todas as asserções são satisfeitas.

    Raises:
        AssertionError: Quando o comportamento observado difere do contrato descrito pelo
            caso.
    """
    patch = np.empty((80, 80, 3), dtype=np.uint8)
    patch[:] = [25, 127, 255]
    first_model = Mock(return_value=torch.tensor([first]).log())
    second_model = Mock(return_value=torch.tensor([second]).log())
    antifraud = MiniFASNet()
    antifraud.cropper = SimpleNamespace(crop=Mock(return_value=patch))
    antifraud.models = [(first_model, 80, 80, 2.7), (second_model, 80, 80, 4.0)]

    assert antifraud.is_live(patch, [10, 10, 60, 60]) is expected

    assert antifraud.cropper.crop.call_count == 2
    assert antifraud.cropper.crop.call_args_list[0].args[2:] == (2.7, 80, 80)
    assert antifraud.cropper.crop.call_args_list[1].args[2:] == (4.0, 80, 80)
    for model in [first_model, second_model]:
        model.assert_called_once()
        tensor = model.call_args.args[0]
        assert tensor.shape == (1, 3, 80, 80)
        assert tensor.dtype == torch.float32
        assert tensor[0, :, 0, 0].tolist() == [25, 127, 255]


@pytest.mark.parametrize('bbox,expected', [
    ([0, 0, 40, 40], (0, 0, 80, 80)),
    ([60, 60, 40, 40], (19, 19, 99, 99)),
])
def test_crop_keeps_the_face_inside_image_boundaries(bbox, expected):
    """Confere as coordenadas de recorte nas bordas e o tamanho entregue ao modelo.

    Args:
        bbox: Caixa facial próxima ao limite da imagem de teste.
        expected: Resultado ou coordenadas esperados para a entrada parametrizada.

    Returns:
        None: O caso termina quando todas as asserções são satisfeitas.

    Raises:
        AssertionError: Quando o comportamento observado difere do contrato descrito pelo
            caso.
    """
    assert CropImage._get_new_box(100, 100, bbox, 2) == expected
    image = np.zeros((100, 100, 3), dtype=np.uint8)
    assert CropImage().crop(image, bbox, 2, 80, 80).shape == (80, 80, 3)
