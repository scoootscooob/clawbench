from shop.cart import CartService
from shop.formatting import format_cents


def render_total(price_cents: int, quantity: int) -> str:
    total = CartService().line_total(price_cents, quantity)
    return format_cents(total)


if __name__ == "__main__":
    print(render_total(1299, 2))

