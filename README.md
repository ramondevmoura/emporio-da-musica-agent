# Empório da Música — AI customer service agent

**Lia** is a text and voice assistant for a musical instrument store in Campo Grande/MS. She answers customers in Portuguese, looks up prices, stock, promotions and orders in real time, applies the store policies, and invites customers to visit the store.

**🔗 Live demo: https://emporio.mouraoncode.com**. No install or API key needed.

`Python` · `OpenAI Responses API (function calling)` · `Streamlit` · `SQLite` · 40 unit tests · 18 evals on the real model (96% pass)

---

## Run it

```bash
git clone https://github.com/ramondevmoura/emporio-da-musica-agent && cd emporio-da-musica-agent
python -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
cp .env.example .env                                   # add your OPENAI_API_KEY
streamlit run app.py                                   # http://localhost:8501
```

| | |
|---|---|
| `python -m emporio.cli --debug` | Terminal chat that shows the tool calls |
| `pytest` | Unit tests (no API key needed) |
| `python -m evals.run_evals` | Evals against the real model |
| `docker build -t emporio-agent . && docker run --env-file .env -p 8501:8501 emporio-agent` | Run with Docker |

---

## How it works

```
Customer (text or 🎤) → Streamlit → Agent loop ⇄ OpenAI (gpt-5.4-mini)
                                        ↓
              6 tools: search_products · get_product_details · quote_purchase
                       find_orders · get_store_status · escalate_to_human
                                        ↓
                       CSV data + pricing rules + opening hours (pure Python)
```

The **policies** go in the prompt. The **data** comes from the tools. **All the math happens in Python.**

---

## Key decisions

| Decision | Why |
|---|---|
| **Function calling for data, the full policy text in the prompt (no RAG)** | Data questions need exact filters ("até R$ 1000", "em estoque"), and embeddings get those wrong. The manual is only 8 pages (about 2.5k tokens), so retrieval would only add a way to fail. It also stays cached and cheap. |
| **No agent framework** | 6 tools and one agent fit in a 60-line loop that is easy to test and explain. LangGraph would come in if the flows grew. |
| **The LLM never does math** | PIX (which doesn't stack with promotions), installment minimums, shipping and the 7/30/90-day return windows are computed in Python. The policy says a wrong price can count as false advertising. |
| **`gpt-5.4-mini`, low reasoning effort** | Fast (4.6 s median per turn), cheap, and good at tool use and Portuguese. The model is configurable, and the evals compare models. |
| **UX for older customers** | Short messages, plain words, big fonts, shortcut buttons, voice input, and map/WhatsApp/phone links. History is kept in the link, so a customer can come back later. |
| **Sells, without pressure** | After answering, the agent invites the customer to come and try the instrument, using the real opening hours (holidays included). It doesn't invite people from other cities to visit, doesn't invent urgency, and doesn't sell during complaints. |
| **Privacy (LGPD)** | Orders are only shown when the phone or e-mail matches. An order number alone reveals nothing. |
| **Resilient** | If the API fails, a fallback built without the LLM still gives the store's contacts, the opening hours and "open/closed right now". A circuit breaker spares customers repeated timeouts. |

Full rationale: **[docs/DESIGN.md](docs/DESIGN.md)**.

---

## Results

- **Evals:** 18 scripted scenarios (catalog, promotions, returns, privacy, complaints, off-topic questions, prompt injection, an English-speaking customer). Over 3 full runs, **52 of 54 passed (96%)**, and both failures were false positives of my checks.
- **Evals as the main dev tool:** they caught real bugs that I then fixed. The agent answered "yes, you can return it" before checking the order, swapped the original and promotional prices, and mixed Portuguese into English replies.
- **[5 example conversations](conversations/)**, recorded from real runs with the tool calls shown. The non-trivial one is a [return request](conversations/03-return-request-policy.md): identity check, order lookup, return deadlines, warranty, and a ticket with a protocol number.

---

## Assumptions about the data

The data has a few inconsistencies. These are the main ones and how I handled them (full list in [DESIGN.md](docs/DESIGN.md#data-treatment-and-assumptions)):

- **Two phone numbers in the policy.** I treat `(67) 3341-4444` as the landline and `(67) 3321-4500` as the WhatsApp.
- **No actual delivery date in the data.** `estimated_delivery` is used as the delivery date when computing return windows.
- **Orders 3 and 20 have totals that don't match their items.** The agent shows the recorded total.
- **The policy says "300+ instruments", but there are 65, and no wind or orchestral instruments.** The agent says so; it doesn't invent products.
- **Language.** The agent uses pt-BR by default and switches to the customer's language.

---

## Limitations and next steps

- **WhatsApp Business API.** The customers live there. Same agent, new channel, plus spoken replies.
- **Real integrations.** A helpdesk instead of the local escalation log, the store's ERP instead of the CSV snapshot, and carrier APIs for shipping quotes.
- **Stronger identity check.** A one-time code sent to the customer's phone or e-mail.
- **More evals and observability.** Real anonymized conversations, an LLM judge for tone, and tracing (Langfuse or OpenTelemetry).
- **Municipal holidays and special hours.** Today only national holidays are covered.

---

## Use of AI coding assistants

I built this with **Claude Code** as a pair programmer. The first working version was scaffolded in a single session, and the later commits show the iteration that followed.

- **I set the direction:**
  - an older, less tech-savvy audience (hence the big fonts, shortcuts and voice input);
  - a sales goal (hence the invitations to visit);
  - the fallback when the API is down;
  - OpenAI as the provider;
  - deploying on my own homelab server;
  - keeping it simple, which meant no framework and no RAG.
- **The assistant** read the case and the data with me (that's how most of the data issues were found), wrote most of the code in small reviewed steps with tests, and ran the evals.
- **The evals caught the assistant's mistakes**, such as the swapped prices and the mixed languages. **My manual testing caught what the evals couldn't:** Streamlit was rendering "R$ … R$" as a LaTeX formula and hiding the prices.

The requirements, the trade-offs and the final review stayed with me.
