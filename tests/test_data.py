from emporio.data import get_store_data, normalize_text


def test_loads_all_tables():
    data = get_store_data()
    assert len(data.products) == 65
    assert len(data.categories) == 9
    assert len(data.orders) == 20
    assert all(order.items for order in data.orders.values())


def test_availability_combines_status_and_stock():
    data = get_store_data()
    by_name = {p.name: p for p in data.products.values()}
    assert by_name["Giannini GF-3D Dreadnought Sunburst"].availability == "out_of_stock"
    assert by_name["Shelby SN-7C 7 Cordas Nylon Natural"].availability == "discontinued"
    assert by_name["Yamaha C40 Nylon Natural"].availability == "in_stock"


def test_only_active_promotions_are_returned():
    data = get_store_data()
    for promo in data.promotions:
        if not promo.is_active:
            active = data.active_promotion(promo.product_id)
            assert active is None or active.is_active


def test_normalize_text():
    assert normalize_text("Violão Elétrico!") == "violao eletrico"
