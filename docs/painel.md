# Painel de revisão

Página local para revisar os cortes de um episódio no navegador: vídeo final,
informações, calendário e edição do `post.md`. O painel **só grava o
`post.md`** de cada corte. Nada mais é alterado, e nada é publicado.

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
