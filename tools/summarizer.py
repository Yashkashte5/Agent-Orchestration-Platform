from llm.groq_client import generate


async def summarize_text(text: str) -> dict:
    prompt = f"Summarize this concisely:\n\n{text}"
    summary = await generate(prompt)
    return {"summary": summary.strip()}