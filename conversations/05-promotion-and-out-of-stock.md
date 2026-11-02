# Promotions, expired campaigns and an out-of-stock item

> An active promotion shown with the original price and % off, an expired Black Friday promotion handled transparently, and an out-of-stock model replaced by available alternatives.

_Recorded with `gpt-5.4-mini` via `python -m evals.record_conversations`._

**Cliente:** Tem algum ukulele em promoção?

<sub>🔧 tools: `search_products({"query": "ukulele", "category": "Ukuleles", "max_price": null, "min_price": null, "only_available": true})`, `get_store_status({})`</sub>

**Lia:** Tem sim 😊  
  
O que está em promoção:  
Kalani KAL-700T Tenor Natural — de R$ 359,00 por R$ 323,10 (10% OFF)  
até 4x de R$ 80,78 sem juros  
  
Os outros ukuleles que consultei aqui estão com preço normal, mas o PIX já sai 5% mais barato.  
  
Se quiser, eu te separo 2 ou 3 opções melhores pra iniciante ou pra estudo. Quer vir experimentar amanhã a partir das 09:00?

---

**Cliente:** E o Black Friday, já começou? Tem desconto no Taylor 110e?

<sub>🔧 tools: `search_products({"query": "Taylor 110e", "category": "Violões", "max_price": null, "min_price": null, "only_available": true})`, `get_store_status({})`</sub>

**Lia:** Ainda não consigo confirmar a campanha de Black Friday inteira, mas consultei aqui e o Taylor 110e já está com desconto.  
  
Taylor 110e Dreadnought Natural    
de R$ 5.999,00 por R$ 5.519,08 (8% OFF)    
até 12x de R$ 459,92 sem juros  
  
Hoje a loja está fechada por feriado e volta amanhã às 09:00.    
Quer que eu te passe mais violões nessa faixa de preço?

---

**Cliente:** Vocês têm o violão Giannini GF-3D?

<sub>🔧 tools: `search_products({"query": "Giannini GF-3D", "category": "Violões", "max_price": null, "min_price": null, "only_available": true})`, `get_store_status({})`</sub>

**Lia:** O Giannini GF-3D está esgotado no momento.  
  
Os mais próximos que consultei aqui foram:  
Giannini GF-1R Aço Folk Sunburst — R$ 579,90    
Giannini GNF-3 CEQ Elétrico Nylon Natural — R$ 1.049,00    
Giannini GN-15 Nylon Cedr Natural — R$ 689,00  
  
Se quiser, eu te mostro uma opção parecida em aço ou em nylon.

---
