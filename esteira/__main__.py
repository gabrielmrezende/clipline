import sys

if sys.argv[1:2] in (["init"], ["iniciar"]):
    # Só a biblioteca padrão: roda logo depois do clone, antes do venv e das dependências.
    from esteira.canal import principal
else:
    from esteira.cli import principal

sys.exit(principal())
