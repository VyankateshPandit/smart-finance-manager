import os
import uuid
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

# Embedding configuration (Google gemini-embedding-001 configured for 768 dimensions)
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "gemini-embedding-001")
EMBEDDING_DIMENSION = 768

# Baseline financial knowledge documents for initial seeding
INITIAL_FINANCIAL_KNOWLEDGE = [
    {
        "id": "kb-50-30-20-rule",
        "title": "50/30/20 Budgeting Rule",
        "text": "The 50/30/20 rule divides your after-tax income into three categories: 50% for Needs (food, rent, utilities, basic travel), 30% for Wants (entertainment, dining out, shopping, hobbies), and 20% for Savings and debt repayment (emergency funds, SIPs, retirement)."
    },
    {
        "id": "kb-emergency-fund",
        "title": "Emergency Fund Guidelines",
        "text": "An emergency fund should cover 3 to 6 months of essential living expenses. Keep this fund in high-liquidity, low-risk instruments such as high-yield savings accounts or liquid mutual funds."
    },
    {
        "id": "kb-sip-investing",
        "title": "Systematic Investment Plans (SIP)",
        "text": "A Systematic Investment Plan (SIP) allows you to invest a fixed amount regularly into mutual funds. It benefits from rupee cost averaging and compounding over the long term, reducing market timing risk."
    },
    {
        "id": "kb-debt-reduction",
        "title": "Debt Reduction Strategies",
        "text": "To eliminate debt, consider either the Debt Avalanche method (paying off debts with the highest interest rates first to minimize interest cost) or the Debt Snowball method (paying smallest balances first for psychological momentum)."
    },
    {
        "id": "kb-expense-tracking",
        "title": "Smart Category Expense Tracking",
        "text": "Categorizing expenses into Food, Travel, Entertainment, Shopping, and Other allows you to spot discretionary overspending quickly. Review your category breakdown weekly to adjust habits before month-end."
    }
]

def get_embedding(text: str, task_type: str = "retrieval_document"):
    """
    Generates a 768-dimensional vector embedding for text using Google Gemini embeddings.
    
    :param text: Input string
    :param task_type: 'retrieval_document' or 'retrieval_query'
    :return: List of floats representing the embedding vector
    """
    if not text or not text.strip():
        raise ValueError("Text cannot be empty for embedding generation.")

    api_key = os.getenv("GEMINI_API") or os.getenv("GEMINI_API_KEY")
    last_err = None

    # 1. Primary: Use new google-genai SDK
    try:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=api_key) if api_key else genai.Client()
        if hasattr(client, "models") and hasattr(client.models, "embed_content"):
            config = types.EmbedContentConfig(output_dimensionality=EMBEDDING_DIMENSION)
            for m_name in [EMBEDDING_MODEL, "gemini-embedding-001", "models/gemini-embedding-001", "gemini-embedding-2"]:
                try:
                    result = client.models.embed_content(
                        model=m_name,
                        contents=text,
                        config=config
                    )
                    if hasattr(result, "embedding") and hasattr(result.embedding, "values"):
                        return result.embedding.values
                    if hasattr(result, "embeddings") and result.embeddings:
                        return result.embeddings[0].values
                except Exception as me:
                    last_err = me
                    continue
    except Exception as ge:
        last_err = ge

    # 2. Fallback: Legacy google.generativeai SDK
    try:
        import google.generativeai as legacy_genai
        if api_key:
            legacy_genai.configure(api_key=api_key)
        for m_name in [EMBEDDING_MODEL, "gemini-embedding-001", "models/gemini-embedding-001", "embedding-001"]:
            try:
                res = legacy_genai.embed_content(
                    model=m_name,
                    content=text,
                    task_type=task_type
                )
                if isinstance(res, dict) and "embedding" in res:
                    return res["embedding"]
                if hasattr(res, "embedding"):
                    return res.embedding
            except Exception as leg_ex:
                last_err = leg_ex
                continue
    except Exception as ex:
        last_err = ex

    raise Exception(f"Failed to generate embedding with Google AI: {last_err}")


def get_pinecone_index(index_name: str = None):
    """
    Initializes and returns the Pinecone index, creating it if it does not exist.
    """
    from pinecone import Pinecone, ServerlessSpec

    api_key = os.getenv("PINECONE_API_KEY")
    if not api_key or api_key == "your_pinecone_api_key_here":
        raise ValueError("PINECONE_API_KEY is not configured in .env.")

    target_index = index_name or os.getenv("PINECONE_INDEX_NAME", "finance-manager")
    pc = Pinecone(api_key=api_key)

    # Check existing indexes
    existing_indexes = [idx.name for idx in pc.list_indexes()]

    if target_index not in existing_indexes:
        print(f"Creating Pinecone index '{target_index}' (dimension={EMBEDDING_DIMENSION})...")
        pc.create_index(
            name=target_index,
            dimension=EMBEDDING_DIMENSION,
            metric="cosine",
            spec=ServerlessSpec(
                cloud="aws",
                region="us-east-1"
            )
        )
        print(f"Pinecone index '{target_index}' created successfully.")

    return pc.Index(target_index)


