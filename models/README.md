# Modelos biométricos: origem, integridade e uso

Estes quatro arquivos são versionados diretamente no Git e acompanham o clone do
projeto, sem Git LFS ou script de download. Com BIOMETRICS_MODE=real, o FastAPI carrega os pesos locais no
lifespan antes de liberar a API; no modo simulated, não carrega os pesos. Não modifique os pesos para ajustes de configuração.

| Arquivo | Finalidade | Licença |
|---|---|---|
| `face_detection_yunet_2023mar.onnx` | Detecção do rosto | [MIT](../licenses/YuNet-LICENSE) |
| `face_recognition_sface_2021dec.onnx` | Vetor de reconhecimento facial | [Apache 2.0](../licenses/SFace-LICENSE) |
| `2.7_80x80_MiniFASNetV2.pth` | Primeiro classificador antifraude | [Apache 2.0](../licenses/MiniFASNet-LICENSE) |
| `4_0_0_80x80_MiniFASNetV1SE.pth` | Segundo classificador antifraude | [Apache 2.0](../licenses/MiniFASNet-LICENSE) |

## Origem

- YuNet: [OpenCV Zoo — detecção](https://github.com/opencv/opencv_zoo/tree/48b10fa505aeb51fbd127fc60a5c660040e823b7/models/face_detection_yunet).
- SFace: [OpenCV Zoo — reconhecimento](https://github.com/opencv/opencv_zoo/tree/48b10fa505aeb51fbd127fc60a5c660040e823b7/models/face_recognition_sface).
- MiniFASNet: [MiniVision — Silent-Face-Anti-Spoofing](https://github.com/minivision-ai/Silent-Face-Anti-Spoofing/tree/b6d5f04ad78778917853b25c778acef6d5626d15/resources/anti_spoof_models).

Os pesos foram preservados sem alterações. As licenças dos fornecedores estão em
`licenses/`; elas se aplicam aos respectivos arquivos, independentemente da licença
do restante do projeto.

## Integridade

Na raiz do projeto, `sha256sum models/*.onnx models/*.pth` deve retornar:

```text
8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4  models/face_detection_yunet_2023mar.onnx
0ba9fbfa01b5270c96627c4ef784da859931e02f04419c829e83484087c34e79  models/face_recognition_sface_2021dec.onnx
a5eb02e1843f19b5386b953cc4c9f011c3f985d0ee2bb9819eea9a142099bec0  models/2.7_80x80_MiniFASNetV2.pth
84ee1d37d96894d5e82de5a57df044ef80a58be2b218b5ed7cdfd875ec2f5990  models/4_0_0_80x80_MiniFASNetV1SE.pth
```

Se algum arquivo estiver ausente ou corrompido, restaure a cópia correspondente do
repositório. Não é necessário baixar os pesos de serviços externos para executar a API.

## Conferência no Windows

No PowerShell, a partir da raiz do repositório, use `Get-FileHash models/*.onnx, models/*.pth -Algorithm SHA256` e compare os valores com a tabela textual acima. O hash identifica o arquivo esperado; não mede precisão, robustez antifraude ou licença de uso do sistema inteiro.

## Integração e limites

`FaceModels.load` carrega os pesos uma vez no lifespan do modo `real`; `Inference` executa as capturas fora do loop HTTP. O modo `simulated` não carrega os pesos nem gera embeddings. Os testes com arquivos locais verificam carregamento, formatos e execução; calibração, acurácia e resistência a ataques dependem de avaliação própria. Consulte [AUTH_LAB.md](../docs/AUTH_LAB.md) para pipeline, parâmetros e evidências.
