# Modelos de rosto

Os arquivos `.onnx` não vão para o git (ver `.gitignore`). Baixe e coloque nesta pasta,
só depois de confirmação do dono do canal.

| Arquivo | Para quê | Licença | Origem |
|---|---|---|---|
| `face_detection_yunet_2023mar.onnx` | detecta rostos (YuNet), cerca de 0,3 MB | MIT | https://github.com/opencv/opencv_zoo/tree/main/models/face_detection_yunet |
| `face_recognition_sface_2021dec.onnx` | reconhece a mesma pessoa (SFace), cerca de 37 MB | Apache 2.0 | https://github.com/opencv/opencv_zoo/tree/main/models/face_recognition_sface |

Os arquivos foram baixados de
`https://media.githubusercontent.com/media/opencv/opencv_zoo/main/models/<pasta>/<arquivo>`.

O código carrega os modelos por buffer, porque o OpenCV no Windows não abre caminho
com acento.
