import traceback
import sys

def main():
    try:
        import main
        print("Import successful!")
        
        # Test semantic search
        from main import search_books, SearchRequest
        req = SearchRequest(query="test", limit=5)
        res = search_books(req)
        print("Semantic search: OK")
        
        # Test similar books
        from main import get_similar_books, SimilarRequest
        sim_req = SimilarRequest(book_title="Dracula", limit=5)
        res = get_similar_books(sim_req)
        print("Similar search: OK")
        
        # Test profile
        from main import get_book_profile
        res = get_book_profile("22")
        print("Profile: OK")
        
        with open("crash.txt", "w") as f:
            f.write("ALL OK")
    except Exception as e:
        with open("crash.txt", "w") as f:
            traceback.print_exc(file=f)

if __name__ == "__main__":
    main()
