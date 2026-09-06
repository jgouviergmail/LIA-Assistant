import asyncio, os
from langchain_openai import ChatOpenAI
KEY = os.environ["OPENAI_API_KEY"]

async def t(model, label, **kw):
    llm = ChatOpenAI(model=model, api_key=KEY, max_completion_tokens=16, **kw)
    try:
        await llm.ainvoke("Say OK")
        print(f"  {model:22} {label:22} -> OK")
    except Exception as e:
        print(f"  {model:22} {label:22} -> 400 : {str(e)[:70]}")

async def main():
    print("=== top_p NON NEUTRE, modele par modele ===")
    for m in ("gpt-5.2-chat-latest", "gpt-5.6-luna", "gpt-4.1-mini"):
        await t(m, "top_p=0.9", model_kwargs={"top_p": 0.9})
    print()
    print("=== penalite NON NEUTRE ===")
    for m in ("gpt-5.2-chat-latest", "gpt-5.6-luna"):
        await t(m, "frequency_penalty=0.5", model_kwargs={"frequency_penalty": 0.5})

asyncio.run(main())
