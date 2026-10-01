import os
import json
from schemas import FinancialAdviceResponse

def generate_financial_advice(prompt: str, expense_context: dict = None, user_id: int = None):
    """
    Generates structured financial advice using Groq AI (openai/gpt-oss-120b, streaming)
    and Pydantic schemas, enriched with Pinecone RAG vector retrieval.
    Embeddings are generated via Google Studio API (Gemini).

    :param prompt: User's question or input prompt
    :param expense_context: Optional dictionary containing user spending breakdown
    :param user_id: Optional user ID for Pinecone namespace isolation and context retrieval
    :return: dict with formatted 'response' text and 'structured' Pydantic dict
    """
    if not prompt or not prompt.strip():
        raise ValueError("Prompt cannot be empty.")

    # 1. Retrieve RAG context from Pinecone if configured
    retrieved_context = []
    if user_id:
        try:
            from loadembeddings import query_relevant_context
            retrieved_context = query_relevant_context(user_id=user_id, query_text=prompt, top_k=3)
        except Exception:
            pass

    # 2. Build enriched prompt
    context_str = ""
    if retrieved_context:
        context_str = "\n\nRelevant Context & Knowledge:\n" + "\n".join(f"- {c}" for c in retrieved_context)

    schema_instruction = (
        "Respond strictly with a JSON object matching this structure:\n"
        "{\n"
        '  "summary": "1-2 sentence executive takeaway",\n'
        '  "risk_level": "Low | Moderate | High",\n'
        '  "spending_assessment": "assessment of spending",\n'
        '  "actionable_tips": [\n'
        '    {"title": "Tip Title", "category": "Food/Travel/etc", "estimated_monthly_savings": "₹amount", "advice": "action steps"}\n'
        "  ],\n"
        '  "key_takeaways": ["point 1", "point 2"]\n'
        "}"
    )

    final_prompt = prompt.strip()
    if expense_context and isinstance(expense_context, dict):
        final_prompt = (
            f"You are a friendly and expert personal financial advisor for 'Smart Finance Manager'.\n"
            f"User's current spending breakdown:\n"
            f"- Food: ₹{expense_context.get('food', 0)}\n"
            f"- Travel: ₹{expense_context.get('travel', 0)}\n"
            f"- Entertainment: ₹{expense_context.get('entertainment', 0)}\n"
            f"- Shopping: ₹{expense_context.get('shopping', 0)}\n"
            f"- Other: ₹{expense_context.get('other', 0)}"
            f"{context_str}\n\n"
            f"User Question: {prompt}\n\n"
            f"{schema_instruction}"
        )
    else:
        final_prompt = f"{final_prompt}\n\n{schema_instruction}"

    # 3. Call Groq API with streaming (openai/gpt-oss-120b)
    groq_api_key = os.getenv("GROQ_API_KEY")
    if not groq_api_key:
        raise Exception("GROQ_API_KEY is not configured in .env.")

    raw_json_or_text = None

    try:
        from groq import Groq

        client = Groq(api_key=groq_api_key)

        print("[Groq] Sending request to openai/gpt-oss-120b (streaming)...")

        completion = client.chat.completions.create(
            model="openai/gpt-oss-120b",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a friendly and expert personal financial advisor for 'Smart Finance Manager'. "
                        "Always respond with valid JSON matching the schema provided by the user."
                    )
                },
                {
                    "role": "user",
                    "content": final_prompt
                }
            ],
            temperature=1,
            max_completion_tokens=2048,
            top_p=1,
            reasoning_effort="medium",
            stream=True,
            stop=None
        )

        # Collect streamed chunks
        collected_chunks = []
        for chunk in completion:
            delta_content = chunk.choices[0].delta.content or ""
            collected_chunks.append(delta_content)
            print(delta_content, end="", flush=True)

        print()  # newline after streaming completes
        raw_json_or_text = "".join(collected_chunks)
        print(f"[Groq] Streaming complete. Total chars received: {len(raw_json_or_text)}")

    except Exception as groq_err:
        raise Exception(f"Groq API call failed: {groq_err}")

    if not raw_json_or_text or not raw_json_or_text.strip():
        raise Exception("Groq returned an empty response. Please try again.")

    # 4. Parse and Validate into Pydantic model
    structured_data = None
    formatted_reply = None

    try:
        clean_text = raw_json_or_text.strip()
        if clean_text.startswith("```json"):
            clean_text = clean_text[7:]
        if clean_text.startswith("```"):
            clean_text = clean_text[3:]
        if clean_text.endswith("```"):
            clean_text = clean_text[:-3]
        clean_text = clean_text.strip()

        # Parse with Pydantic
        if hasattr(FinancialAdviceResponse, "model_validate_json"):
            structured_data = FinancialAdviceResponse.model_validate_json(clean_text)
        else:
            structured_data = FinancialAdviceResponse.parse_raw(clean_text)

        formatted_reply = structured_data.to_formatted_markdown()
    except Exception:
        # Fallback if text format wasn't strict JSON
        formatted_reply = raw_json_or_text
        structured_data = FinancialAdviceResponse(
            summary="Financial analysis generated based on your inputs.",
            risk_level="Moderate",
            spending_assessment="Custom spending breakdown assessment.",
            actionable_tips=[],
            key_takeaways=[raw_json_or_text[:140]]
        )

    # 5. Persist user turn to Pinecone namespace in background thread
    #    (Embeddings use Google Studio API / Gemini via loadembeddings.py)
    if user_id:
        def _persist_memory():
            try:
                from loadembeddings import add_user_message_embedding
                add_user_message_embedding(user_id=user_id, message=prompt, role="user")
                add_user_message_embedding(user_id=user_id, message=formatted_reply, role="assistant")
            except Exception as e:
                print(f"[Pinecone] Background memory save notice: {e}")

        import threading
        threading.Thread(target=_persist_memory, daemon=True).start()

    return {
        "response": formatted_reply,
        "structured": structured_data.model_dump() if hasattr(structured_data, "model_dump") else structured_data.dict()
    }
