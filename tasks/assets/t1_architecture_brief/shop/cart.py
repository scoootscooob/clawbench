class CartService:
    def line_total(self, price_cents: int, quantity: int) -> int:
        return price_cents * quantity

