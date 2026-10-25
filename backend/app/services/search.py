from typing import Protocol

from app.schemas import CandidateCreate


class SearchService(Protocol):
    def search(self, query: str) -> list[CandidateCreate]: ...


class MockSearchProvider:
    """All identities and URLs are fictional, visibly labeled throughout the app."""

    def search(self, query):
        names = [
            "Deniz Aral",
            "Maya Selin",
            "Emre Soyer",
            "Lina Demir",
            "Arda Yalin",
            "Nora Eren",
            "Cem Aydin",
            "Elif Moran",
            "Ada Tan",
            "Ozan Kaya",
            "Mira Deren",
            "Ege Onal",
        ]
        return [
            CandidateCreate(
                full_name=name + " (Demo)",
                job_title=["Research scientist", "Professor", "Founder", "Engineer"][i % 4],
                organization=["Example University", "Example Vision Lab", "Example Studio"][i % 3],
                organization_type=["university", "company", "company"][i % 3],
                field="Artificial Intelligence" if i % 3 else "Design",
                location="Istanbul" if i % 4 else "Ankara",
                city="Istanbul" if i % 4 else "Ankara",
                country="Türkiye",
                headline="Fictional profile for product demonstrations",
                bio="Fictional researcher working on computer vision and machine learning. This is not a real person or a verified source.",
                expertise=["Computer Vision", "Machine Learning"]
                if i % 3
                else ["Design", "Research"],
                website=f"https://example.com/demo/people/{i}",
                source_url=f"https://example.com/demo/profiles/{i}",
                source_name="Fictional demonstration source",
                source_type="demo",
                sources=[
                    {
                        "url": f"https://example.org/demo/conference/{i}",
                        "name": "Fictional conference directory",
                        "source_type": "demo",
                    }
                ],
            )
            for i, name in enumerate(names)
        ]


def get_search_service():
    # MVP intentionally ships a demo provider; n8n supplies live search results.
    return MockSearchProvider()
