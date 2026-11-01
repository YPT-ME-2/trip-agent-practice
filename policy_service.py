import asyncio
from pathlib import Path

from langchain_community.vectorstores import FAISS
from langchain_ollama import OllamaEmbeddings

class PolicyService:
    def __init__(self):
        self.embedding=OllamaEmbeddings(
            model="qwen3-embedding:4b",
            base_url="http://127.0.0.1:11434",
            client_kwargs={"trust_env": False},
        )
        self.vector_store: FAISS | None = None

    async def load(self):
        path=Path(__file__).parent / "差旅政策.txt"
        text = path.read_text(encoding="utf-8-sig")

        # 演示文件按空行分段，每段是一条政策
        chunks=[
            paragraph.strip()
            for paragraph in text.split("\n\n")
            if paragraph.strip()
        ]

        self.vector_store=await FAISS.afrom_texts(
            chunks,
            self.embedding,
            metadatas=[{"source": path.name} for _ in chunks],
        )

    async def search(self,query:str) -> list[dict]:
        if self.vector_store is None:
            raise RuntimeError("请先加载差旅政策")

        documents=await self.vector_store.asimilarity_search(
            query,
            k=2,
        )      
        return [
        {
            "content": doc.page_content,
            "source": doc.metadata["source"],
        }
        for doc in documents
    ]

async def main():
    service=PolicyService()
    print("正在加载政策……")
    await service.load()

    results = await service.search("去杭州出差，住宿报销标准是多少？")

    for item in results:
        print("来源：", item["source"])
        print("条款：", item["content"])
        print()

if __name__=="__main__":
    asyncio.run(main())