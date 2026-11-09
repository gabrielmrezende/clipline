# Painel de revisão

Página local para revisar os cortes de um episódio no navegador: vídeo final,
informações, calendário e edição do `post.md`. O painel grava o
`post.md` de cada corte e, quando você troca a música, remonta o `corte.mp4`
(ver "Música"). Nada é publicado.

## Instalar o FastAPI e o uvicorn

Uma vez só, rode `.venv\Scripts\python.exe -m pip install fastapi uvicorn`
(o `pip install -e .` não funciona neste repositório). Sem eles, o comando
`painel` avisa e não abre.

## Gerar o build

Só na primeira vez, ou depois de mudar o código do painel:

```bash
cd painel-web
npm install
npm run build
```

O build vai para `esteira/painel/estatico/`. Sem ele, o comando avisa e não abre.

## Abrir no notebook

```bash
.venv\Scripts\python.exe -m esteira painel
```

Abra `http://127.0.0.1:8765`. Opções: `--porta N` e `--cortes <pasta>`.

## Abrir no celular (mesma Wi-Fi)

1. Uma vez só, crie o código de acesso. Ele aparece uma única vez, então anote:

   ```bash
   .venv\Scripts\python.exe -m esteira painel codigo
   ```

   É preciso rodar isso antes do primeiro `--rede`.

2. Abra o painel na rede:

   ```bash
   .venv\Scripts\python.exe -m esteira painel --rede
   ```

3. No celular, abra o endereço que o terminal mostra (por exemplo
   `http://192.168.0.10:8765`) e digite o código.

Abrir pelo nome do computador (por exemplo `http://meu-pc:8765`) é recusado com
erro 400. Use sempre o IP mostrado no terminal.

Com VPN ligada, o endereço mostrado pode ser o da VPN, e o celular não abre.
Desligue a VPN antes de rodar `painel --rede`.

## Música

Na tela do corte, o bloco **Música** mostra a música de agora e deixa trocar:

1. Escolha a faixa (primeiro as do episódio, depois a biblioteca por clima) e
   o volume (de -30 a -18 dB). O botão de ouvir toca a faixa sozinha; `Ouvir
   prévia (15 s)` mistura a faixa com a voz do corte a partir do ponto em que o
   player está.
2. Clique em `Montar com esta música`. O painel monta o `corte.mp4` de novo; o
   andamento aparece no bloco e o cartão do episódio mostra `montando…`.
3. Se o corte já tem vídeo final, o painel pede confirmação antes: o vídeo
   final **não muda** e você vai precisar refazer no CapCut. Enquanto isso, o
   corte fica com o selo `vídeo final desatualizado`.
4. O crédito da música no `post.md` é atualizado sozinho. Se não der, o painel
   avisa e o editor do post mostra o aviso de crédito.

Se a montagem falhar, o corte volta ao que era antes.

Não feche o painel enquanto aparece "Montando…". Se fechar, o painel desfaz a troca incompleta na próxima vez que abrir.

A variável de ambiente `ESTEIRA_PAINEL_MONTAGEM_FALSA=1` troca a montagem por
uma de mentira (não roda o ffmpeg). Existe só para os testes automáticos; não
use no dia a dia.

A variável `ESTEIRA_PAINEL_PASTA_MUSICAS` aponta o painel para outra pasta de
músicas (com `catalogo.json` e `uso.json`). Também existe só para os testes
automáticos, para não mexer no `uso.json` real; não use no dia a dia.

Com `--cortes` apontando para uma cópia de teste, use também
`ESTEIRA_PAINEL_PASTA_MUSICAS` com uma cópia da biblioteca, senão o
`uso.json` real é alterado.

## Imagens

Na tela do corte, o bloco **Imagens** lista os momentos em que aparece uma
imagem sobre o vídeo (foto, notícia ou imagem de IA).

1. **Revisar.** Para cada momento de foto, escolha até 3 candidatas do
   Wikimedia Commons ou refaça a busca. Para IA, ajuste o prompt e clique em
   aprovar. Prompt que cita pessoa real não pode ser aprovado. Momentos podem
   ser descartados ou trocar entre foto e IA (notícia não troca).
2. **Baixar as fotos.** O painel mostra quantas fotos e quantos MB serão
   baixados (origem: Wikimedia Commons) e só baixa depois do seu clique. Durante
   o download, as escolhas do corte ficam travadas.
3. **Gerar as imagens de IA.** O painel mostra o custo estimado (quantidade de
   imagens aprovadas sem versão x preço do provedor) antes de gerar. Cada
   momento guarda até 3 versões; `Gerar de novo` cria a próxima. Se faltar a
   chave, o pedido termina com o aviso do que fazer.
4. **Chave do provedor.** Rode uma vez, no terminal, `python -m esteira imagens
   conectar openai` (ou `google`). A chave fica no cofre do Windows e nunca
   aparece no painel.
5. **Configurações.** Em Configurações, escolha o provedor e ajuste o preço por
   imagem usado na estimativa. O painel só mostra se há chave conectada.

O aviso de IA continua entrando na publicação: o `post.md` sai sem ele, e o
aviso de imagens de IA é acrescentado ao post quando a publicação é feita.

A variável de ambiente `ESTEIRA_PAINEL_IMAGEM_FALSA=1` troca os provedores de
IA por um de mentira (devolve uma imagem cinza 1024x1536, sem rede e sem
chave) e faz o painel dizer que há chave conectada. Existe só para os testes
automáticos; não use no dia a dia.

## Cuidados

- Use `--rede` só na Wi-Fi de casa. Nunca em Wi-Fi pública.
- Na primeira vez, o firewall do Windows pergunta se o Python pode receber
  conexões. Permita só para rede privada.
- Feche o painel (Ctrl+C) quando terminar.

## Teste automático

```bash
cd painel-web
npm test        # testes de componentes
npm run e2e     # fumaça no navegador, com um episódio falso (precisa do build)
```

A primeira vez do `e2e` exige `npx playwright install chromium` (cerca de 150 MB).
