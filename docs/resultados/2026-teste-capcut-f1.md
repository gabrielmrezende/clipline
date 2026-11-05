# Teste do fluxo com CapCut: Entre Assuntos #03, Arthur Cerqueira

Data: 2026-11-05. Pasta: `2 - Cortes/Entre Assuntos 03 - Arthur Cerqueira (teste capcut)/`.
Os cortes atuais do episódio não foram tocados.

## Medido
- `vozes`: 127 s no episódio inteiro (45 min), 3 vozes, 492 trechos.
  V3 = Arthur (cerca de 30 min), V2 e V1 = apresentadores (9 e 4 min).
- `planos`: 106 s nos 10 cortes (rostos, ligação, enquadramento, folhas).
  Refeito com `--forcar` em 84 s.
- `preparar`: 1 s. `montar`: 360 s, 10 `corte.mp4`, todos ok.
- `imagens resumo`: 197 s; 39 fotos, 21,8 MB (Wikimedia Commons).
- `imagens sugerir`: 21 s; 39 fotos em 1080x1920 e `guia.md` em cada corte.
- Testes automáticos: 331 passando.

## O que aconteceu
- A ligação automática só ligou o convidado (V3 → P2): nos 10 cortes os
  apresentadores nunca aparecem sozinhos em close. Corrigido à mão em
  `pessoas.json` por eliminação (V1 fala nos planos com P1 e o Arthur;
  V2 nos planos com P1 e P3): V1 → P1 (camisa verde), V2 → P3 (camisa escura).
  Depois de `planos --forcar`, sobrou só 1 alerta (fala sobreposta no corte 02).
- O agrupamento de rostos separou o apresentador de camisa escura em duas
  pessoas (P3 de perfil, P5 de frente). P5 não apareceu em nenhuma cena dos
  cortes, então não afetou o enquadramento.
- Corte 01 (onde o zoom tinha errado): quadros aos 12 s e 34 s mostram o
  apresentador que fala; aos 60 s, o Arthur em close com zoom 1,0.
- Corte 02: "áudio perto de saturar: -0.1 dB".

## Ajustes durante o teste
- pyannote.audio 3.4 usa `use_auth_token`, que o huggingface_hub 1.x/2.x
  removeu. Fixado `huggingface_hub<1.0` (0.36.2) no extra `vozes`, junto
  com torch/torchaudio 2.5.1 (CUDA 12.4).
- OpenCV 5.0 não abre modelo em caminho com acento: os modelos de rosto são
  carregados por buffer.

## Pendente
- Ligação por eliminação nos planos com dois rostos (os apresentadores quase
  nunca têm close sozinhos). Hoje é feita à mão em `pessoas.json`.
- Nomes reais dos apresentadores em `pessoas.json` (hoje "camisa verde" e
  "camisa escura"); confirmar com o dono do canal.
- Só 1 opção de foto por momento neste teste (escolhas do teste anterior).
- O dono do canal comparar os zooms e testar um corte no CapCut.
