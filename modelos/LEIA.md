# Modelos de rosto

Os arquivos `.onnx` não vão para o git (ver `.gitignore`). Baixe e coloque nesta pasta,
só depois de confirmação do dono do canal.

| Arquivo | Para quê | Pasta no repositório de origem |
|---|---|---|
| `face_detection_yunet_2023mar.onnx` | detecta rostos (YuNet), cerca de 0,3 MB | `models/face_detection_yunet/` |
| `face_recognition_sface_2021dec.onnx` | reconhece a mesma pessoa (SFace), cerca de 37 MB | `models/face_recognition_sface/` |

Origem: https://github.com/opencv/opencv_zoo

Licença: Apache 2.0 (a do opencv_zoo). Confira o arquivo `LICENSE` de cada pasta
do modelo antes de redistribuir.