def sync_initial_knowledge_base():
    """
    Idempotent check: inspects Pinecone for which baseline knowledge IDs are already indexed,
    and only generates embeddings and upserts for items that are missing.
    """
    api_key = os.getenv("PINECONE_API_KEY")
    if not api_key or api_key == "your_pinecone_api_key_here":
        print("[Pinecone] PINECONE_API_KEY not configured. Skipping knowledge base sync.")
        return

    try:
        index = get_pinecone_index()
        all_ids = [item["id"] for item in INITIAL_FINANCIAL_KNOWLEDGE]

        # Fetch existing vector IDs from Pinecone knowledge_base namespace
        fetched = index.fetch(ids=all_ids, namespace="knowledge_base")
        existing_ids = set(fetched.get("vectors", {}).keys())

        missing_items = [item for item in INITIAL_FINANCIAL_KNOWLEDGE if item["id"] not in existing_ids]

        if not missing_items:
            print(f"[Pinecone] Baseline knowledge base is already fully indexed ({len(existing_ids)} items).")
            return

        print(f"[Pinecone] Indexing {len(missing_items)} missing items out of {len(all_ids)}...")
        vectors = []
        for item in missing_items:
            vector_values = get_embedding(item["text"], task_type="retrieval_document")
            vectors.append({
                "id": item["id"],
                "values": vector_values,
                "metadata": {
                    "title": item["title"],
                    "text": item["text"],
                    "type": "general_knowledge",
                    "created_at": datetime.utcnow().isoformat()
                }
            })

        index.upsert(vectors=vectors, namespace="knowledge_base")
        print(f"[Pinecone] Successfully indexed {len(vectors)} new items into namespace 'knowledge_base'.")
    except Exception as e:
        print(f"[Pinecone] Warning during knowledge base sync: {e}")


def load_initial_knowledge():
    """Seeds or syncs baseline financial knowledge into Pinecone."""
    sync_initial_knowledge_base()


def add_user_message_embedding(user_id: int, message: str, role: str = "user", extra_metadata: dict = None):
    """
    Embeds and stores a user message/interaction in Pinecone under the user's isolated namespace.
    
    :param user_id: User's database ID (namespace: 'user_{user_id}')
    :param message: Text content of the message
    :param role: 'user' or 'assistant'
    :param extra_metadata: Optional dictionary with extra context (e.g. spending breakdown)
    """
    if not message or not message.strip():
        return None

    index = get_pinecone_index()
    namespace = f"user_{user_id}"
    vector_id = f"msg_{int(datetime.utcnow().timestamp())}_{uuid.uuid4().hex[:6]}"

    vector_values = get_embedding(message, task_type="retrieval_document")

    metadata = {
        "text": message,
        "role": role,
        "user_id": int(user_id),
        "timestamp": datetime.utcnow().isoformat()
    }
    if extra_metadata and isinstance(extra_metadata, dict):
        for k, v in extra_metadata.items():
            if isinstance(v, (str, int, float, bool)):
                metadata[k] = v

    index.upsert(
        vectors=[{
            "id": vector_id,
            "values": vector_values,
            "metadata": metadata
        }],
        namespace=namespace
    )
    return vector_id


def query_relevant_context(user_id: int, query_text: str, top_k: int = 3) -> list:
    """
    Queries Pinecone for relevant context across the user's namespace and general knowledge base.
    
    :param user_id: User ID
    :param query_text: User question/prompt
    :param top_k: Number of relevant matches to retrieve
    :return: List of retrieved text chunks
    """
    index = get_pinecone_index()
    query_vector = get_embedding(query_text, task_type="retrieval_query")
    retrieved_texts = []

    # 1. Search user's historical context namespace
    try:
        user_res = index.query(
            namespace=f"user_{user_id}",
            vector=query_vector,
            top_k=top_k,
            include_metadata=True
        )
        for match in user_res.get("matches", []):
            if match.get("score", 0) > 0.65 and "metadata" in match and "text" in match["metadata"]:
                retrieved_texts.append(f"[User History]: {match['metadata']['text']}")
    except Exception as e:
        print(f"Notice: User namespace query error or empty: {e}")

    # 2. Search general financial knowledge base namespace
    try:
        kb_res = index.query(
            namespace="knowledge_base",
            vector=query_vector,
            top_k=top_k,
            include_metadata=True
        )
        for match in kb_res.get("matches", []):
            if match.get("score", 0) > 0.60 and "metadata" in match and "text" in match["metadata"]:
                retrieved_texts.append(f"[Financial Knowledge - {match['metadata'].get('title', 'Guide')}]: {match['metadata']['text']}")
    except Exception as e:
        print(f"Notice: Knowledge base query error: {e}")

    return retrieved_texts


if __name__ == "__main__":
    print("Running initial embedding loader...")
    try:
        load_initial_knowledge()
        print("Initial knowledge base loaded successfully!")
    except Exception as err:
        print(f"Error loading initial embeddings: {err}")
