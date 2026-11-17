"""Formatadores compartilhados para valores apresentados ao usuário."""


def formatar_brl(valor: float) -> str:
    texto = f"{valor:,.2f}"
    return "R$ " + texto.replace(",", "X").replace(".", ",").replace("X", ".")
