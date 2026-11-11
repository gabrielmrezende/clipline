# Contexto de exemplo

Modelos das regras editoriais que o Claude Code lê antes de sugerir qualquer coisa. Copie esta pasta para
`../Contexto/` (irmã de `Automacao/`) e reescreva com as regras do seu canal:

```powershell
Copy-Item -Recurse Contexto.exemplo ..\Contexto
```

O código só lê o `glossario.md`. O resto orienta o agente. Uma regra que vale para todos os episódios mora
aqui, não no prompt da sessão.
