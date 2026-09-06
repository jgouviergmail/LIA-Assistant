import asyncio, os
from langchain_openai import ChatOpenAI

KEY = os.environ.get("OPENAI_API_KEY", "")
if not KEY:
    print("PAS DE CLE — mesure impossible"); raise SystemExit(0)

async def try_call(label, **kw):
    llm = ChatOpenAI(model="gpt-5.6-luna", api_key=KEY, max_completion_tokens=16, **kw)
    try:
        r = await llm.ainvoke("Say OK")
        print(f"  {label:46} -> OK ({str(r.content)[:20]!r})")
    except Exception as exc:
        msg = str(exc)
        short = msg[:150].replace("\n", " ")
        print(f"  {label:46} -> ECHEC : {short}")

async def main():
    print("=== ce que gpt-5.6-luna accepte reellement ===")
    await try_call("rien (baseline)")
    await try_call("top_p=1.0 (la valeur que LIA envoie)", model_kwargs={"top_p": 1.0})
    await try_call("top_p=0.9", model_kwargs={"top_p": 0.9})
    await try_call("frequency_penalty=0.0", model_kwargs={"frequency_penalty": 0.0})
    await try_call("temperature=0.3", temperature=0.3)

asyncio.run(main())
