from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError

from duckduckgo_search import DDGS

# DuckDuckGo has no official free API; this scrapes an endpoint that
# rate-limits aggressively. Worse than a simple failure: the library's
# own internal retry/executor logic can hang for 60+ seconds before
# finally raising, which is unacceptable inside a chat response. Hard
# cap enforced independently of whatever the library does internally.
_SEARCH_TIMEOUT_SECONDS = 8


def _search(query, max_results):
    with DDGS() as ddgs:
        results = ddgs.text(query, max_results=max_results)
        formatted_results = []
        for res in results:
            title = res.get("title", "No title")
            snippet = res.get("body", "No description available.")
            link = res.get("href", "#")
            formatted_results.append(f"{title} - {snippet} ({link})")
        return formatted_results


def perform_web_search(query, max_results=5):
    """
    Perform a web search using DuckDuckGo and return top results as
    formatted strings. Confidence-gated fallback for chat_page() — only
    called when the persistent clinical knowledge base has no relevant
    chunks for a question.

    Fails often (rate limiting) and, without this timeout, can hang for
    a long time before failing. Callers must treat any exception here —
    including the timeout — as a normal, expected outcome (fall through
    to plain chat), not something to surface as an error.
    """
    # Not using `with ThreadPoolExecutor(...)` deliberately: its __exit__
    # calls shutdown(wait=True), which would block until the underlying
    # thread actually finishes — exactly what this timeout exists to
    # avoid. shutdown(wait=False) lets a still-stuck DDG thread be
    # abandoned (it'll finish or die on its own; Python doesn't support
    # forcibly killing a thread) while this function returns promptly.
    executor = ThreadPoolExecutor(max_workers=1)
    future = executor.submit(_search, query, max_results)
    try:
        return future.result(timeout=_SEARCH_TIMEOUT_SECONDS)
    except FutureTimeoutError:
        raise TimeoutError(f"Web search exceeded {_SEARCH_TIMEOUT_SECONDS}s timeout")
    finally:
        executor.shutdown(wait=False)
